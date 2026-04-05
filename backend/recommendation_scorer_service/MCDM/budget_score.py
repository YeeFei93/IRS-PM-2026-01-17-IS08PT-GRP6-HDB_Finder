"""
recommendation_scorer_service/budget_score.py
=======================
How well the estimated flat price fits within effective budget.

Returns a raw score 0.0 – 1.0.
The aggregator scales this by the dynamically computed MCDM weight.

Scoring curve (based on median / effective_budget ratio):
  ≤ 0.70  → 1.00  (very comfortable headroom)
  ≤ 0.80  → 0.90
  ≤ 0.90  → 0.75
  ≤ 1.00  → 0.55  (right at budget)
  ≤ 1.10  → 0.25  (slightly over — still surfaced for awareness)
  > 1.10  → 0.00  (over budget)
"""


def raw(price_data: dict, budget: float) -> float:
    """Returns 0.0–1.0 budget fit score."""
    median = price_data.get("median", 0)
    if budget <= 0 or median <= 0:
        return 0.0

    ratio = median / budget

    if   ratio <= 0.70: return 1.00
    elif ratio <= 0.80: return 0.90
    elif ratio <= 0.90: return 0.75
    elif ratio <= 1.00: return 0.55
    elif ratio <= 1.10: return 0.25
    else:               return 0.00
