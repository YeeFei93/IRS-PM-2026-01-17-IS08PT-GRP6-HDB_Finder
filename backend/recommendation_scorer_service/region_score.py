"""
scoring/region_score.py
========================
Alignment between estate town and buyer's preferred regions.

Returns a raw score 0.0 – 1.0.
The aggregator scales this by the dynamically computed MCDM weight.
"""

REGIONS = {
    "North":   ["ANG MO KIO","SEMBAWANG","WOODLANDS","YISHUN","SENGKANG","PUNGGOL"],
    "South":   ["BUONA VISTA","QUEENSTOWN","TOA PAYOH","BISHAN","GEYLANG","KALLANG"],
    "East":    ["BEDOK","PASIR RIS","TAMPINES","HOUGANG","SERANGOON"],
    "West":    ["BUKIT BATOK","BUKIT PANJANG","CHOA CHU KANG","CLEMENTI","JURONG EAST","JURONG WEST"],
    "Central": ["CENTRAL AREA","BUKIT MERAH","MARINE PARADE"],
}


def raw(town: str, preferred_regions: list) -> float:
    """
    Returns 1.0 if town is in a preferred region, 0.0 otherwise.
    If no preference set (serendipity use), returns 0.5 for all towns
    so no estate is unfairly penalised.
    """
    if not preferred_regions:
        return 0.5   # neutral — no stated preference

    for region in preferred_regions:
        if town in REGIONS.get(region, []):
            return 1.0
    return 0.0
