"""
CrisisIQ ADK Runner
====================
Two execution modes (CRISISIQ_ADK_MODE env var):

  direct (default)
      Runs the four ADK tool functions in sequence with shared session state.
      Reliable, fast, one Gemini call per phase (inside existing agents).
      Best for POST /api/adk/pipeline in production demos.

  llm
      Full ADK Runner + SequentialAgent + LlmAgent orchestration.
      Each sub-agent uses an extra Gemini call to decide tool invocation.
      Best for `adk web` trace demos; slower and more failure-prone.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_APP_NAME = "crisisiq"
_USER_ID = "crisisiq_api"
MAX_EVENTS = 80


class _StateContext:
    """Minimal stand-in for ToolContext — tools only read/write `.state`."""

    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state


async def _run_direct_pipeline(signals: list[dict], location: str) -> dict[str, Any]:
    """
    Deterministic ADK tool chain — same four tools, shared state, no extra LLM hops.
    """
    from .tools import (
        analyze_situation,
        detect_crisis,
        ingest_signals,
        plan_response_actions,
    )

    state: dict[str, Any] = {}
    ctx = _StateContext(state)

    await ingest_signals(json.dumps(signals, ensure_ascii=False), location, ctx)
    await detect_crisis(location, ctx)

    crisis = state.get("crisis") or {}
    crisis_type = crisis.get("crisis_type", "flood")
    await analyze_situation(str(crisis_type), ctx)

    report = state.get("report") or {}
    severity = (
        report.get("severity_level")
        or crisis.get("severity")
        or "high"
    )
    await plan_response_actions(str(severity), ctx)

    session_id = str(uuid.uuid4())
    logger.info(
        f"[ADK/direct] Pipeline complete session={session_id} "
        f"crisis={crisis.get('crisis_type')} actions={len(state.get('actions') or [])}"
    )

    return {
        "session_id": session_id,
        "orchestrator": "google-adk/tools-sequential",
        "mode": "direct",
        "agents_run": [
            "signal_ingestion_agent",
            "crisis_detection_agent",
            "situation_analysis_agent",
            "action_planner_agent",
        ],
        "crisis": state.get("crisis"),
        "situation_report": state.get("report"),
        "actions": state.get("actions", []),
    }


async def _run_llm_pipeline(signals: list[dict], location: str) -> dict[str, Any]:
    """
    Full ADK Runner with SequentialAgent — for interactive trace / adk web parity.
    """
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part

    from .agent import crisis_pipeline_agent

    session_id = str(uuid.uuid4())
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=_APP_NAME,
        user_id=_USER_ID,
        session_id=session_id,
        state={},
    )

    runner = Runner(
        agent=crisis_pipeline_agent,
        app_name=_APP_NAME,
        session_service=session_service,
    )

    prompt = (
        f"Process the CrisisIQ emergency pipeline for location: {location}\n\n"
        f"Raw signals:\n{json.dumps(signals, ensure_ascii=False, indent=2)}\n\n"
        "Execute the pipeline:\n"
        "1. signal_ingestion_agent — call ingest_signals\n"
        "2. crisis_detection_agent — call detect_crisis\n"
        "3. situation_analysis_agent — call analyze_situation\n"
        "4. action_planner_agent — call plan_response_actions\n"
    )

    logger.info(f"[ADK/llm] Starting session {session_id} for '{location}'")

    event_count = 0
    async for event in runner.run_async(
        user_id=_USER_ID,
        session_id=session_id,
        new_message=Content(role="user", parts=[Part(text=prompt)]),
    ):
        event_count += 1
        if event.is_final_response():
            logger.info(f"[ADK/llm] Session {session_id} done ({event_count} events)")
            break
        if event_count >= MAX_EVENTS:
            logger.warning(f"[ADK/llm] Session {session_id} hit MAX_EVENTS={MAX_EVENTS}")
            break

    session = await session_service.get_session(
        app_name=_APP_NAME,
        user_id=_USER_ID,
        session_id=session_id,
    )
    state: dict = session.state if session else {}

    return {
        "session_id": session_id,
        "orchestrator": "google-adk/SequentialAgent",
        "mode": "llm",
        "agents_run": [
            "signal_ingestion_agent",
            "crisis_detection_agent",
            "situation_analysis_agent",
            "action_planner_agent",
        ],
        "crisis": state.get("crisis"),
        "situation_report": state.get("report"),
        "actions": state.get("actions", []),
    }


async def run_adk_pipeline(signals: list[dict], location: str) -> dict[str, Any]:
    """
    Run the CrisisIQ pipeline through Google ADK.

    Mode controlled by CRISISIQ_ADK_MODE:
      direct (default) | llm
    On llm failure, falls back to direct so the API still returns a result.
    """
    from platform_async import ensure_compatible_event_loop

    ensure_compatible_event_loop()

    mode = os.environ.get("CRISISIQ_ADK_MODE", "direct").strip().lower()

    if mode == "llm":
        try:
            return await _run_llm_pipeline(signals, location)
        except Exception as exc:
            logger.warning(f"[ADK] LLM mode failed ({exc}), falling back to direct")
            result = await _run_direct_pipeline(signals, location)
            result["fallback_from"] = "llm"
            result["fallback_reason"] = str(exc)
            return result

    return await _run_direct_pipeline(signals, location)
