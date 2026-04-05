"""
core/loan.py
============
HDB concessionary loan capacity calculator.
Rate: 2.6% p.a. (HDB rate = CPF OA rate + 0.1%)
"""


def loan_capacity(monthly_repayment: float,
                  rate_annual: float = 0.026,
                  years: int = 25) -> float:
    """
    Given a maximum monthly repayment amount, return the
    maximum loan principal using standard annuity formula.
    """
    if monthly_repayment <= 0:
        return 0.0
    r = rate_annual / 12
    n = years * 12
    factor = ((1 + r) ** n - 1) / (r * (1 + r) ** n)
    return round(monthly_repayment * factor)
