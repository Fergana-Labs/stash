"""Frozen encoder inference for a versioned, learned low-rank reward basis.

Only cloud workers import this module. Backend head fitting uses cached NumPy
features and the JSON manifest, and must not import torch or this module.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification

from rm_worker.basis_manifest import manifest_digest as manifest_digest
from rm_worker.basis_manifest import validate_manifest
from rm_worker.scoring import load_tokenizer, pick_device, precision_context, tokenize

EVALUATOR_KIND = "shared_basis_v1"
FEATURE_EXTRACTOR = "classifier_last_nonpadding_hidden_v2"


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_sha256(directory: Path) -> str:
    """Hash actual saved weights, config and tokenizer, without loading them."""
    digest = hashlib.sha256()
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    if not files:
        raise ValueError("Frozen encoder artifact is empty")
    for path in files:
        relative = path.relative_to(directory).as_posix()
        digest.update(canonical_json([relative, file_sha256(path)]))
    return digest.hexdigest()


def feature_version(encoder_hash: str, parameters_hash: str, input_contract: dict) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "encoder_sha256": encoder_hash,
                "parameters_sha256": parameters_hash,
                "input_contract": input_contract,
                "feature_extractor": input_contract.get("feature_extractor", FEATURE_EXTRACTOR),
            }
        )
    ).hexdigest()


@torch.no_grad()
def linear_pretrained_head(model) -> dict:
    """Only map known decoder classifiers with a single linear last-token head.

    BERT-style classifiers apply additional pooling/nonlinear transforms, so
    accepting any attribute named ``classifier`` would silently change scores.
    Unknown architectures fail closed; smoke tests may explicitly stay unanchored.
    """
    if model.config.model_type not in {"qwen3", "qwen2", "llama", "mistral"}:
        raise ValueError("Pretrained anchor requires a supported decoder sequence classifier")
    head = getattr(model, "score", None)
    if (
        not isinstance(head, torch.nn.Linear)
        or head.out_features != 1
        or head.in_features != model.config.hidden_size
    ):
        raise ValueError("Pretrained anchor requires one linear scalar score head")
    weights = head.weight[0].detach().float().cpu().numpy().copy()
    bias = float(head.bias[0].detach().float().cpu()) if head.bias is not None else 0.0
    if not np.isfinite(weights).all() or not np.isfinite(bias) or not np.any(weights):
        raise ValueError("Invalid pretrained scalar head")
    return {
        "weights": weights,
        "bias": bias,
        "head_name": "score",
        "model_type": model.config.model_type,
    }


@torch.no_grad()
def encoder_features(
    model,
    tokenizer,
    texts,
    device,
    batch_size=4,
    on_progress=None,
    feature_extractor=FEATURE_EXTRACTOR,
):
    """Extract last nonpadding hidden states with the encoder always frozen/eval.

    The extractor is explicit and identical during fitting and serving. It
    supports both left and right padding instead of indexing attention.sum()-1.
    """
    if batch_size < 1:
        raise ValueError("Feature batch size must be positive")
    model.eval()
    rows = []
    for start in range(0, len(texts), batch_size):
        batch = tokenize(tokenizer, texts[start : start + batch_size], device)
        with precision_context(device, model):
            output = model.base_model(**batch, return_dict=True)
        hidden = output.last_hidden_state
        mask = batch["attention_mask"].bool()
        if feature_extractor == FEATURE_EXTRACTOR and model.config.model_type in {
            "qwen3",
            "qwen2",
            "llama",
            "mistral",
        }:
            # Match the pretrained classifier's pooling, which excludes pad IDs
            # even when the pad token also appears within an attended sequence.
            pad_id = model.config.pad_token_id
            if pad_id is not None:
                mask = mask & batch["input_ids"].ne(pad_id)
        elif feature_extractor not in {FEATURE_EXTRACTOR, "last_nonpadding_hidden_v1"}:
            raise ValueError("Unsupported reward basis feature extractor")
        if not mask.any(dim=1).all():
            raise ValueError("Cannot extract features from an empty token sequence")
        positions = torch.arange(mask.shape[1], device=device).expand_as(mask)
        last = positions.masked_fill(~mask, -1).max(dim=1).values
        features = hidden[torch.arange(len(last), device=device), last]
        values = features.float().cpu().numpy()
        if not np.isfinite(values).all():
            raise ValueError("Frozen encoder returned non-finite features")
        rows.append(values)
        if on_progress:
            on_progress(min(start + batch_size, len(texts)))
    if not rows:
        return np.empty((0, model.config.hidden_size), dtype=np.float32)
    return np.concatenate(rows)


class BasisRewardModel:
    """Load immutable encoder/basis artifacts; produce cached features or scores."""

    def __init__(self, model_dir: str | Path, batch_size: int = 4):
        directory = Path(model_dir)
        self.manifest = json.loads((directory / "basis_manifest.json").read_text())
        manifest = validate_manifest(self.manifest)
        encoder_hash = directory_sha256(directory / "encoder")
        parameters_hash = file_sha256(directory / "basis_parameters.npz")
        expected_version = feature_version(
            encoder_hash, parameters_hash, manifest["input_contract"]
        )
        if (
            encoder_hash != manifest["encoder"]["artifact_sha256"]
            or parameters_hash != manifest["parameters_sha256"]
            or expected_version != manifest["feature_version"]
        ):
            raise ValueError("Frozen encoder or learned basis artifact does not match its version")
        with np.load(directory / "basis_parameters.npz", allow_pickle=False) as parameters:
            self.projection = parameters["projection"].astype(np.float32)
            self.mean = parameters["mean"].astype(np.float32)
            self.scale = parameters["scale"].astype(np.float32)
            self.offsets = (
                parameters["offsets"].astype(np.float32)
                if "offsets" in parameters
                else np.zeros(manifest["basis_dimension"], dtype=np.float32)
            )
        dimension = manifest["basis_dimension"]
        self.default_weights = np.asarray(manifest["global_head"]["weights"], dtype=np.float32)
        if (
            self.projection.ndim != 2
            or self.projection.shape[0] != dimension
            or self.mean.shape != (self.projection.shape[1],)
            or self.scale.shape != self.mean.shape
            or self.default_weights.shape != (dimension,)
            or self.offsets.shape != (dimension,)
            or not all(
                np.isfinite(array).all()
                for array in (
                    self.projection,
                    self.mean,
                    self.scale,
                    self.default_weights,
                    self.offsets,
                )
            )
            or np.any(self.scale <= 0)
        ):
            raise ValueError("Invalid reward basis parameters")
        self.device = pick_device()
        self.batch_size = batch_size
        self.tokenizer = load_tokenizer(directory / "encoder", local_files_only=True)
        self.input_version = manifest["input_contract"]["input_version"]
        self.rubric = manifest["input_contract"]["rubric"]
        if (
            self.tokenizer.model_max_length != manifest["input_contract"]["max_length"]
            or self.tokenizer.init_kwargs.get("stash_input_version", 1) != self.input_version
            or self.tokenizer.init_kwargs.get("stash_rubric", []) != self.rubric
        ):
            raise ValueError("Saved tokenizer does not match reward basis input contract")
        self.model = AutoModelForSequenceClassification.from_pretrained(
            directory / "encoder", local_files_only=True, dtype="auto"
        ).to(self.device)
        self.model.requires_grad_(False)
        self.model.eval()

    def features(self, texts: list[str], *, on_progress=None) -> list[list[float]]:
        embeddings = encoder_features(
            self.model,
            self.tokenizer,
            texts,
            self.device,
            self.batch_size,
            on_progress,
            feature_extractor=self.manifest["input_contract"]["feature_extractor"],
        )
        if embeddings.shape[1] != self.projection.shape[1]:
            raise ValueError("Encoder embedding dimension does not match learned projection")
        values = ((embeddings - self.mean) / self.scale) @ self.projection.T + self.offsets
        if not np.isfinite(values).all():
            raise ValueError("Reward basis returned non-finite features")
        return values.tolist()

    def score(self, texts: list[str], *, on_progress=None, head: dict | None = None) -> list[float]:
        weights = self.default_weights
        if head is not None:
            if (
                head.get("feature_version") != self.manifest["feature_version"]
                or head.get("manifest_digest") != self.manifest["manifest_digest"]
            ):
                raise ValueError("Customer head belongs to a different shared reward basis")
            global_weights = np.asarray(head.get("global_weights"), dtype=np.float32)
            residual = np.asarray(head.get("residual_weights"), dtype=np.float32)
            if (
                global_weights.shape != weights.shape
                or residual.shape != weights.shape
                or not np.array_equal(global_weights, weights)
                or not np.isfinite(residual).all()
            ):
                raise ValueError("Invalid pinned customer head weights")
            weights = weights + residual
        values = np.asarray(self.features(texts, on_progress=on_progress), dtype=np.float32)
        if not len(texts):
            return []
        return (values @ weights).tolist()
