"""
CLI entrypoint — run as:

    python -m evals                         # all suites
    python -m evals --suite retrieval       # single suite
    python -m evals --suite retrieval kg    # multiple suites
    python -m evals --compare baseline.json # compare against baseline

Options:
  --suite SUITE [SUITE ...]  suites to run (default: all)
  --compare FILE             diff current results against a baseline JSON
  --out FILE                 write JSON results to FILE
  --llm                      enable LLM-judge suites (requires ANTHROPIC_API_KEY)
  --db URL                   override TEST_DATABASE_URL
  --list                     print available suites and exit
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


def _build_harness(pool):
    from evals.harness import EvalHarness
    from evals.suites.retrieval import RetrievalSuite
    from evals.suites.kg_relations import KGRelationsSuite
    from evals.suites.sleep_agent import SleepAgentSuite
    from evals.suites.end_to_end import EndToEndSuite
    from evals.suites.degradation import DegradationSuite
    from evals.suites.curation_quality import CurationQualitySuite

    harness = EvalHarness(pool)
    harness.register("retrieval", RetrievalSuite())
    harness.register("kg_relations", KGRelationsSuite())
    harness.register("sleep_agent", SleepAgentSuite())
    harness.register("end_to_end", EndToEndSuite())
    harness.register("degradation", DegradationSuite())
    harness.register("curation_quality", CurationQualitySuite())
    return harness


async def _main(args: argparse.Namespace) -> int:
    # Override config from CLI flags
    if args.llm:
        os.environ["EVAL_RUN_LLM_SUITES"] = "true"
    if args.db:
        os.environ["TEST_DATABASE_URL"] = args.db

    from evals.db import eval_db_pool
    from evals.reports import console as console_report
    from evals.reports import json_report

    async with eval_db_pool() as pool:
        harness = _build_harness(pool)
        suites = args.suite or list(harness._suite_registry)

        for suite_name in suites:
            console_report.print_suite_header(suite_name)

        suite_results = []
        for suite_name in suites:
            console_report.print_suite_header(suite_name)
            results = await harness.run([suite_name])
            suite_result = results[0]
            for r in suite_result.results:
                console_report.print_scenario_result(r)
            console_report.print_suite_summary(suite_result)
            suite_results.append(suite_result)

        out_path = json_report.write(suite_results, path=Path(args.out) if args.out else None)
        print(f"\n  Results written to {out_path}")

        if args.compare:
            diff = json_report.compare(Path(args.compare), out_path)
            _print_comparison(diff)

        console_report.print_final_summary(suite_results)

    return 0 if all(s.passed for s in suite_results) else 1


def _print_comparison(diff: dict) -> None:
    print(f"\n  Comparison: {diff['baseline']} → {diff['current']}")
    regressions = diff.get("regressions", [])
    improvements = diff.get("improvements", [])

    if not regressions and not improvements:
        print("  No significant metric changes (threshold: ±0.01).")
        return

    for r in regressions:
        print(f"  ↓ REGRESSION  {r['suite']}/{r['metric']}: {r['baseline']:.4f} → {r['current']:.4f} ({r['delta']:+.4f})")
    for r in improvements:
        print(f"  ↑ improved    {r['suite']}/{r['metric']}: {r['baseline']:.4f} → {r['current']:.4f} ({r['delta']:+.4f})")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m evals",
        description="Octopus evaluation harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--suite", nargs="+", metavar="SUITE",
        choices=[
            "retrieval", "kg_relations", "sleep_agent", "end_to_end",
            "degradation", "curation_quality",
        ],
        help="Suites to run (default: all)",
    )
    parser.add_argument("--compare", metavar="FILE", help="Baseline JSON to diff against")
    parser.add_argument("--out", metavar="FILE", help="Write results to this JSON file")
    parser.add_argument("--llm", action="store_true", help="Enable LLM-judge suites")
    parser.add_argument("--db", metavar="URL", help="Override TEST_DATABASE_URL")
    parser.add_argument(
        "--list", action="store_true", help="List available suites and exit"
    )

    args = parser.parse_args()

    if args.list:
        print("Available suites:")
        for name in [
            "retrieval", "kg_relations", "sleep_agent", "end_to_end",
            "degradation", "curation_quality",
        ]:
            print(f"  {name}")
        return

    exit_code = asyncio.run(_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
