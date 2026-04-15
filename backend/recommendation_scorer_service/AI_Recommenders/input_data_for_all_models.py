from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any


_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVICE_ROOT = os.path.abspath(os.path.join(_THIS_DIR, ".."))
_BACKEND_ROOT = os.path.abspath(os.path.join(_SERVICE_ROOT, ".."))

for _path in (_THIS_DIR, _SERVICE_ROOT, _BACKEND_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from amenity_proximity_service.utils.db_connector import DbConnector
from amenity_proximity_service.utils.distances import block_amenity_stats, warm_all_estates
from budget_estimator_service.effective_budget import effective_budget
from budget_estimator_service.grants import calc_all_grants
from budget_estimator_service.prices import analyse_town_prices
from estate_finder_service.queries import get_all_towns, get_flats_for_estate
from scorer import detect_active_criteria
from vectorizer import buyer_vector, flat_vector


DEFAULT_PROFILE = {
    "cit": "SC_SC",
    "age": 32,
    "marital": "married",
    "income": 6500,
    "ftimer": "first",
    "prox": "none",
    "ftype": "4 ROOM",
    "regions": [],
    "floor": "any",
    "min_lease": 50,
    "cash": 30000,
    "cpf": 80000,
    "loan": 1800,
    "must_have": [],
}

ALL_CIT_VALUES = ["SC_SC", "SC_PR", "SC_NR", "SC_single", "PR_PR"]
SINGLE_CIT_VALUES = {"SC_single", "SC_NR"}

REGION_OPTIONS = [
    ("north", "North"),
    ("northeast", "North-East"),
    ("east", "East"),
    ("west", "West"),
    ("central", "Central"),
]

AMENITY_OPTIONS = [
    ("mrt", "MRT <= 1km"),
    ("hawker", "Hawker <= 1km"),
    ("school", "Primary School <= 1km"),
    ("park", "Park <= 1km"),
    ("mall", "Mall <= 1.5km"),
    ("hospital", "Hospital <= 3km"),
]

CITIZENSHIP_OPTIONS = [
    ("SC_SC", "SC + SC (Couple / Family)"),
    ("SC_PR", "SC + SPR Couple"),
    ("SC_NR", "SC + Non-Resident Spouse/Family"),
    ("SC_single", "SC Single (>=35)"),
    ("PR_PR", "PR + PR (Couple / Family)"),
]

MARITAL_OPTIONS = [
    {"value": "married", "label": "Married", "groups": ["SC_SC", "SC_PR", "SC_NR", "PR_PR"]},
    {"value": "fiancee", "label": "Fiance / Fiancee", "groups": ["SC_SC", "SC_PR", "SC_NR", "PR_PR"]},
    {"value": "widowed", "label": "Widowed / Divorced", "groups": ["SC_SC", "SC_PR"]},
    {"value": "single", "label": "Single", "groups": ["SC_single", "PR_PR"]},
    {"value": "joint", "label": "Joint Singles Scheme (JSS)", "groups": ["SC_single"]},
    {"value": "with_SC_parents", "label": "Single with SC Parents", "groups": ["SC_single", "PR_PR"]},
    {"value": "with_PR_parents", "label": "Single with PR Parents", "groups": ["PR_PR"]},
]

FTIMER_OPTIONS = [
    {"value": "first", "label": "First-Timer", "groups": []},
    {"value": "second", "label": "Second-Timer", "groups": []},
    {"value": "mixed", "label": "One First + One Second Timer", "groups": ["SC_SC", "SC_PR", "PR_PR"]},
]

PROX_OPTIONS = [
    ("none", "No"),
    ("same", "Same Flat as Parents / Children"),
    ("near", "Within 4km of Parents / Children"),
]

FLAT_TYPE_OPTIONS = [
    ("any", "Any"),
    ("2 ROOM", "2-Room Flexi"),
    ("3 ROOM", "3-Room"),
    ("4 ROOM", "4-Room"),
    ("5 ROOM", "5-Room"),
    ("EXECUTIVE", "Executive"),
]

FLOOR_OPTIONS = [
    ("any", "Any Floor"),
    ("low", "Low (1-6F)"),
    ("mid", "Mid (7-15F)"),
    ("high", "High (16F+)"),
]

MIN_ESTATE_POOL = 10
DEFAULT_CANDIDATE_FLAT_LIMIT = 240

RECOMMENDER_REGION_MAP = {
    "Central": ["QUEENSTOWN", "BUKIT MERAH", "TOA PAYOH", "CENTRAL AREA", "MARINE PARADE", "BUKIT TIMAH"],
    "East": ["TAMPINES", "BEDOK", "PASIR RIS", "GEYLANG", "KALLANG/WHAMPOA"],
    "North": ["WOODLANDS", "SEMBAWANG", "YISHUN", "ANG MO KIO", "BISHAN"],
    "Northeast": ["SENGKANG", "PUNGGOL", "HOUGANG", "SERANGOON", "BUANGKOK"],
    "West": ["JURONG WEST", "JURONG EAST", "BUKIT BATOK", "CHOA CHU KANG", "CLEMENTI", "BUKIT PANJANG"],
}

VALID_REGION_VALUES = {value for value, _ in REGION_OPTIONS}
VALID_AMENITY_VALUES = {value for value, _ in AMENITY_OPTIONS}
VALID_CIT_VALUES = {value for value, _ in CITIZENSHIP_OPTIONS}
VALID_MARITAL_VALUES = {item["value"] for item in MARITAL_OPTIONS}
VALID_FTIMER_VALUES = {item["value"] for item in FTIMER_OPTIONS}
VALID_PROX_VALUES = {value for value, _ in PROX_OPTIONS}
VALID_FLAT_TYPE_VALUES = {value for value, _ in FLAT_TYPE_OPTIONS}
VALID_FLOOR_VALUES = {value for value, _ in FLOOR_OPTIONS}

_DISPLAY_AMENITY_TABLE_CANDIDATES = {
    "mrt": ("resale_flats_mrt_stations",),
    "hawker": ("resale_flats_hawker_centres",),
    "mall": ("resale_flats_shopping_malls", "resale_flats_malls"),
    "park": ("resale_flats_parks",),
    "school": ("resale_flats_schools",),
    "hospital": ("resale_flats_public_hospitals", "resale_flats_hospitals"),
}
_flat_display_amenity_cache: dict[str, dict[str, Any]] = {}
_display_amenity_table_cache: dict[str, str | None] = {}
_EMPTY_AMENITY = {
    "dist_km": None,
    "walk_mins": None,
    "within_threshold": False,
    "count_within": 0,
    "avg_dist_km": None,
}
_AMENITY_KEYS = ("mrt", "hawker", "mall", "park", "school", "hospital")


def _bg_warm() -> None:
    try:
        warm_all_estates()
    except Exception:
        pass


threading.Thread(target=_bg_warm, daemon=True, name="ai-recommender-warm").start()


def _clone_defaults() -> dict[str, Any]:
    return {
        **DEFAULT_PROFILE,
        "regions": list(DEFAULT_PROFILE["regions"]),
        "must_have": list(DEFAULT_PROFILE["must_have"]),
    }


def _first_value(form_data: dict[str, list[str]], key: str, default: str) -> str:
    values = form_data.get(key)
    if not values:
        return default
    value = values[0].strip()
    return value if value else default


def _coerce_int(value: str, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def marital_options_for_cit(cit: str) -> list[dict[str, Any]]:
    return [item for item in MARITAL_OPTIONS if cit in item["groups"]]


def ftimer_options_for_cit(cit: str) -> list[dict[str, Any]]:
    visible: list[dict[str, Any]] = []
    for item in FTIMER_OPTIONS:
        if not item["groups"] or cit not in SINGLE_CIT_VALUES:
            visible.append(item)
    return visible


def _normalize_cit_dependent_choices(profile: dict[str, Any]) -> None:
    marital_options = marital_options_for_cit(profile["cit"])
    valid_marital_values = {item["value"] for item in marital_options}
    if profile["marital"] not in valid_marital_values:
        profile["marital"] = marital_options[0]["value"] if marital_options else DEFAULT_PROFILE["marital"]

    ftimer_options = ftimer_options_for_cit(profile["cit"])
    valid_ftimer_values = {item["value"] for item in ftimer_options}
    if profile["ftimer"] not in valid_ftimer_values:
        profile["ftimer"] = ftimer_options[0]["value"] if ftimer_options else DEFAULT_PROFILE["ftimer"]


def parse_profile_form(form_data: dict[str, list[str]]) -> dict[str, Any]:
    profile = _clone_defaults()

    profile["cit"] = _first_value(form_data, "cit", profile["cit"])
    if profile["cit"] not in VALID_CIT_VALUES:
        profile["cit"] = DEFAULT_PROFILE["cit"]

    profile["age"] = max(21, min(70, _coerce_int(_first_value(form_data, "age", str(profile["age"])), profile["age"])))

    profile["marital"] = _first_value(form_data, "marital", profile["marital"])
    if profile["marital"] not in VALID_MARITAL_VALUES:
        profile["marital"] = DEFAULT_PROFILE["marital"]

    profile["income"] = max(0, min(21000, _coerce_int(_first_value(form_data, "income", str(profile["income"])), profile["income"])))
    profile["ftimer"] = _first_value(form_data, "ftimer", profile["ftimer"])
    if profile["ftimer"] not in VALID_FTIMER_VALUES:
        profile["ftimer"] = DEFAULT_PROFILE["ftimer"]

    profile["prox"] = _first_value(form_data, "prox", profile["prox"])
    if profile["prox"] not in VALID_PROX_VALUES:
        profile["prox"] = DEFAULT_PROFILE["prox"]

    profile["ftype"] = _first_value(form_data, "ftype", profile["ftype"])
    if profile["ftype"] not in VALID_FLAT_TYPE_VALUES:
        profile["ftype"] = DEFAULT_PROFILE["ftype"]

    profile["floor"] = _first_value(form_data, "floor", profile["floor"])
    if profile["floor"] not in VALID_FLOOR_VALUES:
        profile["floor"] = DEFAULT_PROFILE["floor"]

    profile["min_lease"] = max(20, min(99, _coerce_int(_first_value(form_data, "min_lease", str(profile["min_lease"])), profile["min_lease"])))
    profile["cash"] = max(0, min(500000, _coerce_int(_first_value(form_data, "cash", str(profile["cash"])), profile["cash"])))
    profile["cpf"] = max(0, min(600000, _coerce_int(_first_value(form_data, "cpf", str(profile["cpf"])), profile["cpf"])))
    profile["loan"] = max(500, min(6000, _coerce_int(_first_value(form_data, "loan", str(profile["loan"])), profile["loan"])))

    profile["regions"] = [
        value for value in form_data.get("regions", [])
        if value in VALID_REGION_VALUES
    ]
    profile["must_have"] = [
        value for value in form_data.get("must_have", [])
        if value in VALID_AMENITY_VALUES
    ]

    _normalize_cit_dependent_choices(profile)

    return profile


def profile_to_json(profile: dict[str, Any]) -> str:
    return json.dumps(profile, sort_keys=True)


def profile_from_json(payload: str) -> dict[str, Any]:
    data = json.loads(payload)
    defaults = _clone_defaults()
    defaults.update(data)
    defaults["regions"] = [value for value in defaults.get("regions", []) if value in VALID_REGION_VALUES]
    defaults["must_have"] = [value for value in defaults.get("must_have", []) if value in VALID_AMENITY_VALUES]
    _normalize_cit_dependent_choices(defaults)
    return defaults


def evaluate_profile_eligibility(profile: dict[str, Any]) -> dict[str, Any]:
    cit = profile["cit"]
    income = profile["income"]
    age = profile["age"]
    marital = profile.get("marital", "married")
    ftimer = profile.get("ftimer", "first")

    eligible = True
    market = "both"
    warnings: list[str] = []
    notes: list[str] = []

    is_joint_single = cit == "SC_single" and marital == "joint"
    is_with_sc_parents = cit == "SC_single" and marital == "with_SC_parents"
    is_single_scheme = cit == "SC_single" and marital == "single"
    is_pr_with_pr_parents = cit == "PR_PR" and marital == "with_PR_parents"
    is_pr_with_sc_parents = cit == "PR_PR" and marital == "with_SC_parents"

    if cit == "PR_PR":
        market = "resale_only"

    if cit == "PR_PR" and marital in {"married", "fiancee"}:
        notes.append("PRs: resale flats only. Both must be PRs for at least 3 years.")

    if cit == "PR_PR" and marital == "single":
        eligible = False
        market = "ineligible"
        warnings.append("PR Singles must form a family nucleus to buy flats.")

    if cit == "SC_NR":
        market = "resale_only"
        notes.append("SC + Non-Resident Spouse: resale flats only. BTO requires both applicants to be SC/PR.")

    if cit == "SC_single" and age < 35:
        eligible = False
        market = "ineligible"
        warnings.append("Singles must be >=35 years old to buy under the Singles / JSS / Single with Parents scheme.")

    if is_joint_single:
        notes.append("Joint Singles Scheme: 2 or more SC singles buying together. Each applicant must be >=35. EHG uses combined household income (<= $9k).")

    if is_with_sc_parents:
        notes.append("Single with SC Parents: PHG (Singles) applies - $15,000 to live with parents/child in the same flat, $10,000 within 4km.")

    if is_single_scheme:
        notes.append("Singapore Single Scheme: PHG (Singles) available - $15,000 to live with parents/child, $10,000 within 4km.")

    if is_pr_with_pr_parents:
        notes.append("PR + PR Parents: At least one parent must be PR for at least 3 years. No grants apply.")

    if is_pr_with_sc_parents:
        notes.append("PR + SC Parents: At least one parent must be SC for grants to apply.")

    if income > 14000:
        warnings.append("Income >$14k: No HDB grants eligible.")
    elif income > 9000 and not is_joint_single and ftimer == "first":
        notes.append("Income >$9k: EHG not applicable. CPF Housing Grant may still apply depending on scheme.")
    elif income > 9000 and is_joint_single and ftimer == "first":
        notes.append("JSS: Combined household income >$9k - EHG not applicable. CPF Housing Grant may still apply up to $14k combined income.")

    return {
        "eligible": eligible,
        "market": market,
        "warnings": warnings,
        "notes": notes,
    }


def _flat_id(flat_row: dict[str, Any]) -> str:
    return "|".join(
        str(flat_row.get(key, ""))
        for key in ("estate", "block", "street_name", "flat_type", "sold_date", "resale_price")
    )


def _flat_mid_storey(flat_row: dict[str, Any]) -> float:
    start = flat_row.get("storey_range_start")
    end = flat_row.get("storey_range_end")
    if start is not None and end is not None:
        return (float(start) + float(end)) / 2.0
    if start is not None:
        return float(start)
    if end is not None:
        return float(end)
    return 5.0


def _remaining_lease_total_years(flat_row: dict[str, Any]) -> float:
    years = flat_row.get("remaining_lease_years") or 0
    months = flat_row.get("remaining_lease_months") or 0
    return round(float(years) + float(months) / 12.0, 2)


def _remaining_lease_years_int(flat_row: dict[str, Any]) -> int:
    return int(flat_row.get("remaining_lease_years") or 0)


def _lease_label(remaining_lease_years: int, remaining_lease_months: int) -> str:
    if remaining_lease_months > 0:
        return f"{remaining_lease_years}y {remaining_lease_months}m"
    return f"{remaining_lease_years}y"


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(value, upper))


def _price_fit_score(price: float, budget: float) -> float:
    if budget <= 0:
        return 0.5
    if price <= budget:
        return 1.0
    allowed = budget * 0.25
    if allowed <= 0:
        return 0.0
    return round(_clamp(1.0 - ((price - budget) / allowed)), 4)


def _lease_fit_score(lease_years: float, min_lease: int) -> float:
    target = max(min_lease, 1)
    if lease_years >= target:
        return 1.0
    return round(_clamp(lease_years / target), 4)


def _floor_match_score(floor_pref: str, flat_row: dict[str, Any]) -> float:
    if floor_pref == "any":
        return 0.75
    level = _flat_mid_storey(flat_row)
    if floor_pref == "low":
        return 1.0 if level <= 6 else 0.35 if level <= 10 else 0.0
    if floor_pref == "mid":
        if 7 <= level <= 15:
            return 1.0
        return 0.45 if 4 <= level <= 18 else 0.0
    if floor_pref == "high":
        return 1.0 if level >= 16 else 0.35 if level >= 12 else 0.0
    return 0.5


def _must_have_match_score(must_have: list[str], failed_must: list[str]) -> float:
    if not must_have:
        return 0.75
    passed = max(len(must_have) - len(failed_must), 0)
    return round(passed / len(must_have), 4)


def _failed_must_have(must_have: list[str], amenities: dict[str, dict[str, Any]]) -> list[str]:
    return [
        amenity
        for amenity in must_have
        if amenities.get(amenity, {}).get("dist_km") is not None
        and not amenities.get(amenity, {}).get("within_threshold", False)
    ]


def _amenity_counts(amenities: dict[str, dict[str, Any]]) -> dict[str, int]:
    return {
        amenity: int(amenities.get(amenity, {}).get("count_within", 0) or 0)
        for amenity, _ in AMENITY_OPTIONS
    }


def _amenity_summary(amenity_counts: dict[str, int]) -> str:
    label_map = {
        "mrt": "MRT",
        "hawker": "Hawker",
        "school": "School",
        "park": "Park",
        "mall": "Mall",
        "hospital": "Hospital",
    }
    ordered = ["mrt", "hawker", "mall", "park", "school", "hospital"]
    return ", ".join(f"{label_map[key]} {amenity_counts.get(key, 0)}" for key in ordered)


def _flat_cache_key(block: str, street_name: str) -> str:
    return f"{str(block or '').strip()}|{str(street_name or '').strip()}"


def _empty_display_amenity_payload() -> dict[str, Any]:
    counts = {amenity: 0 for amenity, _ in AMENITY_OPTIONS}
    return {
        "counts": counts,
        "summary": _amenity_summary(counts),
    }


def _candidate_towns(profile: dict[str, Any]) -> list[str]:
    regions = profile.get("regions", [])
    if not regions:
        return get_all_towns()

    ordered: list[str] = []
    seen: set[str] = set()
    for region in regions:
        for town in RECOMMENDER_REGION_MAP.get(region.title(), []):
            if town not in seen:
                seen.add(town)
                ordered.append(town)
    return ordered


def _resolve_display_amenity_tables() -> dict[str, str | None]:
    unresolved = [
        amenity
        for amenity in _DISPLAY_AMENITY_TABLE_CANDIDATES
        if amenity not in _display_amenity_table_cache
    ]
    if not unresolved:
        return dict(_display_amenity_table_cache)

    db = DbConnector()
    try:
        for amenity in unresolved:
            resolved_table = None
            for table_name in _DISPLAY_AMENITY_TABLE_CANDIDATES[amenity]:
                db.cursor.execute("SHOW TABLES LIKE %s", (table_name,))
                if db.cursor.fetchone():
                    resolved_table = table_name
                    break
            _display_amenity_table_cache[amenity] = resolved_table
    finally:
        db.Close()

    return dict(_display_amenity_table_cache)


def _prime_flat_display_amenities(flat_pairs: list[tuple[str, str]]) -> None:
    missing_pairs: list[tuple[str, str]] = []
    pending_payloads: dict[str, dict[str, Any]] = {}

    for block, street_name in flat_pairs:
        normalised_block = str(block or "").strip()
        normalised_street = str(street_name or "").strip()
        if not normalised_block and not normalised_street:
            continue
        cache_key = _flat_cache_key(normalised_block, normalised_street)
        if cache_key in _flat_display_amenity_cache or cache_key in pending_payloads:
            continue
        pending_payloads[cache_key] = _empty_display_amenity_payload()
        missing_pairs.append((normalised_block, normalised_street))

    if not missing_pairs:
        return

    pair_placeholders = ", ".join(["(%s, %s)"] * len(missing_pairs))
    pair_params: list[Any] = []
    for block, street_name in missing_pairs:
        pair_params.extend([block, street_name])

    tables = _resolve_display_amenity_tables()
    available_tables = {
        amenity: table_name
        for amenity, table_name in tables.items()
        if table_name
    }

    if available_tables:
        db = DbConnector()
        try:
            for amenity, table_name in available_tables.items():
                query = f"""
                    SELECT block, street_name, COUNT(*) AS amenity_count
                    FROM {table_name}
                    WHERE (block, street_name) IN ({pair_placeholders})
                    GROUP BY block, street_name
                """
                db.cursor.execute(query, tuple(pair_params))
                for row in db.cursor.fetchall():
                    cache_key = _flat_cache_key(row.get("block", ""), row.get("street_name", ""))
                    payload = pending_payloads.get(cache_key)
                    if payload is not None:
                        payload["counts"][amenity] = int(row.get("amenity_count") or 0)
        finally:
            db.Close()

    for cache_key, payload in pending_payloads.items():
        payload["summary"] = _amenity_summary(payload["counts"])
        _flat_display_amenity_cache[cache_key] = payload


def _flat_display_amenities(block: str, street_name: str) -> dict[str, Any]:
    cache_key = _flat_cache_key(block, street_name)
    cached = _flat_display_amenity_cache.get(cache_key)
    if cached is None:
        _prime_flat_display_amenities([(block, street_name)])
        cached = _flat_display_amenity_cache.get(cache_key)
    return cached if cached is not None else _empty_display_amenity_payload()


def attach_display_amenities(grouped_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat_pairs: list[tuple[str, str]] = []
    for group in grouped_results:
        for item in group.get("items", []):
            flat_pairs.append((str(item.get("block", "")), str(item.get("street_name", ""))))

    _prime_flat_display_amenities(flat_pairs)

    for group in grouped_results:
        for item in group.get("items", []):
            display_amenities = _flat_display_amenities(
                str(item.get("block", "")),
                str(item.get("street_name", "")),
            )
            item["amenity_counts"] = dict(display_amenities["counts"])
            item["amenity_summary"] = display_amenities["summary"]

    return grouped_results


@dataclass(slots=True)
class EstateCandidate:
    town: str
    price_data: dict[str, Any]
    amenities: dict[str, Any]
    failed_must: list[str]


@dataclass(slots=True)
class FlatCandidate:
    flat_id: str
    estate: str
    block: str
    street_name: str
    flat_type: str
    flat_model: str
    resale_price: float
    floor_area_sqm: float
    remaining_lease_years: int
    remaining_lease_months: int
    remaining_lease_total_years: float
    storey_range_start: int | None
    storey_range_end: int | None
    sold_date: str
    latitude: float | None
    longitude: float | None
    estate_price_data: dict[str, Any]
    price_data: dict[str, Any]
    amenities: dict[str, Any]
    failed_must: list[str]
    flat_vector: list[float]
    budget_fit: float
    lease_fit: float
    floor_match: float
    must_have_match: float

    @property
    def address(self) -> str:
        return f"{self.block} {self.street_name}".strip()

    @property
    def floor_label(self) -> str:
        if self.storey_range_start is not None and self.storey_range_end is not None:
            return f"{self.storey_range_start}-{self.storey_range_end}"
        if self.storey_range_start is not None:
            return str(self.storey_range_start)
        return "N/A"

    @property
    def lease_label(self) -> str:
        return _lease_label(self.remaining_lease_years, self.remaining_lease_months)

    def to_result(
        self,
        model_key: str,
        model_name: str,
        score: float,
        rank: int,
        reason: str,
    ) -> dict[str, Any]:
        scoring_amenity_counts = _amenity_counts(self.amenities)
        display_amenities = _empty_display_amenity_payload()
        return {
            "model_key": model_key,
            "model_name": model_name,
            "rank": rank,
            "score": round(score, 6),
            "score_pct": round(score * 100, 2),
            "reason": reason,
            "flat_id": self.flat_id,
            "estate": self.estate,
            "block": self.block,
            "street_name": self.street_name,
            "address": self.address,
            "flat_type": self.flat_type,
            "flat_model": self.flat_model,
            "resale_price": int(round(self.resale_price)),
            "floor_area_sqm": round(self.floor_area_sqm, 1),
            "remaining_lease_years": self.remaining_lease_years,
            "remaining_lease_months": self.remaining_lease_months,
            "remaining_lease_label": self.lease_label,
            "floor_label": self.floor_label,
            "sold_date": self.sold_date,
            "flat_vector": list(self.flat_vector),
            "amenity_counts": display_amenities["counts"],
            "amenity_summary": display_amenities["summary"],
            "vector_amenity_counts": scoring_amenity_counts,
            "vector_amenity_summary": _amenity_summary(scoring_amenity_counts),
            "budget_fit": self.budget_fit,
            "lease_fit": self.lease_fit,
            "floor_match": self.floor_match,
            "must_have_match": self.must_have_match,
            "failed_must": list(self.failed_must),
        }


@dataclass(slots=True)
class ModelContext:
    profile: dict[str, Any]
    eligibility: dict[str, Any]
    grants: dict[str, Any]
    effective_budget: float
    buyer_vector: list[float]
    active_criteria: list[str]
    estate_candidates: list[EstateCandidate]
    flat_candidates: list[FlatCandidate]
    notes: list[str]


def _estate_candidates_for_profile(profile: dict[str, Any], budget: float) -> tuple[list[EstateCandidate], list[str]]:
    notes: list[str] = []
    towns = _candidate_towns(profile)

    pricing_ftype = profile["ftype"]
    if pricing_ftype == "any":
        pricing_ftype = "4 ROOM"
        notes.append(
            "Flat type 'Any' uses 4 ROOM for estate-level price analysis to stay aligned with the existing scorer."
        )

    qualified: list[EstateCandidate] = []

    for town in towns:
        price_data = analyse_town_prices(town, pricing_ftype)
        if price_data is None:
            continue
        price_data["estate"] = town
        qualified.append(EstateCandidate(town=town, price_data=price_data, amenities={}, failed_must=[]))

    return qualified, notes


def _flat_candidates_for_profile(
    profile: dict[str, Any],
    budget: float,
    buyer_vec: list[float],
    estate_candidates: list[EstateCandidate],
) -> tuple[list[FlatCandidate], list[str]]:
    if not estate_candidates:
        return [], []

    notes: list[str] = []
    candidates: list[FlatCandidate] = []
    seen_ids: set[str] = set()

    def _build_for_estate(estate: EstateCandidate) -> list[FlatCandidate]:
        estate_flats = get_flats_for_estate(
            estate.town,
            ftype=profile["ftype"],
            floor_pref=profile["floor"],
            budget=0,
            min_lease=profile["min_lease"],
            limit=0,
        )
        if budget > 0:
            budget_cap = budget * 1.05
            estate_flats = [flat for flat in estate_flats if float(flat.get("resale_price") or 0) <= budget_cap]

        if not estate_flats:
            return []

        amenity_by_block = block_amenity_stats(estate.town)
        built: list[FlatCandidate] = []

        for flat_row in estate_flats:
            block = str(flat_row.get("block", ""))
            street_name = str(flat_row.get("street_name", ""))
            block_key = (block, street_name)
            flat_amenities = {
                amenity_key: amenity_by_block.get(block_key, {}).get(amenity_key, _EMPTY_AMENITY)
                for amenity_key in _AMENITY_KEYS
            }

            adjusted_price_data = dict(estate.price_data)
            adjusted_price_data["avg_storey"] = _flat_mid_storey(flat_row)

            remaining_lease_years = _remaining_lease_years_int(flat_row)
            remaining_lease_months = int(flat_row.get("remaining_lease_months") or 0)
            remaining_lease_total_years = _remaining_lease_total_years(flat_row)
            adjusted_price_data["avg_lease_years"] = remaining_lease_total_years

            failed_must = _failed_must_have(profile["must_have"], flat_amenities)

            built.append(
                FlatCandidate(
                    flat_id=_flat_id(flat_row),
                    estate=flat_row.get("estate", ""),
                    block=block,
                    street_name=street_name,
                    flat_type=str(flat_row.get("flat_type", "")),
                    flat_model=str(flat_row.get("flat_model", "")),
                    resale_price=float(flat_row.get("resale_price") or 0),
                    floor_area_sqm=float(flat_row.get("floor_area_sqm") or 0),
                    remaining_lease_years=remaining_lease_years,
                    remaining_lease_months=remaining_lease_months,
                    remaining_lease_total_years=remaining_lease_total_years,
                    storey_range_start=flat_row.get("storey_range_start"),
                    storey_range_end=flat_row.get("storey_range_end"),
                    sold_date=str(flat_row.get("sold_date", "")),
                    latitude=flat_row.get("latitude"),
                    longitude=flat_row.get("longitude"),
                    estate_price_data=dict(estate.price_data),
                    price_data=adjusted_price_data,
                    amenities=flat_amenities,
                    failed_must=failed_must,
                    flat_vector=flat_vector(adjusted_price_data, flat_amenities),
                    budget_fit=_price_fit_score(float(flat_row.get("resale_price") or 0), budget),
                    lease_fit=_lease_fit_score(remaining_lease_total_years, profile["min_lease"]),
                    floor_match=_floor_match_score(profile["floor"], flat_row),
                    must_have_match=_must_have_match_score(profile["must_have"], failed_must),
                )
            )

        return built

    with ThreadPoolExecutor(max_workers=min(len(estate_candidates), 8)) as executor:
        futures = {executor.submit(_build_for_estate, estate): estate.town for estate in estate_candidates}
        for future in as_completed(futures):
            for candidate in future.result():
                if candidate.flat_id in seen_ids:
                    continue
                seen_ids.add(candidate.flat_id)
                candidates.append(candidate)

    return candidates, notes


def build_model_context(profile: dict[str, Any]) -> ModelContext:
    eligibility = evaluate_profile_eligibility(profile)
    grants = calc_all_grants(profile)
    budget = effective_budget(profile, grants)
    buyer_vec = buyer_vector(profile, budget)
    active_criteria = detect_active_criteria(profile, budget, profile["must_have"], profile["regions"])

    notes: list[str] = []
    estate_candidates: list[EstateCandidate] = []
    flat_candidates: list[FlatCandidate] = []

    if eligibility["eligible"]:
        estate_candidates, estate_notes = _estate_candidates_for_profile(profile, budget)
        notes.extend(estate_notes)
        flat_candidates, flat_notes = _flat_candidates_for_profile(profile, budget, buyer_vec, estate_candidates)
        notes.extend(flat_notes)
        if not estate_candidates:
            notes.append("No estates passed the current budget, lease, region, and amenity filters.")
        elif not flat_candidates:
            notes.append("Estates passed the filters, but no recent flat transactions matched the remaining flat-level filters.")

    return ModelContext(
        profile=profile,
        eligibility=eligibility,
        grants=grants,
        effective_budget=budget,
        buyer_vector=buyer_vec,
        active_criteria=active_criteria,
        estate_candidates=estate_candidates,
        flat_candidates=flat_candidates,
        notes=notes,
    )
