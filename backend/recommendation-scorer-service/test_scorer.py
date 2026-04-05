"""
recommendation-scorer-service/test_scorer.py
=============================================
Unit + integration tests using sample data.
Run:  python test_scorer.py
"""

import math
import sys
import json
import io
import unittest
from unittest.mock import patch

from vectorizer import buyer_vector, flat_vector, FLAT_TYPE_ORD, AMENITY_DIMS
from cosine_scorer import score_cb, ACTIVE_WEIGHT, INACTIVE_WEIGHT
from weights import (
    CRITERION_BUDGET, CRITERION_FLAT, CRITERION_REGION,
    CRITERION_LEASE, CRITERION_MRT, CRITERION_AMENITY,
    DEFAULTS,
)

# ── Sample data ──────────────────────────────────────────────────────────────

# Buyer who wants a 4-room flat in the north, close MRT, hawker must-have
PROFILE_ACTIVE = {
    "ftype":        "4 ROOM",
    "regions":      ["north"],
    "floor":        "mid",
    "min_lease":    70,          # > 60 → lease criterion active
    "max_mrt_mins": 10,          # < 30 → mrt criterion active
    "must_have":    ["hawker"],
}

# Buyer with all defaults — no stated preferences
PROFILE_DEFAULT = {
    "ftype":        "any",
    "regions":      [],
    "floor":        "any",
    "min_lease":    20,
    "max_mrt_mins": 30,
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
    """Mirrors detect_active_criteria() from app.py."""
    must_have = must_have or profile.get("must_have", [])
    regions   = regions   or profile.get("regions", [])
    active = []
    if budget > 0:
        active.append(CRITERION_BUDGET)
    if profile.get("ftype", DEFAULTS[CRITERION_FLAT]) != DEFAULTS[CRITERION_FLAT]:
        active.append(CRITERION_FLAT)
    if regions:
        active.append(CRITERION_REGION)
    if profile.get("min_lease", DEFAULTS[CRITERION_LEASE]) > DEFAULTS[CRITERION_LEASE]:
        active.append(CRITERION_LEASE)
    if profile.get("max_mrt_mins", DEFAULTS[CRITERION_MRT]) < DEFAULTS[CRITERION_MRT]:
        active.append(CRITERION_MRT)
    if must_have:
        active.append(CRITERION_AMENITY)
    return active


# ── Test cases ────────────────────────────────────────────────────────────────

class TestBuyerVector(unittest.TestCase):

    def test_length(self):
        vec = buyer_vector(PROFILE_ACTIVE)
        self.assertEqual(len(vec), 10)

    def test_all_in_range(self):
        for profile in [PROFILE_ACTIVE, PROFILE_DEFAULT]:
            vec = buyer_vector(profile)
            for i, v in enumerate(vec):
                self.assertGreaterEqual(v, 0.0, f"dim {i} < 0")
                self.assertLessEqual(v, 1.0,    f"dim {i} > 1")

    def test_flat_type_encoding(self):
        vec = buyer_vector({"ftype": "4 ROOM"})
        self.assertAlmostEqual(vec[0], FLAT_TYPE_ORD["4 ROOM"])

    def test_flat_type_all_keys(self):
        for ftype in ["1 ROOM", "2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE", "MULTI-GENERATION"]:
            vec = buyer_vector({"ftype": ftype})
            self.assertAlmostEqual(vec[0], FLAT_TYPE_ORD[ftype], msg=ftype)

    def test_flat_type_ordering(self):
        # Each successive type must have a strictly higher ordinal
        types = ["1 ROOM", "2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE", "MULTI-GENERATION"]
        vals = [FLAT_TYPE_ORD[t] for t in types]
        for i in range(len(vals) - 1):
            self.assertLess(vals[i], vals[i+1], f"{types[i]} should be < {types[i+1]}")

    def test_flat_type_any_is_midpoint(self):
        # "any" and unknown types → 4/7 (true midpoint of 7-type ordinal scale)
        vec = buyer_vector({"ftype": "any"})
        self.assertAlmostEqual(vec[0], round(4/7, 4))

    def test_region_single(self):
        # any region selected → 1.0 (binary active)
        vec = buyer_vector({"regions": ["north"]})
        self.assertAlmostEqual(vec[1], 1.0)

    def test_region_multiple_averages(self):
        # multiple regions still → 1.0 (any preference stated)
        vec = buyer_vector({"regions": ["north", "east"]})
        self.assertAlmostEqual(vec[1], 1.0)

    def test_region_empty_is_midpoint(self):
        vec = buyer_vector({"regions": []})
        self.assertAlmostEqual(vec[1], 0.5)

    def test_mrt_default_is_zero(self):
        # max_mrt_mins=30 → walk_km=2.5 → score=max(0, 1-2.5)=0
        vec = buyer_vector({"max_mrt_mins": 30})
        self.assertAlmostEqual(vec[4], 0.0)

    def test_mrt_close_preference(self):
        # max_mrt_mins=6 → walk_km=0.5 → score=0.5
        vec = buyer_vector({"max_mrt_mins": 6})
        self.assertAlmostEqual(vec[4], 0.5, places=3)

    def test_mrt_very_close_preference(self):
        # max_mrt_mins=3 → walk_km=0.25 → score=0.75
        vec = buyer_vector({"max_mrt_mins": 3})
        self.assertAlmostEqual(vec[4], 0.75, places=3)

    def test_amenity_flags(self):
        vec = buyer_vector({"must_have": ["hawker", "park"]})
        # AMENITY_DIMS = ["hawker","mall","park","school","hospital"] → dims 5-9
        self.assertEqual(vec[5], 1.0)   # hawker — must-have
        self.assertEqual(vec[6], 0.5)   # mall — no preference (neutral)
        self.assertEqual(vec[7], 1.0)   # park — must-have
        self.assertEqual(vec[8], 0.5)   # school — no preference
        self.assertEqual(vec[9], 0.5)   # hospital — no preference

    def test_min_lease_encoding(self):
        vec = buyer_vector({"min_lease": 99})
        self.assertAlmostEqual(vec[3], 1.0, places=3)
        vec2 = buyer_vector({"min_lease": 20})
        self.assertAlmostEqual(vec2[3], 20/99, places=3)


class TestFlatVector(unittest.TestCase):

    def test_length(self):
        vec = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        self.assertEqual(len(vec), 10)

    def test_all_in_range(self):
        vec = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        for i, v in enumerate(vec):
            self.assertGreaterEqual(v, 0.0, f"dim {i} < 0")
            self.assertLessEqual(v, 1.0,    f"dim {i} > 1")

    def test_region_match_scores_one(self):
        vec = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, AMENITIES_GOOD, buyer_regions=["north"])
        self.assertAlmostEqual(vec[1], 1.0)   # north flat, buyer wants north → match

    def test_region_no_match_scores_zero(self):
        vec = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, AMENITIES_GOOD, buyer_regions=["central"])
        self.assertAlmostEqual(vec[1], 0.0)   # north flat, buyer wants central → no match

    def test_region_multi_buyer_match(self):
        # Woodlands is north — should match when buyer selects north+east
        vec = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, AMENITIES_GOOD, buyer_regions=["north", "east"])
        self.assertAlmostEqual(vec[1], 1.0)

    def test_region_no_buyer_preference_is_midpoint(self):
        # No buyer regions → all flats neutral 0.5
        for town, pd in [("WOODLANDS", PRICE_DATA_WOODLANDS), ("BUKIT MERAH", PRICE_DATA_BUKIT_MERAH)]:
            vec = flat_vector(town, pd, AMENITIES_GOOD, buyer_regions=[])
            self.assertAlmostEqual(vec[1], 0.5, msg=town)

    def test_unknown_town_no_buyer_preference_is_midpoint(self):
        vec = flat_vector("UNKNOWN TOWN", PRICE_DATA_WOODLANDS, AMENITIES_GOOD, buyer_regions=[])
        self.assertAlmostEqual(vec[1], 0.5)

    def test_nearby_mrt_dim4(self):
        # dist_km=0.30, max=1.0 → score=0.70
        vec = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        self.assertAlmostEqual(vec[4], 0.70, places=3)

    def test_poor_amenities_score_zero(self):
        vec = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, AMENITIES_POOR)
        # All amenities beyond max_km → all scores 0.0
        for dim in range(4, 10):
            self.assertAlmostEqual(vec[dim], 0.0, places=3, msg=f"dim {dim}")

    def test_missing_amenity_key_scores_zero(self):
        vec = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, AMENITIES_SPARSE)
        self.assertEqual(vec[5], 0.0)   # hawker has no dist_km
        self.assertEqual(vec[6], 0.0)   # mall missing entirely
        self.assertEqual(vec[9], 0.0)   # hospital missing entirely

    def test_dim4_is_mrt_not_hawker(self):
        # Regression: before fix, loop started at dim 4 with AMENITY_DIMS (no MRT)
        # causing hawker at dim 4, mall at dim 5, etc.
        amenities = {
            "mrt":    {"dist_km": 0.10, "walk_mins": 1.2},   # should be dim 4, score≈0.9
            "hawker": {"dist_km": 0.90, "walk_mins": 10.8},  # should be dim 5, score≈0.1
        }
        vec = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, amenities)
        self.assertGreater(vec[4], vec[5], "dim 4 (mrt, close) should outscore dim 5 (hawker, far)")


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

    def test_lease_above_60_activates(self):
        active = _active({"min_lease": 70})
        self.assertIn(CRITERION_LEASE, active)

    def test_lease_at_60_does_not_activate(self):
        active = _active({"min_lease": 60})
        self.assertNotIn(CRITERION_LEASE, active)

    def test_mrt_below_30_activates(self):
        active = _active({"max_mrt_mins": 10})
        self.assertIn(CRITERION_MRT, active)

    def test_mrt_at_30_does_not_activate(self):
        active = _active({"max_mrt_mins": 30})
        self.assertNotIn(CRITERION_MRT, active)

    def test_must_have_activates_amenity(self):
        active = _active({"must_have": ["hawker"]})
        self.assertIn(CRITERION_AMENITY, active)

    def test_all_active(self):
        active = _active(PROFILE_ACTIVE, budget=600000)
        self.assertIn(CRITERION_BUDGET,  active)
        self.assertIn(CRITERION_FLAT,    active)
        self.assertIn(CRITERION_REGION,  active)
        self.assertIn(CRITERION_LEASE,   active)
        self.assertIn(CRITERION_MRT,     active)
        self.assertIn(CRITERION_AMENITY, active)


class TestScoreCb(unittest.TestCase):

    def test_identical_vectors_score_one(self):
        vec = buyer_vector(PROFILE_ACTIVE)
        active = _active(PROFILE_ACTIVE, budget=600000)
        score = score_cb(vec, vec, active)
        self.assertAlmostEqual(score, 1.0, places=3)

    def test_score_in_range(self):
        b_vec = buyer_vector(PROFILE_ACTIVE)
        f_vec = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        active = _active(PROFILE_ACTIVE, budget=600000)
        score = score_cb(b_vec, f_vec, active)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_good_amenities_beats_poor(self):
        b_vec = buyer_vector(PROFILE_ACTIVE)
        active = _active(PROFILE_ACTIVE, budget=600000)
        f_good = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        f_poor = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, AMENITIES_POOR)
        self.assertGreater(score_cb(b_vec, f_good, active),
                           score_cb(b_vec, f_poor, active))

    def test_matching_region_beats_mismatched(self):
        # Buyer prefers north → Woodlands (north=match) should outscore Bukit Merah (central=no match)
        buyer_regions = ["north"]
        b_vec     = buyer_vector({"regions": buyer_regions})
        active    = _active({"regions": buyer_regions})
        f_north   = flat_vector("WOODLANDS",   PRICE_DATA_WOODLANDS,   AMENITIES_GOOD, buyer_regions=buyer_regions)
        f_central = flat_vector("BUKIT MERAH", PRICE_DATA_BUKIT_MERAH, AMENITIES_GOOD, buyer_regions=buyer_regions)
        self.assertGreater(score_cb(b_vec, f_north, active),
                           score_cb(b_vec, f_central, active))

    def test_no_active_criteria_still_returns_score(self):
        # With all defaults, all dims weighted 0.25 — score still valid
        b_vec  = buyer_vector(PROFILE_DEFAULT)
        f_vec  = flat_vector("WOODLANDS", PRICE_DATA_WOODLANDS, AMENITIES_GOOD)
        active = []
        score  = score_cb(b_vec, f_vec, active)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_zero_vector_returns_zero(self):
        zero = [0.0] * 10
        score = score_cb(zero, zero, [CRITERION_FLAT])
        self.assertAlmostEqual(score, 0.0)


class TestAppStdin(unittest.TestCase):
    """Integration test: run full app.py pipeline via subprocess stdin/stdout."""

    def _run_app(self, payload: dict) -> dict:
        import subprocess, os
        script = os.path.join(os.path.dirname(__file__), "app.py")
        result = subprocess.run(
            [sys.executable, script],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return json.loads(result.stdout.decode())

    def test_full_pipeline_active_buyer(self):
        payload = {
            "profile":    PROFILE_ACTIVE,
            "price_data": PRICE_DATA_WOODLANDS,
            "amenities":  AMENITIES_GOOD,
            "budget":     600000,
            "must_have":  PROFILE_ACTIVE["must_have"],
            "regions":    PROFILE_ACTIVE["regions"],
        }
        out = self._run_app(payload)
        self.assertIn("score", out)
        self.assertIn("active_criteria", out)
        self.assertGreaterEqual(out["score"], 0.0)
        self.assertLessEqual(out["score"], 1.0)
        self.assertIn(CRITERION_MRT,    out["active_criteria"])
        self.assertIn(CRITERION_LEASE,  out["active_criteria"])
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
        out = self._run_app(payload)
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
        out = self._run_app(payload)
        self.assertIn("score", out)
        self.assertGreaterEqual(out["score"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
