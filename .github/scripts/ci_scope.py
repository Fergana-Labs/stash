"""Select PR suites conservatively; unknown/shared paths run everything."""

import sys

SUITES = ("www", "frontend", "python")


def suites_for(paths):
    selected = set()
    for path in paths:
        if path.startswith("www/"):
            selected.add("www")
        elif path.startswith("frontend/"):
            selected.add("frontend")
        elif path.startswith(("backend/", "cli/", "plugins/", "stashai/", "stashvfs/", "rm_worker/")):
            selected.add("python")
        elif path.startswith("docs/") or path.endswith(".md"):
            continue
        else:
            return set(SUITES)
    return selected


if __name__ == "__main__":
    selected = set(SUITES) if "--all" in sys.argv else suites_for(
        path for path in sys.stdin.read().split("\0") if path
    )
    for suite in SUITES:
        print(f"{suite}={'true' if suite in selected else 'false'}")
