"""
recommendation_scorer_service/flat_score.py
=====================
Flat attributes: floor area fit vs flat type, and remaining lease.

Returns a raw score 0.0 – 1.0.
The aggregator splits this into two separate MCDM criteria:
  - CRITERION_FLAT  → uses area_raw()
  - CRITERION_LEASE → uses lease_raw()
Both are exported separately so the aggregator can weight them independently.
"""

# Expected floor area ranges by flat type (sqm)
AREA_RANGES = {
    "2 ROOM":    (36,  45),
    "3 ROOM":    (60,  75),
    "4 ROOM":    (85,  105),
    "5 ROOM":    (110, 135),
    "EXECUTIVE": (130, 165),
}


def area_raw(price_data: dict) -> float:
    """
    Returns 0.0–1.0 based on average floor area vs expected range for flat type.
    """
    ftype    = price_data.get("ftype", "4 ROOM")
    avg_area = price_data.get("avg_area", 0)

    if avg_area <= 0 or ftype not in AREA_RANGES:
        return 0.5   # neutral if data unavailable

    lo, hi = AREA_RANGES[ftype]
    if lo <= avg_area <= hi:
        return 1.0
    elif avg_area > hi:
        return 0.90   # larger than expected — generally desirable
    else:
        ratio = avg_area / lo
        return max(round(ratio, 2), 0.0)


def lease_raw(price_data: dict, min_lease: int, buyer_age: int) -> float:
    """
    Returns 0.0–1.0 based on estimated remaining lease.

    Scoring:
      - If town median remaining lease ≥ min_lease: 1.0
      - Penalised linearly as lease falls below min_lease
      - CPF rule: buyer_age + remaining_lease should exceed 80 yrs
        (flag but do not hard-zero — buyer may not use CPF)
    """
    # Remaining lease is estimated from lease_commence_date (town average)
    # price_data carries avg_lease_years if available; default to 60 if absent
    avg_lease = price_data.get("avg_lease_years", 60)

    if avg_lease <= 0:
        return 0.5   # neutral if data unavailable

    # Minimum threshold: buyer's stated requirement
    if avg_lease >= min_lease:
        base = 1.0
    else:
        base = max(avg_lease / min_lease, 0.0)

    # CPF compatibility penalty (soft)
    cpf_threshold = 80 - buyer_age   # minimum remaining lease for full CPF use
    if avg_lease < cpf_threshold:
        base *= 0.75   # 25% penalty — surfaced as a note, not eliminated

    return round(base, 3)
