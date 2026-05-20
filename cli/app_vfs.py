"""App-level shell over the Stash virtual filesystem."""

from __future__ import annotations

import fnmatch
import posixpath
import re
import shlex
from dataclasses import dataclass

from .mount import StashMountError, StashVfsModel


@dataclass
class VfsCommandResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    cwd: str = "/"


class StashAppVfsShell:
    def __init__(self, model: StashVfsModel, cwd: str = "/"):
        self.model = model
        self.cwd = self._resolve_path(cwd)
        self._require_dir(self.cwd)

    def run(self, script: str) -> VfsCommandResult:
        stdout = ""
        for command in _split_unquoted(script, "&&"):
            for part in _split_unquoted(command, ";"):
                part = part.strip()
                if not part:
                    continue
                result = self._run_pipeline(part)
                if result.exit_code != 0:
                    result.cwd = self.cwd
                    return result
                stdout = result.stdout
        return VfsCommandResult(stdout=stdout, cwd=self.cwd)

    def _run_pipeline(self, script: str) -> VfsCommandResult:
        stdin = ""
        stages = _split_unquoted(script, "|")
        for index, stage in enumerate(stages):
            result = self._run_stage(stage.strip(), stdin if index else None)
            if result.exit_code != 0:
                return result
            stdin = result.stdout
        return VfsCommandResult(stdout=stdin, cwd=self.cwd)

    def _run_stage(self, stage: str, stdin: str | None) -> VfsCommandResult:
        name = "shell"
        try:
            command, redirect = _split_redirect(stage)
            args = shlex.split(command)
            if not args:
                return VfsCommandResult(cwd=self.cwd)

            name = args[0]
            output = self._dispatch(name, args[1:], stdin)
            if redirect is not None:
                path, append = redirect
                self._write_output(path, output, append)
                output = ""
            return VfsCommandResult(stdout=output, cwd=self.cwd)
        except VfsShellError as e:
            return VfsCommandResult(stderr=f"{name}: {e}\n", exit_code=e.exit_code, cwd=self.cwd)
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError, PermissionError) as e:
            message = e.args[0] if e.args else str(e)
            return VfsCommandResult(stderr=f"{name}: {message}\n", exit_code=1, cwd=self.cwd)
        except (StashMountError, ValueError) as e:
            return VfsCommandResult(stderr=f"{name}: {e}\n", exit_code=2, cwd=self.cwd)

    def _dispatch(self, name: str, args: list[str], stdin: str | None) -> str:
        if name == "pwd":
            return f"{self.cwd}\n"
        if name == "cd":
            return self._cd(args)
        if name == "ls":
            return self._ls(args)
        if name == "cat":
            return self._cat(args)
        if name == "find":
            return self._find(args)
        if name == "tree":
            return self._tree(args)
        if name in ("grep", "rg"):
            return self._grep(name, args, stdin)
        if name == "sed":
            return self._sed(args, stdin)
        if name == "head":
            return self._head_or_tail(args, stdin, from_tail=False)
        if name == "tail":
            return self._head_or_tail(args, stdin, from_tail=True)
        if name == "wc":
            return self._wc(args, stdin)
        if name == "echo":
            return self._echo(args)
        if name == "printf":
            return self._printf(args)
        if name == "tee":
            return self._tee(args, stdin)
        if name == "stat":
            return self._stat(args)
        if name == "help":
            return _help_text()
        raise VfsShellError(f"unsupported command: {name}")

    def _cd(self, args: list[str]) -> str:
        if len(args) > 1:
            raise VfsShellError("too many arguments")
        path = self._resolve_path(args[0] if args else "/")
        self._require_dir(path)
        self.cwd = path
        return ""

    def _ls(self, args: list[str]) -> str:
        long = False
        paths: list[str] = []
        for arg in args:
            if arg.startswith("-"):
                if "l" in arg:
                    long = True
                continue
            paths.append(arg)
        if not paths:
            paths = ["."]

        blocks = []
        for raw_path in paths:
            path = self._resolve_path(raw_path)
            node = self.model._get_node(path)
            if node.is_file:
                blocks.append(self._format_ls_entry(path, long))
                continue
            names = self.model.list_dir(path)
            lines = [self._format_ls_entry(posixpath.join(path, name), long) for name in names]
            blocks.append("\n".join(lines))
        return "\n".join(block for block in blocks if block) + ("\n" if blocks else "")

    def _format_ls_entry(self, path: str, long: bool) -> str:
        if not long:
            return posixpath.basename(path) or "/"
        attrs = self.model.getattr(path)
        mode = "d" if self.model._get_node(path).is_dir else "-"
        size = int(attrs.get("st_size", 0))
        return f"{mode} {size:>8} {posixpath.basename(path) or '/'}"

    def _cat(self, args: list[str]) -> str:
        if not args:
            raise VfsShellError("missing file")
        return "".join(self._read_text(self._resolve_path(path)) for path in args)

    def _find(self, args: list[str]) -> str:
        path = "."
        maxdepth: int | None = None
        name_pattern = ""
        ignore_name_case = False
        type_filter = ""
        index = 0
        if args and not args[0].startswith("-"):
            path = args[0]
            index = 1
        while index < len(args):
            option = args[index]
            if option == "-maxdepth":
                if index + 1 >= len(args):
                    raise VfsShellError("-maxdepth requires a value", exit_code=2)
                index += 1
                try:
                    maxdepth = int(args[index])
                except ValueError as e:
                    raise VfsShellError("-maxdepth value must be an integer", exit_code=2) from e
            elif option == "-type":
                if index + 1 >= len(args):
                    raise VfsShellError("-type requires a value", exit_code=2)
                index += 1
                type_filter = args[index]
                if type_filter not in ("f", "d"):
                    raise VfsShellError("-type supports only f or d", exit_code=2)
            elif option in ("-name", "-iname"):
                if index + 1 >= len(args):
                    raise VfsShellError(f"{option} requires a value", exit_code=2)
                index += 1
                name_pattern = args[index]
                ignore_name_case = option == "-iname"
            else:
                raise VfsShellError(f"unsupported find option: {option}")
            index += 1

        root = self._resolve_path(path)
        rows = []
        for node_path in self._walk(root):
            depth = 0 if node_path == root else len(posixpath.relpath(node_path, root).split("/"))
            if maxdepth is not None and depth > maxdepth:
                continue
            node = self.model._get_node(node_path)
            if type_filter == "f" and not node.is_file:
                continue
            if type_filter == "d" and not node.is_dir:
                continue
            if name_pattern and not _name_matches(node_path, name_pattern, ignore_name_case):
                continue
            rows.append(node_path)
        return "\n".join(rows) + ("\n" if rows else "")

    def _tree(self, args: list[str]) -> str:
        max_depth: int | None = None
        path = "."
        index = 0
        while index < len(args):
            arg = args[index]
            if arg == "-L":
                if index + 1 >= len(args):
                    raise VfsShellError("-L requires a value", exit_code=2)
                index += 1
                try:
                    max_depth = int(args[index])
                except ValueError as e:
                    raise VfsShellError("-L value must be an integer", exit_code=2) from e
            elif arg.startswith("-"):
                if arg != "-a":
                    raise VfsShellError(f"unsupported tree option: {arg}", exit_code=2)
            else:
                path = arg
            index += 1

        root = self._resolve_path(path)
        self.model._get_node(root)
        lines = [root]
        lines.extend(self._tree_lines(root, prefix="", depth=1, max_depth=max_depth))
        return "\n".join(lines) + "\n"

    def _tree_lines(
        self,
        path: str,
        *,
        prefix: str,
        depth: int,
        max_depth: int | None,
    ) -> list[str]:
        if max_depth is not None and depth > max_depth:
            return []
        node = self.model._get_node(path)
        if node.is_file:
            return []

        names = self.model.list_dir(path)
        rows = []
        for index, name in enumerate(names):
            child_path = posixpath.join(path, name)
            is_last = index == len(names) - 1
            connector = "`-- " if is_last else "|-- "
            rows.append(f"{prefix}{connector}{name}")
            child_prefix = f"{prefix}{'    ' if is_last else '|   '}"
            rows.extend(
                self._tree_lines(
                    child_path,
                    prefix=child_prefix,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
            )
        return rows

    def _grep(self, name: str, args: list[str], stdin: str | None) -> str:
        ignore_case = False
        recursive = name == "rg"
        show_line_numbers = name == "rg"
        options_done = False
        values: list[str] = []
        for arg in args:
            if not options_done and arg == "--":
                options_done = True
                continue
            if not options_done and arg.startswith("-"):
                if arg.startswith("--"):
                    if arg in ("--ignore-case", "--smart-case"):
                        ignore_case = True
                    elif arg == "--line-number":
                        show_line_numbers = True
                    elif arg == "--recursive":
                        recursive = True
                    else:
                        raise VfsShellError(f"unsupported {name} option: {arg}", exit_code=2)
                    continue
                flags = arg[1:]
                unsupported = sorted(set(flags) - set("inrR"))
                if unsupported:
                    raise VfsShellError(
                        f"unsupported {name} option: -{unsupported[0]}",
                        exit_code=2,
                    )
                ignore_case = ignore_case or "i" in flags
                recursive = recursive or "r" in flags or "R" in flags
                show_line_numbers = show_line_numbers or "n" in flags
                continue
            values.append(arg)
        if not values:
            raise VfsShellError("missing pattern")

        pattern = values[0]
        paths = values[1:]
        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            raise VfsShellError(str(e)) from e

        if stdin is not None and not paths:
            return _grep_text(regex, stdin, "", show_line_numbers=False, prefix_path=False)

        if not paths:
            paths = ["."]
        matches = []
        for raw_path in paths:
            path = self._resolve_path(raw_path)
            node = self.model._get_node(path)
            file_paths = [path] if node.is_file else self._file_paths(path) if recursive else []
            if node.is_dir and not recursive:
                raise VfsShellError(f"{raw_path}: is a directory")
            for file_path in file_paths:
                text = self._read_text(file_path)
                matches.append(
                    _grep_text(
                        regex,
                        text,
                        file_path,
                        show_line_numbers=show_line_numbers,
                        prefix_path=len(file_paths) > 1 or recursive,
                    )
                )
        return "".join(matches)

    def _sed(self, args: list[str], stdin: str | None) -> str:
        if not args:
            raise VfsShellError("missing script")
        args = [arg for arg in args if arg != "-n"]
        script = args[0]
        text = stdin if len(args) == 1 and stdin is not None else self._cat(args[1:])
        match = re.fullmatch(r"(\d+),(\d+)p", script)
        if not match:
            match = re.fullmatch(r"(\d+)p", script)
            if not match:
                raise VfsShellError("only sed -n 'N,Mp' is supported")
            start = end = int(match.group(1))
        else:
            start = int(match.group(1))
            end = int(match.group(2))
        lines = text.splitlines(keepends=True)
        return "".join(lines[start - 1 : end])

    def _head_or_tail(self, args: list[str], stdin: str | None, *, from_tail: bool) -> str:
        count = 10
        paths: list[str] = []
        index = 0
        while index < len(args):
            arg = args[index]
            if arg == "-n":
                if index + 1 >= len(args):
                    raise VfsShellError("-n requires a value", exit_code=2)
                index += 1
                try:
                    count = int(args[index])
                except ValueError as e:
                    raise VfsShellError("-n value must be an integer", exit_code=2) from e
            elif arg.startswith("-") and arg[1:].isdigit():
                count = int(arg[1:])
            else:
                paths.append(arg)
            index += 1
        text = stdin if not paths and stdin is not None else self._cat(paths)
        lines = text.splitlines(keepends=True)
        selected = lines[-count:] if from_tail else lines[:count]
        return "".join(selected)

    def _wc(self, args: list[str], stdin: str | None) -> str:
        line_only = not args or args == ["-l"]
        paths = [arg for arg in args if not arg.startswith("-")]
        text = stdin if not paths and stdin is not None else self._cat(paths)
        lines = text.count("\n")
        if line_only:
            return f"{lines}\n"
        words = len(text.split())
        return f"{lines} {words} {len(text.encode('utf-8'))}\n"

    def _echo(self, args: list[str]) -> str:
        newline = True
        if args and args[0] == "-n":
            newline = False
            args = args[1:]
        return " ".join(args) + ("\n" if newline else "")

    def _printf(self, args: list[str]) -> str:
        if not args:
            return ""
        text = args[0].encode("utf-8").decode("unicode_escape")
        if len(args) > 1:
            text += " ".join(args[1:])
        return text

    def _tee(self, args: list[str], stdin: str | None) -> str:
        append = False
        paths = []
        for arg in args:
            if arg == "-a":
                append = True
            else:
                paths.append(arg)
        if not paths:
            raise VfsShellError("missing file")
        text = stdin or ""
        for path in paths:
            self._write_output(path, text, append)
        return text

    def _stat(self, args: list[str]) -> str:
        if len(args) != 1:
            raise VfsShellError("expected one path")
        path = self._resolve_path(args[0])
        attrs = self.model.getattr(path)
        node = self.model._get_node(path)
        kind = "directory" if node.is_dir else "file"
        return f"{path}\n  type: {kind}\n  size: {attrs.get('st_size', 0)}\n"

    def _write_output(self, raw_path: str, output: str, append: bool) -> None:
        path = self._resolve_path(raw_path)
        data = output.encode("utf-8")
        if append:
            data = self.model.read_file(path) + data
        self.model.write_file(path, data)

    def _read_text(self, path: str) -> str:
        return self.model.read_file(path).decode("utf-8", errors="replace")

    def _walk(self, root: str) -> list[str]:
        self.model._get_node(root)
        paths = [root]
        node = self.model._get_node(root)
        if node.is_file:
            return paths
        for name in self.model.list_dir(root):
            child = posixpath.join(root, name)
            paths.extend(self._walk(child))
        return paths

    def _file_paths(self, root: str) -> list[str]:
        return [path for path in self._walk(root) if self.model._get_node(path).is_file]

    def _resolve_path(self, path: str) -> str:
        if path in ("", "."):
            path = self.cwd
        elif path == "~":
            path = "/"
        elif not path.startswith("/"):
            path = posixpath.join(self.cwd, path)
        clean = posixpath.normpath(path)
        return "/" if clean == "." else clean

    def _require_dir(self, path: str) -> None:
        try:
            node = self.model._get_node(path)
        except FileNotFoundError as e:
            raise StashMountError(f"directory not found: {path}") from e
        if not node.is_dir:
            raise StashMountError(f"not a directory: {path}")


class VfsShellError(Exception):
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


def _grep_text(
    regex: re.Pattern[str],
    text: str,
    path: str,
    *,
    show_line_numbers: bool,
    prefix_path: bool,
) -> str:
    rows = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not regex.search(line):
            continue
        prefix = ""
        if prefix_path:
            prefix += f"{path}:"
        if show_line_numbers:
            prefix += f"{line_number}:"
        rows.append(f"{prefix}{line}")
    return "\n".join(rows) + ("\n" if rows else "")


def _split_redirect(stage: str) -> tuple[str, tuple[str, bool] | None]:
    for token in (">>", ">"):
        parts = _split_unquoted(stage, token)
        if len(parts) == 1:
            continue
        if len(parts) != 2:
            raise VfsShellError("only one redirect is supported", exit_code=2)
        target = parts[1].strip()
        if not target:
            raise VfsShellError("missing redirect target", exit_code=2)
        target_args = shlex.split(target)
        if not target_args:
            raise VfsShellError("missing redirect target", exit_code=2)
        return parts[0].strip(), (target_args[0], token == ">>")
    return stage, None


def _split_unquoted(text: str, separator: str) -> list[str]:
    parts = []
    current = []
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            current.append(char)
            index += 1
            if index < len(text):
                current.append(text[index])
        elif quote:
            current.append(char)
            if char == quote:
                quote = ""
        elif char in ("'", '"'):
            quote = char
            current.append(char)
        elif text.startswith(separator, index):
            parts.append("".join(current))
            current = []
            index += len(separator) - 1
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def _help_text() -> str:
    return "\n".join(
        [
            "Supported commands:",
            "  pwd, cd, ls, cat, find, tree, rg, grep, sed -n, head, tail, wc, echo, printf, tee, stat",
            "  pipes with |, command chaining with && or ;, and > / >> writes to existing writable files",
            "",
        ]
    )


def _name_matches(path: str, pattern: str, ignore_case: bool) -> bool:
    name = posixpath.basename(path)
    if ignore_case:
        return fnmatch.fnmatchcase(name.lower(), pattern.lower())
    return fnmatch.fnmatchcase(name, pattern)
