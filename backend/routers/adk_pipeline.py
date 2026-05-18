"""
ADK Pipeline Router
====================
Exposes POST /api/adk/pipeline — the Google ADK-orchestrated version of
the CrisisIQ crisis response pipeline.

This router is PURELY ADDITIVE.  The existing POST /api/pipeline in
routers/crises.py is not touched; both endpoints run side-by-side.

The ADK import is intentionally lazy (inside the endpoint function) so:
  • Server starts normally even if google-adk is not yet installed.
  • A clear HTTP 501 is returned instead of a startup crash.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import get_db
from db.crud import get_signals_by_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/adk", tags=["adk"])


class AdkPipelineRequest(BaseModel):
    signal_ids: list[int] = []
    location: str


@router.post("/pipeline", summary="Run crisis pipeline via Google ADK SequentialAgent")
async def run_adk_pipeline_endpoint(
    body: AdkPipelineRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Runs the same 4-agent crisis response pipeline as POST /api/pipeline,
    but orchestrated through Google ADK (SequentialAgent + 4 LlmAgents).

    Returns the same response structure plus ADK-specific fields:
      • session_id   — ADK session identifier
      • orchestrator — "google-adk/SequentialAgent"
      • agents_run   — list of the four ADK agent names
    """
    # Lazy import: fails gracefully with HTTP 501 if google-adk is absent.
    try:
        from crisisiq_agents.runner import run_adk_pipeline
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail=(
                f"Google ADK is not installed: {exc}. "
                "Add 'google-adk' to requirements.txt and reinstall."
            ),
        )

    # Resolve raw signals from DB (same logic as /api/pipeline).
    raw_signals: list[dict] = []
    if body.signal_ids:
        db_signals = await get_signals_by_ids(db, body.signal_ids)
        raw_signals = [
            {
                "text": s.text,
                "source_type": (
                    s.source_type.value
                    if hasattr(s.source_type, "value")
                    else s.source_type
                ),
                "location": s.location or body.location,
            }
            for s in db_signals
        ]

    # If no signal IDs provided (or none found), synthesise a placeholder.
    if not raw_signals:
        raw_signals = [{
            "text": f"Crisis signal reported at {body.location}",
            "source_type": "form",
            "location": body.location,
        }]

    try:
        result = await run_adk_pipeline(signals=raw_signals, location=body.location)
    except Exception as exc:
        logger.error(f"[ADK] Pipeline endpoint error: {exc}")
        raise HTTPException(status_code=500, detail=f"ADK pipeline error: {exc}")

    return result
