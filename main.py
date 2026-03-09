"""FastAPI app for Tempus Sales Copilot backend."""

from __future__ import annotations

import os
from pathlib import Path as PathLib

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ingest import ingest, _get_chroma_persist_dir
from models import (
    BriefRequest,
    BriefResponse,
    ChatRequest,
    ChatResponse,
    IntelRequest,
    IntelResponse,
    OutcomeRequest,
    OutcomeResponse,
    ProviderRank,
)
from rag import (
    PhysicianNotFoundError,
    generate_physician_brief,
    get_ranked_providers,
    process_chat,
)
from intel import fetch_intel
from outcomes import get_outcome_history, log_outcome


BASE_DIR = PathLib(__file__).resolve().parent

load_dotenv(override=False)

app = FastAPI(title="Tempus Sales Copilot Backend")

# CORS — allow all origins for now (frontend on separate domain)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _index_ready() -> bool:
    persist_dir = _get_chroma_persist_dir()
    return persist_dir.exists() and any(persist_dir.iterdir())


@app.on_event("startup")
async def startup_event() -> None:
    """Run ingestion on startup if index doesn't exist."""
    if not _index_ready():
        ingest(force=False)


@app.get("/health")
async def health():
    """Healthcheck endpoint."""
    return {"status": "ok", "index_ready": _index_ready()}


@app.post("/brief", response_model=BriefResponse)
async def brief(request: BriefRequest) -> BriefResponse:
    """Generate a structured brief for a given physician."""
    if not _index_ready():
        raise HTTPException(status_code=503, detail="Index building in progress")
    try:
        brief_resp = generate_physician_brief(
            physician_name=request.physician_name,
            physician_id=request.physician_id,
        )
    except PhysicianNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"{e}. Please check the spelling or ensure the physician exists in market_data.",
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Failed to generate brief: {e}")
    return brief_resp


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Coach the rep on follow-up questions using brief context."""
    try:
        return process_chat(request)
    except PhysicianNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Chat failed: {e}")


@app.post("/intel", response_model=IntelResponse)
async def intel_endpoint(request: IntelRequest) -> IntelResponse:
    """Generate pre-call intel digest for a physician."""
    if not _index_ready():
        raise HTTPException(status_code=503, detail="Index building in progress")
    try:
        return fetch_intel(request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Intel generation failed: {e}")


@app.post("/outcomes", response_model=OutcomeResponse)
async def log_outcome_endpoint(request: OutcomeRequest) -> OutcomeResponse:
    """Log a meeting outcome and update physician profile."""
    try:
        return log_outcome(request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Failed to log outcome: {e}")


@app.get("/outcomes/{physician_id}", response_model=list)
async def outcome_history(physician_id: str) -> list:
    """Return meeting history for a physician."""
    try:
        return get_outcome_history(physician_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/providers", response_model=list[ProviderRank])
async def providers(
    city: str | None = Query(default=None, description="Filter by city (e.g. Chicago)"),
    limit: int = Query(default=10, ge=1, le=50, description="Max number of providers to return"),
) -> list[ProviderRank]:
    """Return ranked providers by priority_score."""
    if not _index_ready():
        raise HTTPException(status_code=503, detail="Index building in progress")
    return get_ranked_providers(city=city, limit=limit)


# Serve built frontend (Railway single-service deployment)
_dist = BASE_DIR / "dist"
if _dist.exists() and _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
