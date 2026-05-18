"""
CrisisIQ ADK Tools
==================
Four async tool functions — one per pipeline phase — that wrap the existing
run_*_agent functions without modifying them.

Data flows through `tool_context.state` (ADK session state), which is
automatically shared across all sub-agents running in the same session.

Import pattern: all imports of db/agents code are LAZY (inside function
bodies) so this module loads cleanly even before FastAPI finishes startup.
"""
import json
import logging

from typing import Any, Protocol

logger = logging.getLogger(__name__)


class ToolStateContext(Protocol):
    """Tools only need a mutable `.state` dict (ToolContext or _StateContext)."""

    state: dict[str, Any]


# ---------------------------------------------------------------------------
# Tool 1 — Signal Ingestion
# ---------------------------------------------------------------------------

async def ingest_signals(
    signals_json: str,
    location: str,
    tool_context: ToolStateContext,
) -> str:
    """Ingest and normalize raw crisis signals from social media, weather APIs, and traffic systems.

    Args:
        signals_json: JSON array of signal objects. Each object must have:
            text (str), source_type (one of: social_media, weather, traffic, form),
            location (str).
        location: Primary Karachi location context (e.g. "Lyari Karachi").

    Returns:
        JSON confirmation string with the count of normalized signals.
    """
    # Lazy import — db.base is already loaded at server startup.
    from db.base import AsyncSessionLocal
    from agents.agent1_ingestion import run_ingestion_agent

    try:
        raw_signals = json.loads(signals_json)
        if not isinstance(raw_signals, list):
            raw_signals = [raw_signals]
    except (json.JSONDecodeError, TypeError):
        # Fall back gracefully: treat the whole string as a single text signal.
        raw_signals = [{"text": str(signals_json), "source_type": "form", "location": location}]

    normalized: list[dict] = []
    async with AsyncSessionLocal() as db:
        for sig in raw_signals:
            try:
                result = await run_ingestion_agent(
                    db=db,
                    text=sig.get("text", ""),
                    source_type=sig.get("source_type", "form"),
                    location=sig.get("location", location),
                )
                normalized.append(result)
            except Exception as exc:
                logger.warning(f"[ADK] Ingestion fallback for one signal: {exc}")
                normalized.append({
                    "normalized_text": sig.get("text", ""),
                    "language": "en",
                    "source_type": sig.get("source_type", "form"),
                    "location": location,
                })
        await db.commit()

    if not normalized:
        normalized = [{
            "normalized_text": f"Crisis signal reported at {location}",
            "language": "en",
            "source_type": "form",
            "location": location,
        }]

    # Persist to ADK session state so the next sub-agent can read it.
    tool_context.state["signals"] = normalized
    tool_context.state["location"] = location

    logger.info(f"[ADK] Ingestion complete — {len(normalized)} signal(s) normalized")
    return json.dumps({"status": "ingested", "signals_count": len(normalized)})


# ---------------------------------------------------------------------------
# Tool 2 — Crisis Detection
# ---------------------------------------------------------------------------

async def detect_crisis(
    location: str,
    tool_context: ToolStateContext,
) -> str:
    """Detect and classify the urban crisis from the normalized signals.

    Args:
        location: Karachi location where the crisis is occurring
            (e.g. "Lyari Karachi", "Shahrah-e-Faisal").

    Returns:
        JSON string with detected crisis_type, severity, confidence_score,
        and geo-coordinates.
    """
    from db.base import AsyncSessionLocal
    from agents.agent2_detection import run_detection_agent

    signals: list[dict] = tool_context.state.get("signals", [])
    if not signals:
        return json.dumps({"error": "No normalized signals in session state. Run ingest_signals first."})

    async with AsyncSessionLocal() as db:
        crisis = await run_detection_agent(db=db, signals=signals, location=location)
        await db.commit()

    tool_context.state["crisis"] = crisis

    logger.info(
        f"[ADK] Detection complete — {crisis.get('crisis_type')} "
        f"at {crisis.get('location')} ({crisis.get('severity')})"
    )
    return json.dumps({
        "status": "detected",
        "crisis_type": crisis.get("crisis_type"),
        "location": crisis.get("location"),
        "severity": crisis.get("severity"),
        "confidence_score": crisis.get("confidence_score"),
    })


# ---------------------------------------------------------------------------
# Tool 3 — Situation Analysis
# ---------------------------------------------------------------------------

async def analyze_situation(
    crisis_type: str,
    tool_context: ToolStateContext,
) -> str:
    """Generate a detailed situation analysis and impact report for the detected crisis.

    Args:
        crisis_type: The detected crisis type (e.g. "flood", "heatwave",
            "accident", "road_block"). Extract this from the detection output.

    Returns:
        JSON string with severity_level, affected_area, impact_estimate,
        reasoning, and recommended_actions.
    """
    from db.base import AsyncSessionLocal
    from agents.agent3_analysis import run_analysis_agent

    crisis: dict = tool_context.state.get("crisis", {})
    signals: list[dict] = tool_context.state.get("signals", [])

    if not crisis:
        return json.dumps({"error": "No crisis data in session state. Run detect_crisis first."})

    async with AsyncSessionLocal() as db:
        report = await run_analysis_agent(db=db, crisis=crisis, signals=signals)
        await db.commit()

    tool_context.state["report"] = report

    logger.info(
        f"[ADK] Analysis complete — {report.get('severity_level')} | "
        f"{report.get('affected_area')}"
    )
    return json.dumps({
        "status": "analyzed",
        "severity_level": report.get("severity_level"),
        "affected_area": report.get("affected_area"),
        "impact_estimate": report.get("impact_estimate"),
        "recommended_actions_count": len(report.get("recommended_actions", [])),
    })


# ---------------------------------------------------------------------------
# Tool 4 — Response Action Planning & Simulation
# ---------------------------------------------------------------------------

async def plan_response_actions(
    severity: str,
    tool_context: ToolStateContext,
) -> str:
    """Generate and simulate coordinated emergency response actions for the crisis.

    Produces before/after metrics for each action type (reroute, dispatch,
    alert, ticket) and persists them to the database.

    Args:
        severity: The crisis severity level (e.g. "critical", "high", "medium").
            Extract this from the situation analysis output.

    Returns:
        JSON string with simulated actions count and action types executed.
    """
    from db.base import AsyncSessionLocal
    from agents.agent4_planner import run_planner_agent

    crisis: dict = tool_context.state.get("crisis", {})
    report: dict = tool_context.state.get("report", {})

    if not crisis or not report:
        return json.dumps({
            "error": "Missing crisis or report data in session state. "
                     "Run detect_crisis and analyze_situation first."
        })

    async with AsyncSessionLocal() as db:
        actions = await run_planner_agent(db=db, situation_report=report, crisis=crisis)
        await db.commit()

    tool_context.state["actions"] = actions

    action_types = list({a.get("action_type") for a in actions if a.get("action_type")})
    logger.info(f"[ADK] Planning complete — {len(actions)} action(s): {action_types}")
    return json.dumps({
        "status": "planned",
        "actions_count": len(actions),
        "action_types": action_types,
    })
