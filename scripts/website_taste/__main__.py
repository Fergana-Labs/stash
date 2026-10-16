from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .corpus import discover, recover


def main():
    parser = argparse.ArgumentParser(description="Prepare real-history website taste experiments")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("discover")
    scan.add_argument("--output", type=Path, required=True)
    scan.add_argument("--home", type=Path, default=Path.home())
    recover_cmd = commands.add_parser("recover")
    recover_cmd.add_argument("--output", type=Path, required=True)
    extract_cmd = commands.add_parser("extract")
    extract_cmd.add_argument("--output", type=Path, required=True)
    extract_cmd.add_argument("--limit", type=int, default=240)
    extract_cmd.add_argument("--model", required=True)
    for name in (
        "calibrate",
        "prepare-test",
        "sync-reviews",
        "plan",
        "freeze",
        "fit",
        "skill",
        "optimize",
        "sample-dpo",
        "train-dpo",
        "evaluate",
        "auto-label",
    ):
        command = commands.add_parser(name)
        command.add_argument("--output", type=Path, required=True)
        if name in ("fit", "skill", "optimize"):
            command.add_argument("--reflection-model", default="claude-sonnet-4-6")
        if name == "prepare-test":
            command.add_argument("--model", required=True)
        if name == "auto-label":
            command.add_argument("--model", required=True)
            command.add_argument("--source", type=Path, required=True)
        if name == "freeze":
            command.add_argument(
                "--automatic-exploratory",
                action="store_true",
                help="Only when automatic labels were explicitly authorized; no human-validation claim.",
            )
        if name in ("optimize", "sample-dpo", "train-dpo", "evaluate"):
            command.add_argument(
                "--probe-output",
                type=Path,
                help="Use a released, versioned frozen-model activation probe instead of the legacy classifier",
            )
            command.add_argument(
                "--allow-cloud",
                action="store_true",
                help="Only after Henry approves the bounded cloud job",
            )
        if name == "evaluate":
            command.add_argument("--adapter")
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.command == "discover":
        print(json.dumps(discover(args.home, args.output)), flush=True)
    elif args.command == "recover":
        candidates = [
            json.loads(s) for s in (args.output / "candidates.jsonl").read_text().splitlines()
        ]
        counts = {"sessions": 0, "artifacts": 0, "screenshots": 0}
        with (args.output / "recovered.jsonl").open("w") as out:
            for candidate in candidates:
                record = recover(candidate, args.output / "html")
                out.write(json.dumps(record) + "\n")
                counts["sessions"] += 1
                counts["artifacts"] += len(record["artifacts"])
                counts["screenshots"] += len(record["screenshots"])
        print(json.dumps(counts), flush=True)
    elif args.command == "extract":
        from .preferences import extract

        print(json.dumps(extract(args.output, limit=args.limit, model=args.model)))
    else:
        from . import calibration, classifier, experiment, protocol
        from .runtime import FrozenScorer, Runner, environment_stash

        output = args.output
        model = {"id": "Qwen/Qwen3-8B", "revision": "b968826d9c46dd6066d109eabc6255188de91218"}
        if args.command == "plan":
            plan = {
                "model": model,
                "gepa_metric_calls": 24,
                "generation_calls_total": 72,
                "max_output_tokens_per_call": 4096,
                "inference_gpu": "Modal L4",
                "inference_timeout_seconds": 600,
                "training": "reward-labeled DPO, LoRA rank 8, 40 steps, train-only generated pairs",
                "training_gpu": "Modal A100-80GB",
                "training_timeout_minutes": 45,
                "local_model_loading": False,
                "cloud_launched": False,
                "requires": [
                    "reviewed labels",
                    "grouped train/dev/test with both labels",
                    "six unseen classifier examples and >=75% pilot agreement",
                    "explicit cloud approval",
                ],
                "tasks": protocol.tasks(),
            }
            (output / "cloud-plan.json").write_text(json.dumps(plan, indent=2))
            print(json.dumps(plan, indent=2))
            return
        if args.command == "calibrate":
            print(json.dumps(calibration.prepare(output, environment_stash())))
            return
        if args.command == "auto-label":
            from .autolabel import prepare

            print(json.dumps(prepare(args.source, output, environment_stash(), model=args.model)))
            return
        if args.command == "prepare-test":
            from .test_candidates import prepare

            print(json.dumps(prepare(output, environment_stash(), model=args.model)))
            return
        if args.command == "sync-reviews":
            print(json.dumps(calibration.sync_reviews(output, environment_stash())))
            return
        if args.command == "freeze":
            examples = [json.loads(s) for s in (output / "reviewed.jsonl").read_text().splitlines()]
            print(
                json.dumps(
                    {
                        "sha256": protocol.seal(
                            output,
                            examples,
                            protocol.tasks(),
                            model,
                            label_policy="automatic_exploratory"
                            if args.automatic_exploratory
                            else "human_reviewed",
                        )["sha256"]
                    }
                )
            )
            return
        frozen = protocol.load(output)
        if args.command in ("fit", "skill", "optimize"):
            reflect = experiment.Reflector(output, args.reflection_model)
        if args.command == "fit":
            print(json.dumps(classifier.fit(output, environment_stash(), reflect)))
            return
        if args.command == "skill":
            experiment.make_skill(output, reflect)
            print(json.dumps({"skill": str(output / "SKILL.md")}))
            return
        if not args.allow_cloud:
            parser.error(
                "This step launches cloud GPU work. Obtain approval for cloud-plan.json, then pass --allow-cloud."
            )
        if (output / "pilot-invalidated.json").exists():
            raise ValueError(
                "This reward was invalidated by human feedback. Fit and validate a new classifier before launching more GPU work."
            )
        probe_output = args.probe_output or (
            output if (output / "activation-probe.json").exists() else None
        )
        if probe_output:
            from .probe_pipeline import ProbeScorer

            reward = ProbeScorer(probe_output)
            # Frozen evidence and generation split identities must agree.
            from .probe_pipeline import dataset_at

            if dataset_at(probe_output)["source_experiment"] != frozen["sha256"]:
                raise ValueError("Activation probe belongs to a different generation experiment")
        else:
            scorer = json.loads((output / "classifier.json").read_text())
            if not scorer["pilot_gate_passed"] or scorer["experiment"] != frozen["sha256"]:
                raise ValueError("The frozen taste classifier has not passed the pilot gate")
            if not classifier.development_gate(
                json.loads((output / "classifier-training.json").read_text())
            ):
                raise ValueError("The frozen taste classifier failed the development checks")
            reward = FrozenScorer(environment_stash(), scorer["model_id"], scorer["version_id"])
        # Importing the cloud module may create private Modal volumes; do this only
        # after the explicit operator gate, never during plan/discover/review commands.
        from .cloud import RemoteGenerator

        runner = Runner(
            output,
            frozen,
            RemoteGenerator(frozen["model"]),
            reward,
            call_limit=frozen["max_generation_calls"],
        )
        if args.command == "optimize":
            result = experiment.optimize(output, runner, reflect)
            print(
                json.dumps(
                    {"candidates": len(result["candidates"]), "best_index": result["best_index"]}
                )
            )
        elif args.command == "sample-dpo":
            print(json.dumps({"pairs": len(experiment.dpo_pairs(output, runner))}))
        elif args.command == "train-dpo":
            import modal

            pairs = [json.loads(s) for s in (output / "dpo-pairs.jsonl").read_text().splitlines()]
            config, run_id = experiment.training_identity(
                frozen, pairs, getattr(reward, "identity", None)
            )
            file = output / "posttraining.json"
            if file.exists():
                raise ValueError(
                    "A training receipt already exists; inspect it before launching another GPU run"
                )
            result = modal.Function.from_name("stash-website-taste", "train").remote(
                frozen["model"], pairs, config, run_id
            )
            file.write_text(json.dumps(result, indent=2))
            print(
                json.dumps(
                    {k: result[k] for k in ("adapter", "steps", "requested_steps", "method")}
                )
            )
        elif args.command == "evaluate":
            result = experiment.evaluate(output, runner, adapter=args.adapter)
            print(
                json.dumps({"arms": result["arms"], "gallery": str(output / "blind-gallery.html")})
            )


if __name__ == "__main__":
    main()
