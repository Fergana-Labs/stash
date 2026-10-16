"""Operate the evidence -> frozen multimodal activations -> linear probe path.

Cloud-only extraction/fitting, immutable inputs/weights, no agent verdict features.
Exploratory scores never bypass the separate optimization release gate.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from . import activation_head, evidence
from .activation_spec import SPEC
from .corpus import digest
from .gallery import read_json, read_jsonl

REPRESENTATION = digest(json.dumps(SPEC, sort_keys=True))


def dataset_at(output):
    data = read_json(output / "evidence.json", limit=64_000_000)
    original = {k: v for k, v in data.items() if k != "sha256"}
    if data.get("sha256") != digest(json.dumps(original, sort_keys=True)):
        raise ValueError("Evidence dataset changed after freezing")
    seen, groups = {}, {}
    for row in data["examples"]:
        for key, table in (
            (row["input"]["render"]["sha256"], seen),
            (row["supervision"]["group"], groups),
        ):
            partition = row["supervision"]["partition"]
            if key in table and table[key] != partition:
                raise ValueError("Related evidence crosses dataset splits")
            table[key] = partition
    return data


def reserve(output, kind):
    """Conservative compute allocation within the existing shared $25 pilot.

    Counts failed/started requests too. This is a request/time cap, not an API
    billing cap. $0.001/s bounds this L4+CPU configuration conservatively.
    """
    ledger = output / "probe-cloud-ledger.jsonl"
    with ledger.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        rows = [json.loads(line) for line in stream if line.strip()]
        if sum(r["kind"] == kind for r in rows) >= (3 if kind == "extract" else 2):
            raise ValueError("Probe cloud call budget exhausted; inspect existing receipts")
        allocation = 0.93 if kind == "extract" else 0.05
        if sum(r["reserved_usd"] for r in rows) + allocation > 3:
            raise ValueError("The probe's $3 allocation within the shared $25 budget is exhausted")
        stream.write(
            json.dumps(
                {
                    "kind": kind,
                    "reserved_usd": allocation,
                    "at": datetime.now(UTC).isoformat(),
                    "workspace": "fergana-labs",
                }
            )
            + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())


def feature_path(output, identity):
    return output / "activations" / (digest(REPRESENTATION + identity) + ".json")


def extract_features(output, packets, remote=None, *, budget_output=None):
    cached, missing = {}, {}
    for row in packets:
        # Cached activations still require the same canonical packet and pixels.
        evidence.model_payload(row)
        record = read_json(feature_path(output, row["id"]))
        if record:
            if record.get("spec") != SPEC or record.get("id") != row["id"]:
                raise ValueError("Cached activations use a different representation")
            cached[row["id"]] = record
        else:
            missing[row["id"]] = row
    if missing:
        if len(missing) > 32:
            raise ValueError("Pilot permits at most 32 uncached packets per cloud call")
        payloads = [evidence.model_payload(row) for row in missing.values()]
        reserve(budget_output or output, "extract")
        if remote is None:
            import modal

            remote = modal.Function.from_name("stash-website-taste-probe", "extract").remote
        result = remote(payloads, SPEC)
        if result.get("spec") != SPEC or result.get("backbone_frozen") is not True:
            raise ValueError("Cloud extractor changed representation or unfroze the backbone")
        features = result["features"]
        if {f["id"] for f in features} != set(missing) or len(features) != len(missing):
            raise ValueError("Cloud feature receipts do not match requested evidence")
        for record in features:
            if (
                record.get("spec") != SPEC
                or record.get("generated_tokens") != 0
                or record.get("trainable_backbone_parameters") != 0
                or record["pixel_sha256"] != missing[record["id"]]["input"]["render"]["sha256"]
            ):
                raise ValueError("Invalid frozen-forward receipt")
            path = feature_path(output, record["id"])
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(record))
            cached[record["id"]] = record
        receipt_dir = output / "extraction-receipts"
        receipt_dir.mkdir(exist_ok=True)
        receipt = {
            "ids": list(missing),
            "gpu_seconds": result["gpu_seconds"],
            "spec": SPEC,
            "backbone_frozen": True,
        }
        (receipt_dir / (digest(json.dumps(receipt, sort_keys=True)) + ".json")).write_text(
            json.dumps(receipt, indent=2)
        )
    return [cached[row["id"]] for row in packets]


def fit_probe(output, remote=None, *, budget_output=None):
    dataset = dataset_at(output)
    file = output / "activation-probe.json"
    if file.exists():
        return load_probe(output)
    rows = []
    for value in dataset["examples"]:
        record = read_json(feature_path(output, value["id"]))
        if record.get("spec") != SPEC or record.get("id") != value["id"]:
            raise ValueError("Extract all frozen evidence packets before fitting")
        rows.append(
            {
                "id": value["id"],
                "activation": record["activation"],
                "label": value["supervision"]["label"],
                "partition": value["supervision"]["partition"],
            }
        )
    reserve(budget_output or output, "fit")
    if remote is None:
        import modal

        remote = modal.Function.from_name("stash-website-taste-probe", "fit").remote
    result = remote(rows)
    expected = [r["id"] for r in rows if r["partition"] == "train"]
    if result["head"]["train_ids"] != expected:
        raise ValueError("Head was fitted with the wrong training rows")
    record = {
        "kind": "frozen-multimodal-activation-probe",
        "spec": SPEC,
        "representation": REPRESENTATION,
        "dataset": dataset["sha256"],
        "head": result["head"],
        "metrics": result["metrics"],
        "release_gate": activation_head.release_gate(dataset, result["metrics"]),
        "label_policy": dataset.get("label_policy"),
        "heldout_status": dataset["heldout_status"],
        "agent_role": "Evidence curation and audit only. Agent verdicts are not probe inputs or features.",
        "limitations": [
            "Automatic label interpretations have not been human-reviewed.",
            "Existing teacher-test examples were already examined in an earlier pilot; this is not independent human validation.",
            "Positive reference images and negative generated interfaces may confound style with evidence provenance.",
            "History packets select bounded public spans before the target feedback; they do not claim complete long-session coverage.",
            "Historical screenshots mostly lack their contemporaneous source HTML; missing artifacts are explicit.",
            "The sigmoid readout is uncalibrated and is not a probability of human approval.",
        ],
    }
    record["version"] = digest(json.dumps(record, sort_keys=True))
    file.write_text(json.dumps(record, indent=2))
    return record


def load_probe(output):
    record = read_json(output / "activation-probe.json")
    if not record or record.get("version") != digest(
        json.dumps({k: v for k, v in record.items() if k != "version"}, sort_keys=True)
    ):
        raise ValueError("Probe artifact is missing or its version hash changed")
    if (
        record.get("spec") != SPEC
        or record.get("representation") != REPRESENTATION
        or record.get("dataset") != dataset_at(output)["sha256"]
    ):
        raise ValueError("Probe representation or evidence identity changed")
    return record


class ProbeScorer:
    def __init__(self, output, *, exploratory=False, remote=None, budget_output=None):
        self.output, self.remote = output, remote
        self.budget_output = budget_output
        self.probe = load_probe(output)
        audit = read_json(output / "probe-audit.json")
        if (
            not exploratory
            and audit.get("version") == self.probe["version"]
            and audit.get("human_failures")
        ):
            raise ValueError(
                "Probe fails a confirmed human counterexample; optimization remains stopped"
            )
        if not exploratory and not self.probe["release_gate"]["passed"]:
            raise ValueError(
                "Activation probe has not passed the human-validation release gate; optimization remains stopped"
            )
        self.identity = {
            "kind": self.probe["kind"],
            "version": self.probe["version"],
            "representation": REPRESENTATION,
            "dataset": self.probe["dataset"],
        }

    def score_packet(self, value):
        feature = extract_features(
            self.output, [value], remote=self.remote, budget_output=self.budget_output
        )[0]
        return {
            **activation_head.predict(self.probe["head"], feature["activation"]),
            "reward": self.identity,
            "input_id": value["id"],
            "generated_tokens": 0,
        }

    def score_run(self, task, messages, generation, html, png):
        root, identity = html.parents[2], html.parent.name
        value = evidence.from_trial(root, identity)
        return self.score_packet(value)


def score_saved(output, source, remote=None):
    packets = []
    for trial in read_jsonl(source / "trials.jsonl"):
        directory = source / "artifacts" / trial["id"]
        if not read_json(directory / "receipt.json").get("valid"):
            continue
        value = evidence.from_trial(source, trial["id"])
        packets.append({**value, "trial_id": trial["id"], "task": trial["task"]})
    extract_features(output, packets, remote=remote)
    scorer = ProbeScorer(output, exploratory=True, remote=remote)
    predictions = []
    human = {r["trial_id"]: r.get("label") for r in read_jsonl(source / "human-feedback.jsonl")}
    for value in packets:
        result = scorer.score_packet(value)
        agent = read_json(source / "agent-judge" / value["trial_id"] / "latest.json")
        record = {
            "trial_id": value["trial_id"],
            "task": value["task"],
            "prediction": result,
            "inputs": value["input"],
            "audit": {
                "human_label": human.get(value["trial_id"]),
                "agent_label": (agent.get("verdict") or {}).get("label"),
                "used_for_fitting": False,
            },
        }
        path = output / "probe-predictions" / (value["trial_id"] + ".json")
        path.parent.mkdir(exist_ok=True)
        if path.exists() and read_json(path) != record:
            raise ValueError("Saved probe prediction changed; use a separate version directory")
        path.write_text(json.dumps(record, indent=2))
        predictions.append(record)
    audit = {
        "version": scorer.probe["version"],
        "human_failures": [
            r["trial_id"]
            for r in predictions
            if r["audit"]["human_label"] and r["audit"]["human_label"] != r["prediction"]["label"]
        ],
        "agent_disagreements": [
            r["trial_id"]
            for r in predictions
            if r["audit"]["agent_label"] and r["audit"]["agent_label"] != r["prediction"]["label"]
        ],
        "policy": "Confirmed human counterexamples block optimization. Agent disagreements flag investigation; agent verdicts do not replace probe scores or become labels automatically.",
        "used_for_fitting": False,
    }
    (output / "probe-audit.json").write_text(json.dumps(audit, indent=2))
    return predictions


def summary(output):
    if not output:
        return {"status": "not-configured"}
    dataset = read_json(output / "evidence.json", limit=64_000_000)
    record = read_json(output / "activation-probe.json")
    if not dataset:
        return {"status": "not-prepared"}
    counts = {
        part: dict(
            Counter(
                r["supervision"]["label"]
                for r in dataset["examples"]
                if r["supervision"]["partition"] == part
            )
        )
        for part in ("train", "dev", "test")
    }
    return {
        "status": "fitted" if record else "prepared",
        "kind": "frozen-multimodal-activation-probe",
        "version": record.get("version"),
        "spec": SPEC,
        "dimensions": record.get("head", {}).get("dimensions"),
        "trainable_parameters": len(record.get("head", {}).get("weights", []))
        + (1 if record else 0),
        "backbone_frozen": True,
        "agent_role": record.get("agent_role"),
        "label_counts": counts,
        "metrics": record.get("metrics"),
        "release_gate": record.get("release_gate"),
        "audit": read_json(output / "probe-audit.json"),
        "visual_diagnostic": read_json(output / "probe-diagnostics" / "visual-ablation.json"),
        "limitations": record.get("limitations", []),
        "scores": [read_json(p) for p in sorted((output / "probe-predictions").glob("*.json"))],
        "evidence_coverage": {
            "examples": len(dataset["examples"]),
            "with_trace": sum(bool(r["input"]["trace"]["steps"]) for r in dataset["examples"]),
            "references": sum(
                r["supervision"]["provenance"]["reference_image"] for r in dataset["examples"]
            ),
        },
        "examples": [
            {
                "id": row["id"],
                "label": row["supervision"]["label"],
                "partition": row["supervision"]["partition"],
                "quote": row["supervision"].get("quote"),
                "label_source": row["supervision"].get("label_source"),
                "human_reviewed": row["supervision"].get("human_reviewed"),
                "reference": row["supervision"]["provenance"]["reference_image"],
                "trace_steps": len(row["input"]["trace"]["steps"]),
                "image": "/probe-images/" + row["id"] + ".png",
            }
            for row in dataset["examples"]
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "extract", "fit", "score-saved", "status"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--allow-cloud", action="store_true")
    parser.add_argument(
        "--fresh-human-holdout",
        action="store_true",
        help="Attest a genuinely new human-reviewed holdout; rejects unreviewed or already-fitted source experiments",
    )
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.command == "prepare":
        if not args.source or not args.history:
            parser.error("prepare requires --source and --history")
        value = evidence.prepare(
            args.source, args.history, args.output, fresh_human_holdout=args.fresh_human_holdout
        )
        print(json.dumps({"dataset": value["sha256"], "examples": len(value["examples"])}))
        return
    if args.command == "status":
        print(json.dumps(summary(args.output)))
        return
    if not args.allow_cloud or os.environ.get("MODAL_PROFILE") != "fergana-labs":
        parser.error("Use --allow-cloud with the authorized MODAL_PROFILE=fergana-labs workspace")
    if args.command == "extract":
        values = extract_features(args.output, dataset_at(args.output)["examples"])
        print(json.dumps({"activations": len(values), "dimensions": values[0]["dimensions"]}))
    elif args.command == "fit":
        value = fit_probe(args.output)
        print(
            json.dumps(
                {
                    "version": value["version"],
                    "metrics": value["metrics"],
                    "release_gate": value["release_gate"],
                }
            )
        )
    elif args.command == "score-saved":
        if not args.source:
            parser.error("score-saved requires --source")
        values = score_saved(args.output, args.source)
        print(
            json.dumps(
                [{k: value[k] for k in ("trial_id", "prediction", "audit")} for value in values]
            )
        )


if __name__ == "__main__":
    main()
