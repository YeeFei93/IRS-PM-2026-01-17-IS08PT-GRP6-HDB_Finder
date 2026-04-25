from __future__ import annotations

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any


_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.abspath(os.path.join(_THIS_DIR, ".."))

for _path in (_THIS_DIR, _BACKEND_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from amenity_proximity_service.utils.distances import block_amenity_stats, warm_all_estates
from budget_estimator_service.effective_budget import effective_budget
from budget_estimator_service.grants import calc_all_grants
from budget_estimator_service.prices import analyse_town_prices
from eligibility_checker_service.eligibility import check_eligibility
from estate_finder_service.queries import get_all_towns, get_flats_for_estate
from recommendation_scorer_service.vectorizer import buyer_vector, flat_vector
from recommendation_scorer_service.weights import (
    AMENITY_CRITERIA,
    CRITERION_BUDGET,
    CRITERION_FLAT,
    CRITERION_FLOOR,
    CRITERION_REGION,
    DEFAULTS,
)


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

_VALID_REGION_VALUES = {"north", "northeast", "east", "west", "central"}
_AMENITY_KEYS = ("mrt", "hawker", "mall", "park", "school", "hospital")
_EMPTY_AMENITY = {
    "dist_km": None,
    "walk_mins": None,
    "within_threshold": False,
    "count_within": 0,
    "avg_dist_km": None,
}


def _bg_warm() -> None:
    try:
        warm_all_estates()
    except Exception:
        pass


threading.Thread(target=_bg_warm, daemon=True, name="recommendation-scorer-warm").start()


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalise_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_values = value
    else:
        raw_values = [value]

    normalised: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        clean = str(item or "").strip()
        if not clean:
            continue
        if clean not in seen:
            seen.add(clean)
            normalised.append(clean)
    return normalised


def _normalise_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(profile or {})
    normalised = {
        **DEFAULT_PROFILE,
        **raw,
    }

    normalised["income"] = _coerce_int(raw.get("income", raw.get("inc", normalised["income"])), DEFAULT_PROFILE["income"])
    normalised["age"] = _coerce_int(raw.get("age", normalised["age"]), DEFAULT_PROFILE["age"])
    normalised["cash"] = _coerce_int(raw.get("cash", normalised["cash"]), DEFAULT_PROFILE["cash"])
    normalised["cpf"] = _coerce_int(raw.get("cpf", normalised["cpf"]), DEFAULT_PROFILE["cpf"])
    normalised["loan"] = _coerce_int(raw.get("loan", normalised["loan"]), DEFAULT_PROFILE["loan"])
    normalised["min_lease"] = _coerce_int(
        raw.get("min_lease", raw.get("lease", normalised["min_lease"])),
        DEFAULT_PROFILE["min_lease"],
    )

    regions = [
        item.lower()
        for item in _normalise_list(raw.get("regions", raw.get("selRegions", normalised["regions"])))
        if item.lower() in _VALID_REGION_VALUES
    ]
    must_have = [
        item.lower()
        for item in _normalise_list(raw.get("must_have", raw.get("mustAmenities", normalised["must_have"])))
        if item.lower() in _AMENITY_KEYS
    ]

    normalised["regions"] = regions
    normalised["must_have"] = must_have
    normalised["floor"] = str(raw.get("floor", raw.get("floor_pref", normalised["floor"])) or DEFAULT_PROFILE["floor"]).strip().lower()
    normalised["ftype"] = str(raw.get("ftype", normalised["ftype"]) or DEFAULT_PROFILE["ftype"]).strip() or DEFAULT_PROFILE["ftype"]
    normalised["cit"] = str(raw.get("cit", normalised["cit"]) or DEFAULT_PROFILE["cit"]).strip()
    normalised["marital"] = str(raw.get("marital", normalised["marital"]) or DEFAULT_PROFILE["marital"]).strip()
    normalised["ftimer"] = str(raw.get("ftimer", normalised["ftimer"]) or DEFAULT_PROFILE["ftimer"]).strip()
    normalised["prox"] = str(raw.get("prox", normalised["prox"]) or DEFAULT_PROFILE["prox"]).strip()

    return normalised


def _detect_active_criteria(profile: dict[str, Any], budget: float) -> list[str]:
    active: list[str] = []

    if budget > 0:
        active.append(CRITERION_BUDGET)
    if str(profile.get("ftype", DEFAULTS[CRITERION_FLAT])).lower() != DEFAULTS[CRITERION_FLAT]:
        active.append(CRITERION_FLAT)
    if str(profile.get("floor", DEFAULTS[CRITERION_FLOOR])).lower() != DEFAULTS[CRITERION_FLOOR]:
        active.append(CRITERION_FLOOR)
    if profile.get("regions"):
        active.append(CRITERION_REGION)

    for amenity in profile.get("must_have", []):
        if amenity in AMENITY_CRITERIA and amenity not in active:
            active.append(amenity)

    return active


def _candidate_towns(profile: dict[str, Any]) -> list[str]:
    regions = profile.get("regions") or None
    return get_all_towns(regions)


def _resale_flat_id(flat_row: dict[str, Any]) -> str:
    explicit_id = flat_row.get("resale_flat_id")
    if explicit_id:
        return str(explicit_id)
    raise ValueError("Expected resale_flat_id in flat query result")


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
    return round(float(years) + (float(months) / 12.0), 2)


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


def _failed_must_have(must_have: list[str], amenities: dict[str, dict[str, Any]]) -> list[str]:
    failed: list[str] = []
    for amenity in must_have:
        if not amenities.get(amenity, {}).get("within_threshold", False):
            failed.append(amenity)
    return failed


def _must_have_match_score(must_have: list[str], failed_must: list[str]) -> float:
    if not must_have:
        return 0.75
    passed = max(len(must_have) - len(failed_must), 0)
    return round(passed / len(must_have), 4)


def _amenity_counts(amenities: dict[str, dict[str, Any]]) -> dict[str, int]:
    return {
        amenity: int(amenities.get(amenity, {}).get("count_within", 0) or 0)
        for amenity in _AMENITY_KEYS
    }


def _amenity_summary(amenity_counts: dict[str, int]) -> str:
    label_map = {
        "mrt": "MRT",
        "hawker": "Hawker",
        "mall": "Mall",
        "park": "Park",
        "school": "School",
        "hospital": "Hospital",
    }
    return ", ".join(f"{label_map[key]} {amenity_counts.get(key, 0)}" for key in _AMENITY_KEYS)


@dataclass(slots=True)
class EstateCandidate:
    town: str
    price_data: dict[str, Any]
    amenities: dict[str, Any]
    failed_must: list[str]


@dataclass(slots=True)
class FlatCandidate:
    resale_flat_id: str
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
        amenity_counts = _amenity_counts(self.amenities)
        amenity_summary = _amenity_summary(amenity_counts)
        return {
            "model_key": model_key,
            "model_name": model_name,
            "rank": rank,
            "score": round(score, 6),
            "score_pct": round(score * 100, 2),
            "reason": reason,
            "resale_flat_id": self.resale_flat_id,
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
            "storey_range_start": self.storey_range_start,
            "storey_range_end": self.storey_range_end,
            "floor_label": self.floor_label,
            "sold_date": self.sold_date,
            "latitude": float(self.latitude) if self.latitude is not None else None,
            "longitude": float(self.longitude) if self.longitude is not None else None,
            "flat_vector": list(self.flat_vector),
            "amenity_counts": amenity_counts,
            "amenity_summary": amenity_summary,
            "vector_amenity_counts": dict(amenity_counts),
            "vector_amenity_summary": amenity_summary,
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
    del budget

    notes: list[str] = []
    pricing_ftype = profile["ftype"]
    if pricing_ftype.lower() == "any":
        pricing_ftype = "4 ROOM"
        notes.append(
            "Flat type 'Any' uses 4 ROOM for estate-level price analysis."
        )

    qualified: list[EstateCandidate] = []
    for town in _candidate_towns(profile):
        price_data = analyse_town_prices(town, pricing_ftype)
        if price_data is None:
            continue
        price_data["estate"] = town
        qualified.append(
            EstateCandidate(
                town=town,
                price_data=price_data,
                amenities={},
                failed_must=[],
            )
        )

    return qualified, notes


def _build_flat_candidates_for_estate(
    estate: EstateCandidate,
    profile: dict[str, Any],
    budget: float,
) -> list[FlatCandidate]:
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
        estate_flats = [
            flat
            for flat in estate_flats
            if float(flat.get("resale_price") or 0.0) <= budget_cap
        ]
    if not estate_flats:
        return []

    amenity_by_block = block_amenity_stats(estate.town)
    built: list[FlatCandidate] = []

    for flat_row in estate_flats:
        block = str(flat_row.get("block", ""))
        street_name = str(flat_row.get("street_name", ""))
        block_key = (block, street_name)
        flat_amenities = {
            amenity_key: dict(amenity_by_block.get(block_key, {}).get(amenity_key, _EMPTY_AMENITY))
            for amenity_key in _AMENITY_KEYS
        }

        adjusted_price_data = dict(estate.price_data)
        adjusted_price_data["avg_storey"] = _flat_mid_storey(flat_row)

        remaining_lease_years = _remaining_lease_years_int(flat_row)
        remaining_lease_months = int(flat_row.get("remaining_lease_months") or 0)
        remaining_lease_total_years = _remaining_lease_total_years(flat_row)
        adjusted_price_data["avg_lease_years"] = remaining_lease_total_years

        failed_must = _failed_must_have(profile["must_have"], flat_amenities)
        resale_price = float(flat_row.get("resale_price") or 0.0)

        built.append(
            FlatCandidate(
                resale_flat_id=_resale_flat_id(flat_row),
                estate=str(flat_row.get("estate") or estate.town),
                block=block,
                street_name=street_name,
                flat_type=str(flat_row.get("flat_type", "")),
                flat_model=str(flat_row.get("flat_model", "")),
                resale_price=resale_price,
                floor_area_sqm=float(flat_row.get("floor_area_sqm") or 0.0),
                remaining_lease_years=remaining_lease_years,
                remaining_lease_months=remaining_lease_months,
                remaining_lease_total_years=remaining_lease_total_years,
                storey_range_start=flat_row.get("storey_range_start"),
                storey_range_end=flat_row.get("storey_range_end"),
                sold_date=str(flat_row.get("sold_date", "")),
                latitude=(
                    _coerce_float(flat_row.get("latitude"), 0.0)
                    if flat_row.get("latitude") is not None else None
                ),
                longitude=(
                    _coerce_float(flat_row.get("longitude"), 0.0)
                    if flat_row.get("longitude") is not None else None
                ),
                estate_price_data=dict(estate.price_data),
                price_data=adjusted_price_data,
                amenities=flat_amenities,
                failed_must=failed_must,
                flat_vector=flat_vector(adjusted_price_data, flat_amenities),
                budget_fit=_price_fit_score(resale_price, budget),
                lease_fit=_lease_fit_score(remaining_lease_total_years, profile["min_lease"]),
                floor_match=_floor_match_score(profile["floor"], flat_row),
                must_have_match=_must_have_match_score(profile["must_have"], failed_must),
            )
        )

    return built


def _flat_candidates_for_profile(
    profile: dict[str, Any],
    budget: float,
    estate_candidates: list[EstateCandidate],
) -> tuple[list[FlatCandidate], list[str]]:
    if not estate_candidates:
        return [], []

    notes: list[str] = []
    candidates: list[FlatCandidate] = []
    seen_ids: set[str] = set()

    max_workers = min(len(estate_candidates), 8)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_build_flat_candidates_for_estate, estate, profile, budget): estate.town
            for estate in estate_candidates
        }
        for future in as_completed(futures):
            for candidate in future.result():
                if candidate.resale_flat_id in seen_ids:
                    continue
                seen_ids.add(candidate.resale_flat_id)
                candidates.append(candidate)

    return candidates, notes


def build_model_context(profile: dict[str, Any]) -> ModelContext:
    profile = _normalise_profile(profile)
    eligibility = check_eligibility(profile)
    grants = calc_all_grants(profile)
    budget = effective_budget(profile, grants)
    buyer_vec = buyer_vector(profile, budget)
    active_criteria = _detect_active_criteria(profile, budget)

    notes: list[str] = []
    estate_candidates: list[EstateCandidate] = []
    flat_candidates: list[FlatCandidate] = []

    if eligibility.get("eligible"):
        estate_candidates, estate_notes = _estate_candidates_for_profile(profile, budget)
        notes.extend(estate_notes)
        flat_candidates, flat_notes = _flat_candidates_for_profile(profile, budget, estate_candidates)
        notes.extend(flat_notes)

        if not estate_candidates:
            notes.append("No estates passed the current price and region filters.")
        elif not flat_candidates:
            notes.append("Estates passed the filters, but no recent flat transactions matched the flat-level constraints.")

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
