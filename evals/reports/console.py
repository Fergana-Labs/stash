"""Rich console reporter — pretty-prints suite results during a run."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evals.harness import EvalResult, SuiteResult

_USE_RICH = True
try:
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
except ImportError:
    _USE_RICH = False


def _bar(value: float, width: int = 20) -> str:
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled)


def print_suite_header(suite_name: str) -> None:
    msg = f"\n  ▶ Suite: {suite_name}"
    if _USE_RICH:
        console.print(f"\n[bold cyan]▶ Suite: {suite_name}[/bold cyan]")
    else:
        print(msg)


def print_scenario_result(result: "EvalResult") -> None:
    icon = "✓" if result.passed else "✗"
    colour = "green" if result.passed else "red"
    metrics_str = "  ".join(f"{k}={v:.3f}" for k, v in result.metrics.items())
    error_str = f"  ERROR: {result.error}" if result.error else ""

    if _USE_RICH:
        console.print(
            f"  [{colour}]{icon}[/{colour}] [dim]{result.scenario_id}[/dim] "
            f"{result.description}  [yellow]{metrics_str}[/yellow]{error_str}"
        )
    else:
        print(f"  {icon} [{result.scenario_id}] {result.description}  {metrics_str}{error_str}")


def print_suite_summary(suite_result: "SuiteResult") -> None:
    passed = sum(1 for r in suite_result.results if r.passed)
    total = len(suite_result.results)
    suite_icon = "✓" if suite_result.passed else "✗"
    colour = "green" if suite_result.passed else "red"

    agg_str = "  ".join(f"{k}={v:.3f}" for k, v in suite_result.aggregate.items())

    if _USE_RICH:
        console.print(
            f"\n  [{colour}]{suite_icon} {suite_result.suite}[/{colour}]  "
            f"{passed}/{total} passed  [{'{:.0f}'.format(suite_result.duration_s * 1000)}ms]  "
            f"[dim]{agg_str}[/dim]"
        )
    else:
        print(
            f"\n  {suite_icon} {suite_result.suite}: {passed}/{total} passed "
            f"({suite_result.duration_s * 1000:.0f}ms)  {agg_str}"
        )


def print_final_summary(suite_results: "list[SuiteResult]") -> None:
    all_passed = all(s.passed for s in suite_results)
    total_scenarios = sum(len(s.results) for s in suite_results)
    total_passed = sum(sum(1 for r in s.results if r.passed) for s in suite_results)

    if _USE_RICH:
        console.rule()
        status_colour = "green" if all_passed else "red"
        status_text = "ALL SUITES PASSED" if all_passed else "SOME SUITES FAILED"
        console.print(
            f"[bold {status_colour}]{status_text}[/bold {status_colour}]  "
            f"{total_passed}/{total_scenarios} scenarios"
        )

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("Suite", style="cyan")
        table.add_column("Pass", justify="center")
        table.add_column("Scenarios", justify="right")
        table.add_column("Duration", justify="right")
        table.add_column("Key metrics", style="dim")

        for s in suite_results:
            p = sum(1 for r in s.results if r.passed)
            t = len(s.results)
            metrics = "  ".join(f"{k}={v:.3f}" for k, v in s.aggregate.items())
            icon = "✓" if s.passed else "✗"
            colour = "green" if s.passed else "red"
            table.add_row(
                s.suite,
                f"[{colour}]{icon}[/{colour}]",
                f"{p}/{t}",
                f"{s.duration_s * 1000:.0f}ms",
                metrics,
            )
        console.print(table)
    else:
        print("\n" + "=" * 60)
        status = "ALL SUITES PASSED" if all_passed else "SOME SUITES FAILED"
        print(f"{status}  {total_passed}/{total_scenarios} scenarios")
        for s in suite_results:
            p = sum(1 for r in s.results if r.passed)
            icon = "✓" if s.passed else "✗"
            metrics = "  ".join(f"{k}={v:.3f}" for k, v in s.aggregate.items())
            print(f"  {icon} {s.suite}: {p}/{len(s.results)}  {metrics}")

    if not all_passed:
        sys.exit(1)
