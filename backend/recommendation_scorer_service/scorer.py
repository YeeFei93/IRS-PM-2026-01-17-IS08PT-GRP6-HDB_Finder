from vectorizer import buyer_vector, flat_vector
from cosine_scorer import score_cb
from weights import (
    CRITERION_BUDGET, CRITERION_FLAT, CRITERION_REGION,
    CRITERION_LEASE, CRITERION_AMENITY,
    DEFAULTS,
)


def detect_active_criteria(profile: dict, budget: float,
                            must_have: list, regions: list) -> list:
    active = []
    if budget > 0:
        active.append(CRITERION_BUDGET)
    if profile.get("ftype", DEFAULTS[CRITERION_FLAT]) != DEFAULTS[CRITERION_FLAT]:
        active.append(CRITERION_FLAT)
    if regions:
        active.append(CRITERION_REGION)
    if profile.get("min_lease", DEFAULTS[CRITERION_LEASE]) > DEFAULTS[CRITERION_LEASE]:
        active.append(CRITERION_LEASE)
    if must_have:
        active.append(CRITERION_AMENITY)
    return active


def score_payload(payload: dict) -> dict:
    """Score a single candidate flat/town against a buyer profile.

    Derives ``regions`` and ``must_have`` from ``profile`` so that
    ``buyer_vector``, ``flat_vector``, and ``detect_active_criteria``
    all see the same values.
    """
    profile    = payload["profile"]
    price_data = payload["price_data"]
    amenities  = payload["amenities"]
    budget     = payload["budget"]
    must_have  = profile.get("must_have",  payload.get("must_have", []))
    regions    = profile.get("regions",    payload.get("regions", []))

    b_vec      = buyer_vector(profile, budget)
    f_vec      = flat_vector(price_data.get("estate", ""), price_data, amenities, regions)
    active     = detect_active_criteria(profile, budget, must_have, regions)
    similarity = score_cb(b_vec, f_vec, active)

    return {"score": similarity, "active_criteria": active}
