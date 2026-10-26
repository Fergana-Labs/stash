"""Selection invariants can run before installing backend dependencies."""

import unittest

from backend.tests.shard_plugin import assign_files


class ShardTests(unittest.TestCase):
    def test_complete_disjoint_balanced_and_module_local(self):
        nodeids = [f"test_{file}.py::test_{index}[param]"
                   for file in range(12) for index in range(8)]
        assignments = assign_files(nodeids, 4)
        selected = [{nodeid for nodeid in nodeids
                     if assignments[nodeid.split("::", 1)[0]] == shard}
                    for shard in range(1, 5)]
        self.assertEqual(set.union(*selected), set(nodeids))
        self.assertEqual(sum(map(len, selected)), len(nodeids))
        self.assertEqual([len(part) for part in selected], [24] * 4)
        for first in range(4):
            for second in range(first + 1, 4):
                self.assertFalse(selected[first] & selected[second])

    def test_assignment_is_independent_of_collection_order(self):
        nodeids = ["b.py::test_x", "a.py::test_z", "a.py::test_y", "c.py::test_x"]
        self.assertEqual(assign_files(nodeids, 2), assign_files(list(reversed(nodeids)), 2))

    def test_new_files_are_included_and_largest_first(self):
        nodeids = ["small.py::test_one"] + [f"new.py::test_{i}" for i in range(20)]
        self.assertEqual(assign_files(nodeids, 2), {"new.py": 1, "small.py": 2})

    def test_one_shard_and_empty_collection(self):
        self.assertEqual(assign_files(["x.py::test"], 1), {"x.py": 1})
        self.assertEqual(assign_files([], 4), {})

    def test_invalid_count(self):
        for count in (0, -1):
            with self.assertRaises(ValueError):
                assign_files([], count)
