from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date
from .models import Signal, Crisis, SituationReport, Action, AgentLog, CrisisStatusEnum


async def create_signal(db: AsyncSession, data: dict) -> Signal:
    signal = Signal(**data)
    db.add(signal)
    await db.flush()
    await db.refresh(signal)
    return signal


async def get_signals(db: AsyncSession) -> list[Signal]:
    result = await db.execute(select(Signal).order_by(Signal.created_at.desc()))
    return result.scalars().all()


async def get_signals_by_ids(db: AsyncSession, ids: list[int]) -> list[Signal]:
    result = await db.execute(select(Signal).where(Signal.id.in_(ids)))
    return result.scalars().all()


async def create_crisis(db: AsyncSession, data: dict) -> Crisis:
    crisis = Crisis(**data)
    db.add(crisis)
    await db.flush()
    await db.refresh(crisis)
    return crisis


async def get_crises(db: AsyncSession) -> list[Crisis]:
    result = await db.execute(select(Crisis).order_by(Crisis.created_at.desc()))
    return result.scalars().all()


async def get_crisis_by_id(db: AsyncSession, crisis_id: int) -> Optional[Crisis]:
    result = await db.execute(select(Crisis).where(Crisis.id == crisis_id))
    return result.scalar_one_or_none()


async def create_situation_report(db: AsyncSession, data: dict) -> SituationReport:
    report = SituationReport(**data)
    db.add(report)
    await db.flush()
    await db.refresh(report)
    return report


async def get_situation_report_by_crisis(db: AsyncSession, crisis_id: int) -> Optional[SituationReport]:
    result = await db.execute(
        select(SituationReport).where(SituationReport.crisis_id == crisis_id)
        .order_by(SituationReport.created_at.desc())
    )
    return result.scalars().first()


async def create_action(db: AsyncSession, data: dict) -> Action:
    action = Action(**data)
    db.add(action)
    await db.flush()
    await db.refresh(action)
    return action


async def get_actions(db: AsyncSession) -> list[Action]:
    result = await db.execute(select(Action).order_by(Action.created_at.desc()))
    return result.scalars().all()


async def get_actions_by_crisis(db: AsyncSession, crisis_id: int) -> list[Action]:
    result = await db.execute(
        select(Action).where(Action.crisis_id == crisis_id).order_by(Action.created_at.asc())
    )
    return result.scalars().all()


async def create_agent_log(db: AsyncSession, data: dict) -> AgentLog:
    log = AgentLog(**data)
    db.add(log)
    await db.flush()
    await db.refresh(log)
    return log


async def get_agent_logs(db: AsyncSession) -> list[AgentLog]:
    result = await db.execute(select(AgentLog).order_by(AgentLog.created_at.desc()))
    return result.scalars().all()


async def get_agent_logs_by_crisis(db: AsyncSession, crisis_id: int) -> list[AgentLog]:
    result = await db.execute(
        select(AgentLog).where(AgentLog.crisis_id == crisis_id).order_by(AgentLog.created_at.asc())
    )
    return result.scalars().all()


async def get_stats(db: AsyncSession) -> dict:
    active_crises_result = await db.execute(
        select(func.count()).where(Crisis.status == CrisisStatusEnum.active)
    )
    active_crises = active_crises_result.scalar() or 0

    total_signals_result = await db.execute(select(func.count()).select_from(Signal))
    total_signals = total_signals_result.scalar() or 0

    alerts_result = await db.execute(
        select(func.count()).select_from(Action).where(Action.action_type == "alert")
    )
    alerts_sent = alerts_result.scalar() or 0

    today = datetime.now(timezone.utc).date()
    resolved_result = await db.execute(
        select(func.count()).where(
            Crisis.status == CrisisStatusEnum.resolved,
            cast(Crisis.resolved_at, Date) == today
        )
    )
    resolved_today = resolved_result.scalar() or 0

    return {
        "active_crises": active_crises,
        "total_signals": total_signals,
        "alerts_sent": alerts_sent,
        "resolved_today": resolved_today,
    }
