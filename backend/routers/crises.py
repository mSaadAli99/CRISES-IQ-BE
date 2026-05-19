from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from db.base import get_db
from db.models import Signal
from db.crud import (
    get_crises,
    get_crisis_by_id,
    get_situation_report_by_crisis,
    get_actions_by_crisis,
    get_agent_logs_by_crisis,
    get_signals_by_ids,
    get_stats,
)
from agents.agent1_ingestion import run_ingestion_agent
from agents.agent2_detection import run_detection_agent
from agents.agent3_analysis import run_analysis_agent
from agents.agent4_planner import run_planner_agent
from db.crud import create_signal

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api", tags=["crises"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()


class PipelineRequest(BaseModel):
    signal_ids: list[int] = []
    location: str


def _serialize_crisis(c, *, include_social: bool = False):
    data = {
        "id": c.id,
        "crisis_type": c.crisis_type.value if hasattr(c.crisis_type, "value") else c.crisis_type,
        "location": c.location,
        "latitude": c.latitude,
        "longitude": c.longitude,
        "confidence_score": c.confidence_score,
        "severity": c.severity.value if hasattr(c.severity, "value") else c.severity,
        "status": c.status.value if hasattr(c.status, "value") else c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
    }
    if include_social:
        data["social_verification_sources"] = c.social_verification_sources or []
        sources = c.social_verification_sources or []
        data["social_sources_count"] = len(sources) if isinstance(sources, list) else 0
    return data


def _serialize_report(r):
    if not r:
        return None
    return {
        "id": r.id,
        "crisis_id": r.crisis_id,
        "severity_level": r.severity_level.value if hasattr(r.severity_level, "value") else r.severity_level,
        "affected_area": r.affected_area,
        "impact_estimate": r.impact_estimate,
        "reasoning": r.reasoning,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_action(a):
    return {
        "id": a.id,
        "crisis_id": a.crisis_id,
        "action_type": a.action_type.value if hasattr(a.action_type, "value") else a.action_type,
        "description": a.description,
        "status": a.status.value if hasattr(a.status, "value") else a.status,
        "simulation_result": a.simulation_result,
        "before_metrics": a.before_metrics,
        "after_metrics": a.after_metrics,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _serialize_log(l):
    return {
        "id": l.id,
        "crisis_id": l.crisis_id,
        "agent_number": l.agent_number,
        "agent_name": l.agent_name,
        "input_data": l.input_data,
        "output_data": l.output_data,
        "reasoning": l.reasoning,
        "duration_ms": l.duration_ms,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    }


@router.post("/pipeline")
async def run_pipeline(body: PipelineRequest, db: AsyncSession = Depends(get_db)):
    raw_signals = await get_signals_by_ids(db, body.signal_ids)
    if not raw_signals and not body.location:
        raise HTTPException(status_code=400, detail="Provide signal_ids or a location")

    normalized_signals = []
    for sig in raw_signals:
        agent1_out = await run_ingestion_agent(
            db=db,
            text=sig.text,
            source_type=sig.source_type.value if hasattr(sig.source_type, "value") else sig.source_type,
            location=sig.location or body.location,
        )
        normalized_signals.append(agent1_out)

    if not normalized_signals:
        normalized_signals = [{
            "normalized_text": f"Crisis signal reported at {body.location}",
            "language": "en",
            "source_type": "form",
            "location": body.location,
        }]

    crisis_data = await run_detection_agent(db=db, signals=normalized_signals, location=body.location)

    report_data = await run_analysis_agent(db=db, crisis=crisis_data, signals=normalized_signals)

    actions_data = await run_planner_agent(db=db, situation_report=report_data, crisis=crisis_data)

    agent_logs = await get_agent_logs_by_crisis(db, crisis_data["crisis_id"])

    return_data = {
        "crisis": crisis_data,
        "situation_report": report_data,
        "actions": actions_data,
        "agent_logs": [_serialize_log(l) for l in agent_logs],
    }
    
    # Broadcast to all connected websocket clients
    await manager.broadcast({"event": "new_crisis", "data": return_data})
    
    return return_data


@router.get("/crises")
async def list_crises(
    limit: Optional[int] = None, 
    offset: Optional[int] = 0, 
    db: AsyncSession = Depends(get_db)
):
    crises = await get_crises(db, limit=limit, offset=offset)
    return [_serialize_crisis(c) for c in crises]


@router.websocket("/ws/crises")
async def websocket_crises(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.get("/dashboard/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    db_stats = await get_stats(db)
    
    # Simulate agents running for now (you can add a real tracker later)
    # E.g., counting active pipelines or background workers
    agents_running = 4 
    
    return {
        "active_crises": db_stats.get("active_crises", 0),
        "agents_running": agents_running,
        "system_status": "stable"
    }


@router.get("/crises/{crisis_id}")
async def get_crisis(crisis_id: int, db: AsyncSession = Depends(get_db)):
    crisis = await get_crisis_by_id(db, crisis_id)
    if not crisis:
        raise HTTPException(status_code=404, detail="Crisis not found")

    report = await get_situation_report_by_crisis(db, crisis_id)
    actions = await get_actions_by_crisis(db, crisis_id)
    logs = await get_agent_logs_by_crisis(db, crisis_id)

    return {
        **_serialize_crisis(crisis, include_social=True),
        "situation_report": _serialize_report(report),
        "actions": [_serialize_action(a) for a in actions],
        "agent_logs": [_serialize_log(l) for l in logs],
    }
