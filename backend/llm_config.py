"""
Central LLM configuration for CrisisIQ.

Supports two backends (set in .env):
  • API key  — Google AI Studio (GEMINI_API_KEY), free tier quotas apply
  • Vertex AI — Google Cloud (ADC via `gcloud auth application-default login`)

Vertex uses your GCP $300 trial / billing and avoids AI Studio free-tier limits.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_LOCATION = "us-central1"
VERTEX_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def use_vertex_ai() -> bool:
    flag = (
        os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")
        or os.environ.get("CRISISIQ_USE_VERTEX_AI")
        or ""
    ).strip().lower()
    return flag in ("1", "true", "yes", "on")


def get_model_name() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def _write_credentials_json() -> None:
    """Materialize Vercel's JSON env var into /tmp for Google auth."""
    raw_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
    raw_b64 = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON_BASE64", "").strip()
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    if not raw_json and raw_b64:
        raw_json = base64.b64decode(raw_b64).decode("utf-8")
    if not raw_json:
        return

    credentials_path = Path("/tmp/google-credentials.json")
    credentials_path.write_text(raw_json, encoding="utf-8")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credentials_path)


def apply_llm_env() -> None:
    """Set env vars for ADK / google-genai before any client is created."""
    if use_vertex_ai():
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        if not project:
            raise ValueError(
                "GOOGLE_GENAI_USE_VERTEXAI is enabled but GOOGLE_CLOUD_PROJECT is not set"
            )
        _write_credentials_json()
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

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is required when Vertex AI is disabled. "
            "Set GOOGLE_GENAI_USE_VERTEXAI=true to use GCP instead."
        )
    genai.configure(api_key=api_key)


def _vertex_access_token() -> str:
    import google.auth
    from google.auth.transport.requests import Request

    apply_llm_env()
    credentials, _ = google.auth.default(scopes=[VERTEX_SCOPE])
    credentials.refresh(Request())
    return credentials.token


def _vertex_part(part) -> dict:
    if isinstance(part, str):
        return {"text": part}
    if isinstance(part, dict) and "data" in part:
        data = part["data"]
        if isinstance(data, bytes):
            data = base64.b64encode(data).decode("ascii")
        return {
            "inlineData": {
                "mimeType": part.get("mime_type", "application/octet-stream"),
                "data": data,
            }
        }
    return {"text": str(part)}


def _extract_vertex_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    for candidate in candidates:
        parts = ((candidate.get("content") or {}).get("parts")) or []
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        if text:
            return text
    raise RuntimeError(f"Vertex AI returned no text: {payload}")


def _call_vertex_generate_content(parts: list) -> str:
    apply_llm_env()
    project = os.environ["GOOGLE_CLOUD_PROJECT"].strip()
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", DEFAULT_LOCATION).strip()
    model = get_model_name()
    endpoint = (
        f"https://{location}-aiplatform.googleapis.com/v1/"
        f"projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent"
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [_vertex_part(part) for part in parts],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_vertex_access_token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return _extract_vertex_text(json.loads(response.read().decode("utf-8")))


@dataclass
class _TextResponse:
    text: str


class _VertexGenerativeModel:
    def generate_content(self, content):
        parts = content if isinstance(content, list) else [content]
        return _TextResponse(text=_call_vertex_generate_content(parts))


def get_generative_model():
    """Return a configured GenerativeModel (shared by all pipeline agents)."""
    if use_vertex_ai():
        apply_llm_env()
        return _VertexGenerativeModel()
    import google.generativeai as genai

    configure_generativeai()
    return genai.GenerativeModel(get_model_name())

def call_gemini_json(prompt: str, *, agent_label: str = "agent") -> dict:
    """Call Gemini and parse a JSON object from the response."""

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
