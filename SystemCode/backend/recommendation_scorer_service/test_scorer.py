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
    CRITERION_BUDGET, CRITERION_FLAT, CRITERION_FLOOR, CRITERION_REGION,
    CRITERION_MRT, CRITERION_HAWKER, CRITERION_MALL,
    CRITERION_PARK, CRITERION_SCHOOL, CRITERION_HOSPITAL,
    AMENITY_CRITERIA,
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
    floor = profile.get("floor", profile.get("floor_pref", "any"))
    if floor != DEFAULTS[CRITERION_FLOOR]:
        active.append(CRITERION_FLOOR)
    if regions:
        active.append(CRITERION_REGION)
    must_set = set(must_have) if must_have else set()
    for crit in AMENITY_CRITERIA:
        if crit in must_set:
            active.append(crit)
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

    def test_must_have_activates_individual_amenity(self):
        active = _active({"must_have": ["hawker"]})
        self.assertIn(CRITERION_HAWKER, active)
        self.assertNotIn(CRITERION_MRT, active)
        self.assertNotIn(CRITERION_MALL, active)

    def test_multiple_must_haves_activate_each(self):
        active = _active({"must_have": ["hawker", "mrt", "school"]})
        self.assertIn(CRITERION_HAWKER, active)
        self.assertIn(CRITERION_MRT, active)
        self.assertIn(CRITERION_SCHOOL, active)
        self.assertNotIn(CRITERION_MALL, active)
        self.assertNotIn(CRITERION_PARK, active)
        self.assertNotIn(CRITERION_HOSPITAL, active)

    def test_all_active(self):
        profile = {
            "ftype": "4 ROOM", "regions": ["north"], "floor": "mid",
            "min_lease": 70,
            "must_have": ["mrt", "hawker", "mall", "park", "school", "hospital"],
        }
        active = _active(profile, budget=600000)
        self.assertIn(CRITERION_BUDGET,   active)
        self.assertIn(CRITERION_FLAT,     active)
        self.assertIn(CRITERION_FLOOR,    active)
        self.assertIn(CRITERION_REGION,   active)
        for crit in AMENITY_CRITERIA:
            self.assertIn(crit, active)

    def test_floor_mid_activates(self):
        active = _active({"floor": "mid"})
        self.assertIn(CRITERION_FLOOR, active)

    def test_floor_any_does_not_activate(self):
        active = _active({"floor": "any"})
        self.assertNotIn(CRITERION_FLOOR, active)

    def test_ftype_without_floor_does_not_activate_floor(self):
        """Picking a flat type should NOT activate floor preference."""
        active = _active({"ftype": "4 ROOM", "floor": "any"})
        self.assertIn(CRITERION_FLAT, active)
        self.assertNotIn(CRITERION_FLOOR, active)


class TestWeightMapping(unittest.TestCase):
    """Verify _DIM_CRITERION maps each 7-dim vector slot to the correct criterion."""

    def test_dim_criterion_length_matches_vector(self):
        from cosine_scorer import _DIM_CRITERION
        self.assertEqual(len(_DIM_CRITERION), 7,
                         "_DIM_CRITERION must have exactly 7 entries (one per vector dim)")

    def test_floor_dim_uses_floor_criterion(self):
        """Dim 0 (floor) must map to CRITERION_FLOOR, not CRITERION_FLAT."""
        from cosine_scorer import _DIM_CRITERION
        self.assertEqual(_DIM_CRITERION[0], CRITERION_FLOOR,
                         "dim 0 should be CRITERION_FLOOR, not CRITERION_FLAT")

    def test_amenity_dims_use_per_amenity_criteria(self):
        """Each amenity dim maps to its own criterion."""
        from cosine_scorer import _DIM_CRITERION
        expected = [CRITERION_MRT, CRITERION_HAWKER, CRITERION_MALL,
                    CRITERION_PARK, CRITERION_SCHOOL, CRITERION_HOSPITAL]
        for dim, exp in zip(range(1, 7), expected):
            self.assertEqual(_DIM_CRITERION[dim], exp,
                             f"dim {dim} should be {exp}, got {_DIM_CRITERION[dim]}")

    def test_mrt_weight_active_only_when_mrt_must_have(self):
        """MRT dim (1) should only get ACTIVE_WEIGHT when CRITERION_MRT is active."""
        from cosine_scorer import _build_weight_vector
        # Only hawker is must-have → MRT should be inactive
        w = _build_weight_vector([CRITERION_HAWKER])
        self.assertEqual(w[1], INACTIVE_WEIGHT,
                         "MRT dim should be inactive when only hawker is must-have")
        # MRT is must-have → MRT should be active
        w2 = _build_weight_vector([CRITERION_MRT])
        self.assertEqual(w2[1], ACTIVE_WEIGHT,
                         "MRT dim should be active when MRT is must-have")

    def test_floor_weight_inactive_when_floor_any(self):
        """Floor dim must get INACTIVE_WEIGHT when only flat type is active (floor=any)."""
        from cosine_scorer import _build_weight_vector
        w = _build_weight_vector([CRITERION_FLAT])  # flat type active, floor NOT active
        self.assertEqual(w[0], INACTIVE_WEIGHT,
                         "Floor dim should be inactive when only flat type is selected")

    def test_floor_weight_active_when_floor_specified(self):
        """Floor dim must get ACTIVE_WEIGHT when CRITERION_FLOOR is active."""
        from cosine_scorer import _build_weight_vector
        w = _build_weight_vector([CRITERION_FLOOR])
        self.assertEqual(w[0], ACTIVE_WEIGHT,
                         "Floor dim should be active when floor preference is set")


class TestScoreCb(unittest.TestCase):

    def test_identical_vectors_score_one(self):
        """Identical vectors with ALL dims active → perfect score 1.0."""
        vec = buyer_vector(PROFILE_ACTIVE)
        # PROFILE_ACTIVE has floor=mid + hawker only → 2/7 active → coverage < 1.0
        # Use all dims active to get perfect 1.0
        active = [CRITERION_FLOOR] + list(AMENITY_CRITERIA)
        score = score_cb(vec, vec, active)
        self.assertAlmostEqual(score, 1.0, places=3)

    def test_identical_vectors_partial_active(self):
        """Identical vectors with only 2/7 dims active → coverage scales down."""
        vec = buyer_vector(PROFILE_ACTIVE)
        active = _active(PROFILE_ACTIVE, budget=600000)  # floor + hawker = 2 dims
        score = score_cb(vec, vec, active)
        # coverage = 0.4 + 0.6 * (2/7) ≈ 0.571
        self.assertAlmostEqual(score, 0.571, places=2)
        self.assertLess(score, 1.0)

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

    def test_no_active_dims_scores_lower_than_all_active(self):
        """With no active vector dims (floor=any, no must-haves), coverage
        factor should produce a substantially lower score than with all active."""
        f_vec = flat_vector(PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        # All defaults: floor=any, no must-haves → 0 active dims
        b_default = buyer_vector(PROFILE_DEFAULT)
        score_none = score_cb(b_default, f_vec, [])
        # All active: floor=mid, all amenities → 7 active dims
        b_active = buyer_vector(PROFILE_ACTIVE)
        active_all = [CRITERION_FLOOR] + list(AMENITY_CRITERIA)
        score_all = score_cb(b_active, f_vec, active_all)
        # Score with no preferences should be meaningfully lower
        self.assertLess(score_none, score_all * 0.7,
                        "No-preference score should be well below full-preference score")

    def test_coverage_factor_zero_active_dims_caps_at_40pct(self):
        """With 0 active vector dims, max possible score should be ~0.40."""
        from cosine_scorer import COVERAGE_FLOOR
        # Identical vectors → raw cosine=1.0, but coverage scales it down
        vec = buyer_vector(PROFILE_DEFAULT)
        score = score_cb(vec, vec, [])
        self.assertAlmostEqual(score, COVERAGE_FLOOR, places=2,
                               msg=f"0 active dims should cap score at ~{COVERAGE_FLOOR}")

    def test_coverage_factor_all_active_dims_no_change(self):
        """With all 7 vector dims active, coverage factor should be 1.0."""
        vec = buyer_vector(PROFILE_ACTIVE)
        active = [CRITERION_FLOOR] + list(AMENITY_CRITERIA)
        score = score_cb(vec, vec, active)
        self.assertAlmostEqual(score, 1.0, places=3,
                               msg="All active dims should produce coverage=1.0")


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
        self.assertIn(CRITERION_HAWKER, out["active_criteria"])

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

    def test_budget_reward_boosts_cheap_flat(self):
        """A flat at 80% of budget should score higher than one at 100%."""
        base = {
            "profile":    PROFILE_ACTIVE,
            "price_data": PRICE_DATA_WOODLANDS,
            "amenities":  AMENITIES_GOOD,
            "budget":     600000,
            "must_have":  PROFILE_ACTIVE["must_have"],
            "regions":    PROFILE_ACTIVE["regions"],
        }
        out_cheap  = self._run({**base, "resale_price": 480000})  # 80% of budget
        out_at100  = self._run({**base, "resale_price": 600000})  # 100% of budget
        self.assertGreater(out_cheap["score"], out_at100["score"],
                           "Cheaper flat should score higher due to budget reward")

    def test_budget_penalty_lowers_over_budget(self):
        """A flat at 103% of budget should score lower than one at 100%."""
        base = {
            "profile":    PROFILE_ACTIVE,
            "price_data": PRICE_DATA_WOODLANDS,
            "amenities":  AMENITIES_GOOD,
            "budget":     600000,
            "must_have":  PROFILE_ACTIVE["must_have"],
            "regions":    PROFILE_ACTIVE["regions"],
        }
        out_at100  = self._run({**base, "resale_price": 600000})  # 100%
        out_over   = self._run({**base, "resale_price": 618000})  # 103%
        self.assertGreater(out_at100["score"], out_over["score"],
                           "Over-budget flat should score lower")

    def test_reward_decreases_under_budget(self):
        """Flats further under budget should get more reward."""
        base = {
            "profile":    PROFILE_ACTIVE,
            "price_data": PRICE_DATA_WOODLANDS,
            "amenities":  AMENITIES_GOOD,
            "budget":     600000,
            "must_have":  PROFILE_ACTIVE["must_have"],
            "regions":    PROFILE_ACTIVE["regions"],
        }
        out_very_cheap = self._run({**base, "resale_price": 420000})  # 70%
        out_cheap      = self._run({**base, "resale_price": 510000})  # 85%
        out_at95       = self._run({**base, "resale_price": 570000})  # 95%
        self.assertGreater(out_very_cheap["score"], out_cheap["score"])
        self.assertGreater(out_cheap["score"], out_at95["score"])

    def test_no_adjustment_without_resale_price(self):
        """Without resale_price in payload, score equals raw cosine similarity."""
        payload = {
            "profile":    PROFILE_ACTIVE,
            "price_data": PRICE_DATA_WOODLANDS,
            "amenities":  AMENITIES_GOOD,
            "budget":     600000,
            "must_have":  PROFILE_ACTIVE["must_have"],
            "regions":    PROFILE_ACTIVE["regions"],
        }
        out_no_price = self._run(payload)
        # With price at exactly 100%, adjustment is 0 → same score
        out_at100    = self._run({**payload, "resale_price": 600000})
        self.assertEqual(out_no_price["score"], out_at100["score"])


class TestBudgetAdjustment(unittest.TestCase):
    """Unit tests for _budget_adjustment()."""

    def setUp(self):
        from scorer import _budget_adjustment
        self.adj = _budget_adjustment

    def test_zero_budget_no_adjustment(self):
        self.assertEqual(self.adj(500000, 0), 0.0)

    def test_zero_price_no_adjustment(self):
        self.assertEqual(self.adj(0, 600000), 0.0)

    def test_well_under_budget_full_reward(self):
        # 60% of budget → max reward
        self.assertAlmostEqual(self.adj(360000, 600000), 0.05, places=3)

    def test_exactly_70_pct_full_reward(self):
        self.assertAlmostEqual(self.adj(420000, 600000), 0.05, places=3)

    def test_85_pct_half_reward(self):
        # 85% is midpoint of 70-100% range → ~50% of max reward
        adj = self.adj(510000, 600000)
        self.assertAlmostEqual(adj, 0.025, places=3)

    def test_exactly_100_pct_zero(self):
        self.assertAlmostEqual(self.adj(600000, 600000), 0.0, places=3)

    def test_exactly_105_pct_full_penalty(self):
        adj = self.adj(630000, 600000)
        self.assertAlmostEqual(adj, -0.05, places=3)

    def test_beyond_105_pct_capped(self):
        adj = self.adj(700000, 600000)
        self.assertAlmostEqual(adj, -0.05, places=3)

    def test_adjustment_decreases_monotonically(self):
        budget = 600000
        prev = 1.0  # start high
        for pct in [0.60, 0.70, 0.80, 0.90, 1.00, 1.02, 1.05, 1.10]:
            adj = self.adj(budget * pct, budget)
            self.assertLessEqual(adj, prev, f"adjustment should decrease at {pct}")
            prev = adj


if __name__ == "__main__":
    unittest.main(verbosity=2)
