"""App-level shell over the Stash virtual filesystem."""

from __future__ import annotations

import fnmatch
import posixpath
import re
import shlex
import time
from dataclasses import dataclass
from datetime import datetime

from .client import VfsClientError
from .model import MountError, StashVfsModel


@dataclass
class VfsCommandResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    cwd: str = "/"


class SkillAppVfsShell:
    def __init__(self, model: StashVfsModel, cwd: str = "/"):
        self.model = model
        self.cwd = self._resolve_path(cwd)
        self._warnings: list[str] = []
        self._require_dir(self.cwd)

    def run(self, script: str) -> VfsCommandResult:
        stdout_parts = []
        stderr_parts = []
        for command in _split_unquoted(script, "&&"):
            for part in _split_unquoted(command, ";"):
                part = part.strip()
                if not part:
                    continue
                result = self._run_pipeline(part)
                if result.stdout:
                    stdout_parts.append(result.stdout)
                if result.stderr:
                    stderr_parts.append(result.stderr)
                if result.exit_code != 0:
                    result.stdout = "".join(stdout_parts)
                    result.stderr = "".join(stderr_parts)
                    result.cwd = self.cwd
                    return result
        return VfsCommandResult(
            stdout="".join(stdout_parts), stderr="".join(stderr_parts), cwd=self.cwd
        )

    def _run_pipeline(self, script: str) -> VfsCommandResult:
        stdin = ""
        stderr_parts = []
        stages = _split_unquoted(script, "|")
        for index, stage in enumerate(stages):
            result = self._run_stage(stage.strip(), stdin if index else None)
            if result.stderr:
                stderr_parts.append(result.stderr)
            if result.exit_code != 0:
                result.stderr = "".join(stderr_parts)
                return result
            stdin = result.stdout
        return VfsCommandResult(stdout=stdin, stderr="".join(stderr_parts), cwd=self.cwd)

    def _run_stage(self, stage: str, stdin: str | None) -> VfsCommandResult:
        name = "shell"
        self._warnings = []
        try:
            _reject_redirect(stage)
            args = shlex.split(stage)
            if not args:
                return self._stage_result()

            name = args[0]
            output = self._dispatch(name, args[1:], stdin)
            return self._stage_result(stdout=output)
        except VfsShellExit as e:
            return self._stage_result(exit_code=e.exit_code)
        except VfsShellError as e:
            return self._stage_result(stderr=f"{name}: {e}\n", exit_code=e.exit_code)
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError, PermissionError) as e:
            message = e.args[0] if e.args else str(e)
            return self._stage_result(stderr=f"{name}: {message}\n", exit_code=1)
        except (MountError, ValueError) as e:
            return self._stage_result(stderr=f"{name}: {e}\n", exit_code=2)
        except VfsClientError as e:
            return self._stage_result(stderr=f"{name}: {e}\n", exit_code=2)

    def _stage_result(
        self, *, stdout: str = "", stderr: str = "", exit_code: int = 0
    ) -> VfsCommandResult:
        return VfsCommandResult(
            stdout=stdout,
            stderr="".join(self._warnings) + stderr,
            exit_code=exit_code,
            cwd=self.cwd,
        )

    def _warn(self, message: str) -> None:
        self._warnings.append(f"{message}\n")

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
        if name == "sort":
            return self._sort(args, stdin)
        if name == "uniq":
            return self._uniq(args, stdin)
        if name == "cut":
            return self._cut(args, stdin)
        if name == "xargs":
            return self._xargs(args, stdin)
        if name == "echo":
            return self._echo(args)
        if name == "printf":
            return self._printf(args)
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
        by_time = False
        paths: list[str] = []
        for arg in args:
            if arg.startswith("-"):
                if "l" in arg:
                    long = True
                if "t" in arg:
                    by_time = True
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
            if by_time:
                # Newest first, like `ls -t`; entries with no known mtime sort
                # last so real timestamps are never buried under unknowns.
                names.sort(
                    key=lambda name: (
                        self.model._get_node(posixpath.join(path, name)).updated_at or 0.0
                    ),
                    reverse=True,
                )
            lines = [self._format_ls_entry(posixpath.join(path, name), long) for name in names]
            blocks.append("\n".join(lines))
            hit = self.model.truncated_root_containing(path)
            if hit:
                source_root, shown = hit
                self._warn(
                    f"ls: '{source_root}' was truncated at {shown} entries; this listing "
                    "may be INCOMPLETE."
                )
        return "\n".join(block for block in blocks if block) + ("\n" if blocks else "")

    def _format_ls_entry(self, path: str, long: bool) -> str:
        name = posixpath.basename(path) or "/"
        if not long:
            return name
        node = self.model._get_node(path)
        attrs = self.model.getattr(path)
        mode = "d" if node.is_dir else "-"
        size = int(attrs.get("st_size", 0))
        return f"{mode} {size:>8} {_ls_time(node.updated_at)} {name}"

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
        mtime_spec = ""
        newer_than: float | None = None
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
            elif option == "-mtime":
                if index + 1 >= len(args):
                    raise VfsShellError("-mtime requires a value", exit_code=2)
                index += 1
                mtime_spec = args[index]
                if not re.fullmatch(r"[+-]?\d+", mtime_spec):
                    raise VfsShellError("-mtime value must be [+-]N days", exit_code=2)
            elif option == "-newer":
                if index + 1 >= len(args):
                    raise VfsShellError("-newer requires a path", exit_code=2)
                index += 1
                reference = self.model._get_node(self._resolve_path(args[index]))
                if not reference.updated_at:
                    raise VfsShellError(
                        f"-newer reference has no modification time: {args[index]}",
                        exit_code=2,
                    )
                newer_than = reference.updated_at
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
            # A time predicate can only match a node whose mtime is known —
            # sources that don't report one are excluded, never guessed at.
            if (mtime_spec or newer_than is not None) and not node.updated_at:
                continue
            if mtime_spec and not _mtime_matches(node.updated_at, mtime_spec):
                continue
            if newer_than is not None and node.updated_at <= newer_than:
                continue
            rows.append(node_path)
        for source_root, shown in self.model.truncated_roots_under(root):
            self._warn(
                f"find: '{source_root}' has more than {shown} entries; only the first "
                f"{shown} were listed. This result is INCOMPLETE — do not treat it as the "
                "full set."
            )
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
        for source_root, shown in self.model.truncated_roots_under(root):
            self._warn(
                f"tree: '{source_root}' has more than {shown} entries; only the first "
                f"{shown} were listed. This tree is INCOMPLETE."
            )
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
        fixed_strings = False
        before = 0
        after = 0
        options_done = False
        values: list[str] = []
        index = 0
        while index < len(args):
            arg = args[index]
            if not options_done and arg == "--":
                options_done = True
                index += 1
                continue
            if not options_done and arg.startswith("-") and arg != "-":
                if arg.startswith("--"):
                    if arg in ("--ignore-case", "--smart-case"):
                        ignore_case = True
                    elif arg == "--line-number":
                        show_line_numbers = True
                    elif arg == "--recursive":
                        recursive = True
                    elif arg == "--extended-regexp":
                        pass  # patterns are always extended regex here
                    elif arg == "--fixed-strings":
                        fixed_strings = True
                    else:
                        raise VfsShellError(f"unsupported {name} option: {arg}", exit_code=2)
                    index += 1
                    continue
                if arg[1] in ("A", "B", "C"):
                    context_flag = arg[1]
                    value_str = arg[2:]
                    if not value_str:
                        index += 1
                        if index >= len(args):
                            raise VfsShellError(f"-{context_flag} requires a value", exit_code=2)
                        value_str = args[index]
                    try:
                        value = int(value_str)
                    except ValueError as e:
                        msg = f"-{context_flag} value must be an integer"
                        raise VfsShellError(msg, exit_code=2) from e
                    if context_flag in ("A", "C"):
                        after = value
                    if context_flag in ("B", "C"):
                        before = value
                    index += 1
                    continue
                flags = arg[1:]
                unsupported = sorted(set(flags) - set("inrREF"))
                if unsupported:
                    raise VfsShellError(
                        f"unsupported {name} option: -{unsupported[0]}",
                        exit_code=2,
                    )
                ignore_case = ignore_case or "i" in flags
                recursive = recursive or "r" in flags or "R" in flags
                show_line_numbers = show_line_numbers or "n" in flags
                fixed_strings = fixed_strings or "F" in flags
                index += 1
                continue
            values.append(arg)
            index += 1
        if not values:
            raise VfsShellError("missing pattern")

        pattern = values[0]
        paths = values[1:]
        flags = re.IGNORECASE if ignore_case else 0
        if fixed_strings:
            regex = re.compile(re.escape(pattern), flags)
        else:
            _reject_bre_escapes(pattern)
            try:
                regex = re.compile(pattern, flags)
            except re.error as e:
                raise VfsShellError(str(e)) from e

        if stdin is not None and not paths:
            output = _grep_text(
                regex,
                stdin,
                "",
                show_line_numbers=False,
                prefix_path=False,
                before=before,
                after=after,
            )
            if not output:
                raise VfsShellExit(1)
            return output

        if not paths:
            paths = ["."]
        matches = []
        for raw_path in paths:
            path = self._resolve_path(raw_path)
            node = self.model._get_node(path)
            file_paths = [path] if node.is_file else self._file_paths(path) if recursive else []
            if node.is_dir and not recursive:
                raise VfsShellError(f"{raw_path}: is a directory")
            self.model.prefetch(file_paths)
            for file_path in file_paths:
                try:
                    text = self._read_text(file_path)
                except VfsClientError as e:
                    self._warn(f"{name}: {file_path}: {e.detail}")
                    continue
                matches.append(
                    _grep_text(
                        regex,
                        text,
                        file_path,
                        show_line_numbers=show_line_numbers,
                        prefix_path=len(file_paths) > 1 or recursive,
                        before=before,
                        after=after,
                    )
                )
        output = "".join(matches)
        if not output:
            raise VfsShellExit(1)
        return output

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
        selected = lines[start - 1 : end]
        dropped = len(lines) - len(selected)
        if dropped > 0:
            self._warn(
                f"sed: showing lines {start}-{min(end, len(lines))} of {len(lines)}; "
                f"{dropped} lines were NOT shown."
            )
        return "".join(selected)

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
        dropped = len(lines) - len(selected)
        if dropped > 0:
            name = "tail" if from_tail else "head"
            which = "last" if from_tail else "first"
            self._warn(
                f"{name}: showing the {which} {len(selected)} of {len(lines)} lines; "
                f"{dropped} lines were NOT shown."
            )
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

    def _sort(self, args: list[str], stdin: str | None) -> str:
        reverse = numeric = unique = fold = False
        paths: list[str] = []
        for arg in args:
            if arg.startswith("-") and arg != "-":
                flags = arg[1:]
                unsupported = sorted(set(flags) - set("rnuf"))
                if unsupported:
                    raise VfsShellError(f"unsupported sort option: -{unsupported[0]}", exit_code=2)
                reverse = reverse or "r" in flags
                numeric = numeric or "n" in flags
                unique = unique or "u" in flags
                fold = fold or "f" in flags
                continue
            paths.append(arg)
        text = stdin if not paths and stdin is not None else self._cat(paths)

        def key(line: str):
            if numeric:
                return _numeric_key(line)
            return line.lower() if fold else line

        keyed = sorted(((key(line), line) for line in text.splitlines()), key=lambda kv: kv[0])
        if reverse:
            keyed.reverse()
        if unique:
            lines = []
            previous = object()
            for k, line in keyed:
                if k == previous:
                    continue
                previous = k
                lines.append(line)
        else:
            lines = [line for _, line in keyed]
        return "\n".join(lines) + ("\n" if lines else "")

    def _uniq(self, args: list[str], stdin: str | None) -> str:
        count = only_dup = only_unique = ignore_case = False
        paths: list[str] = []
        for arg in args:
            if arg.startswith("-") and arg != "-":
                flags = arg[1:]
                unsupported = sorted(set(flags) - set("cdui"))
                if unsupported:
                    raise VfsShellError(f"unsupported uniq option: -{unsupported[0]}", exit_code=2)
                count = count or "c" in flags
                only_dup = only_dup or "d" in flags
                only_unique = only_unique or "u" in flags
                ignore_case = ignore_case or "i" in flags
                continue
            paths.append(arg)
        if len(paths) > 1:
            raise VfsShellError("uniq accepts at most one file", exit_code=2)
        text = stdin if not paths and stdin is not None else self._cat(paths)

        groups: list[tuple[str, int]] = []
        previous_key = object()
        for line in text.splitlines():
            line_key = line.lower() if ignore_case else line
            if groups and line_key == previous_key:
                groups[-1] = (groups[-1][0], groups[-1][1] + 1)
                continue
            groups.append((line, 1))
            previous_key = line_key

        rows = []
        for line, n in groups:
            if only_dup and n < 2:
                continue
            if only_unique and n > 1:
                continue
            rows.append(f"{n:>7} {line}" if count else line)
        return "\n".join(rows) + ("\n" if rows else "")

    def _cut(self, args: list[str], stdin: str | None) -> str:
        delimiter = "\t"
        fields_spec = ""
        chars_spec = ""
        paths: list[str] = []
        index = 0
        while index < len(args):
            arg = args[index]
            if arg in ("-d", "-f", "-c"):
                if index + 1 >= len(args):
                    raise VfsShellError(f"{arg} requires a value", exit_code=2)
                index += 1
                value = args[index]
            elif arg[:2] in ("-d", "-f", "-c"):
                value = arg[2:]
            elif arg.startswith("-") and arg != "-":
                raise VfsShellError(f"unsupported cut option: {arg}", exit_code=2)
            else:
                paths.append(arg)
                index += 1
                continue
            flag = arg[1]
            if flag == "d":
                delimiter = value
            elif flag == "f":
                fields_spec = value
            else:
                chars_spec = value
            index += 1

        if bool(fields_spec) == bool(chars_spec):
            raise VfsShellError("cut requires exactly one of -f or -c", exit_code=2)
        ranges = _parse_cut_ranges(fields_spec or chars_spec)
        text = stdin if not paths and stdin is not None else self._cat(paths)

        rows = []
        for line in text.splitlines():
            if chars_spec:
                rows.append("".join(_select_indexed(list(line), ranges)))
            elif delimiter not in line:
                rows.append(line)
            else:
                rows.append(delimiter.join(_select_indexed(line.split(delimiter), ranges)))
        return "\n".join(rows) + ("\n" if rows else "")

    def _xargs(self, args: list[str], stdin: str | None) -> str:
        max_args: int | None = None
        replace: str | None = None
        index = 0
        while index < len(args):
            arg = args[index]
            if arg == "-n" or arg == "-I":
                if index + 1 >= len(args):
                    raise VfsShellError(f"{arg} requires a value", exit_code=2)
                index += 1
                max_args, replace = self._set_xargs_value(arg[1], args[index], max_args, replace)
            elif arg.startswith("-n") or arg.startswith("-I"):
                max_args, replace = self._set_xargs_value(arg[1], arg[2:], max_args, replace)
            elif arg.startswith("-") and arg != "-":
                raise VfsShellError(f"unsupported xargs option: {arg}", exit_code=2)
            else:
                break
            index += 1

        command = args[index:]
        if not command:
            raise VfsShellError("xargs requires a command", exit_code=2)
        name, base = command[0], command[1:]

        # Split on newlines, not arbitrary whitespace: Stash paths routinely
        # contain spaces (skill/session titles), and the common pipelines feeding
        # xargs here — `find …` and `grep -l …` — emit one path per line.
        items = [line.strip() for line in (stdin or "").splitlines() if line.strip()]
        if not items:
            return ""

        if replace is not None:
            calls = [[a.replace(replace, item) for a in base] for item in items]
        else:
            batches = _chunk(items, max_args) if max_args else [items]
            calls = [base + batch for batch in batches]
        return "".join(self._dispatch(name, call, None) for call in calls)

    def _set_xargs_value(
        self, flag: str, value: str, max_args: int | None, replace: str | None
    ) -> tuple[int | None, str | None]:
        if flag == "I":
            return max_args, value
        try:
            return int(value), replace
        except ValueError as e:
            raise VfsShellError("-n value must be an integer", exit_code=2) from e

    def _echo(self, args: list[str]) -> str:
        newline = True
        if args and args[0] == "-n":
            newline = False
            args = args[1:]
        return " ".join(args) + ("\n" if newline else "")

    def _printf(self, args: list[str]) -> str:
        if not args:
            return ""
        template = args[0].encode("utf-8").decode("unicode_escape")
        values = args[1:]
        if "%" not in template:
            return template
        if not values:
            return _render_printf_template(template, [])[0]

        output = []
        value_index = 0
        while value_index < len(values):
            rendered, used = _render_printf_template(template, values[value_index:])
            output.append(rendered)
            if used == 0:
                break
            value_index += used
        return "".join(output)

    def _stat(self, args: list[str]) -> str:
        if len(args) != 1:
            raise VfsShellError("expected one path")
        path = self._resolve_path(args[0])
        attrs = self.model.getattr(path)
        node = self.model._get_node(path)
        kind = "directory" if node.is_dir else "file"
        out = (
            f"{path}\n"
            f"  type: {kind}\n"
            f"  size: {attrs.get('st_size', 0)}\n"
            f"  modified: {_iso_time(node.updated_at)}\n"
            f"  created: {_iso_time(node.created_at)}\n"
        )
        if node.external_ref:
            out += f"  external_ref: {node.external_ref}\n"
        if node.source_id:
            out += f"  source_id: {node.source_id}\n"
        if node.app_url:
            out += f"  app_url: {node.app_url}\n"
            out += f"  share: stash shares add source {node.source_id} <email>\n"
        return out

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
            raise MountError(f"directory not found: {path}") from e
        if not node.is_dir:
            raise MountError(f"not a directory: {path}")


class VfsShellError(Exception):
    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class VfsShellExit(Exception):
    def __init__(self, exit_code: int):
        self.exit_code = exit_code
        super().__init__(exit_code)


def _render_printf_template(template: str, values: list[str]) -> tuple[str, int]:
    output = []
    used = 0
    index = 0
    while index < len(template):
        char = template[index]
        if char != "%":
            output.append(char)
            index += 1
            continue

        if index + 1 >= len(template):
            raise VfsShellError("unsupported printf format: trailing %", exit_code=2)

        specifier = template[index + 1]
        if specifier == "%":
            output.append("%")
            index += 2
            continue
        if specifier != "s":
            raise VfsShellError(f"unsupported printf format: %{specifier}", exit_code=2)

        output.append(values[used] if used < len(values) else "")
        if used < len(values):
            used += 1
        index += 2

    return "".join(output), used


def _reject_bre_escapes(pattern: str) -> None:
    """Patterns compile as Python (extended) regex, where BRE's operator escapes
    `\\|` `\\(` `\\)` mean the *literal* character — so a caller writing default-grep
    syntax like `foo\\|bar` would silently match nothing. Refuse loudly instead."""
    index = 0
    while index < len(pattern) - 1:
        if pattern[index] != "\\":
            index += 1
            continue
        escaped = pattern[index + 1]
        if escaped in "|()":
            raise VfsShellError(
                f"pattern escape \\{escaped} is BRE syntax; patterns here are extended "
                f"regex — use {escaped} as the operator, or -F to match text literally",
                exit_code=2,
            )
        index += 2


def _grep_text(
    regex: re.Pattern[str],
    text: str,
    path: str,
    *,
    show_line_numbers: bool,
    prefix_path: bool,
    before: int = 0,
    after: int = 0,
) -> str:
    lines = text.splitlines()
    matched = {i for i, line in enumerate(lines) if regex.search(line)}
    if not matched:
        return ""

    # Map each line index we will print to whether it is a match (vs. context).
    # GNU grep separates matches from their filename/line with `:` and context
    # lines with `-`, and inserts a `--` line between non-adjacent groups.
    selected: dict[int, bool] = {}
    for i in matched:
        for context in range(max(0, i - before), min(len(lines), i + after + 1)):
            selected.setdefault(context, context in matched)
        selected[i] = True

    rows = []
    previous = None
    for i in sorted(selected):
        if (before or after) and previous is not None and i > previous + 1:
            rows.append("--")
        separator = ":" if selected[i] else "-"
        prefix = ""
        if prefix_path:
            prefix += f"{path}{separator}"
        if show_line_numbers:
            prefix += f"{i + 1}{separator}"
        rows.append(f"{prefix}{lines[i]}")
        previous = i
    return "\n".join(rows) + "\n"


def _numeric_key(line: str) -> float:
    """Leading numeric value of a line, like `sort -n`. Lines without a leading
    number sort as 0, matching coreutils."""
    match = re.match(r"\s*([+-]?\d+(?:\.\d+)?)", line)
    return float(match.group(1)) if match else 0.0


def _parse_cut_ranges(spec: str) -> list[tuple[int, int | None]]:
    """Parse a cut field/char list like `1,3-5,7-` into 1-indexed (start, end)
    pairs. `end` is None for an open-ended range (`3-`)."""
    ranges = []
    for part in spec.split(","):
        try:
            if "-" in part:
                low, high = part.split("-", 1)
                start = int(low) if low else 1
                end = int(high) if high else None
            else:
                start = end = int(part)
        except ValueError as e:
            raise VfsShellError(f"invalid cut range: {part}", exit_code=2) from e
        ranges.append((start, end))
    return ranges


def _select_indexed(items: list[str], ranges: list[tuple[int, int | None]]) -> list[str]:
    """Pick 1-indexed items covered by any range. Like cut, output is in item
    order (not range order) with no duplicates."""
    chosen: set[int] = set()
    for start, end in ranges:
        last = end if end is not None else len(items)
        chosen.update(i for i in range(start, last + 1) if 1 <= i <= len(items))
    return [items[i - 1] for i in sorted(chosen)]


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _reject_redirect(stage: str) -> None:
    """The Stash VFS is read-only. A redirect is the only write syntax the
    shell could express, so reject it loudly rather than silently treating
    `>` as a literal argument."""
    for token in (">>", ">"):
        if len(_split_unquoted(stage, token)) > 1:
            raise VfsShellError("the Stash VFS is read-only: writes are not supported", exit_code=2)


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
            "Supported commands (read-only):",
            "  pwd, cd, ls, cat, find, tree, rg, grep, sed -n, head, tail, wc,",
            "  sort, uniq, cut, xargs, echo, printf, stat",
            "  pipes with |, command chaining with && or ;",
            "",
        ]
    )


_SIX_MONTHS_SECONDS = 182 * 24 * 3600


def _ls_time(epoch: float | None) -> str:
    """`ls -l`-style 12-wide modified-time column. Recent entries show the
    time, older ones the year, exactly like coreutils. A node the backend
    gave no timestamp for shows `-` rather than a fabricated date."""
    if not epoch:
        return f"{'-':>12}"
    when = datetime.fromtimestamp(epoch)
    tail = (
        when.strftime("%H:%M")
        if abs(time.time() - epoch) < _SIX_MONTHS_SECONDS
        else when.strftime(" %Y")
    )
    return f"{when.strftime('%b'):>3} {when.day:>2} {tail}"


def _iso_time(epoch: float | None) -> str:
    if not epoch:
        return "-"
    return datetime.fromtimestamp(epoch).isoformat()


def _mtime_matches(epoch: float, spec: str) -> bool:
    """GNU find -mtime semantics in whole 24h units: `-N` = modified within the
    last N days, `+N` = older than N+1 days, `N` = age rounds to exactly N."""
    age_days = int((time.time() - epoch) // 86400)
    if spec.startswith("-"):
        return age_days < int(spec[1:])
    if spec.startswith("+"):
        return age_days > int(spec[1:])
    return age_days == int(spec)


def _name_matches(path: str, pattern: str, ignore_case: bool) -> bool:
    name = posixpath.basename(path)
    if ignore_case:
        return fnmatch.fnmatchcase(name.lower(), pattern.lower())
    return fnmatch.fnmatchcase(name, pattern)
