from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from db.base import get_db
from db.crud import get_agent_logs, get_stats

router = APIRouter(prefix="/api", tags=["logs"])


@router.get("/logs")
async def list_logs(db: AsyncSession = Depends(get_db)):
    logs = await get_agent_logs(db)
    return [
        {
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
        for l in logs
    ]


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    return await get_stats(db)
