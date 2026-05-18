"""
Central LLM configuration for CrisisIQ.

Supports two backends (set in .env):
  • API key  — Google AI Studio (GEMINI_API_KEY), free tier quotas apply
  • Vertex AI — Google Cloud (ADC via `gcloud auth application-default login`)

Vertex uses your GCP $300 trial / billing and avoids AI Studio free-tier limits.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_LOCATION = "us-central1"


def use_vertex_ai() -> bool:
    flag = (
        os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")
        or os.environ.get("CRISISIQ_USE_VERTEX_AI")
        or ""
    ).strip().lower()
    return flag in ("1", "true", "yes", "on")


def get_model_name() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def apply_llm_env() -> None:
    """Set env vars for ADK / google-genai before any client is created."""
    if use_vertex_ai():
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        if not project:
            raise ValueError(
                "GOOGLE_GENAI_USE_VERTEXAI is enabled but GOOGLE_CLOUD_PROJECT is not set"
            )
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION)
        logger.info(
            "LLM backend: Vertex AI (project=%s, location=%s)",
            project,
            os.environ["GOOGLE_CLOUD_LOCATION"],
        )
    else:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        if api_key and not os.environ.get("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = api_key
        logger.debug("LLM backend: Gemini API key (AI Studio)")


def configure_generativeai() -> None:
    """Configure google.generativeai for pipeline agents."""
    import google.generativeai as genai

    if use_vertex_ai():
        project = os.environ["GOOGLE_CLOUD_PROJECT"].strip()
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION)
        genai.configure(vertexai=True, project=project, location=location)
    else:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is required when Vertex AI is disabled. "
                "Set GOOGLE_GENAI_USE_VERTEXAI=true to use GCP instead."
            )
        genai.configure(api_key=api_key)


def get_generative_model():
    """Return a configured GenerativeModel (shared by all pipeline agents)."""
    import google.generativeai as genai

    configure_generativeai()
    return genai.GenerativeModel(get_model_name())


def call_gemini_json(prompt: str, *, agent_label: str = "agent") -> dict:
    """Call Gemini and parse a JSON object from the response."""
    import json

    model = get_generative_model()
    last_error: Exception | None = None
    raw = ""

    for attempt in range(2):
        try:
            response = model.generate_content(prompt)
            raw = response.text.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except json.JSONDecodeError as e:
            last_error = e
            if attempt == 0:
                logger.warning(
                    "%s JSON parse failed (attempt 1), retrying. Raw: %s",
                    agent_label,
                    raw[:200],
                )
                continue
            raise ValueError(
                f"Gemini returned invalid JSON: {e}. Raw: {raw[:300]}"
            ) from e
        except Exception as e:
            last_error = e
            if attempt == 0:
                logger.warning("%s Gemini call failed (attempt 1): %s", agent_label, e)
                continue
            raise

    if last_error:
        raise last_error
    raise RuntimeError(f"{agent_label}: Gemini call failed")
