"""
api/routes.py
=============
All HTTP route definitions. Kept intentionally thin:
- Validates the incoming request shape (via Pydantic)
- Calls the recommender orchestrator
- Returns the JSON response

No business logic lives here.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.recommender import run_recommendation
from db.queries import get_price_trend

router = APIRouter()


# ── Request schema ───────────────────────────────────────────────────────────

class BuyerProfile(BaseModel):
    # Buyer identity
    cit: str = Field(..., description="Citizenship group: SC_SC | SC_PR | SC_single | PR_PR")
    marital: str = Field(..., description="Marital status value from dropdown")
    age: int = Field(..., ge=21, le=99)
    income: float = Field(..., ge=0)
    ftimer: str = Field(..., description="first | second | mixed")
    prox: str = Field("none", description="none | same | near")

    # Flat preferences
    ftype: str = Field("any", description="any | 2 ROOM | 3 ROOM | 4 ROOM | 5 ROOM | EXECUTIVE")
    regions: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    max_mrt_mins: int = Field(30, ge=1, le=60)
    min_lease: int = Field(60, ge=0, le=99)

    # Budget
    cash: float = Field(0, ge=0)
    cpf: float = Field(0, ge=0)
    loan: float = Field(0, ge=0, description="Max monthly loan repayment ($)")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@router.post("/api/recommend")
def recommend(profile: BuyerProfile):
    """
    Main recommendation endpoint.
    Returns top 10 scored flat recommendations with grant breakdown,
    effective budget, price estimates, and nearest amenity distances.
    """
    try:
        result = run_recommendation(profile.model_dump())
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recommendation error: {str(e)}")


@router.get("/api/prices")
def prices(town: str, ftype: str = "4 ROOM"):
    """
    Returns last 24-month price trend for a specific town + flat type.
    Used by the front-end Trends tab.
    """
    try:
        data = get_price_trend(town.upper(), ftype.upper())
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/refresh")
def refresh_data():
    """
    Trigger a manual re-load of the resale CSV into SQLite.
    Call this after downloading a fresh resale_prices.csv.
    """
    from db.loader import load_resale_csv
    try:
        count = load_resale_csv()
        return {"status": "ok", "rows_loaded": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
