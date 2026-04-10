"""
recommendation_scorer_service/recommender.py
===================
Orchestrates all services to produce the final cosine-similarity-ranked
recommendation list. Replaces the old MCDM/recommender.py.

Flow:
  1. Eligibility check
  2. Grant calculation + effective budget
  3. Determine candidate towns (from selected regions, or all)
  4. For each town: price analysis + budget filter (p25 <= 1.18 x budget)
  5. For each passing town: amenity distances + hard filters
       - MRT max walk (slider)
       - Must-have threshold check (checkboxes)
  6. CB cosine scoring via score_payload()
  7. Return top 10 sorted by score
"""

import os
import sys

# Ensure recommendation_scorer_service/ is on sys.path so scorer bare-imports work
_SERVICE_ROOT = os.path.dirname(os.path.abspath(__file__))
if _SERVICE_ROOT not in sys.path:
    sys.path.insert(0, _SERVICE_ROOT)

# Ensure backend root is on sys.path for cross-service imports
_BACKEND_ROOT = os.path.abspath(os.path.join(_SERVICE_ROOT, ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from eligibility_checker_service.eligibility import check_eligibility
from budget_estimator_service.grants import calc_all_grants
from budget_estimator_service.prices import analyse_town_prices
from budget_estimator_service.effective_budget import effective_budget
from estate_finder_service.queries import get_all_towns
from amenity_proximity_service.distances import nearest_amenities
from scorer import score_payload  # bare import — service dir is on sys.path above


# Town → Region mapping (mirrors frontend constants.js REGIONS)
_REGIONS = {
    'Central':   ['QUEENSTOWN', 'BUKIT MERAH', 'TOA PAYOH', 'CENTRAL AREA', 'MARINE PARADE'],
    'East':      ['TAMPINES', 'BEDOK', 'PASIR RIS', 'GEYLANG', 'KALLANG/WHAMPOA'],
    'North':     ['WOODLANDS', 'SEMBAWANG', 'YISHUN', 'ANG MO KIO', 'BISHAN'],
    'Northeast': ['SENGKANG', 'PUNGGOL', 'HOUGANG', 'SERANGOON', 'BUANGKOK'],
    'West':      ['JURONG WEST', 'JURONG EAST', 'BUKIT BATOK', 'CHOA CHU KANG', 'CLEMENTI', 'BUKIT PANJANG'],
}

_MIN_RESULTS = 10


def run_recommendation(profile: dict) -> dict:
    """
    Main entry point called by recommendation_adapter.py via Redis queue.
    Accepts a BuyerProfile dict, returns a JSON-serialisable result dict.
    """

    # ── 1. Eligibility ────────────────────────────────────────────────────────
    elig = check_eligibility(profile)
    if not elig["eligible"]:
        return {
            "eligible":        False,
            "warnings":        elig["warnings"],
            "notes":           elig["notes"],
            "recommendations": [],
        }

    # ── 2. Grants + effective budget ─────────────────────────────────────────
    grants = calc_all_grants(profile)
    budget = effective_budget(profile, grants)

    # ── 3. Candidate towns ───────────────────────────────────────────────────
    regions   = profile.get("regions", [])
    ftype     = profile.get("ftype", "4 ROOM")
    floor_pref = profile.get("floor", "any")
    if ftype == "any":
        ftype = "4 ROOM"  # default for price lookups

    if regions:
        # Normalise to title-case to match _REGIONS keys
        towns = [t for r in regions for t in _REGIONS.get(r.title(), [])]
    else:
        towns = get_all_towns()

    # ── 4. Price analysis + budget filter ────────────────────────────────────
    candidates = []
    for town in towns:
        price_data = analyse_town_prices(town, ftype)
        if price_data is None:
            continue
        # Filter: p25 must be within 118% of effective budget
        if price_data["p25"] > budget * 1.18:
            continue
        price_data["estate"] = town  # needed by flat_vector() via score_payload
        candidates.append({"town": town, "ftype": ftype, "price_data": price_data})

    # ── 5. Amenity distances + hard filters ──────────────────────────────────
    must_have    = profile.get("must_have", [])
    max_mrt_mins = profile.get("max_mrt_mins", 30)

    scored        = []
    fallback_pool = []  # Towns that miss must-have threshold — used as top-up

    for c in candidates:
        amenities = nearest_amenities(c["town"])

        # Hard filter: MRT max walk (panel slider)
        mrt_mins = amenities.get("mrt", {}).get("walk_mins", 999)
        if mrt_mins > max_mrt_mins:
            continue

        # Must-have threshold check (checkboxes)
        failed_must = [
            k for k in must_have
            if not amenities.get(k, {}).get("within_threshold", False)
        ]

        entry = {**c, "amenities": amenities, "failed_must": failed_must}

        if not failed_must:
            scored.append(entry)
        else:
            fallback_pool.append(entry)

    # Guarantee at least _MIN_RESULTS using fallback pool top-up
    if len(scored) < _MIN_RESULTS:
        scored.extend(fallback_pool[: _MIN_RESULTS - len(scored)])

    # ── 6. CB cosine scoring ─────────────────────────────────────────────────
    results = []
    for item in scored:
        scored_result = score_payload({
            "profile":    profile,
            "price_data": item["price_data"],
            "amenities":  item["amenities"],
            "budget":     budget,
        })
        results.append({
            "town":             item["town"],
            "ftype":            item["ftype"],
            "price_data":       item["price_data"],
            "amenities":        item["amenities"],
            "failed_must":      item.get("failed_must", []),
            "score":            scored_result["score"],
            "active_criteria":  scored_result["active_criteria"],
            "grants":           grants,
            "effective_budget": int(budget),
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "eligible":         True,
        "warnings":         elig["warnings"],
        "notes":            elig["notes"],
        "grants":           grants,
        "effective_budget": int(budget),
        "recommendations":  results[:_MIN_RESULTS],
    }
