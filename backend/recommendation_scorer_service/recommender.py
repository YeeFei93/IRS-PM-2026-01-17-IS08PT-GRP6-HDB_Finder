"""
recommendation_scorer_service/recommender.py
===================
Orchestrates all services to produce the final cosine-similarity-ranked
recommendation list.  Scores **every** individual flat (sold from 2025-10)
and derives estate rankings from the globally-ranked flat list.

Flow:
  1. Eligibility check
  2. Grant calculation + effective budget
  3. Determine candidate towns (from selected regions, or all)
  4. For each town: fetch price analysis for display metadata
  5. For each town: fetch **all** flats, filter resale_price <= budget*1.05
     + remaining_lease_years >= min_lease (SQL-level)
  6. Per-block amenity stats + CB cosine scoring per flat via score_payload()
  7. Sort all scored flats globally by score (descending)
  8. Group flats into estates — estate ordered by most qualifying flats
  9. Return all estates with qualifying flats, each with up to 10 cosine-ranked flats
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

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from eligibility_checker_service.eligibility import check_eligibility
from budget_estimator_service.grants import calc_all_grants
from budget_estimator_service.prices import analyse_town_prices
from budget_estimator_service.effective_budget import effective_budget
from estate_finder_service.queries import get_all_towns, get_flats_for_estate
from amenity_proximity_service.utils.distances import block_amenity_stats, warm_all_estates
from scorer import score_payload  # bare import — service dir is on sys.path above

# Pre-warm the amenity cache in the background the moment this module loads
# so the first recommendation request hits the cache instead of the DB.
def _bg_warm():
    try:
        warm_all_estates()
    except Exception:
        pass

threading.Thread(target=_bg_warm, daemon=True, name="amenity-cache-warm").start()


# Town → Region mapping (mirrors frontend constants.js REGIONS)
_REGIONS = {
    'Central':   ['QUEENSTOWN', 'BUKIT MERAH', 'TOA PAYOH', 'CENTRAL AREA', 'MARINE PARADE', 'BUKIT TIMAH'],
    'East':      ['TAMPINES', 'BEDOK', 'PASIR RIS', 'GEYLANG', 'KALLANG/WHAMPOA'],
    'North':     ['WOODLANDS', 'SEMBAWANG', 'YISHUN', 'ANG MO KIO', 'BISHAN'],
    'Northeast': ['SENGKANG', 'PUNGGOL', 'HOUGANG', 'SERANGOON', 'BUANGKOK'],
    'West':      ['JURONG WEST', 'JURONG EAST', 'BUKIT BATOK', 'CHOA CHU KANG', 'CLEMENTI', 'BUKIT PANJANG'],
}

_TOP_FLATS = 10           # max flats to include per estate in response

_EMPTY_AMENITY = {
    "dist_km": None, "walk_mins": None,
    "within_threshold": False, "count_within": 0,
}

_AMENITY_KEYS = ("mrt", "hawker", "mall", "park", "school", "hospital")


def _score_estate_flats(town, ftype, floor_pref, min_lease, profile, budget):
    """Fetch **all** flats for one estate, compute per-block amenity stats, score each flat.

    Returns (town, scored_flats, active_criteria).
    scored_flats is sorted by score descending; each flat dict has extra
    ``score`` and ``flat_amenities`` keys.
    """
    flats = get_flats_for_estate(
        town, ftype, floor_pref,
        budget=0, min_lease=min_lease, limit=0,  # limit=0 → fetch all
    )
    # Flat-level budget filter: only score flats within 105% of effective budget
    if budget > 0:
        cap = budget * 1.05
        flats = [f for f in flats if f["resale_price"] <= cap]
    if not flats:
        return town, [], None

    amenity_by_block = block_amenity_stats(town)

    scored_flats = []
    active_criteria = None

    for flat in flats:
        key = (str(flat["block"]), flat["street_name"])
        flat_amenities = {}
        for akey in _AMENITY_KEYS:
            flat_amenities[akey] = amenity_by_block.get(key, {}).get(akey, _EMPTY_AMENITY)

        storey_mid = (
            (flat.get("storey_range_start", 5) + flat.get("storey_range_end", 10)) / 2.0
        )

        result = score_payload({
            "profile":      profile,
            "price_data":   {"avg_storey": storey_mid},
            "amenities":    flat_amenities,
            "budget":       budget,
            "resale_price": flat.get("resale_price", 0),
        })

        flat["score"] = result["score"]
        flat["score_breakdown"] = result["breakdown"]
        flat["flat_amenities"] = flat_amenities
        if active_criteria is None:
            active_criteria = result["active_criteria"]
        scored_flats.append(flat)

    scored_flats.sort(key=lambda f: f["score"], reverse=True)
    return town, scored_flats, active_criteria


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

    # ── 4. Price analysis per town (metadata only, no coarse filtering) ────
    min_lease = profile.get("min_lease", 0)
    candidates = []
    for town in towns:
        price_data = analyse_town_prices(town, ftype)
        if price_data is None:
            continue
        candidates.append({"town": town, "price_data": price_data})

    # ── 5. Fetch ALL flats + score individually (parallel per estate) ───────
    all_scored = []  # list of (flat_dict, town, price_data, active_criteria)

    if candidates:
        with ThreadPoolExecutor(max_workers=min(len(candidates), 8)) as executor:
            futures = {
                executor.submit(
                    _score_estate_flats, c["town"], ftype, floor_pref,
                    min_lease, profile, budget,
                ): c
                for c in candidates
            }
            for future in as_completed(futures):
                c = futures[future]
                try:
                    town, scored_flats, active_criteria = future.result()
                except Exception as exc:
                    print(f"[recommender] Estate scoring failed for {c['town']}: {exc}", flush=True)
                    continue
                for flat in scored_flats:
                    all_scored.append({
                        "flat": flat,
                        "town": town,
                        "price_data": c["price_data"],
                        "active_criteria": active_criteria or [],
                    })

    # ── 6. Sort ALL flats globally by cosine score ───────────────────────────
    all_scored.sort(key=lambda x: x["flat"]["score"], reverse=True)

    # ── 7. Group into estates ────────────────────────────────────────────
    estate_map = {}    # town → { estate result dict, total qualifying flat count }

    for item in all_scored:
        town = item["town"]
        flat = item["flat"]
        flat_amenities = flat.pop("flat_amenities", {})
        flat_clean = {k: v for k, v in flat.items()}

        if town not in estate_map:
            estate_map[town] = {
                "town":             town,
                "ftype":            ftype,
                "price_data":       item["price_data"],
                "amenities":        flat_amenities,   # best flat's amenities
                "score":            flat["score"],     # best flat's score
                "active_criteria":  item["active_criteria"],
                "top_flats":        [],
                "qualifying_flats": 0,
                "grants":           grants,
                "effective_budget": int(budget),
            }

        estate_map[town]["qualifying_flats"] += 1

        if len(estate_map[town]["top_flats"]) < _TOP_FLATS:
            estate_map[town]["top_flats"].append(flat_clean)

    # Compute per-estate avg score and strong-match count from top flats
    for estate in estate_map.values():
        scores = [f["score"] for f in estate["top_flats"]]
        estate["avg_score"]      = round(sum(scores) / len(scores), 4) if scores else 0.0
        estate["strong_matches"] = sum(1 for s in scores if s >= 0.75)

    # Sort estates by avg score of top flats (primary), qualifying flats as tiebreaker
    estate_results = sorted(estate_map.values(), key=lambda e: (e["avg_score"], e["qualifying_flats"]), reverse=True)

    # ── Baseline rankings for academic comparison ─────────────────────────────
    # Baseline 1 — Price proximity: rank by |median_price − effective_budget| ascending
    #   Represents a naive "closest-to-budget" recommender with no preference modelling.
    price_sorted = sorted(
        estate_results,
        key=lambda e: abs(e["price_data"]["median"] - budget),
    )
    price_rank_map = {e["town"]: i + 1 for i, e in enumerate(price_sorted)}

    # Baseline 2 — Popularity: rank by transaction count (market liquidity signal)
    #   Represents a non-personalised popularity-based recommender.
    pop_sorted = sorted(
        estate_results,
        key=lambda e: e["price_data"]["n"],
        reverse=True,
    )
    pop_rank_map = {e["town"]: i + 1 for i, e in enumerate(pop_sorted)}

    for estate in estate_results:
        estate["baseline_price_rank"] = price_rank_map[estate["town"]]
        estate["baseline_pop_rank"]   = pop_rank_map[estate["town"]]

    return {
        "eligible":         True,
        "warnings":         elig["warnings"],
        "notes":            elig["notes"],
        "grants":           grants,
        "effective_budget": int(budget),
        "recommendations":  estate_results,
    }
