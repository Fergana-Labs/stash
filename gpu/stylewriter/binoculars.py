"""Binoculars (Hans et al., 2024): a zero-shot detector that needs no
training data and no API key. Two related models read the same text; the
ratio of the observer's perplexity to the cross-perplexity between the two
separates machine text (low) from human text (high). The threshold is the
paper's low-false-positive setting for the Falcon pair.

Only the arithmetic lives here so it can be tested; the models are loaded
by the Modal class that calls it.
"""

from __future__ import annotations

import math

OBSERVER_MODEL = "tiiuae/falcon-7b"
PERFORMER_MODEL = "tiiuae/falcon-7b-instruct"

# Scores above this read as human. Paper's reported threshold for the
# accuracy-optimised setting is ~0.9015.
THRESHOLD = 0.9015
# How sharply the score maps onto a probability around the threshold.
SCALE = 0.04


def p_human(score: float) -> float:
    """A probability-shaped view of the raw score, so callers can gate at
    0.5 and report a number people understand. Not calibrated; monotone."""
    return round(1.0 / (1.0 + math.exp(-(score - THRESHOLD) / SCALE)), 4)
