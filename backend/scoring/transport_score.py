"""
scoring/transport_score.py
==========================
Walking distance to nearest MRT station.

Returns a raw score 0.0 – 1.0.
The aggregator scales this by the dynamically computed MCDM weight.

Note: MRT criterion is active when buyer set max_mrt_mins < 30 (default ceiling).
This score is also used as the MRT sub-component within serendipity.
"""


def raw(amenities: dict) -> float:
    """Returns 0.0–1.0 MRT proximity score."""
    walk_mins = amenities.get("mrt", {}).get("walk_mins", 999)

    if   walk_mins <=  5: return 1.00
    elif walk_mins <= 10: return 0.85
    elif walk_mins <= 15: return 0.65
    elif walk_mins <= 20: return 0.45
    elif walk_mins <= 30: return 0.20
    else:                 return 0.00
