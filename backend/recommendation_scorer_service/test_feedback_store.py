import os
import sys
import math
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

for path in (CURRENT_DIR, BACKEND_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from feedback_store import _parse_top_k_snapshot, calculate_model_evaluations


class TestTopKSnapshotParsing(unittest.TestCase):
    def test_parse_top_k_snapshot_filters_invalid_entries(self):
        parsed = _parse_top_k_snapshot(
            [
                {"resale_flat_id": "flat-1", "position": 1},
                {"resale_flat_id": "flat-1", "position": 2},
                {"resale_flat_id": "flat-2", "position": 1},
                {"resale_flat_id": "flat-3", "position": 11},
                {"resale_flat_id": "flat-4"},
                {"position": 5},
                "not-a-dict",
            ]
        )

        self.assertEqual(
            parsed,
            [
                {"resale_flat_id": "flat-1", "position": 1},
                {"resale_flat_id": "flat-4", "position": 5},
            ],
        )


class TestModelEvaluations(unittest.TestCase):
    def test_calculates_precision_recall_ndcg_and_favourite_rate_at_10(self):
        metrics = calculate_model_evaluations(
            [
                {
                    "session_id": "session-1",
                    "recommendation": "euclidean_distance",
                    "resale_flat_id": "flat-1",
                    "position": 1,
                    "user_view_count": 1,
                    "user_like_count": 0,
                },
                {
                    "session_id": "session-1",
                    "recommendation": "euclidean_distance",
                    "resale_flat_id": "flat-2",
                    "position": 2,
                    "user_view_count": 1,
                    "user_like_count": 1,
                },
                {
                    "session_id": "session-1",
                    "recommendation": "euclidean_distance",
                    "resale_flat_id": "flat-3",
                    "position": 3,
                    "user_view_count": 1,
                    "user_like_count": 0,
                },
            ]
        )

        euclidean = next(
            item for item in metrics if item["recommendation"] == "euclidean_distance"
        )

        self.assertEqual(euclidean["sessions"], 1)
        self.assertAlmostEqual(euclidean["precision_score"], 0.1, places=6)
        self.assertAlmostEqual(euclidean["recall_score"], 1.0, places=6)
        self.assertAlmostEqual(
            euclidean["ndcg_score"],
            1.0 / math.log2(3),
            places=6,
        )
        self.assertEqual(euclidean["viewed_flats"], 3)
        self.assertEqual(euclidean["favourited_flats"], 1)
        self.assertAlmostEqual(euclidean["favourite_rate"], 1 / 3, places=6)

    def test_recall_uses_all_favourites_even_when_not_in_top_10(self):
        metrics = calculate_model_evaluations(
            [
                {
                    "session_id": "session-2",
                    "recommendation": "weighted_cosine",
                    "resale_flat_id": "flat-1",
                    "position": 1,
                    "user_view_count": 1,
                    "user_like_count": 0,
                },
                {
                    "session_id": "session-2",
                    "recommendation": "weighted_cosine",
                    "resale_flat_id": "flat-2",
                    "position": 2,
                    "user_view_count": 1,
                    "user_like_count": 0,
                },
                {
                    "session_id": "session-2",
                    "recommendation": "weighted_cosine",
                    "resale_flat_id": "flat-3",
                    "position": 3,
                    "user_view_count": 1,
                    "user_like_count": 0,
                },
                {
                    "session_id": "session-2",
                    "recommendation": "weighted_cosine",
                    "resale_flat_id": "flat-outside-top-10",
                    "position": None,
                    "user_view_count": 1,
                    "user_like_count": 1,
                },
            ]
        )

        weighted = next(
            item for item in metrics if item["recommendation"] == "weighted_cosine"
        )

        self.assertEqual(weighted["sessions"], 1)
        self.assertAlmostEqual(weighted["precision_score"], 0.0, places=6)
        self.assertAlmostEqual(weighted["recall_score"], 0.0, places=6)
        self.assertAlmostEqual(weighted["ndcg_score"], 0.0, places=6)
        self.assertEqual(weighted["viewed_flats"], 4)
        self.assertEqual(weighted["favourited_flats"], 1)
        self.assertAlmostEqual(weighted["favourite_rate"], 0.25, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
