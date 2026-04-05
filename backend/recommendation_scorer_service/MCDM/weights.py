"""
recommendation_scorer_service/weights.py
==================
MCDM + Serendipity scoring constants.

Architecture
------------
Total score (100 pts) = MCDM (80 pts) + Serendipity (20 pts)

MCDM slice (80 pts):
  Divided EQUALLY among whichever criteria the buyer actively set.
  A criterion counts as "active" only when the buyer made a
  meaningful choice — not left at default.

  The 6 criteria map directly to the buyer panel inputs:
    CRITERION_BUDGET    ← buyer entered cash / CPF / loan
    CRITERION_FLAT      ← buyer chose a specific flat type (not "any")
    CRITERION_REGION    ← buyer selected ≥1 region tag
    CRITERION_LEASE     ← buyer set min lease > baseline (60 yrs)
    CRITERION_MRT       ← buyer set max MRT walk < ceiling (30 min)
    CRITERION_AMENITY   ← buyer selected ≥1 must-have amenity

  Example — buyer sets budget + region + MRT only:
    → 3 active criteria → each gets 80 / 3 ≈ 26.7 pts
    → lease, flat, amenity excluded from MCDM slice

  If NO criteria are active (bare default search):
    → all 6 treated as equally active (80 / 6 ≈ 13.3 pts each)

Serendipity slice (20 pts):
  Scores the estate on criteria the buyer did NOT prioritise.
  Purpose: prevent over-filtering from producing < 10 results,
  and surface genuinely good estates the buyer may not have considered.
  Always computed from the INACTIVE criteria set.
  If all 6 criteria are active → serendipity scores all 6 uniformly.
"""

# ── Fixed allocation ──────────────────────────────────────────────────────────
MCDM_TOTAL        = 80   # pts allocated to buyer-driven criteria
SERENDIPITY_TOTAL = 20   # pts always reserved for discovery
TOTAL             = 100

assert MCDM_TOTAL + SERENDIPITY_TOTAL == TOTAL

# ── Criterion identifiers (match panel input names) ──────────────────────────
CRITERION_BUDGET  = "budget"
CRITERION_FLAT    = "flat"
CRITERION_REGION  = "region"
CRITERION_LEASE   = "lease"
CRITERION_MRT     = "mrt"
CRITERION_AMENITY = "amenity"

ALL_CRITERIA = [
    CRITERION_BUDGET,
    CRITERION_FLAT,
    CRITERION_REGION,
    CRITERION_LEASE,
    CRITERION_MRT,
    CRITERION_AMENITY,
]

# ── Default values — criterion is INACTIVE when buyer leaves it at default ───
DEFAULTS = {
    CRITERION_FLAT:    "any",   # flat type "any" → not a stated preference
    CRITERION_REGION:  [],       # no regions chosen → no regional preference
    CRITERION_LEASE:   60,       # ≤ 60 yrs → not a meaningful constraint
    CRITERION_MRT:     30,       # = 30 min ceiling → not tightened
    CRITERION_AMENITY: [],       # no must-haves → no amenity preference
    # budget: always active if effective_budget > 0
}
