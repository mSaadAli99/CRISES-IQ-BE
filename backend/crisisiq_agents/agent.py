"""
CrisisIQ ADK Agent Definitions
================================
Defines the Google ADK SequentialAgent that orchestrates the four-phase
CrisisIQ crisis response pipeline:

    Phase 1  signal_ingestion_agent   — normalizes raw signals (Urdu / English)
    Phase 2  crisis_detection_agent   — classifies crisis type, severity, confidence
    Phase 3  situation_analysis_agent — produces impact report + recommended actions
    Phase 4  action_planner_agent     — simulates response (reroute/dispatch/alert/ticket)

The root SequentialAgent (`crisis_pipeline_agent`) is the entry point for both:
  • `adk web`  — interactive tracing UI (run from backend/ directory)
  • Runner     — programmatic API calls via crisisiq_agents/runner.py

Nothing in agents/, routers/, or db/ is modified by this file.
"""
import logging
import os

from google.adk.agents import LlmAgent, SequentialAgent

from .tools import (
    analyze_situation,
    detect_crisis,
    ingest_signals,
    plan_response_actions,
)

logger = logging.getLogger(__name__)

# Gemini model used for each sub-agent's orchestration decision.
# Matches the model already used in the existing pipeline agents.
_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


# ---------------------------------------------------------------------------
# Phase 1 — Signal Ingestion Agent
# ---------------------------------------------------------------------------
signal_ingestion_agent = LlmAgent(
    name="signal_ingestion_agent",
    model=_MODEL,
    description="Ingests and normalizes raw crisis signals from social media, weather APIs, and traffic systems",
    instruction=(
        "You are the CrisisIQ Signal Ingestion Agent for Karachi, Pakistan.\n"
        "Your single task: call the `ingest_signals` tool exactly once.\n\n"
        "Parameters to pass:\n"
        "  • signals_json — the JSON array of signal objects from the user message "
        "(keep all fields: text, source_type, location)\n"
        "  • location — the primary Karachi location from the user message\n\n"
        "Do not explain your reasoning. Do not ask questions. "
        "Call the tool immediately and return its result."
    ),
    tools=[ingest_signals],
)


# ---------------------------------------------------------------------------
# Phase 2 — Crisis Detection Agent
# ---------------------------------------------------------------------------
crisis_detection_agent = LlmAgent(
    name="crisis_detection_agent",
    model=_MODEL,
    description="Detects and classifies urban crisis type, severity, and confidence from normalized signals",
    instruction=(
        "You are the CrisisIQ Crisis Detection Agent.\n"
        "The Signal Ingestion Agent has already normalized the signals — "
        "they are stored in session state.\n\n"
        "Your single task: call the `detect_crisis` tool exactly once.\n\n"
        "Parameters to pass:\n"
        "  • location — the Karachi location from the original user message\n\n"
        "Do not explain. Do not ask questions. Call the tool immediately."
    ),
    tools=[detect_crisis],
)


# ---------------------------------------------------------------------------
# Phase 3 — Situation Analysis Agent
# ---------------------------------------------------------------------------
situation_analysis_agent = LlmAgent(
    name="situation_analysis_agent",
    model=_MODEL,
    description="Generates situation analysis, impact assessment, and recommended response actions",
    instruction=(
        "You are the CrisisIQ Situation Analysis Agent.\n"
        "The crisis has been detected and stored in session state.\n\n"
        "Your single task: call the `analyze_situation` tool exactly once.\n\n"
        "Parameters to pass:\n"
        "  • crisis_type — the detected crisis type from the detection output "
        "(e.g. 'flood', 'heatwave', 'accident', 'road_block')\n\n"
        "Do not explain. Do not ask questions. Call the tool immediately."
    ),
    tools=[analyze_situation],
)


# ---------------------------------------------------------------------------
# Phase 4 — Action Planner Agent
# ---------------------------------------------------------------------------
action_planner_agent = LlmAgent(
    name="action_planner_agent",
    model=_MODEL,
    description="Plans and simulates coordinated emergency response actions with before/after metrics",
    instruction=(
        "You are the CrisisIQ Action Planning Agent.\n"
        "The situation report has been generated and stored in session state.\n\n"
        "Your single task: call the `plan_response_actions` tool exactly once.\n\n"
        "Parameters to pass:\n"
        "  • severity — the severity level from the situation analysis output "
        "(e.g. 'critical', 'high', 'medium', 'low')\n\n"
        "Do not explain. Do not ask questions. Call the tool immediately."
    ),
    tools=[plan_response_actions],
)


# ---------------------------------------------------------------------------
# Root Orchestrator — SequentialAgent
# ---------------------------------------------------------------------------
crisis_pipeline_agent = SequentialAgent(
    name="crisis_pipeline_agent",
    description=(
        "CrisisIQ multi-agent crisis response orchestrator for Karachi, Pakistan. "
        "Runs four agents in strict sequence: "
        "(1) signal ingestion, (2) crisis detection, "
        "(3) situation analysis, (4) action planning & simulation."
    ),
    sub_agents=[
        signal_ingestion_agent,
        crisis_detection_agent,
        situation_analysis_agent,
        action_planner_agent,
    ],
)

# Required alias for `adk web` auto-discovery.
root_agent = crisis_pipeline_agent
