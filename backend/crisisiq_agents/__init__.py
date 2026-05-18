"""
CrisisIQ ADK Agents Package
============================
Google Agent Development Kit (ADK) wrapper around the CrisisIQ 4-agent pipeline.

This package exposes `root_agent` — the entry point required by `adk web`
and the ADK Runner — and bridges the GEMINI_API_KEY environment variable
to the GOOGLE_API_KEY name that ADK expects.

Existing backend code (agents/, routers/, db/) is completely untouched.
"""
import os

# ADK uses GOOGLE_API_KEY; CrisisIQ stores the key as GEMINI_API_KEY.
# Set it here before any ADK import so the LlmAgents can authenticate.
_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
if _api_key and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = _api_key

try:
    from .agent import crisis_pipeline_agent as root_agent  # noqa: F401

    __all__ = ["root_agent"]
except Exception:
    # Graceful degradation if google-adk is not installed.
    pass
