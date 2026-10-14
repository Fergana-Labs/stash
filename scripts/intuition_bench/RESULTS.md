# Intuition benchmark

Accuracy on a fixed held-out test set per task, with 95% Wilson intervals. Every arm sees the same test items; labeled examples come from a separate pool.

| Task | Kind | Test n | Jev zero-shot | Claude, no examples | Claude + 8 examples | **Intuition, 8 labels** | Claude + 32 examples | **Intuition, 32 labels** |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Support reply review | 3-way quality call on short text | 20 | 95% <sub>[76%–99%]</sub> | 95% <sub>[76%–99%]</sub> | 90% <sub>[70%–97%]</sub> | 95% <sub>[76%–99%]</sub> | 100% <sub>[84%–100%]</sub> | 95% <sub>[76%–99%]</sub> |
| Web agent success (AgentRewardBench) | binary verification of long agent trajectories | 60 | 75% <sub>[63%–84%]</sub> | 83% <sub>[72%–91%]</sub> | 80% <sub>[68%–88%]</sub> | 73% <sub>[61%–83%]</sub> | 83% <sub>[72%–91%]</sub> | 78% <sub>[66%–87%]</sub> |
| Math answer grading (GSM8K) | binary correctness of a small model's solutions | 60 | 67% <sub>[54%–77%]</sub> | 90% <sub>[80%–95%]</sub> | 93% <sub>[84%–97%]</sub> | 73% <sub>[61%–83%]</sub> | 93% <sub>[84%–97%]</sub> | 72% <sub>[59%–81%]</sub> |
| One person's summary taste (OpenAI TL;DR) | pairwise preference of one human labeler | 60 | 58% <sub>[46%–70%]</sub> | 67% <sub>[54%–77%]</sub> | 58% <sub>[46%–70%]</sub> | 58% <sub>[46%–70%]</sub> | 63% <sub>[51%–74%]</sub> | 58% <sub>[46%–70%]</sub> |
| Bank support intents (Banking77, 8 card intents) | fine-grained 8-way intent | 64 | 91% <sub>[81%–96%]</sub> | 92% <sub>[83%–97%]</sub> | 95% <sub>[87%–98%]</sub> | 89% <sub>[79%–95%]</sub> | 95% <sub>[87%–98%]</sub> | 92% <sub>[83%–97%]</sub> |
| Negative emotions in comments (GoEmotions, multi-label) | multi-label: any of 5 emotions, or none | 60 | 10% <sub>[5%–20%]</sub> | 18% <sub>[11%–30%]</sub> | 27% <sub>[17%–39%]</sub> | 23% <sub>[14%–35%]</sub> | 20% <sub>[12%–32%]</sub> | 37% <sub>[26%–49%]</sub> |
| Needs my action (Sam's inbox, self-supervised) | binary, personal, labels from behavior | 22 | 86% <sub>[67%–95%]</sub> | 82% <sub>[61%–93%]</sub> | 95% <sub>[78%–99%]</sub> | 86% <sub>[67%–95%]</sub> | 86% <sub>[67%–95%]</sub> | 82% <sub>[61%–93%]</sub> |

## Run

2026-10-14, one draw per budget, Jev `JEV_MODEL` as the judge, Claude Sonnet (the backend's QUALITY tier)
for the baseline. Test sets are small (20–64): differences under ~15 points are within noise.
Reproduce with `python -m scripts.intuition_bench.run --owner <user> --budgets 8,32`, then
`python -m scripts.intuition_bench.report`.

## What it says

1. **The judge is the ceiling.** Where Jev alone is weak, the intuition stays weak: GSM8K grading
   (Jev 67%, intuition 72%, Claude 90–93%) and AgentRewardBench (75% / 78% / 80–83%). Labels and
   criteria add a few points over Jev but cannot close a gap in the judge's own reasoning. This is
   the one clearly significant result.
2. **At 8–32 labels the head mostly reproduces "Jev + references".** The combined model equals the
   Jev-with-references signal on 5 of 7 tasks; the verdict prior is doing its job (never worse than
   the judge) but rarely finds more.
3. **Multi-label is where the learned head wins.** GoEmotions exact match: 37% at 32 labels vs
   17–27% for everything else, with the best per-emotion accuracy on 4 of 5 emotions. Per-issue
   thresholds learned from labels matter more than a better prompt.
4. **Calibration is mixed:** best or near-best on support, Banking77, GoEmotions and the inbox task;
   worse than Claude on GSM8K and AgentRewardBench, again where the judge is weak.
5. **Subjective taste is hard for everyone:** one labeler's summary preferences sit at 58–67% for
   all arms; neither prompting nor 32 labels learn that taste.
6. **The probe only helps with more data** (AgentRewardBench 78%, Banking77 84% alone at 32 labels;
   near chance at 8).

## What to change

- Let the judge be swappable or stacked: add a frontier-model verdict as one more signal, so the head
  can weigh it against Jev. On GSM8K and AgentRewardBench that alone should close most of the gap.
- Report cost and latency next to accuracy (Jev is the cheap, fast path; this run did not measure it).
- Rerun with 3+ draws per budget and larger test sets before reading small differences.

## Calibration (expected calibration error, lower is better)

| Task | Jev zero-shot | Claude, no examples | Claude + 8 examples | **Intuition, 8 labels** | Claude + 32 examples | **Intuition, 32 labels** |
|---|---:|---:|---:|---:|---:|---:|
| Support reply review | 0.130 | 0.146 | 0.089 | 0.069 | 0.104 | 0.066 |
| Web agent success (AgentRewardBench) | 0.172 | 0.054 | 0.070 | 0.222 | 0.048 | 0.077 |
| Math answer grading (GSM8K) | 0.224 | 0.040 | 0.030 | 0.167 | 0.020 | 0.167 |
| One person's summary taste (OpenAI TL;DR) | 0.037 | 0.116 | 0.164 | 0.050 | 0.081 | 0.074 |
| Bank support intents (Banking77, 8 card intents) | 0.068 | 0.085 | 0.079 | 0.056 | 0.068 | 0.079 |
| Negative emotions in comments (GoEmotions, multi-label) | 0.173 | 0.245 | 0.159 | 0.080 | 0.201 | 0.113 |
| Needs my action (Sam's inbox, self-supervised) | 0.081 | 0.129 | 0.124 | 0.097 | 0.102 | 0.054 |

## Inside the intuition: each signal alone on the same test set

**8 labels**

| Task | Jev + references | probe only | criteria only | combined | criteria from |
|---|---:|---:|---:|---:|---|
| Support reply review | 95% | 45% | 45% | 95% | contrastive |
| Web agent success (AgentRewardBench) | 75% | 52% | 68% | 73% | contrastive |
| Math answer grading (GSM8K) | 72% | 50% | 77% | 73% | contrastive |
| One person's summary taste (OpenAI TL;DR) | 60% | 53% | 57% | 58% | describe |
| Bank support intents (Banking77, 8 card intents) | 89% | 67% | 89% | 89% | contrastive |
| Negative emotions in comments (GoEmotions, multi-label) | 15% | 18% | 17% | 23% | contrastive |
| Needs my action (Sam's inbox, self-supervised) | 86% | 59% | 82% | 86% | contrastive |

**32 labels**

| Task | Jev + references | probe only | criteria only | combined | criteria from |
|---|---:|---:|---:|---:|---|
| Support reply review | 95% | 35% | 75% | 95% | contrastive |
| Web agent success (AgentRewardBench) | 75% | 78% | 53% | 78% | contrastive |
| Math answer grading (GSM8K) | 70% | 48% | 68% | 72% | contrastive |
| One person's summary taste (OpenAI TL;DR) | 58% | 48% | 52% | 58% | describe |
| Bank support intents (Banking77, 8 card intents) | 92% | 84% | 75% | 92% | contrastive |
| Negative emotions in comments (GoEmotions, multi-label) | 17% | 17% | 20% | 37% | contrastive |
| Needs my action (Sam's inbox, self-supervised) | 82% | 59% | 86% | 82% | contrastive |

## Multi-label: per-emotion accuracy

- Claude, no examples: anger 77%, annoyance 73%, disappointment 78%, disapproval 58%, sadness 82%
- Claude + 8 examples: anger 82%, annoyance 78%, disappointment 78%, disapproval 63%, sadness 87%
- **Intuition, 8 labels**: anger 72%, annoyance 67%, disappointment 78%, disapproval 67%, sadness 82%
- Claude + 32 examples: anger 80%, annoyance 77%, disappointment 75%, disapproval 63%, sadness 83%
- **Intuition, 32 labels**: anger 87%, annoyance 80%, disappointment 78%, disapproval 82%, sadness 88%

