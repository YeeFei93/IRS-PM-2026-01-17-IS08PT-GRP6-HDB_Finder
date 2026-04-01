"""
scoring/cosine_scorer.py
========================
Weighted Cosine Similarity scoring for Content-Based filtering.

Computes:  score_cb = cosine_similarity(W ⊙ buyer_vec, W ⊙ flat_vec)

The weight vector W amplifies dimensions the buyer actively configured
(weight 1.0) and dampens dimensions left at defaults (weight 0.25),
so the similarity is driven by what the buyer cares about most while
still allowing serendipitous matches on unconfigured dimensions.

Requires 10-aligned vectors: buyer_vector (11-dim) has its last
dimension (has_hospital) dropped to match the flat_vector (10-dim).

Academic basis: Content-Based Filtering with Similarity-Based Reasoning
(Day 4 slides), with feature weighting per active criterion.
"""

from __future__ import annotations

import math

from scoring.weights import (
    CRITERION_FLAT,
    CRITERION_REGION,
    CRITERION_LEASE,
    CRITERION_MRT,
    CRITERION_AMENITY,
)

# ── Dimension → criterion mapping (10-dim aligned vectors) ──────────────────
# Each vector dimension maps to one of the 6 MCDM criteria.
# "budget" has no vector dimension — it's a separate hybrid signal.
_DIM_CRITERION: list[str] = [
    CRITERION_FLAT,     # 0  flat_type
    CRITERION_REGION,   # 1  region
    CRITERION_FLAT,     # 2  floor_pref / floor
    CRITERION_FLAT,     # 3  flat_area
    CRITERION_LEASE,    # 4  remaining_lease
    CRITERION_MRT,      # 5  has_mrt / nearby_mrt
    CRITERION_AMENITY,  # 6  has_hawker / nearby_hawker
    CRITERION_AMENITY,  # 7  has_mall / nearby_mall
    CRITERION_AMENITY,  # 8  has_park / nearby_park
    CRITERION_AMENITY,  # 9  has_school / nearby_school
]

ACTIVE_WEIGHT   = 1.0
INACTIVE_WEIGHT = 0.25


def _build_weight_vector(active_criteria: list[str]) -> list[float]:
    """Build 10-dim weight vector from the list of active criterion IDs.

    Parameters
    ----------
    active_criteria : list[str]
        Criterion IDs that the buyer actively configured, e.g.
        ``["budget", "flat", "mrt"]``.  Only the IDs that map to vector
        dimensions are used (``budget`` is ignored here since it has no
        corresponding vector dimension).

    Returns
    -------
    list[float]
        Length-10 weight vector with 1.0 for active dims, 0.25 for inactive.
    """
    active_set = set(active_criteria)
    return [
        ACTIVE_WEIGHT if crit in active_set else INACTIVE_WEIGHT
        for crit in _DIM_CRITERION
    ]


def _align_buyer_vector(buyer_vec: list[float]) -> list[float]:
    """Drop the 11th dimension (has_hospital) to align with 10-dim flat vector."""
    if len(buyer_vec) == 11:
        return buyer_vec[:10]
    return list(buyer_vec)  # already 10-dim or unexpected length


def _weighted_cosine(a: list[float], b: list[float],
                     w: list[float]) -> float:
    """Compute cosine similarity of weight-scaled vectors W⊙a and W⊙b.

    Returns a score in [0, 1].  If either weighted vector has zero
    magnitude the similarity is 0.0 (no meaningful comparison).
    """
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for ai, bi, wi in zip(a, b, w):
        wa = wi * ai
        wb = wi * bi
        dot += wa * wb
        norm_a += wa * wa
        norm_b += wb * wb

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


# ── Public API ───────────────────────────────────────────────────────────────

def score_cb(buyer_vec: list[float],
             flat_vec: list[float],
             active_criteria: list[str]) -> float:
    """Compute Content-Based cosine similarity score between buyer and flat.

    Parameters
    ----------
    buyer_vec : list[float]
        11-dim buyer preference vector from ``vectorizer.buyer_vector()``.
    flat_vec : list[float]
        10-dim eligible flat vector from ``vectorizer.flat_vector()``.
    active_criteria : list[str]
        Criterion IDs the buyer actively configured (from
        ``aggregator.detect_active_criteria()``).

    Returns
    -------
    float
        Similarity score in [0.0, 1.0].
    """
    aligned = _align_buyer_vector(buyer_vec)
    w = _build_weight_vector(active_criteria)
    return round(_weighted_cosine(aligned, flat_vec, w), 4)
