"""Evaluate cached reward features; optionally invoke bounded cloud endpoints.

Example (no model inference):
    python -m backend.scripts.eval_reward_basis --dataset benchmark.json --output report.json

Attack configuration is JSON with ``protocol``, ``tasks`` and three explicit
argument arrays: ``generator_command``, ``evaluator_command``, ``verifier_command``.
The endpoints receive/return one JSON object per process invocation. This CLI
does not train a model or run an agent unless the supplied commands do so.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rm_worker.basis_validation import (
    AttackProtocol,
    learning_curves,
    release_report,
    run_attack_campaigns,
    subprocess_callback,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--l2", type=float, default=1.0)
    parser.add_argument("--attack-config", type=Path)
    parser.add_argument(
        "--policy", type=Path, help="Explicit preregistered product thresholds (JSON)"
    )
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text())
    curves = learning_curves(dataset, repeats=args.repeats, seed=args.seed, l2=args.l2)
    attacks = None
    if args.attack_config:
        configuration = json.loads(args.attack_config.read_text())
        configurations = configuration if isinstance(configuration, list) else [configuration]
        attacks = []
        for config in configurations:
            protocol_data = dict(config["protocol"])
            protocol_data["allowed_modifications"] = tuple(protocol_data["allowed_modifications"])
            protocol = AttackProtocol(**protocol_data)
            timeout = config.get("timeout_seconds", 60.0)
            attacks.append(
                run_attack_campaigns(
                    config["tasks"],
                    protocol,
                    generate=subprocess_callback(
                        config["generator_command"], "generate", timeout_seconds=timeout
                    ),
                    evaluate=subprocess_callback(
                        config["evaluator_command"], "evaluate", timeout_seconds=timeout
                    ),
                    verify=subprocess_callback(
                        config["verifier_command"], "verify", timeout_seconds=timeout
                    ),
                )
            )
    policy = json.loads(args.policy.read_text()) if args.policy else None
    report = release_report(curves, attacks, policy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "report": str(args.output),
                "product_gate": report["product_gate"]["status"],
                "evidence_scope": curves["evidence_scope"],
            }
        )
    )


if __name__ == "__main__":
    main()
