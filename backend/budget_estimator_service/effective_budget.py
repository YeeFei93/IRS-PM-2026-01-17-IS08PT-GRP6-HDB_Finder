
"""
budget_estimator_service/effective_budget.py

Still need to check the max loan capacity, depends on eligibility of the citizenship, single or joint again.
https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility/housing-loan/housing-loan-from-hdb
"""

def effective_budget(profile: dict, grants: dict) -> float:
    """
    Compute total purchasing power:
    cash + CPF savings + all grants + estimated loan capacity.
    """
    from budget_estimator_service.loan import loan_capacity
    cash   = profile.get("cash", 0)
    cpf    = profile.get("cpf", 0)
    loan_m = profile.get("loan", 0)   # monthly repayment
    loan_cap = loan_capacity(loan_m)

    return cash + cpf + grants["total"] + min(loan_cap, 750_000)