import copy
import unittest
from datetime import date

from audit_npm import ADVISORY, DEV_CHAIN, evaluate


def reports():
    edges = {
        "eslint-config-next": ["@next/eslint-plugin-next"],
        "@next/eslint-plugin-next": ["fast-glob"],
        "fast-glob": ["micromatch"],
        "micromatch": ["braces"],
        "braces": [{"name": "braces", "url": ADVISORY}],
    }
    packages, findings = {}, {}
    for name, version in DEV_CHAIN.items():
        node = "node_modules/" + name
        packages[node] = {"version": version, "dev": True}
        findings[name] = {
            "severity": "high",
            "nodes": [node],
            "via": edges[name],
            "fixAvailable": {
                "name": "eslint-config-next",
                "version": "14.2.35",
                "isSemVerMajor": True,
            },
        }
    return {"auditReportVersion": 2, "vulnerabilities": findings}, {"packages": packages}


class NpmAuditPolicyTests(unittest.TestCase):
    def check(self, report, lock, today=date(2026, 10, 13)):
        return evaluate(report, lock, today=today)

    def test_exact_reviewed_dev_chain_has_visible_exception(self):
        report, lock = reports()
        failures, exceptions = self.check(report, lock)
        self.assertEqual(failures, [])
        self.assertEqual(set(exceptions), set(DEV_CHAIN))

    def test_production_or_unknown_package_nodes_block_the_entire_chain(self):
        for change in ({"dev": False}, {"dev": None}, {"version": "3.0.4"}):
            report, lock = reports()
            lock["packages"]["node_modules/braces"].update(change)
            self.assertEqual(set(self.check(report, lock)[0]), set(DEV_CHAIN))

    def test_a_second_production_copy_cannot_hide_behind_a_dev_copy(self):
        report, lock = reports()
        node = "node_modules/production-consumer/node_modules/braces"
        report["vulnerabilities"]["braces"]["nodes"].append(node)
        lock["packages"][node] = {"version": "3.0.3"}
        self.assertEqual(set(self.check(report, lock)[0]), set(DEV_CHAIN))

    def test_new_advisory_on_braces_still_blocks(self):
        report, lock = reports()
        report["vulnerabilities"]["braces"]["via"].append(
            {"name": "braces", "url": "https://example.com/new"}
        )
        self.assertEqual(set(self.check(report, lock)[0]), set(DEV_CHAIN))

    def test_other_dev_vulnerabilities_and_new_consumers_are_not_exempt(self):
        report, lock = reports()
        report["vulnerabilities"]["another-consumer"] = copy.deepcopy(
            report["vulnerabilities"]["micromatch"]
        )
        self.assertEqual(self.check(report, lock)[0], ["another-consumer"])

    def test_cycles_and_missing_metadata_fail_closed(self):
        report, lock = reports()
        report["vulnerabilities"]["braces"]["via"] = ["micromatch"]
        self.assertEqual(set(self.check(report, lock)[0]), set(DEV_CHAIN))

    def test_unreviewed_edges_between_known_packages_are_not_exempt(self):
        report, lock = reports()
        report["vulnerabilities"]["fast-glob"]["via"] = ["braces"]
        failures, _ = self.check(report, lock)
        self.assertIn("fast-glob", failures)
        self.assertIn("eslint-config-next", failures)
        report, lock = reports()
        del lock["packages"]["node_modules/braces"]
        self.assertEqual(set(self.check(report, lock)[0]), set(DEV_CHAIN))

    def test_expiry_and_available_compatible_fix_end_the_exception(self):
        report, lock = reports()
        self.assertEqual(set(self.check(report, lock, date(2026, 10, 27))[0]), set(DEV_CHAIN))
        for fix in (
            True,
            {"name": "eslint-config-next", "isSemVerMajor": False},
            {"name": "eslint-config-next", "version": "17.0.0", "isSemVerMajor": True},
        ):
            report, lock = reports()
            report["vulnerabilities"]["braces"]["fixAvailable"] = fix
            self.assertEqual(set(self.check(report, lock)[0]), set(DEV_CHAIN))

    def test_audit_errors_and_unsupported_formats_cannot_pass(self):
        for report in (
            {"error": {"code": "EAUDIT"}},
            {"auditReportVersion": 3},
            {"auditReportVersion": 2},
        ):
            with self.assertRaises(ValueError):
                self.check(report, {"packages": {}})


if __name__ == "__main__":
    unittest.main()
