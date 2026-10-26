"""Opt-in CI sharding by test file; normal local pytest runs are unchanged.

Greedily balance collected test counts while keeping module fixtures together.
Every runner collects the same suite and computes the same assignment, without
needing a checked-in list that can omit newly added tests.
"""

from collections import Counter


def assign_files(nodeids: list[str], count: int) -> dict[str, int]:
    if count < 1:
        raise ValueError("shard count must be positive")
    sizes = Counter(nodeid.split("::", 1)[0] for nodeid in nodeids)
    loads = [0] * count
    assignments = {}
    for path in sorted(sizes, key=lambda path: (-sizes[path], path)):
        shard = min(range(count), key=lambda index: (loads[index], index))
        assignments[path] = shard + 1
        loads[shard] += sizes[path]
    return assignments


def pytest_addoption(parser):
    group = parser.getgroup("CI sharding")
    group.addoption("--shard-count", type=int, default=1)
    group.addoption("--shard-index", type=int, default=1)


def pytest_configure(config):
    import pytest

    count = config.getoption("shard_count")
    index = config.getoption("shard_index")
    if count < 1 or not 1 <= index <= count:
        raise pytest.UsageError(
            "require --shard-count >= 1 and 1 <= --shard-index <= --shard-count"
        )


def pytest_collection_modifyitems(config, items):
    count = config.getoption("shard_count")
    if count == 1:
        return
    index = config.getoption("shard_index")
    assignments = assign_files([item.nodeid for item in items], count)
    selected, deselected = [], []
    for item in items:
        target = selected if assignments[item.nodeid.split("::", 1)[0]] == index else deselected
        target.append(item)
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected


def pytest_report_header(config):
    return f"CI shard {config.getoption('shard_index')}/{config.getoption('shard_count')}"
