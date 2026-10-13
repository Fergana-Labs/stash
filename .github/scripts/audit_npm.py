"""Audit every dependency, with one expiring, exact-version dev-tool exception."""

import argparse
import json
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

ADVISORY = "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm"
EXPIRES = date(2026, 10, 26)
DEV_CHAIN = {
    "eslint-config-next": "16.3.8",
    "@next/eslint-plugin-next": "16.3.8",
    "fast-glob": "3.3.1",
    "micromatch": "4.0.8",
    "braces": "3.0.3",
}
DEV_EDGES = {
    "eslint-config-next": "@next/eslint-plugin-next",
    "@next/eslint-plugin-next": "fast-glob",
    "fast-glob": "micromatch",
    "micromatch": "braces",
}
SEVERITY = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}


def evaluate(report, lock, *, today=None):
    today = today or datetime.now(UTC).date()
    if report.get("error") or report.get("auditReportVersion") != 2:
        raise ValueError("npm audit did not return a supported vulnerability report")
    findings = report.get("vulnerabilities")
    packages = lock.get("packages")
    if not isinstance(findings, dict) or not isinstance(packages, dict):
        raise ValueError("Missing audit findings or lockfile package metadata")

    def reviewed_dev_only(name, visiting):
        if today > EXPIRES or name not in DEV_CHAIN or name in visiting:
            return False
        finding = findings.get(name)
        if not isinstance(finding, dict) or not finding.get("nodes"):
            return False
        for node in finding["nodes"]:
            package = packages.get(node, {})
            if package.get("dev") is not True or package.get("version") != DEV_CHAIN[name]:
                return False
        via = finding.get("via")
        if not isinstance(via, list) or len(via) != 1:
            return False
        for source in via:
            if isinstance(source, str):
                if source != DEV_EDGES.get(name) or not reviewed_dev_only(
                    source, visiting | {name}
                ):
                    return False
            elif isinstance(source, dict):
                if (
                    name != "braces"
                    or source.get("name") != "braces"
                    or source.get("url") != ADVISORY
                ):
                    return False
            else:
                return False
        # Stop exempting as soon as npm can fix this chain without the currently
        # suggested unsupported downgrade to ESLint's Next 14 configuration.
        fix = finding.get("fixAvailable")
        return (
            isinstance(fix, dict)
            and fix.get("name") == "eslint-config-next"
            and fix.get("version") == "14.2.35"
            and fix.get("isSemVerMajor") is True
        )

    failures, exceptions = [], []
    for name, finding in findings.items():
        severity = finding.get("severity")
        if severity not in SEVERITY:
            raise ValueError("Unrecognized vulnerability severity")
        if SEVERITY[severity] < SEVERITY["moderate"]:
            continue
        if reviewed_dev_only(name, set()):
            exceptions.append(name)
        else:
            failures.append(name)
    return sorted(failures), sorted(exceptions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    project = parser.parse_args().project.resolve()
    result = subprocess.run(
        ["npm", "audit", "--package-lock-only", "--audit-level=moderate", "--json"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        if result.returncode not in (0, 1):
            raise ValueError("npm audit failed before returning findings")
        report = json.loads(result.stdout)
        print(json.dumps(report, indent=2))  # Retain the complete raw findings in CI.
        lock = json.loads((project / "package-lock.json").read_text())
        failures, exceptions = evaluate(report, lock)
    except (ValueError, OSError) as exc:
        print(f"::error::{exc}")
        return 1
    if exceptions:
        print(
            f"::warning::Reviewed dev-only {ADVISORY} exception expires {EXPIRES}: "
            + ", ".join(exceptions)
        )
    if failures:
        print("::error::Blocking npm audit findings: " + ", ".join(failures))
        return 1
    print("No blocking npm audit findings; all non-exempt dependencies were audited.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
