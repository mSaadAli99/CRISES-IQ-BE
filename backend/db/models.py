import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey,
    Enum as SAEnum, JSON, func
)
from .base import Base


class LanguageEnum(str, enum.Enum):
    ur = "ur"
    en = "en"


class SourceTypeEnum(str, enum.Enum):
    social_media = "social_media"
    weather = "weather"
    traffic = "traffic"
    form = "form"


class CrisisTypeEnum(str, enum.Enum):
    flood = "flood"
    heatwave = "heatwave"
    accident = "accident"
    road_block = "road_block"


class SeverityEnum(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class CrisisStatusEnum(str, enum.Enum):
    active = "active"
    resolved = "resolved"
    monitoring = "monitoring"


class ActionTypeEnum(str, enum.Enum):
    reroute = "reroute"
    dispatch = "dispatch"
    alert = "alert"
    ticket = "ticket"


class ActionStatusEnum(str, enum.Enum):
    simulated = "simulated"
    pending = "pending"
    executed = "executed"


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    normalized_text = Column(Text, nullable=True)
    language = Column(SAEnum(LanguageEnum), nullable=True)
    source_type = Column(SAEnum(SourceTypeEnum), nullable=False)
    location = Column(String(255), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Crisis(Base):
    __tablename__ = "crises"

    id = Column(Integer, primary_key=True, index=True)
    crisis_type = Column(SAEnum(CrisisTypeEnum), nullable=False)
    location = Column(String(255), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=False)
    severity = Column(SAEnum(SeverityEnum), nullable=False)
    status = Column(SAEnum(CrisisStatusEnum), default=CrisisStatusEnum.active, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class SituationReport(Base):
    __tablename__ = "situation_reports"

    id = Column(Integer, primary_key=True, index=True)
    crisis_id = Column(Integer, ForeignKey("crises.id", ondelete="CASCADE"), nullable=False)
    severity_level = Column(SAEnum(SeverityEnum), nullable=False)
    affected_area = Column(String(500), nullable=False)
    impact_estimate = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Action(Base):
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True, index=True)
    crisis_id = Column(Integer, ForeignKey("crises.id", ondelete="CASCADE"), nullable=False)
    action_type = Column(SAEnum(ActionTypeEnum), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(SAEnum(ActionStatusEnum), default=ActionStatusEnum.simulated, nullable=False)
    simulation_result = Column(JSON, nullable=True)
    before_metrics = Column(JSON, nullable=True)
    after_metrics = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, index=True)
    crisis_id = Column(Integer, ForeignKey("crises.id", ondelete="SET NULL"), nullable=True)
    agent_number = Column(Integer, nullable=False)
    agent_name = Column(String(100), nullable=False)
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    reasoning = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
