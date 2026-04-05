"""
estate_finder_service/queries.py
=============
All SQL queries in one place. No business logic here.
Returns Hard filters for recommendation scorer to apply on the candidate list of towns, and reduce solution space.
"""

from datetime import datetime, timedelta
from db.connection import get_conn #to get from data service db connection


def get_all_towns() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT town FROM resale_transactions ORDER BY town"
        ).fetchall()
    return [r["town"] for r in rows]


def get_transactions_for_town(town: str, ftype: str,
                               months: int = 14) -> list[dict]:
    """
    Return resale transactions for a town + flat type within the last N months.
    Outlier removal: exclude prices > 3 std deviations from town median.
    """
    cutoff = (datetime.now() - timedelta(days=months * 30.5)).strftime("%Y-%m")

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT resale_price, floor_area_sqm, month, storey_range
            FROM resale_transactions
            WHERE town = ?
              AND flat_type = ?
              AND month >= ?
            ORDER BY month DESC
        """, (town, ftype, cutoff)).fetchall()

    if not rows:
        return []

    records = [dict(r) for r in rows]

    # ── Outlier removal (±3 std dev from median) ─────────────────────────────
    prices = [r["resale_price"] for r in records]
    if len(prices) >= 5:
        import statistics
        med = statistics.median(prices)
        std = statistics.stdev(prices)
        records = [r for r in records
                   if abs(r["resale_price"] - med) <= 3 * std]

    return records


def get_price_trend(town: str, ftype: str) -> dict:
    """
    Return monthly median prices for the last 24 months for Trends tab.
    """
    cutoff = (datetime.now() - timedelta(days=24 * 30.5)).strftime("%Y-%m")

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT month, resale_price
            FROM resale_transactions
            WHERE town = ? AND flat_type = ? AND month >= ?
            ORDER BY month
        """, (town, ftype, cutoff)).fetchall()

    if not rows:
        return {"town": town, "ftype": ftype, "months": [], "medians": []}

    # Group by month
    from collections import defaultdict
    import statistics
    monthly: dict[str, list] = defaultdict(list)
    for r in rows:
        monthly[r["month"]].append(r["resale_price"])

    months  = sorted(monthly.keys())
    medians = [int(statistics.median(monthly[m])) for m in months]

    return {
        "town":    town,
        "ftype":   ftype,
        "months":  months,
        "medians": medians,
        "n":       len(rows),
    }


def get_latest_data_date() -> str | None:
    """Return the most recent transaction month in the DB."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(month) as latest FROM resale_transactions"
        ).fetchone()
    return row["latest"] if row else None
