from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from db.base import get_db
from db.crud import create_signal, get_signals
from agents.agent1_ingestion import run_ingestion_agent

router = APIRouter(prefix="/api", tags=["signals"])


class IngestRequest(BaseModel):
    text: str
    source_type: str
    location: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@router.post("/ingest")
async def ingest_signal(body: IngestRequest, db: AsyncSession = Depends(get_db)):
    agent_result = await run_ingestion_agent(
        db=db,
        text=body.text,
        source_type=body.source_type,
        location=body.location,
    )

    signal = await create_signal(db, {
        "text": body.text,
        "normalized_text": agent_result.get("normalized_text"),
        "language": agent_result.get("language", "en"),
        "source_type": body.source_type,
        "location": agent_result.get("location", body.location),
        "latitude": body.latitude,
        "longitude": body.longitude,
    })

    return {
        "id": signal.id,
        "text": signal.text,
        "normalized_text": signal.normalized_text,
        "language": signal.language.value if hasattr(signal.language, "value") else signal.language,
        "source_type": signal.source_type.value if hasattr(signal.source_type, "value") else signal.source_type,
        "location": signal.location,
        "latitude": signal.latitude,
        "longitude": signal.longitude,
        "created_at": signal.created_at.isoformat() if signal.created_at else None,
    }


@router.get("/signals")
async def list_signals(db: AsyncSession = Depends(get_db)):
    signals = await get_signals(db)
    return [
        {
            "id": s.id,
            "text": s.text,
            "normalized_text": s.normalized_text,
            "language": s.language.value if hasattr(s.language, "value") else s.language,
            "source_type": s.source_type.value if hasattr(s.source_type, "value") else s.source_type,
            "location": s.location,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in signals
    ]
