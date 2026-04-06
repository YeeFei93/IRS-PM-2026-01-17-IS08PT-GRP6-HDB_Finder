"""
recommendation_scorer_service/recommender.py
===================
Orchestrates all modules to produce the final ranked recommendation list.
This is the only module that calls across module boundaries.

Flow:
  1. Eligibility check
  2. Grant calculation + effective budget
  3. For each candidate town: price analysis → budget filter
  4. For each passing town: distance computation
  5. Score each candidate
  6. Return top 10 sorted by score
"""

from eligibility_checker_service.eligibility  import check_eligibility
from budget_estimator_service.grants       import calc_all_grants
from budget_estimator_service.prices       import analyse_town_prices
from budget_estimator_service.effective_budget       import effective_budget
from geo.distances     import nearest_amenities #Get from amenity service. Distance computation already completed in that module.
from geo.centroids     import get_centroid #Need to change to summary of top 10 recommended flats and then summarize & plot the estates.
from recommendation_scorer_service.MCDM.aggregator import compute_scores # to recompute MCDM scores or even cosine similarity scores
from estate_finder_service.queries        import get_all_towns  #Get from Estate_finder.py

# Town → Region mapping (mirrors front-end)

REGIONS = {
    'Central': ['QUEENSTOWN', 'BUKIT MERAH', 'TOA PAYOH', 'CENTRAL AREA', 'MARINE PARADE'],
    'East': ['TAMPINES', 'BEDOK', 'PASIR RIS', 'GEYLANG', 'KALLANG/WHAMPOA'],
    'North': ['WOODLANDS', 'SEMBAWANG', 'YISHUN', 'ANG MO KIO', 'BISHAN'],
    'Northeast': ['SENGKANG', 'PUNGGOL', 'HOUGANG', 'SERANGOON', 'BUANGKOK'],
    'West': ['JURONG WEST', 'JURONG EAST', 'BUKIT BATOK', 'CHOA CHU KANG', 'CLEMENTI', 'BUKIT PANJANG']
}

def run_recommendation(profile: dict) -> dict:
    """
    Main entry point called by the API route.
    Returns a JSON-serialisable dict.
    """
    # ── 1. Eligibility ───────────────────────────────────────────────────────
    elig = check_eligibility(profile)
    if not elig["eligible"]:
        return {
            "eligible":   False,
            "warnings":   elig["warnings"],
            "notes":      elig["notes"],
            "recommendations": [],
        }

    # ── 2. Grants + budget ───────────────────────────────────────────────────
    grants  = calc_all_grants(profile)
    budget  = effective_budget(profile, grants)

    # ── 3. Determine candidate towns ─────────────────────────────────────────
    regions = profile.get("regions", [])
    if regions:
        towns = [t for r in regions for t in REGIONS.get(r, [])]
    else:
        towns = get_all_towns()

    ftype = profile.get("ftype", "4 ROOM")
    if ftype == "any":
        ftype = "4 ROOM"   # default for price lookups

    # ── 4. Price analysis + budget filter ────────────────────────────────────
    candidates = []
    for town in towns:
        pd = analyse_town_prices(town, ftype)
        if pd is None:
            continue
        # Filter: p25 must be within 118% of effective budget
        if pd["p25"] > budget * 1.18:
            continue
        candidates.append({"town": town, "ftype": ftype, "price_data": pd})

    # ── 5. Distance computation + amenity threshold filtering ────────────────
    must_have    = profile.get("must_have", [])
    max_mrt_mins = profile.get("max_mrt_mins", 30)
    min_lease    = profile.get("min_lease", 60)

    scored = []
    serendipity_pool = []   # Towns that miss must-haves — kept for serendipity top-up

    for c in candidates:
        centroid = get_centroid(c["town"])
        if centroid is None:
            continue

        amenities = nearest_amenities(centroid["lat"], centroid["lng"])

        # Hard filter: MRT max walk (panel slider)
        mrt_mins = amenities.get("mrt", {}).get("walk_mins", 999)
        if mrt_mins > max_mrt_mins:
            continue

        # Must-have threshold check (panel checkboxes)
        # A must-have is "met" when within_threshold is True
        failed_must = [
            k for k in must_have
            if not amenities.get(k, {}).get("within_threshold", False)
        ]

        entry = {**c, "centroid": centroid, "amenities": amenities,
                 "failed_must": failed_must}

        if not failed_must:
            scored.append(entry)
        else:
            serendipity_pool.append(entry)   # missed threshold — serendipity only

    # Guarantee at least 10 results using serendipity pool top-up
    MIN_RESULTS = 10
    if len(scored) < MIN_RESULTS:
        needed = MIN_RESULTS - len(scored)
        scored.extend(serendipity_pool[:needed])

    # ── 6. Scoring ────────────────────────────────────────────────────────────
    results = []
    for item in scored:
        score = compute_score(
            price_data  = item["price_data"],
            amenities   = item["amenities"],
            profile     = profile,
            budget      = budget,
            must_have   = must_have,
            regions     = regions,
        )
        results.append({
            "town":           item["town"],
            "ftype":          item["ftype"],
            "price_data":     item["price_data"],
            "amenities":      item["amenities"],
            "failed_must":    item.get("failed_must", []),
            "score":          score,
            "grants":         grants,
            "effective_budget": int(budget),
        })

    results.sort(key=lambda x: x["score"]["total"], reverse=True)
    top10 = results[:10]

    return {
        "eligible":          True,
        "warnings":          elig["warnings"],
        "notes":             elig["notes"],
        "grants":            grants,
        "effective_budget":  int(budget),
        "recommendations":   top10,
    }
