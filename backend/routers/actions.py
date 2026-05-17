from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from db.base import get_db
from db.crud import get_actions

router = APIRouter(prefix="/api", tags=["actions"])


@router.get("/actions")
async def list_actions(db: AsyncSession = Depends(get_db)):
    actions = await get_actions(db)
    return [
        {
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
        for a in actions
    ]
