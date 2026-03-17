"""
core/eligibility.py
===================
HDB eligibility rules — pure functions, no I/O.
Returns a structured result so the API can explain WHY
a buyer is or isn't eligible rather than just True/False.
"""


def check_eligibility(profile: dict) -> dict:
    """
    Validate buyer profile against HDB eligibility rules.

    Returns:
        {
          "eligible": bool,
          "market": "both" | "resale_only" | "ineligible",
          "warnings": [str],   # blocking issues
          "notes": [str],      # advisory only
        }
    """
    cit    = profile["cit"]
    age    = profile["age"]
    income = profile["income"]
    ftimer = profile["ftimer"]

    eligible = True
    market   = "both"
    warnings = []
    notes    = []

    # ── Citizenship-based market restrictions ────────────────────────────────
    if cit == "PR_PR":
        market = "resale_only"
        notes.append("PRs may only purchase resale HDB flats.")

    # ── Singles scheme age requirement ───────────────────────────────────────
    if cit == "SC_single" and age < 35:
        eligible = False
        warnings.append("Singles Scheme requires all buyers to be ≥35 years old.")

    # ── Income ceiling checks ────────────────────────────────────────────────
    if income > 16000:
        eligible = False
        market   = "ineligible"
        warnings.append("Household income >$16,000/month exceeds HDB eligibility ceiling.")
    elif income > 14000:
        market = "resale_only"
        warnings.append("Income $14,001–$16,000/month: resale flats only. "
                        "No CPF Housing Grant applicable.")
    elif income > 9000:
        notes.append("Income >$9,000/month: EHG not applicable. "
                     "CPF Housing Grant (≤$14,000) may still apply.")

    # ── Singles income ceiling for CPF Housing Grant ─────────────────────────
    if cit == "SC_single":
        marital = profile.get("marital", "single")
        ceiling = 14000 if marital == "joint" else 7000
        if income > ceiling:
            notes.append(f"Singles CPF Housing Grant income ceiling: "
                         f"${ceiling:,}/month. Grant not applicable at current income.")

    # ── Second-timer advisory ─────────────────────────────────────────────────
    if ftimer == "second":
        notes.append("Second-timers: EHG and CPF Housing Grant not applicable. "
                     "PHG may still apply for resale purchases near parents.")

    # ── Policy reminder ──────────────────────────────────────────────────────
    notes.append("Verify current HDB policies at https://www.hdb.gov.sg — "
                 "rules may change.")

    return {
        "eligible": eligible,
        "market":   market,
        "warnings": warnings,
        "notes":    notes,
    }
