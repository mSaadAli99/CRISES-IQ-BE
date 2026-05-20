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


from fastapi import UploadFile, File, Form
import shutil
import uuid
import os
from agents.agent5_forensics import run_forensic_agent
from agents.agent2_detection import run_detection_agent
from agents.agent3_analysis import run_analysis_agent
from agents.agent4_planner import run_planner_agent
from db.crud import get_agent_logs_by_crisis
from routers.crises import manager, _serialize_log
from uploads_config import UPLOAD_DIR, UPLOAD_URL_PREFIX

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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


@router.post("/ingest-with-image")
async def ingest_signal_with_image(
    text: str = Form(...),
    source_type: str = Form(...),
    location: str = Form(...),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db)
):
    image_url = None
    verification_score = None
    is_ai_generated = False
    forensic_log = None
    
    # 1. Save uploaded image proof
    if image:
        file_ext = os.path.splitext(image.filename)[1].lower() if image.filename else ".jpg"
        file_name = f"{uuid.uuid4()}{file_ext}"
        image_path = os.path.join(UPLOAD_DIR, file_name)
        
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        
        # Public URL path
        image_url = f"{UPLOAD_URL_PREFIX}/{file_name}"
        
        # 2. Run Multimodal Forensic Agent
        forensic_res = await run_forensic_agent(
            db=db,
            image_path=image_path,
            report_text=text,
            reported_location=location
        )
        
        verification_score = forensic_res.get("authenticity_score", 0.70)
        is_ai_generated = forensic_res.get("is_likely_ai_generated", False)
        forensic_log = forensic_res

    # 3. Run Signal Ingestion & Translation Agent
    agent_result = await run_ingestion_agent(
        db=db,
        text=text,
        source_type=source_type,
        location=location,
    )

    # 4. Save Signal with verification metrics
    signal = await create_signal(db, {
        "text": text,
        "normalized_text": agent_result.get("normalized_text"),
        "language": agent_result.get("language", "en"),
        "source_type": source_type,
        "location": agent_result.get("location", location),
        "latitude": latitude,
        "longitude": longitude,
        "image_url": image_url,
        "verification_score": verification_score,
        "is_ai_generated": is_ai_generated,
        "forensic_log": forensic_log
    })

    # Prepare signal dict for detection agent
    sig_dict = {
        "text": signal.text,
        "normalized_text": signal.normalized_text,
        "language": signal.language.value if hasattr(signal.language, "value") else signal.language,
        "source_type": signal.source_type.value if hasattr(signal.source_type, "value") else signal.source_type,
        "location": signal.location,
        "latitude": signal.latitude,
        "longitude": signal.longitude,
        "image_url": signal.image_url,
        "verification_score": signal.verification_score,
        "is_ai_generated": signal.is_ai_generated
    }

    # 5. Automatically trigger downstream multi-agent pipeline
    crisis_data = await run_detection_agent(db=db, signals=[sig_dict], location=location)
    report_data = await run_analysis_agent(db=db, crisis=crisis_data, signals=[sig_dict])
    actions_data = await run_planner_agent(db=db, situation_report=report_data, crisis=crisis_data)

    # Get agent execution logs
    agent_logs = await get_agent_logs_by_crisis(db, crisis_data["crisis_id"])

    return_data = {
        "signal": {
            "id": signal.id,
            "image_url": signal.image_url,
            "verification_score": signal.verification_score,
            "is_ai_generated": signal.is_ai_generated
        },
        "crisis": crisis_data,
        "situation_report": report_data,
        "actions": actions_data,
        "agent_logs": [_serialize_log(l) for l in agent_logs]
    }

    # 6. Broadcast to all active screens
    await manager.broadcast({"event": "new_crisis", "data": return_data})

    return return_data


def _serialize_signal(s):
    return {
        "id": s.id,
        "text": s.text,
        "normalized_text": s.normalized_text,
        "language": s.language.value if hasattr(s.language, "value") else s.language,
        "source_type": s.source_type.value if hasattr(s.source_type, "value") else s.source_type,
        "location": s.location,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "image_url": s.image_url,
        "verification_score": s.verification_score,
        "is_ai_generated": bool(s.is_ai_generated) if s.is_ai_generated is not None else False,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("/signals")
async def list_signals(db: AsyncSession = Depends(get_db)):
    signals = await get_signals(db)
    return [_serialize_signal(s) for s in signals]
