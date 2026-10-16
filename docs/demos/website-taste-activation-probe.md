# Frozen-model activation taste grader

The grader is a frozen vision-language model plus a personal linear readout.
Agents help interpret source feedback and investigate failures. Their verdicts
are excluded from the model input and never substituted for the readout.

```text
Training evidence + preference labels
              ↓
Frozen Qwen2.5-VL-3B activations → learned linear head

New request + recorded trace + available source + rendered screenshot
              ↓
Same frozen backbone → same frozen personal head → taste readout
                                                      ↓
                                         independent human/agent audits
```

## Evidence and representation

`evidence.py` freezes source-bound packets from recovered Codex history. It
selects the first public request and a bounded tail of public messages/tool
records before the target feedback. Target criticism and future messages are
excluded. Omitted/clipped spans are explicit; this does not promise complete
long-session coverage. Missing source remains missing. Reference images retain
their provenance rather than being described as approved agent outputs.

Labels, feedback quotes, teacher receipts, partitions, file paths, and agent
verdicts stay outside the model payload. Recognized credentials and embedded
image strings are redacted from selected text. Images reach the vision model
directly, without Claude-generated descriptions. Generated-trial packets include
the actual request/response and matching HTML, excluding candidate skill text.

The [Qwen2.5-VL-3B-Instruct backbone](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct)
is pinned to revision `66285546d2b821cf421d4f5eb2576359d3770cd3`. The processor,
resolution caps, fixed assessment prompt, hidden-state index `-5`, and last-query-
token pooling are frozen in `activation_spec.py`. Extraction uses `eval()`,
`requires_grad_(False)`, and an inference-only multimodal forward pass, bypassing
vocabulary logits. It generates no tokens. Oversized context fails explicitly.
See the [official model API](https://huggingface.co/docs/transformers/model_doc/qwen2_5_vl).

The class-balanced L2 logistic head fits 2,048 coefficients and one bias using
training rows only. Normalization, training-only centering, and fixed ridge
strength are explicit. Its sigmoid readout is **uncalibrated**, not probability
of human approval. Evidence/model/head hashes pin every score and reward run.

## Operate and inspect

All pretrained-model loading and real head fitting run on Modal. Laptop execution
fails before importing model libraries. Tiny synthetic-vector tests run locally.

```sh
python -m scripts.website_taste.probe_pipeline prepare \
  --source /private/tmp/website-taste-auto \
  --history /private/tmp/website-taste --output /private/tmp/website-taste-probe
MODAL_PROFILE=fergana-labs modal deploy scripts/website_taste/probe_cloud.py
MODAL_PROFILE=fergana-labs python -m scripts.website_taste.probe_pipeline extract \
  --output /private/tmp/website-taste-probe --allow-cloud
MODAL_PROFILE=fergana-labs python -m scripts.website_taste.probe_pipeline fit \
  --output /private/tmp/website-taste-probe --allow-cloud
MODAL_PROFILE=fergana-labs python -m scripts.website_taste.probe_pipeline score-saved \
  --output /private/tmp/website-taste-probe --source /private/tmp/website-taste-auto --allow-cloud
python -m scripts.website_taste.gallery --output /private/tmp/website-taste-auto \
  --probe-output /private/tmp/website-taste-probe --port 3458
```

Open `http://localhost:3458/?view=probe`. **Grader** shows actual scores, exact
input packets, frozen weights, metrics, and label provenance. **Investigator**
shows separate agent audits and the old invalidated classifier. The loopback-only
server exposes known, hash-verified images and allowlisted JSON, never arbitrary
paths. Private experiment outputs are excluded from Git and public deployments.

Within the shared approved $25 pilot, this operator reserves a conservative $3
allowance: at most three L4 extraction calls (900-second timeouts, one container,
30-second idle window, at most 32 packets each) and two short CPU fitting calls.
A locked durable ledger counts failed/started calls. These are request/time
limits, not a provider billing cap. Billing can lag; new folders do not authorize
additional spending. No local pretrained model is loaded.

## Observed first run

Real cloud extraction processed 21 examples, including 14 with public trace
spans and three reference images. It returned 2,048-dimensional vectors, zero
generated tokens, and zero trainable backbone parameters. The head fitted 14
training rows and then scored five saved Qwen designs.

| Check | Result |
| --- | --- |
| Development agreement | 1/3 |
| Reused teacher checks | 2/4 |
| Rejected monitoring dashboard | Incorrectly liked; readout 0.515 |
| Independent audit | Human and agent both disagree with that probe prediction |
| Optimization | Blocked |

This is an executed pipeline and a failed first grader. It does not establish
reliable taste judgment. The tiny automatically interpreted dataset, positive
references versus negative generated interfaces, missing source, and differing
trace distributions are limitations. Do not repeatedly tune on the old checks.

A separately labeled synthetic diagnostic held text fixed and swapped only the
screenshot. Activations changed, confirming that pixels reach the representation;
the readout moved from 0.5146 to 0.5131. With the original screenshot but trace/source
withheld, it became 0.5003. These single-case input-condition checks do not establish
taste accuracy. They did not enter fitting, change the frozen head, or become real
trial results. Their receipt is `probe-diagnostics/visual-ablation.json`.

## Validation and independent optimization

Saved-design audits join human/agent judgments **after** prediction. Confirmed
human counterexamples block optimization; agent disagreements flag investigation
without overwriting rewards or creating human labels. `probe-audit.json` binds
the audit to its probe version.

Release requires explicitly human-reviewed labels, a fresh human holdout, both
classes represented with at least 50% recall, at least four development examples
(two per class), six test examples, and at least 75% agreement on each partition.
Preparing a genuinely new reviewed source accepts `--fresh-human-holdout` as an
operator attestation, rejecting automatic or already-fitted source folders. It
cannot prove nobody saw those images elsewhere. Automatic data stays exploratory.

After release, select `--probe-output` for `optimize`, `sample-dpo`, `train-dpo`,
or `evaluate` in a fresh generation directory. The runner passes actual responses
and artifacts to the probe and refuses changed rewards in one run. Pair files,
training configs, and adapter IDs bind the frozen reward and exact pair contents.
Deploy updated `cloud.py` before later generator training.

GEPA varies instructions with fixed generator weights. Weight refinement varies
generator weights with the original baseline skill. Neither uses the other's
result, and both use the same released grader. Neither optimization branch ran
in this probe pilot.
