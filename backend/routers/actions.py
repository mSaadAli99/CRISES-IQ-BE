from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.base import get_db
from db.crud import get_actions
from db.models import Action

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


@router.post("/actions/{action_id}/execute")
async def execute_action_endpoint(action_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Action).where(Action.id == action_id))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    
    action.status = "executed"
    await db.commit()
    
    return {
        "id": action.id,
        "crisis_id": action.crisis_id,
        "action_type": action.action_type.value if hasattr(action.action_type, "value") else action.action_type,
        "description": action.description,
        "status": action.status.value if hasattr(action.status, "value") else action.status,
        "simulation_result": action.simulation_result,
        "before_metrics": action.before_metrics,
        "after_metrics": action.after_metrics,
        "created_at": action.created_at.isoformat() if action.created_at else None,
    }
