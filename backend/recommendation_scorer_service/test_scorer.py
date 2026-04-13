"""
recommendation-scorer-service/test_scorer.py
=============================================
Unit + integration tests using sample data.
Run:  python test_scorer.py
"""

import unittest

from vectorizer import buyer_vector, flat_vector, AMENITY_DIMS
from cosine_scorer import score_cb, ACTIVE_WEIGHT, INACTIVE_WEIGHT
from weights import (
    CRITERION_BUDGET, CRITERION_FLAT, CRITERION_REGION,
    CRITERION_AMENITY,
    DEFAULTS,
)

# ── Sample data ──────────────────────────────────────────────────────────────

# Buyer who wants a 4-room flat in the north, hawker must-have
PROFILE_ACTIVE = {
    "ftype":        "4 ROOM",
    "regions":      ["north"],
    "floor":        "mid",
    "min_lease":    70,          # > 60 → lease criterion active
    "must_have":    ["hawker"],
}

# Buyer with all defaults — no stated preferences
PROFILE_DEFAULT = {
    "ftype":        "any",
    "regions":      [],
    "floor":        "any",
    "min_lease":    20,
    "must_have":    [],
}

# Price data for a north-region town (e.g. Woodlands)
PRICE_DATA_WOODLANDS = {
    "estate":          "WOODLANDS",
    "ftype":           "4 ROOM",
    "avg_storey":      8.0,      # low-mid floor
    "avg_lease_years": 72,
}

# Price data for a central-region town (e.g. Bukit Merah)
PRICE_DATA_BUKIT_MERAH = {
    "estate":          "BUKIT MERAH",
    "ftype":           "4 ROOM",
    "avg_storey":      12.0,
    "avg_lease_years": 55,
}

# Good amenities — everything close
AMENITIES_GOOD = {
    "mrt":      {"dist_km": 0.30, "walk_mins": 3.6},
    "hawker":   {"dist_km": 0.25, "walk_mins": 3.0},
    "mall":     {"dist_km": 0.60, "walk_mins": 7.2},
    "park":     {"dist_km": 0.80, "walk_mins": 9.6},
    "school":   {"dist_km": 0.40, "walk_mins": 4.8},
    "hospital": {"dist_km": 1.20, "walk_mins": 14.4},
}

# Poor amenities — everything far
AMENITIES_POOR = {
    "mrt":      {"dist_km": 1.50, "walk_mins": 18.0},
    "hawker":   {"dist_km": 1.20, "walk_mins": 14.4},
    "mall":     {"dist_km": 2.00, "walk_mins": 24.0},
    "park":     {"dist_km": 2.00, "walk_mins": 24.0},
    "school":   {"dist_km": 1.50, "walk_mins": 18.0},
    "hospital": {"dist_km": 3.00, "walk_mins": 36.0},
}

# Sparse amenities — missing some keys
AMENITIES_SPARSE = {
    "mrt":   {"dist_km": 0.50, "walk_mins": 6.0},
    "hawker": {},           # no dist_km
    # mall/park/school/hospital missing entirely
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _active(profile, budget=0, must_have=None, regions=None):
    """Mirrors detect_active_criteria() from scorer.py."""
    if must_have is None:
        must_have = profile.get("must_have", [])
    if regions is None:
        regions = profile.get("regions", [])
    active = []
    if budget > 0:
        active.append(CRITERION_BUDGET)
    if profile.get("ftype", DEFAULTS[CRITERION_FLAT]) != DEFAULTS[CRITERION_FLAT]:
        active.append(CRITERION_FLAT)
    if regions:
        active.append(CRITERION_REGION)
    if must_have:
        active.append(CRITERION_AMENITY)
    return active


# ── Test cases ────────────────────────────────────────────────────────────────

class TestBuyerVector(unittest.TestCase):

    def test_length(self):
        vec = buyer_vector(PROFILE_ACTIVE)
        self.assertEqual(len(vec), 7)

    def test_all_in_range(self):
        for profile in [PROFILE_ACTIVE, PROFILE_DEFAULT]:
            vec = buyer_vector(profile)
            for i, v in enumerate(vec):
                self.assertGreaterEqual(v, 0.0, f"dim {i} < 0")
                self.assertLessEqual(v, 1.0,    f"dim {i} > 1")

    def test_floor_pref_encoding(self):
        for floor, expected in [("low", 0.33), ("mid", 0.66), ("high", 1.0), ("any", 0.5)]:
            vec = buyer_vector({"floor": floor})
            self.assertAlmostEqual(vec[0], expected, places=2, msg=floor)

    def test_amenity_flags(self):
        vec = buyer_vector({"must_have": ["hawker", "park"]})
        # AMENITY_DIMS = ["mrt","hawker","mall","park","school","hospital"] → dims 1-6
        self.assertEqual(vec[1], 0.5)   # mrt — no preference (neutral)
        self.assertEqual(vec[2], 1.0)   # hawker — must-have
        self.assertEqual(vec[3], 0.5)   # mall — no preference (neutral)
        self.assertEqual(vec[4], 1.0)   # park — must-have
        self.assertEqual(vec[5], 0.5)   # school — no preference
        self.assertEqual(vec[6], 0.5)   # hospital — no preference



class TestFlatVector(unittest.TestCase):

    def test_length(self):
        vec = flat_vector(PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        self.assertEqual(len(vec), 7)

    def test_all_in_range(self):
        vec = flat_vector(PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        for i, v in enumerate(vec):
            self.assertGreaterEqual(v, 0.0, f"dim {i} < 0")
            self.assertLessEqual(v, 1.0,    f"dim {i} > 1")

    def test_nearby_mrt_dim1(self):
        # dist_km=0.30, max_km=1.0, fallback proximity: 1 - 0.30/1.0 = 0.70
        vec = flat_vector(PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        self.assertAlmostEqual(vec[1], 0.70, places=3)

    def test_poor_amenities_score_zero(self):
        vec = flat_vector(PRICE_DATA_WOODLANDS, AMENITIES_POOR)
        # All amenities beyond max_km → all scores 0.0
        for dim in range(1, 7):
            self.assertAlmostEqual(vec[dim], 0.0, places=3, msg=f"dim {dim}")

    def test_missing_amenity_key_scores_neutral(self):
        vec = flat_vector(PRICE_DATA_WOODLANDS, AMENITIES_SPARSE)
        self.assertEqual(vec[2], 0.5)   # hawker has no dist_km → neutral
        self.assertEqual(vec[3], 0.5)   # mall missing entirely → neutral
        self.assertEqual(vec[6], 0.5)   # hospital missing entirely → neutral

    def test_dim1_is_mrt_not_hawker(self):
        # Regression: verify amenity dimension order is correct
        amenities = {
            "mrt":    {"dist_km": 0.10, "walk_mins": 1.2},   # should be dim 1, score≈0.9
            "hawker": {"dist_km": 0.90, "walk_mins": 10.8},  # should be dim 2, score≈0.1
        }
        vec = flat_vector(PRICE_DATA_WOODLANDS, amenities)
        self.assertGreater(vec[1], vec[2], "dim 1 (mrt, close) should outscore dim 2 (hawker, far)")


class TestDetectActiveCriteria(unittest.TestCase):

    def test_all_defaults_no_active_criteria(self):
        active = _active(PROFILE_DEFAULT, budget=0)
        self.assertEqual(active, [])

    def test_budget_activates(self):
        active = _active(PROFILE_DEFAULT, budget=500000)
        self.assertIn(CRITERION_BUDGET, active)

    def test_ftype_non_any_activates(self):
        active = _active({"ftype": "4 ROOM"})
        self.assertIn(CRITERION_FLAT, active)

    def test_ftype_any_does_not_activate(self):
        active = _active({"ftype": "any"})
        self.assertNotIn(CRITERION_FLAT, active)

    def test_region_activates(self):
        active = _active({"regions": ["north"]})
        self.assertIn(CRITERION_REGION, active)

    def test_must_have_activates_amenity(self):
        active = _active({"must_have": ["hawker"]})
        self.assertIn(CRITERION_AMENITY, active)

    def test_all_active(self):
        active = _active(PROFILE_ACTIVE, budget=600000)
        self.assertIn(CRITERION_BUDGET,  active)
        self.assertIn(CRITERION_FLAT,    active)
        self.assertIn(CRITERION_REGION,  active)
        self.assertIn(CRITERION_AMENITY, active)


class TestWeightMapping(unittest.TestCase):
    """Verify _DIM_CRITERION maps each 7-dim vector slot to the correct criterion."""

    def test_dim_criterion_length_matches_vector(self):
        from cosine_scorer import _DIM_CRITERION
        self.assertEqual(len(_DIM_CRITERION), 7,
                         "_DIM_CRITERION must have exactly 7 entries (one per vector dim)")

    def test_amenity_dims_use_amenity_criterion(self):
        """Dims 1-6 (all amenity slots) must map to CRITERION_AMENITY."""
        from cosine_scorer import _DIM_CRITERION
        for dim in range(1, 7):
            self.assertEqual(_DIM_CRITERION[dim], CRITERION_AMENITY,
                             f"dim {dim} should be CRITERION_AMENITY, got {_DIM_CRITERION[dim]}")

    def test_mrt_weight_follows_amenity_not_region(self):
        """Regression: MRT dim (1) must get ACTIVE_WEIGHT when CRITERION_AMENITY
        is active, regardless of whether CRITERION_REGION is active."""
        from cosine_scorer import _build_weight_vector
        w = _build_weight_vector([CRITERION_AMENITY])
        self.assertEqual(w[1], ACTIVE_WEIGHT,
                         "MRT dim should be weighted by amenity, not region")


class TestScoreCb(unittest.TestCase):

    def test_identical_vectors_score_one(self):
        vec = buyer_vector(PROFILE_ACTIVE)
        active = _active(PROFILE_ACTIVE, budget=600000)
        score = score_cb(vec, vec, active)
        self.assertAlmostEqual(score, 1.0, places=3)

    def test_score_in_range(self):
        b_vec = buyer_vector(PROFILE_ACTIVE)
        f_vec = flat_vector(PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        active = _active(PROFILE_ACTIVE, budget=600000)
        score = score_cb(b_vec, f_vec, active)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_good_amenities_beats_poor(self):
        b_vec = buyer_vector(PROFILE_ACTIVE)
        active = _active(PROFILE_ACTIVE, budget=600000)
        f_good = flat_vector(PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        f_poor = flat_vector(PRICE_DATA_WOODLANDS, AMENITIES_POOR)
        self.assertGreater(score_cb(b_vec, f_good, active),
                           score_cb(b_vec, f_poor, active))

    def test_no_active_criteria_still_returns_score(self):
        # With all defaults, all dims weighted 0.25 — score still valid
        b_vec  = buyer_vector(PROFILE_DEFAULT)
        f_vec  = flat_vector(PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        active = []
        score  = score_cb(b_vec, f_vec, active)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_zero_vector_returns_zero(self):
        zero = [0.0] * 7
        score = score_cb(zero, zero, [CRITERION_FLAT])
        self.assertAlmostEqual(score, 0.0)


class TestScorePayload(unittest.TestCase):
    """Integration test: run full pipeline via score_payload()."""

    def _run(self, payload: dict) -> dict:
        from scorer import score_payload
        return score_payload(payload)

    def test_full_pipeline_active_buyer(self):
        payload = {
            "profile":    PROFILE_ACTIVE,
            "price_data": PRICE_DATA_WOODLANDS,
            "amenities":  AMENITIES_GOOD,
            "budget":     600000,
            "must_have":  PROFILE_ACTIVE["must_have"],
            "regions":    PROFILE_ACTIVE["regions"],
        }
        out = self._run(payload)
        self.assertIn("score", out)
        self.assertIn("active_criteria", out)
        self.assertGreaterEqual(out["score"], 0.0)
        self.assertLessEqual(out["score"], 1.0)
        self.assertIn(CRITERION_AMENITY, out["active_criteria"])

    def test_full_pipeline_default_buyer(self):
        payload = {
            "profile":    PROFILE_DEFAULT,
            "price_data": PRICE_DATA_WOODLANDS,
            "amenities":  AMENITIES_GOOD,
            "budget":     0,
            "must_have":  [],
            "regions":    [],
        }
        out = self._run(payload)
        self.assertEqual(out["active_criteria"], [])
        self.assertGreaterEqual(out["score"], 0.0)

    def test_full_pipeline_sparse_amenities(self):
        payload = {
            "profile":    PROFILE_ACTIVE,
            "price_data": PRICE_DATA_WOODLANDS,
            "amenities":  AMENITIES_SPARSE,
            "budget":     400000,
            "must_have":  ["hawker"],
            "regions":    ["north"],
        }
        out = self._run(payload)
        self.assertIn("score", out)
        self.assertGreaterEqual(out["score"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
