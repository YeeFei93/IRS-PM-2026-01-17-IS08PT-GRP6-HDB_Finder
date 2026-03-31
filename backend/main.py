"""
HDB Estate Recommender — Backend Entry Point
=============================================
Run locally:   uvicorn main:app --reload --port 8000
Run prod:      uvicorn main:app --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from db.loader import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load all data files into SQLite once at startup."""
    print("[startup] Initialising database and loading data files…")
    init_db()
    print("[startup] Ready.")
    yield
    # Nothing to teardown for SQLite


app = FastAPI(
    title="HDB Estate Recommender API",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS: allow the HTML file to call this from any origin ──────────────────
# For production, replace "*" with your specific Railway/Render URL
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)
