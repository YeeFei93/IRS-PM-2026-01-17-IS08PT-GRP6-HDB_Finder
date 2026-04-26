"""
recommendation-scorer-service/weights.py
==================
Scoring criterion constants.

Each criterion maps directly to a buyer panel input:
  CRITERION_BUDGET     ← buyer entered cash / CPF / loan      (pre-filter)
  CRITERION_FLAT       ← buyer chose a specific flat type (not "any")
  CRITERION_FLOOR      ← buyer chose a specific floor pref (not "any")
  CRITERION_REGION     ← buyer selected ≥1 region tag
  CRITERION_LEASE      ← buyer set min lease > baseline (60 yrs)  (pre-filter only)
  CRITERION_MRT        ← buyer marked MRT as must-have
  CRITERION_HAWKER     ← buyer marked hawker as must-have
  CRITERION_MALL       ← buyer marked mall as must-have
  CRITERION_PARK       ← buyer marked park as must-have
  CRITERION_SCHOOL     ← buyer marked school as must-have
  CRITERION_HOSPITAL   ← buyer marked hospital as must-have

A criterion is ACTIVE when the buyer made a meaningful choice vs
leaving it at the default value. Active dimensions are weighted 1.0
in cosine similarity; inactive dimensions are weighted 0.25.

Note: "budget" and "lease" have no vector dimensions. They are
constraints (upper/lower bounds) handled via pre-filtering before
cosine scoring. Cosine similarity penalises deviations symmetrically,
which is wrong for constraints where exceeding the target is acceptable.
"""

# ── Criterion identifiers (match panel input names) ──────────────────────────
CRITERION_BUDGET   = "budget"
CRITERION_FLAT     = "flat"
CRITERION_FLOOR    = "floor"
CRITERION_REGION   = "region"
CRITERION_LEASE    = "lease"

# Per-amenity criteria (one per vector dimension)
CRITERION_MRT      = "mrt"
CRITERION_HAWKER   = "hawker"
CRITERION_MALL     = "mall"
CRITERION_PARK     = "park"
CRITERION_SCHOOL   = "school"
CRITERION_HOSPITAL = "hospital"

# Convenience list of all amenity criteria (order matches vectorizer.AMENITY_DIMS)
AMENITY_CRITERIA = [
    CRITERION_MRT, CRITERION_HAWKER, CRITERION_MALL,
    CRITERION_PARK, CRITERION_SCHOOL, CRITERION_HOSPITAL,
]

# Legacy alias — kept for backward compatibility in case external code references it
CRITERION_AMENITY = "amenity"

ALL_CRITERIA = [
    CRITERION_BUDGET,
    CRITERION_FLAT,
    CRITERION_FLOOR,
    CRITERION_REGION,
    CRITERION_LEASE,
    CRITERION_MRT,
    CRITERION_HAWKER,
    CRITERION_MALL,
    CRITERION_PARK,
    CRITERION_SCHOOL,
    CRITERION_HOSPITAL,
]

# ── Default values — criterion is INACTIVE when buyer leaves it at default ───
DEFAULTS = {
    CRITERION_FLAT:    "any",   # flat type "any" → not a stated preference
    CRITERION_FLOOR:   "any",   # floor "any" → not a stated preference
    CRITERION_REGION:  [],       # no regions chosen → no regional preference
    CRITERION_LEASE:   60,       # ≤ 60 yrs → not a meaningful constraint (slider range 20–99, threshold matches engine.js)
    # Per-amenity defaults: each is inactive unless buyer marks it as must-have
    CRITERION_MRT:      False,
    CRITERION_HAWKER:   False,
    CRITERION_MALL:     False,
    CRITERION_PARK:     False,
    CRITERION_SCHOOL:   False,
    CRITERION_HOSPITAL: False,
    # budget: always active if effective_budget > 0
}
