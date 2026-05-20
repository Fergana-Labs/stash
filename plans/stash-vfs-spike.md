# Stash Virtual Filesystem Spike

## Summary

We started with the idea of exposing Stash as a real local filesystem so coding
agents could navigate shared memory with familiar bash semantics. The initial
product instinct was right: agents are much better at `ls`, `find`, `rg`, `cat`,
and `sed` than they are at remembering bespoke CLI/API workflows.

The spike changed our implementation direction. A kernel/system-level virtual
filesystem is possible, but it creates scary macOS install prompts and provider
complexity that are not necessary for the core agent use case. The solution we
landed on is an app-level virtual filesystem shell:

```bash
stash vfs ls /
stash vfs "tree /workspaces -L 2"
stash vfs "find /workspaces -maxdepth 3 -type f"
stash vfs "rg \"query\" /workspaces"
stash vfs "cat '/workspaces/<workspace>/README.md' | sed -n '1,80p'"
```

This keeps the agent-facing interaction bash-shaped without mounting anything
into the operating system.

## Goal

Expose all of Stash to coding agents in a filesystem-shaped way:

- Workspaces
- Files: folders, pages, uploads, tables
- Sessions and transcripts
- Stashes

The primary user is not a human opening Finder. The primary user is a local
coding agent trained to use shell tools for exploration and editing.

## Evaluation Criteria

We evaluated options against these constraints:

- Agents should be able to explore Stash with bash-shaped commands.
- Installation should not ask users to lower macOS security settings.
- The first version should be small enough to reason about and iterate.
- Editing should be possible for the resources where we have clear write
  semantics.
- The implementation should reuse Stash's existing CLI auth and client layer.

## Options Considered

### OS-Level FUSE Mount

This is the Mesa-style approach. A local mount appears at a real path, and every
host process can use normal filesystem APIs against it.

Why it was attractive:

- Best match for native POSIX filesystem behavior.
- Unmodified agents can run `cd /Volumes/Stash && ls`.
- Any host program can read files from the mount.

What we found:

- macOS requires a filesystem provider.
- macFUSE can require enabling third-party kernel extensions on Apple Silicon.
  That can send users through a shutdown and Recovery security flow.
- FUSE-T avoids kernel extensions, but it exposes the mount through local
  network-volume machinery. In our smoke tests, simple `ls`/`cat` operations hit
  macOS permission errors.
- macFUSE FSKit looked promising on paper, but the package path we tested did
  not produce a working "just install and mount" flow.

Decision:

Keep the FUSE spike code as useful research, but do not make OS-level mounting
the primary Stash agent path right now. The user trust and install cost are too
high for the first version.

### Native macOS File Provider

This is the Apple-native cloud-files approach used by many sync products.

Why it was attractive:

- No third-party kernel extension.
- Built for cloud-backed file surfaces.
- Better macOS product posture than FUSE.

Why we did not choose it for this spike:

- Requires a signed/notarized macOS app and File Provider extension.
- Adds platform-specific app lifecycle work before we have validated that an
  OS-visible filesystem is necessary.
- Mount location and behavior are Apple-shaped, not a simple CLI-only surface.

Decision:

Potential future path if we later need a first-class Finder/local-path
experience on macOS. Not the right first implementation for agent navigation.

### Real Sync Folder

This would materialize Stash into a normal local folder and run a daemon to sync
changes.

Why it was attractive:

- No kernel extension.
- Very familiar to users and agents.
- Easy for arbitrary local tools to read.

Why we did not choose it:

- It is not actually virtual.
- Lazy remote exploration is hard without a filesystem layer.
- We would need to choose between eager materialization and complex sync state.
- It adds write-conflict and offline-state behavior before we know we need it.

Decision:

Not the right shape for a spike. It may be useful later for explicit export or
workspace caching, but it is heavier than the agent-navigation problem requires.

### Mirage/Mesa-Style App-Level VFS

This approach does not mount a real filesystem. Instead, it gives the agent a
shell-shaped command surface backed by a virtual tree.

Why it was attractive:

- No macOS system extension.
- No FUSE provider.
- No Recovery-mode security flow.
- Still speaks in the command patterns agents know: `ls`, `find`, `rg`, `cat`,
  pipes, redirects, and simple edits.
- Can reuse the same `StashVfsModel` we built for the FUSE spike.

Tradeoff:

- It is visible to agents only when they call `stash vfs ...`.
- It does not create a real path like `~/Stash` for arbitrary local programs.

Decision:

This is the solution we chose for the next iteration because our actual product
goal is coding-agent navigation, not Finder integration.

## What We Built

The spike now has two layers:

### Shared Virtual Tree Model

`cli/mount.py` contains `StashVfsModel`, which builds a tree like:

```text
/
  README.md
  workspaces/
    <workspace-name--id>/
      README.md
      files/
      sessions/
      stashes/
      tables/
```

This model fetches workspace overviews, pages, uploads, stashes, sessions,
transcripts, and tables from the Stash API.

Current write semantics:

- Markdown/HTML pages are writable.
- Sessions, stashes, uploaded files, and table projections are read-only.

That is intentional. Page editing has a clear remote API contract today. Other
resource writes need product design before we expose them through filesystem
commands.

### App-Level VFS Shell

`cli/app_vfs.py` implements `StashAppVfsShell`, exposed through:

```bash
stash vfs ...
```

Supported shell-shaped operations:

- Navigation: `pwd`, `cd`, `ls`, `find`, `tree`, `stat`
- Reads: `cat`, `head`, `tail`, `sed -n`, `wc`
- Search: `rg`, `grep`, including common `-n`, `-i`, and recursive forms
- Writes to existing writable files: `echo`, `printf`, `tee`, `>`, `>>`
- Composition: pipes with `|`, command chaining with `&&` and `;`

Example:

```bash
stash vfs "tree /workspaces -L 2"
stash vfs "find /workspaces -maxdepth 4 -type f | head -n 20"
stash vfs "rg \"memory leak\" /workspaces | head -n 20"
stash vfs "cat '/workspaces/<workspace>/files/<page>.md' | sed -n '1,80p'"
```

The command also supports an interactive prompt when run without arguments.

## Agent Integration

We updated the instruction surfaces that Stash already installs for agents:

- Codex `AGENTS.md`
- opencode `AGENTS.md`
- Cursor `.mdc` rule
- Claude plugin context/docs
- `stash connect` generated `CLAUDE.md`
- setup-complete splash
- README

The important behavior is that agents are taught to reach for `stash vfs` when
they want to browse Stash like a filesystem.

## Productionization Decision

The production path is `stash vfs`, not OS-level mounting:

- The default installer installs the Stash CLI and agent hooks only.
- The default installer does not install any filesystem provider.
- `fusepy` is not a default package dependency.
- `stash mount` remains hidden experimental spike code for future research.

## Why This Is Better For The First Product Version

This version preserves the important part of the original idea: agents interact
with Stash using bash-shaped exploration.

It avoids the part that made the FUSE plan risky: asking users to approve
low-level filesystem providers before they have experienced product value.

The implementation is also much easier to reason about:

- One Python module for the shell.
- One shared VFS model.
- Existing CLI auth/config.
- Existing API client.
- No daemon lifecycle.
- No OS mount lifecycle.
- No third-party filesystem provider.

## What This Does Not Solve

`stash vfs` is not visible as a real path on disk. These are not equivalent:

```bash
stash vfs "cat /workspaces/..."
cat ~/Stash/...
```

The second form requires an OS-level filesystem, sync folder, File Provider, or
similar local integration. We are intentionally not solving that yet.

This is acceptable for the current target because coding agents can call shell
commands, and we can teach them to use `stash vfs`.

## Validation Plan

The next validation step is product/agent behavior, not filesystem engineering:

1. Ask fresh Codex/Claude/Cursor/opencode sessions to explore Stash.
2. Watch whether they naturally use `stash vfs`.
3. Compare task quality against old CLI-only flows.
4. Add the missing shell commands agents attempt first.
5. Measure whether agents can find relevant sessions/files/stashes with fewer
   prompts and less user guidance.

Concrete prompts to test:

```text
Use Stash's virtual filesystem to list my workspaces.
```

```text
Use Stash to find prior work on the mount-vfs spike and summarize the decision.
```

```text
Use Stash's virtual filesystem to find relevant sessions about FUSE, Mesa, or app-level VFS.
```

## Future Decisions

We should revisit OS-level filesystem work only if we learn that:

- Agents fail to use `stash vfs` reliably.
- Users need non-agent local tools to browse Stash.
- Editing through app-level commands is too awkward.
- We need long-lived local paths for workflows outside agent shells.

If that happens, the likely split is:

- Linux: FUSE.
- macOS: File Provider for product-grade UX, or macFUSE only if we explicitly
  accept the security-policy cost.

For now, the app-level VFS is the right wedge.
