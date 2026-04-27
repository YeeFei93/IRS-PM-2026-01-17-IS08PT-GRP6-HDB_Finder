from vectorizer import buyer_vector, flat_vector
from cosine_scorer import score_cb, score_cb_breakdown
from weights import (
    CRITERION_BUDGET, CRITERION_FLAT, CRITERION_FLOOR, CRITERION_REGION,
    AMENITY_CRITERIA,
    DEFAULTS,
)

# Budget adjustment parameters
# Flats under budget receive a reward; flats over budget receive a penalty.
#   ≤ 70% budget  → +BUDGET_MAX reward (best value)
#   70–100%       → reward scales linearly from +BUDGET_MAX to 0
#   100–105%      → penalty scales linearly from 0 to -BUDGET_MAX
#   > 105%        → capped at -BUDGET_MAX (usually filtered out)
BUDGET_REWARD_FLOOR = 0.70    # full reward at or below 70% of budget
BUDGET_PENALTY_CAP  = 1.05    # full penalty at 105% of budget
BUDGET_MAX          = 0.05    # max reward or penalty (5 points on 0-100 scale)


def detect_active_criteria(profile: dict, budget: float,
                            must_have: list, regions: list) -> list:
    active = []
    if budget > 0:
        active.append(CRITERION_BUDGET)
    ftype_val = profile.get("ftype", DEFAULTS[CRITERION_FLAT])
    # ftype is now a list; active when non-empty list or non-'any' string
    if (isinstance(ftype_val, list) and ftype_val) or \
       (isinstance(ftype_val, str) and ftype_val.lower() != DEFAULTS[CRITERION_FLAT]):
        active.append(CRITERION_FLAT)
    floor_val = profile.get("floor", profile.get("floor_pref", "any"))
    # floor is active only when exactly one floor is selected
    if (isinstance(floor_val, list) and len(floor_val) == 1) or \
       (isinstance(floor_val, str) and floor_val.lower() != DEFAULTS[CRITERION_FLOOR]):
        active.append(CRITERION_FLOOR)
    if regions:
        active.append(CRITERION_REGION)
    # Activate each amenity criterion individually based on must_have list
    must_set = set(must_have) if must_have else set()
    for crit in AMENITY_CRITERIA:
        if crit in must_set:            # crit IDs match amenity names: "mrt", "hawker", etc.
            active.append(crit)
    return active


def _budget_adjustment(price: float, budget: float) -> float:
    """Return a score adjustment for budget fit: positive (reward) or negative (penalty).

    ≤ 70% of budget  → +BUDGET_MAX  (best value)
    70–100%          → linear from +BUDGET_MAX to 0
    100%             → 0 (exactly at budget)
    100–105%         → linear from 0 to -BUDGET_MAX
    > 105%           → -BUDGET_MAX (capped)
    """
    if budget <= 0 or price <= 0:
        return 0.0
    ratio = price / budget
    if ratio <= BUDGET_REWARD_FLOOR:
        return round(BUDGET_MAX, 4)
    if ratio <= 1.0:
        # Linear reward: +BUDGET_MAX at 70% → 0 at 100%
        t = (1.0 - ratio) / (1.0 - BUDGET_REWARD_FLOOR)
        return round(t * BUDGET_MAX, 4)
    # Over budget: linear penalty 0 at 100% → -BUDGET_MAX at 105%
    t = (ratio - 1.0) / (BUDGET_PENALTY_CAP - 1.0)
    return round(-min(t, 1.0) * BUDGET_MAX, 4)


def score_payload(payload: dict) -> dict:
    """Score a single candidate flat/town against a buyer profile.

    Derives ``regions`` and ``must_have`` from ``profile`` so that
    ``buyer_vector``, ``flat_vector``, and ``detect_active_criteria``
    all see the same values.

    When ``resale_price`` is provided in the payload and ``budget`` > 0,
    a small tie-breaking penalty is applied for flats near or above budget.
    """
    profile    = payload["profile"]
    price_data = payload["price_data"]
    amenities  = payload["amenities"]
    budget     = payload["budget"]
    must_have  = profile.get("must_have",  payload.get("must_have", []))
    regions    = profile.get("regions",    payload.get("regions", []))

    b_vec      = buyer_vector(profile, budget)
    f_vec      = flat_vector(price_data, amenities)
    active     = detect_active_criteria(profile, budget, must_have, regions)
    similarity = score_cb(b_vec, f_vec, active)
    breakdown  = score_cb_breakdown(b_vec, f_vec, active)

    # Apply budget adjustment (reward for under-budget, penalty for over)
    resale_price = payload.get("resale_price", 0)
    adj = _budget_adjustment(resale_price, budget) if resale_price else 0.0
    final_score = round(max(min(similarity + adj, 1.0), 0.0), 4)

    # Append budget row to breakdown
    breakdown.append({
        "dim":      "budget",
        "icon":     "💰",
        "buyer":    round(budget, 0) if budget else 0,
        "flat":     round(resale_price, 0) if resale_price else 0,
        "weight":   1.0 if budget > 0 else 0.0,
        "priority": budget > 0,
        "contrib":  round(adj, 4),
    })

    return {"score": final_score, "active_criteria": active, "breakdown": breakdown}
