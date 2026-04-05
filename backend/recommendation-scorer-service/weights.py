"""
recommendation-scorer-service/weights.py
==================
Scoring criterion constants.

The 6 criteria map directly to the buyer panel inputs:
  CRITERION_BUDGET    ← buyer entered cash / CPF / loan
  CRITERION_FLAT      ← buyer chose a specific flat type (not "any")
  CRITERION_REGION    ← buyer selected ≥1 region tag
  CRITERION_LEASE     ← buyer set min lease > baseline (60 yrs)
  CRITERION_MRT       ← buyer set max MRT walk < ceiling (30 min)
  CRITERION_AMENITY   ← buyer selected ≥1 must-have amenity

A criterion is ACTIVE when the buyer made a meaningful choice vs
leaving it at the default value. Active dimensions are weighted 1.0
in cosine similarity; inactive dimensions are weighted 0.25.
"""

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
    CRITERION_LEASE:   60,       # ≤ 60 yrs → not a meaningful constraint (slider range 20–99, threshold matches engine.js)
    CRITERION_MRT:     30,       # = 30 min ceiling → not tightened
    CRITERION_AMENITY: [],       # no must-haves → no amenity preference
    # budget: always active if effective_budget > 0
}
