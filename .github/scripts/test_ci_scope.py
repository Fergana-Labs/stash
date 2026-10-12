import unittest

from ci_scope import SUITES, suites_for


class ScopeTests(unittest.TestCase):
    def test_frontend_only(self):
        self.assertEqual(suites_for(["frontend/src/app/page.tsx"]), {"frontend"})

    def test_marketing_only(self):
        self.assertEqual(suites_for(["www/package-lock.json"]), {"www"})

    def test_python_shared_suites(self):
        for path in ("backend/main.py", "cli/main.py", "plugins/tests/test_hooks.py", "stashai/plugin/hooks.py", "rm_worker/train.py", "stashvfs/core.py"):
            with self.subTest(path=path):
                self.assertEqual(suites_for([path]), {"python"})

    def test_mixed_changes(self):
        self.assertEqual(suites_for(["frontend/package.json", "backend/requirements.txt"]), {"frontend", "python"})

    def test_docs_only(self):
        self.assertEqual(suites_for(["docs/design.html", "README.md"]), set())

    def test_unknown_and_global_changes_run_all(self):
        for path in (".github/workflows/test.yml", "pyproject.toml", "Dockerfile", "scripts/build.py", "new-service/server.ts"):
            with self.subTest(path=path):
                self.assertEqual(suites_for([path]), set(SUITES))

    def test_deletion_and_rename_paths(self):
        self.assertEqual(suites_for(["backend/old.py", "frontend/new.ts"]), {"python", "frontend"})
