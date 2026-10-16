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
    ):
        command = commands.add_parser(name)
        command.add_argument("--output", type=Path, required=True)
        if name in ("fit", "skill", "optimize"):
            command.add_argument("--reflection-model", default="claude-sonnet-4-6")
        if name == "prepare-test":
            command.add_argument("--model", required=True)
        if name in ("optimize", "sample-dpo", "train-dpo", "evaluate"):
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
                    {"sha256": protocol.seal(output, examples, protocol.tasks(), model)["sha256"]}
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
        scorer = json.loads((output / "classifier.json").read_text())
        if not scorer["pilot_gate_passed"] or scorer["experiment"] != frozen["sha256"]:
            raise ValueError("The frozen taste classifier has not passed the pilot gate")
        # Importing the cloud module may create private Modal volumes; do this only
        # after the explicit operator gate, never during plan/discover/review commands.
        from .cloud import RemoteGenerator

        runner = Runner(
            output,
            frozen,
            RemoteGenerator(frozen["model"]),
            FrozenScorer(environment_stash(), scorer["model_id"], scorer["version_id"]),
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
            run_id = frozen["sha256"][:24]
            file = output / "posttraining.json"
            if file.exists():
                raise ValueError(
                    "A training receipt already exists; inspect it before launching another GPU run"
                )
            result = modal.Function.from_name("stash-website-taste", "train").remote(
                frozen["model"], pairs, protocol.cloud_training_config(frozen), run_id
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
