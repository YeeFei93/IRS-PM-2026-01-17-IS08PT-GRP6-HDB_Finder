"""
core/prices.py
==============
Price analysis and forward estimation.
Reads from SQLite (via db/queries.py) — no direct CSV I/O here.
"""

import statistics
from db.queries import get_transactions_for_town


def analyse_town_prices(town: str, ftype: str, months: int = 14) -> dict | None:
    """
    Analyse recent resale transactions for a town + flat type.

    Returns a price summary dict, or None if insufficient data.
    """
    rows = get_transactions_for_town(town, ftype, months=months)

    if len(rows) < 3:
        # Try 24-month fallback
        rows = get_transactions_for_town(town, ftype, months=24)
        if len(rows) < 3:
            return None

    prices = sorted(r["resale_price"] for r in rows)
    n = len(prices)

    median  = statistics.median(prices)
    mean    = statistics.mean(prices)
    p25     = prices[int(n * 0.25)]
    p75     = prices[int(n * 0.75)]
    areas   = [r["floor_area_sqm"] for r in rows if r["floor_area_sqm"] > 0]
    avg_area = round(statistics.mean(areas), 1) if areas else 0
    psm     = round(median / avg_area) if avg_area else 0

    # ── Average storey (midpoint of storey_range strings) ────────────────────
    def _storey_mid(s: str) -> float | None:
        try:
            parts = s.upper().replace("TO", " ").split()
            nums = [int(p) for p in parts if p.isdigit()]
            if len(nums) >= 2:
                return (nums[0] + nums[1]) / 2.0
            if len(nums) == 1:
                return float(nums[0])
        except (ValueError, AttributeError):
            pass
        return None

    storey_vals = [
        v for r in rows
        if (v := _storey_mid(r.get("storey_range", ""))) is not None
    ]
    avg_storey = round(statistics.mean(storey_vals), 1) if storey_vals else 5.0

    # ── Average remaining lease (years) ──────────────────────────────────────
    def _lease_years(val) -> float | None:
        if isinstance(val, (int, float)) and val > 0:
            return float(val)
        if isinstance(val, str):
            s = val.lower()
            try:
                yr = float(s.split("year")[0].strip()) if "year" in s else 0.0
                mo_str = s.split("month")[0].strip().split()[-1] if "month" in s else "0"
                mo = float(mo_str) / 12.0
                total = yr + mo
                return total if total > 0 else None
            except (ValueError, IndexError):
                pass
        return None

    lease_vals = [
        v for r in rows
        if (v := _lease_years(r.get("remaining_lease"))) is not None
    ]
    avg_lease_years = round(statistics.mean(lease_vals), 1) if lease_vals else 60.0

    # ── 12-month trend: compare first-half vs second-half median ─────────────
    trend_pct = 0.0
    if n >= 8:
        mid = n // 2
        old_med = statistics.median(prices[:mid])
        new_med = statistics.median(prices[mid:])
        if old_med > 0:
            trend_pct = round((new_med - old_med) / old_med * 100, 1)

    # ── Forward estimate: project 3–6 months ahead using trend ───────────────
    projection_factor = 1 + (trend_pct / 100) * 0.5   # half the annual trend
    est_low  = round(p25 * projection_factor / 1000) * 1000
    est_high = round(p75 * projection_factor / 1000) * 1000

    low_confidence = n < 5
    months_used = 24 if len(get_transactions_for_town(town, ftype, months=14)) < 3 else 14

    return {
        "town":         town,
        "ftype":        ftype,
        "n":            n,
        "median":       int(median),
        "mean":         int(mean),
        "p25":          int(p25),
        "p75":          int(p75),
        "psm":          psm,
        "avg_area":     avg_area,
        "avg_storey":   avg_storey,
        "avg_lease_years": avg_lease_years,
        "trend_pct":    trend_pct,
        "est_low":      est_low,
        "est_high":     est_high,
        "low_confidence": low_confidence,
        "months_used":  months_used,
        "data_note":    (
            f"⚠️ Low confidence — only {n} transactions in last {months_used} months."
            if low_confidence else
            f"Based on {n} transactions over last {months_used} months."
        ),
    }


def effective_budget(profile: dict, grants: dict) -> float:
    """
    Compute total purchasing power:
    cash + CPF savings + all grants + estimated loan capacity.
    """
    from core.loan import loan_capacity
    cash   = profile.get("cash", 0)
    cpf    = profile.get("cpf", 0)
    loan_m = profile.get("loan", 0)   # monthly repayment
    loan_cap = loan_capacity(loan_m)

    return cash + cpf + grants["total"] + min(loan_cap, 750_000)
