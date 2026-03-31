"""
core/grants.py
==============
HDB grant calculation logic — pure functions, no I/O.
Sources:
  - EHG: HDB EHG_amount tables Aug 2024
  - CPF Housing Grant: hdb.gov.sg updated Dec 2025
  - PHG: HDB Proximity Housing Grant rules
"""

# ── EHG Table A: First-Timer Couples & Families ──────────────────────────────
# Indexed by household income ceiling → grant amount
EHG_FAMILY = [
    (1500, 120000), (2000, 110000), (2500, 105000), (3000, 95000),
    (3500, 90000),  (4000, 80000),  (4500, 70000),  (5000, 65000),
    (5500, 55000),  (6000, 50000),  (6500, 40000),  (7000, 30000),
    (7500, 25000),  (8000, 20000),  (8500, 10000),  (9000, 5000),
]

# ── EHG Table B: Singles & Mixed Couples ─────────────────────────────────────
# Indexed by HALF of household income ceiling → grant amount
EHG_SINGLES = [
    (750,  60000), (1000, 55000), (1250, 52500), (1500, 47500),
    (1750, 45000), (2000, 40000), (2250, 35000), (2500, 32500),
    (2750, 27500), (3000, 25000), (3250, 20000), (3500, 15000),
    (3750, 12500), (4000, 10000), (4250, 5000),  (4500, 2500),
]


def _lookup(bands: list, value: float) -> int:
    """Return grant from a banded table given an income value."""
    for ceiling, amount in bands:
        if value <= ceiling:
            return amount
    return 0


def calc_ehg(cit: str, marital: str, income: float, ftimer: str) -> int:
    """
    Calculate Enhanced Housing Grant (EHG).
    Applies to both BTO and resale first-timer purchases.
    """
    if ftimer != "first":
        return 0

    is_pr = cit == "PR_PR"
    if is_pr:
        return 0  # PRs not eligible for EHG

    is_single = cit == "SC_single"
    is_mixed_couple = ftimer == "mixed"  # one first + one second timer

    if is_single or is_mixed_couple:
        # Table B: use half-income as the lookup index
        if income / 2 > 4500:
            return 0
        return _lookup(EHG_SINGLES, income / 2)
    else:
        # Table A: SC/SC or SC/PR both first-timers
        if income > 9000:
            return 0
        return _lookup(EHG_FAMILY, income)


def calc_cpf_housing_grant(cit: str, marital: str, income: float,
                            ftype: str, ftimer: str) -> int:
    """
    Calculate CPF Housing Grant (resale flats only).
    Source: hdb.gov.sg Dec 2025.
    """
    if ftimer == "second":
        return 0  # Second-timers not eligible
    if cit == "PR_PR":
        return 0  # PRs not eligible

    large = ftype in ("5 ROOM", "EXECUTIVE")

    if cit == "SC_SC" and ftimer == "first":
        if income > 14000:
            return 0
        return 50000 if large else 80000

    elif cit == "SC_PR" and ftimer == "first":
        if income > 14000:
            return 0
        return 40000 if large else 70000

    elif ftimer == "mixed":
        # One first-timer + one second-timer couple
        if income > 14000:
            return 0
        return 25000 if large else 40000

    elif cit == "SC_single":
        if marital == "joint":
            # Single + Single(s) buying together: $40k each × 2
            if income > 14000:
                return 0
            return 50000 if large else 80000
        else:
            # Solo single
            if income > 7000:
                return 0
            return 25000 if large else 40000

    return 0


def calc_phg(cit: str, prox: str) -> int:
    """
    Calculate Proximity Housing Grant (resale flats only).
    No income ceiling. Cannot be used for BTO.
    """
    if cit == "PR_PR":
        return 0
    if prox == "same":
        return 30000
    if prox == "near":
        return 20000
    return 0


def calc_all_grants(profile: dict) -> dict:
    """
    Compute and stack all applicable grants.
    Returns a breakdown dict with individual amounts and total.
    """
    cit    = profile["cit"]
    marital = profile["marital"]
    income = profile["income"]
    ftype  = profile.get("ftype", "4 ROOM")
    ftimer = profile["ftimer"]
    prox   = profile.get("prox", "none")

    ehg  = calc_ehg(cit, marital, income, ftimer)
    cpfg = calc_cpf_housing_grant(cit, marital, income, ftype, ftimer)
    phg  = calc_phg(cit, prox)

    return {
        "ehg":   ehg,
        "cpf_grant": cpfg,
        "phg":   phg,
        "total": ehg + cpfg + phg,
    }
