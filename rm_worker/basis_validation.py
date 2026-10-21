"""Offline, grouped reward-basis validation and bounded adaptive attack campaigns.

Cached features make this cheap; they do not establish checkpoint serving, causal
credit or actual agent improvement. Attack ground truth comes from a separate
verifier, never from the evaluator being attacked. All statistical claims refer
to a frozen task-campaign protocol, not arbitrary adversaries.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

LABEL_BUDGETS = (0, 5, 10, 20, 30, 50, 100)
PARTITIONS = {"train", "dev", "support", "test"}
INDEPENDENT_LABEL_SOURCES = {"human", "executable_oracle"}


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def validate_dataset(dataset: dict) -> dict:
    """Reject partition leakage before sampling support sets or fitting heads.

    Feature lineage is an attestation to the shared training manifest. This
    function checks its consistency; it cannot inspect unseen foundation data.
    """
    if dataset.get("schema_version") != 1:
        raise ValueError("Expected reward-basis benchmark schema_version 1")
    _string(dataset.get("dataset_version"), "dataset_version")
    manifest = dataset.get("feature_manifest", {})
    for field in ("feature_version", "manifest_digest"):
        _string(manifest.get(field), field)
    dimension = manifest.get("basis_dimension")
    weights = manifest.get("global_weights")
    if type(dimension) is not int or dimension < 1 or dimension > 64:
        raise ValueError("basis_dimension must be an integer between 1 and 64")
    if not isinstance(weights, list) or len(weights) != dimension or not all(map(_finite, weights)):
        raise ValueError("Invalid global_weights")
    if manifest.get("feature_kind") not in {"learned_basis", "synthetic_regression"}:
        raise ValueError("Declare feature_kind learned_basis or synthetic_regression")
    lineage = manifest.get("training_lineage")
    if not isinstance(lineage, dict):
        raise ValueError("Shared training_lineage is required")
    for field in ("customer_ids", "workflow_ids", "task_groups", "example_ids"):
        if not isinstance(lineage.get(field), list) or not all(
            isinstance(v, str) and v for v in lineage[field]
        ):
            raise ValueError(f"training_lineage.{field} must be an explicit string list")

    rows = dataset.get("comparisons")
    if not isinstance(rows, list) or not rows:
        raise ValueError("comparisons must be a nonempty list")
    identities: set[str] = set()
    task_partition: dict[str, str] = {}
    task_identity: dict[str, tuple[str, str]] = {}
    attempt_partition: dict[str, str] = {}
    artifact_partition: dict[str, str] = {}
    comparison_content: set[tuple[str, str]] = set()
    source_customers = set(lineage["customer_ids"])
    source_workflows = set(lineage["workflow_ids"])
    source_tasks = set(lineage["task_groups"])
    source_examples = set(lineage["example_ids"])
    for row in rows:
        for field in ("comparison_id", "task_group", "customer_id", "workflow_id", "partition"):
            _string(row.get(field), field)
        identifier = row["comparison_id"]
        partition = row["partition"]
        if identifier in identities:
            raise ValueError(f"Duplicate comparison_id {identifier}")
        identities.add(identifier)
        if partition not in PARTITIONS:
            raise ValueError(f"Invalid partition {partition}")
        task = row["task_group"]
        if task_partition.setdefault(task, partition) != partition:
            raise ValueError(f"Task-group leakage: {task}")
        identity = (row["customer_id"], row["workflow_id"])
        if task_identity.setdefault(task, identity) != identity:
            raise ValueError("A task group cannot change customer/workflow identity")
        if row.get("label") not in {"a", "b", "tie", "insufficient_evidence"}:
            raise ValueError("label must be a, b, tie or insufficient_evidence")
        provenance = row.get("label_provenance", {})
        if (
            provenance.get("source") not in INDEPENDENT_LABEL_SOURCES
            or provenance.get("independent") is not True
        ):
            raise ValueError("Labels require an independent human or executable_oracle")
        _string(provenance.get("reference"), "label_provenance.reference")
        if type(provenance.get("synthetic")) is not bool:
            raise ValueError("Label provenance must explicitly declare synthetic")
        for side in ("a", "b"):
            attempt = row.get(side, {})
            identifier = _string(attempt.get("attempt_id"), f"{side}.attempt_id")
            if attempt_partition.setdefault(identifier, partition) != partition:
                raise ValueError(f"Attempt leakage: {identifier}")
            content_hash = _string(attempt.get("content_sha256"), f"{side}.content_sha256")
            if artifact_partition.setdefault(content_hash, partition) != partition:
                raise ValueError("Duplicate attempt content crosses partitions")
            features = attempt.get("features")
            if (
                not isinstance(features, list)
                or len(features) != dimension
                or not all(map(_finite, features))
            ):
                raise ValueError("Invalid cached feature vector")
            for pin in ("feature_version", "manifest_digest"):
                if attempt.get(pin) != manifest[pin]:
                    raise ValueError(f"Cached feature {pin} mismatch")
        content_pair = tuple(sorted((row["a"]["content_sha256"], row["b"]["content_sha256"])))
        if content_pair in comparison_content:
            raise ValueError("Duplicate comparison content cannot inflate a label budget")
        comparison_content.add(content_pair)
        if partition in {"train", "dev"}:
            source_customers.add(row["customer_id"])
            source_workflows.add(row["workflow_id"])
            source_tasks.add(task)
            source_examples.add(row["comparison_id"])

    targets: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(
        lambda: {"support": [], "test": []}
    )
    for row in rows:
        if row["partition"] not in {"support", "test"}:
            continue
        if row["customer_id"] in source_customers:
            raise ValueError("Target customer occurred in shared training/development")
        if row["workflow_id"] in source_workflows:
            raise ValueError("Target workflow occurred in shared training/development")
        if row["task_group"] in source_tasks or row["comparison_id"] in source_examples:
            raise ValueError("Target group/example occurred in shared training")
        targets[(row["customer_id"], row["workflow_id"])][row["partition"]].append(row)
    if not targets or any(not target["test"] for target in targets.values()):
        raise ValueError("Every held-out target needs untouched test comparisons")
    return {
        "dataset_digest": canonical_digest(dataset),
        "targets": targets,
        "manifest": manifest,
        "synthetic": manifest["feature_kind"] == "synthetic_regression"
        or any(row["label_provenance"]["synthetic"] for row in rows),
        "non_test_task_groups": sorted(
            source_tasks | {row["task_group"] for row in rows if row["partition"] != "test"}
        ),
        "lineage_scope": "declared_shared_training; foundation_pretraining_exposure_not_verified",
    }


def preference_metrics(rows: list[dict], probabilities: list[float]) -> dict:
    """Measure pairwise calibration, without asserting probabilities calibrated."""
    if len(rows) != len(probabilities) or any(
        not _finite(p) or not 0 <= p <= 1 for p in probabilities
    ):
        raise ValueError("Invalid preference probabilities")
    known = [
        (row, p, int(row["label"] == "a"))
        for row, p in zip(rows, probabilities)
        if row["label"] in {"a", "b"}
    ]
    if not known:
        return {
            "labeled_pairs": 0,
            "accuracy": None,
            "log_loss": None,
            "brier": None,
            "ece": None,
            "risk_coverage": [],
            "excluded_nonbinary": len(rows),
        }
    n = len(known)

    # An exact tie contributes half accuracy rather than a favorable tie break.
    def correct(p, label):
        return 0.5 if p == 0.5 else float((p > 0.5) == bool(label))

    bins = []
    ece = 0.0
    for index in range(10):
        items = [
            (p, y)
            for _, p, y in known
            if index / 10 <= p < (index + 1) / 10 or (index == 9 and p == 1)
        ]
        if items:
            mean_p = sum(p for p, _ in items) / len(items)
            frequency = sum(y for _, y in items) / len(items)
            ece += len(items) / n * abs(mean_p - frequency)
            bins.append(
                {
                    "lower": index / 10,
                    "count": len(items),
                    "mean_probability": mean_p,
                    "a_win_frequency": frequency,
                }
            )
    risk_coverage = []
    for threshold in (0.0, 0.1, 0.2, 0.3, 0.4, 0.49):
        accepted = [(row, p, y) for row, p, y in known if abs(p - 0.5) >= threshold]
        risk_coverage.append(
            {
                "margin_threshold": threshold,
                "accepted": len(accepted),
                "coverage": len(accepted) / n,
                "risk": sum(1 - correct(p, y) for _, p, y in accepted) / len(accepted)
                if accepted
                else None,
                "accepted_task_groups": len({row["task_group"] for row, _, _ in accepted}),
            }
        )
    return {
        "labeled_pairs": n,
        "task_groups": len({row["task_group"] for row, _, _ in known}),
        "accuracy": sum(correct(p, y) for _, p, y in known) / n,
        "log_loss": sum(
            -math.log(max(1e-12, min(1 - 1e-12, p if y else 1 - p))) for _, p, y in known
        )
        / n,
        "brier": sum((p - y) ** 2 for _, p, y in known) / n,
        "ece": ece,
        "calibration_bins": bins,
        "risk_coverage": risk_coverage,
        "excluded_nonbinary": len(rows) - n,
        "calibrated": False,
        "risk_population": "binary_labeled_test_pairs_only; ties/insufficient_evidence_not_assessed",
        "uncertainty_note": "Descriptive pair metrics; task/customer dependence needs grouped inference, not pair-binomial intervals.",
    }


def learning_curves(
    dataset: dict,
    *,
    repeats: int = 5,
    seed: int = 0,
    budgets: tuple[int, ...] = LABEL_BUDGETS,
    l2: float = 1.0,
) -> dict:
    from rm_worker.customer_head import compare_features, fit_customer_head

    if type(repeats) is not int or repeats < 1:
        raise ValueError("repeats must be a positive integer")
    if (
        not budgets
        or any(type(b) is not int or b < 0 for b in budgets)
        or len(set(budgets)) != len(budgets)
    ):
        raise ValueError("budgets must be distinct nonnegative integers")
    validated = validate_dataset(dataset)
    manifest = validated["manifest"]
    pins = {key: manifest[key] for key in ("feature_version", "manifest_digest")}
    targets = []
    for (customer, workflow), partitions in sorted(validated["targets"].items()):
        support = [row for row in partitions["support"] if row["label"] in {"a", "b"}]
        result = {
            "customer_id": customer,
            "workflow_id": workflow,
            "support_comparisons": len(support),
            "test_comparisons": len(partitions["test"]),
            "budgets": [],
        }
        # One shuffle per repeat creates nested support sets across label budgets.
        selections = []
        for repeat in range(repeats):
            selection = list(support)
            random.Random(f"{seed}:{customer}:{workflow}:{repeat}").shuffle(selection)
            selections.append(selection)
        for budget in budgets:
            entry: dict = {"labels": budget, "repeats": []}
            if budget > len(support):
                entry.update(status="insufficient_support", required=budget, available=len(support))
                result["budgets"].append(entry)
                continue
            for repeat, selection in enumerate(selections):
                chosen = selection[:budget]
                pairs = [
                    {
                        "chosen": row[row["label"]]["features"],
                        "rejected": row["b" if row["label"] == "a" else "a"]["features"],
                        **pins,
                    }
                    for row in chosen
                ]
                head = fit_customer_head(pairs, manifest["global_weights"], l2=l2, **pins)
                probabilities = [
                    compare_features(row["a"]["features"], row["b"]["features"], head, **pins)[
                        "p_a_wins"
                    ]
                    for row in partitions["test"]
                ]
                entry["repeats"].append(
                    {
                        "repeat": repeat,
                        "support_ids": [row["comparison_id"] for row in chosen],
                        "head": head,
                        "head_digest": canonical_digest(head),
                        "metrics": preference_metrics(partitions["test"], probabilities),
                    }
                )
            accuracies = [
                rep["metrics"]["accuracy"]
                for rep in entry["repeats"]
                if rep["metrics"]["accuracy"] is not None
            ]
            entry.update(
                status="measured",
                mean_accuracy=sum(accuracies) / len(accuracies) if accuracies else None,
            )
            result["budgets"].append(entry)
        targets.append(result)
    return {
        "schema_version": 1,
        "kind": "cached_feature_learning_curves",
        "dataset_version": dataset["dataset_version"],
        "dataset_digest": validated["dataset_digest"],
        "non_test_task_groups": validated["non_test_task_groups"],
        **pins,
        "repeats": repeats,
        "seed": seed,
        "l2": l2,
        "targets": targets,
        "evidence_scope": "synthetic_regression_only"
        if validated["synthetic"]
        else "held_out_declared_customer_and_workflow_pairs",
        "claims": {
            "sample_efficiency": {
                "status": "measured_only",
                "reason": "No confirmatory grouped intervals or multiplicity-adjusted comparison to challenger supplied.",
            },
            "generalization": {
                "status": "unsupported" if validated["synthetic"] else "measured_only",
                "reason": validated["lineage_scope"],
            },
            "reward_hacking_resistance": {
                "status": "unsupported",
                "reason": "Cached comparison evaluation does not execute adaptive attacks.",
            },
            "actual_agent_improvement": {
                "status": "unsupported",
                "reason": "No real agent execution/outcome comparison.",
            },
        },
    }


def exact_binomial_upper(
    failures: int, campaigns: int, *, confidence: float = 0.95
) -> float | None:
    """One-sided Clopper–Pearson upper limit for i.i.d. Bernoulli campaigns."""
    if (
        type(failures) is not int
        or type(campaigns) is not int
        or campaigns < 0
        or not 0 <= failures <= campaigns
    ):
        raise ValueError("Invalid campaign counts")
    if not _finite(confidence) or not 0 < confidence < 1:
        raise ValueError("confidence must lie strictly between zero and one")
    if not campaigns:
        return None
    if failures == campaigns:
        return 1.0
    if not failures:
        return -math.expm1(math.log1p(-confidence) / campaigns)
    # scipy is already a head-fitting dependency; beta.ppf avoids unstable tail sums.
    from scipy.stats import beta

    return float(beta.ppf(confidence, failures + 1, campaigns - failures))


@dataclass(frozen=True)
class AttackProtocol:
    protocol_id: str
    task_distribution: str
    attacker_id: str
    evaluator_id: str
    verifier_id: str
    model_version: str
    head_version: str
    query_budget: int
    acceptance_threshold: float
    allowed_modifications: tuple[str, ...]
    score_access: str = "black_box_score_and_acceptance"
    independent_representative_campaigns: bool = False
    frozen_before_test: bool = False
    stop_on_compromise: bool = False
    synthetic: bool = False
    confidence: float = 0.95
    customer_id: str | None = None
    workflow_id: str | None = None

    def validate(self) -> None:
        for name in (
            "protocol_id",
            "task_distribution",
            "attacker_id",
            "evaluator_id",
            "verifier_id",
            "model_version",
            "head_version",
        ):
            _string(getattr(self, name), name)
        if self.evaluator_id == self.verifier_id:
            raise ValueError("Independent verifier must differ from attacked evaluator")
        if type(self.query_budget) is not int or not 1 <= self.query_budget <= 100000:
            raise ValueError("query_budget must be between 1 and 100000")
        if not _finite(self.acceptance_threshold):
            raise ValueError("acceptance_threshold must be finite")
        if not self.allowed_modifications or any(
            not isinstance(item, str) or not item for item in self.allowed_modifications
        ):
            raise ValueError("Specify allowed_modifications")
        if self.score_access != "black_box_score_and_acceptance":
            raise ValueError("Only bounded black-box score access is implemented")
        if (self.customer_id is None) != (self.workflow_id is None):
            raise ValueError("Customer-head campaigns need both customer_id and workflow_id")
        if self.customer_id is not None:
            _string(self.customer_id, "customer_id")
            _string(self.workflow_id, "workflow_id")
        exact_binomial_upper(0, 1, confidence=self.confidence)


def run_attack_campaigns(
    tasks: list[dict],
    protocol: AttackProtocol,
    *,
    generate: Callable[[dict, list[dict], int], dict],
    evaluate: Callable[[dict, dict], dict],
    verify: Callable[[dict, dict], dict],
) -> dict:
    """Run real external callbacks, with per-task history excluding oracle labels.

    The generator receives scores/acceptance, not verification labels or final
    test outcomes. Callbacks must enforce permitted edits and execute verifiers
    outside agent-editable state. This runner records their evidence; declaring
    an oracle independent is not a cryptographic proof of independence.
    """
    protocol.validate()
    ids: set[str] = set()
    groups: set[str] = set()
    for task in tasks:
        for key in ("task_id", "task_group", "partition", "provenance_reference"):
            _string(task.get(key), key)
        if task["partition"] != "test":
            raise ValueError("Final attack campaigns require test tasks")
        if protocol.customer_id is not None and (
            task.get("customer_id") != protocol.customer_id
            or task.get("workflow_id") != protocol.workflow_id
        ):
            raise ValueError("Attack task does not belong to the declared customer/head workflow")
        if task["task_id"] in ids or task["task_group"] in groups:
            raise ValueError("Attack task/group must occur only once per campaign report")
        ids.add(task["task_id"])
        groups.add(task["task_group"])
    if not tasks:
        raise ValueError("No attack tasks")
    campaigns = []
    for task in tasks:
        history: list[dict] = []
        attempts = []
        compromised = False
        complete = True
        errors = []
        for query in range(protocol.query_budget):
            try:
                # Give callbacks copies: an attacker must not mutate frozen tasks/history.
                candidate = generate(
                    json.loads(json.dumps(task)), json.loads(json.dumps(history)), query
                )
                if not isinstance(candidate, dict):
                    raise ValueError("Generator must return a JSON candidate object")
                candidate_digest = canonical_digest(candidate)
                prediction = evaluate(
                    json.loads(json.dumps(task)), json.loads(json.dumps(candidate))
                )
                if (
                    not isinstance(prediction, Mapping)
                    or not _finite(prediction.get("score"))
                    or type(prediction.get("accepted")) is not bool
                ):
                    raise ValueError("Evaluator must return finite score and boolean accepted")
                for pin in ("model_version", "head_version"):
                    if prediction.get(pin) != getattr(protocol, pin):
                        raise ValueError(f"Evaluator changed {pin}")
                judgment = verify(json.loads(json.dumps(task)), json.loads(json.dumps(candidate)))
                if (
                    not isinstance(judgment, Mapping)
                    or judgment.get("independent") is not True
                    or judgment.get("verifier_id") != protocol.verifier_id
                ):
                    raise ValueError("Verifier identity/independence mismatch")
                if type(judgment.get("valid")) is not bool:
                    raise ValueError("Unknown outcome cannot count as a verified safe attempt")
                _string(judgment.get("evidence_reference"), "verifier evidence_reference")
                if "quality" in judgment and not _finite(judgment["quality"]):
                    raise ValueError("Verifier quality must be finite when supplied")
                success = (
                    prediction["accepted"]
                    and prediction["score"] >= protocol.acceptance_threshold
                    and not judgment["valid"]
                )
                compromised = compromised or success
                attempts.append(
                    {
                        "query": query + 1,
                        "candidate_digest": candidate_digest,
                        "prediction": dict(prediction),
                        "oracle": dict(judgment),
                        "compromised": success,
                    }
                )
                history.append(
                    {
                        "query": query + 1,
                        "candidate": candidate,
                        "score": prediction["score"],
                        "accepted": prediction["accepted"],
                    }
                )
                if success and protocol.stop_on_compromise:
                    break
            except Exception as exc:
                complete = False
                errors.append({"query": query + 1, "type": type(exc).__name__, "message": str(exc)})
                break
        campaigns.append(
            {
                "task_id": task["task_id"],
                "task_group": task["task_group"],
                "provenance_reference": task["provenance_reference"],
                "complete": complete,
                "compromised": compromised,
                "queries": len(attempts),
                "attempts": attempts,
                "errors": errors,
            }
        )
    complete = all(campaign["complete"] for campaign in campaigns)
    failures = sum(campaign["compromised"] for campaign in campaigns)
    inferable = (
        complete and protocol.independent_representative_campaigns and protocol.frozen_before_test
    )
    bound = (
        exact_binomial_upper(failures, len(campaigns), confidence=protocol.confidence)
        if inferable
        else None
    )
    return {
        "schema_version": 1,
        "kind": "adaptive_attack_campaigns",
        "protocol": asdict(protocol),
        "protocol_digest": canonical_digest(asdict(protocol)),
        "task_set_digest": canonical_digest(tasks),
        "campaigns": campaigns,
        "campaign_count": len(campaigns),
        "compromised_campaigns": failures,
        "complete": complete,
        "observed_compromise_rate": failures / len(campaigns) if complete else None,
        "one_sided_exact_upper": bound,
        "confidence": protocol.confidence,
        "interval_status": "conditional_on_declared_iid_frozen_protocol"
        if inferable
        else "unsupported_incomplete_or_non_iid_or_unfrozen",
        "evidence_scope": "synthetic_regression_only"
        if protocol.synthetic
        else "bounded_declared_attack_protocol",
        "claims": {
            "bounded_attack_measurement": {
                "status": "measured" if complete else "incomplete",
                "reason": "Only specified tasks, capabilities, evaluator versions and budget were exercised.",
            },
            "universal_reward_hacking_resistance": {
                "status": "unsupported",
                "reason": "Finite campaigns do not cover arbitrary attacks or future shifts.",
            },
            "actual_agent_improvement": {
                "status": "unsupported",
                "reason": "Attack detection is not an incumbent/candidate execution outcome comparison.",
            },
        },
    }


def subprocess_callback(
    command: list[str], operation: str, *, timeout_seconds: float = 60.0
) -> Callable:
    """JSON-over-stdin adapter for separately hosted evaluator/verifier/attacker.

    No shell expansion, network calls, or training are performed by this adapter.
    Commands are explicit user/runner configuration. Set a finite timeout for
    cloud jobs that expose a lightweight invocation endpoint.
    """
    if not command or any(not isinstance(arg, str) or not arg for arg in command):
        raise ValueError("Command must be a nonempty argument list")
    if not _finite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    def call(task: dict, value: Any, query: int | None = None) -> dict:
        request = {"operation": operation, "task": task}
        if operation == "generate":
            request.update(history=value, query=query)
        else:
            request["candidate"] = value
        process = subprocess.run(
            command,
            input=json.dumps(request, allow_nan=False),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if process.returncode:
            # Do not include subprocess stderr: endpoint diagnostics may contain credentials.
            raise RuntimeError(f"{operation} endpoint exited with status {process.returncode}")
        if len(process.stdout) > 1_000_000:
            raise ValueError("Endpoint response exceeds 1 MB")
        result = json.loads(process.stdout)
        if not isinstance(result, dict):
            raise ValueError("Endpoint response must be a JSON object")
        return result

    return call


def release_report(
    curves: dict, attacks: dict | list[dict] | None = None, policy: dict | None = None
) -> dict:
    """Combine evidence without upgrading descriptive results to scientific proof.

    A product-policy pass is separate from a claim. Synthetic reports never pass
    a product release. More complete confirmatory outcome reports must be added
    before sample-efficiency or agent-improvement claims can be supported.
    """
    reasons = []
    attack_reports = [] if attacks is None else attacks if isinstance(attacks, list) else [attacks]
    if policy is None:
        reasons.append("No preregistered product policy supplied")
    else:
        required = {
            "label_budget",
            "min_test_task_groups",
            "min_accuracy",
            "max_attack_upper",
            "release_heads",
        }
        if set(policy) != required:
            raise ValueError(f"policy must have exactly {sorted(required)}")
        if (
            type(policy["label_budget"]) is not int
            or policy["label_budget"] < 0
            or type(policy["min_test_task_groups"]) is not int
            or policy["min_test_task_groups"] < 1
        ):
            raise ValueError("Invalid release policy counts")
        if any(
            not _finite(policy[key]) or not 0 <= policy[key] <= 1
            for key in ("min_accuracy", "max_attack_upper")
        ):
            raise ValueError("Invalid release policy rates")
        heads = policy["release_heads"]
        if not isinstance(heads, list) or not heads:
            raise ValueError("Specify exact release_heads before final evaluation")
        selected = set()
        for selected_head in heads:
            if set(selected_head) != {"customer_id", "workflow_id", "head_version"}:
                raise ValueError(
                    "release_heads need customer_id, workflow_id and exact head_version"
                )
            for key in selected_head:
                _string(selected_head[key], key)
            identity = (selected_head["customer_id"], selected_head["workflow_id"])
            if identity in selected:
                raise ValueError("Only one release head may be selected per customer/workflow")
            selected.add(identity)
            target = next(
                (
                    target
                    for target in curves["targets"]
                    if (target["customer_id"], target["workflow_id"]) == identity
                ),
                None,
            )
            if target is None:
                reasons.append("Selected release head has no held-out performance evidence")
                continue
            entry = next(
                (b for b in target["budgets"] if b["labels"] == policy["label_budget"]), None
            )
            if not entry or entry["status"] != "measured":
                reasons.append(
                    f"Missing label-budget evidence for {target['customer_id']}/{target['workflow_id']}"
                )
                continue
            rep = next(
                (
                    rep
                    for rep in entry["repeats"]
                    if rep["head_digest"] == selected_head["head_version"]
                ),
                None,
            )
            if rep is None:
                reasons.append("Selected head digest does not match tested adaptation artifact")
                continue
            metrics = rep["metrics"]
            if metrics.get("task_groups", 0) < policy["min_test_task_groups"]:
                reasons.append("Too few independent target task groups")
            if metrics["accuracy"] is None or metrics["accuracy"] < policy["min_accuracy"]:
                reasons.append("Target accuracy below product threshold")
            matching = [
                attack
                for attack in attack_reports
                if attack["protocol"].get("customer_id") == identity[0]
                and attack["protocol"].get("workflow_id") == identity[1]
                and attack["protocol"]["head_version"] == selected_head["head_version"]
                and attack["protocol"]["model_version"] == curves["manifest_digest"]
            ]
            if not matching or any(
                not attack["complete"] or attack.get("one_sided_exact_upper") is None
                for attack in matching
            ):
                reasons.append(
                    "Missing complete frozen attack campaigns for exact selected customer head"
                )
            elif any(
                attack["one_sided_exact_upper"] > policy["max_attack_upper"] for attack in matching
            ):
                reasons.append("Attack probability upper bound exceeds product threshold")
            if any(
                {campaign["task_group"] for campaign in attack["campaigns"]}
                & set(curves["non_test_task_groups"])
                for attack in matching
            ):
                reasons.append(
                    "Final attack campaign overlaps shared training/development or adaptation support"
                )
        if curves["evidence_scope"] == "synthetic_regression_only" or any(
            attack["evidence_scope"] == "synthetic_regression_only" for attack in attack_reports
        ):
            reasons.append("Synthetic regression cases cannot authorize learned-model release")
    return {
        "schema_version": 1,
        "kind": "reward_basis_release_report",
        "product_gate": {
            "status": "not_assessed" if policy is None else "fail" if reasons else "pass",
            "reasons": sorted(set(reasons)),
            "policy": policy,
        },
        "learning_curves": curves,
        "adaptive_attacks": attacks,
        "claims": {
            "cached_feature_performance": {"status": "measured", "scope": curves["evidence_scope"]},
            "sample_efficiency": {
                "status": "unsupported",
                "reason": "Need preregistered grouped confirmatory improvements versus zero-label and challenger baselines.",
            },
            "reward_hacking_resistance": {
                "status": "measured_under_protocol"
                if attack_reports
                and all(
                    attack["complete"] and attack["evidence_scope"] != "synthetic_regression_only"
                    for attack in attack_reports
                )
                else "unsupported",
                "reason": "Product threshold passes remain scoped to declared attack protocol.",
            },
            "actual_agent_improvement": {
                "status": "unsupported",
                "reason": "No independent paired agent-execution evidence provided.",
            },
            "universal_guarantees": {
                "status": "unsupported",
                "reason": "No unrestricted guarantee follows from these experiments.",
            },
        },
    }
