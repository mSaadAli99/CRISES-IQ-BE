import os
import json
import time
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from db.crud import create_agent_log, create_crisis

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")


def _get_gemini_model():
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))


def _call_gemini(prompt: str) -> dict:
    model = _get_gemini_model()
    for attempt in range(2):
        try:
            response = model.generate_content(prompt)
            raw = response.text.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except json.JSONDecodeError as e:
            if attempt == 0:
                logger.warning(f"Agent2 JSON parse failed (attempt 1), retrying.")
                continue
            logger.error(f"Agent2 invalid JSON after retry: {response.text[:500]}")
            raise ValueError(f"Gemini returned invalid JSON: {str(e)}. Raw: {response.text[:300]}")
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Agent2 Gemini call failed (attempt 1): {e}")
                continue
            raise


async def run_detection_agent(
    db: AsyncSession,
    signals: list[dict],
    location: str,
) -> dict:
    start_time = time.time()

    signals_text = "\n".join([
        f"- [{s.get('source_type', 'unknown')}] {s.get('normalized_text', '')} (location: {s.get('location', location)})"
        for s in signals
    ])

    prompt = f"""You are a crisis detection agent for CrisisIQ, an urban emergency response system focused exclusively on Karachi, Pakistan.

Analyze these normalized signals and identify if they indicate an urban crisis. Return ONLY valid JSON.

Signals:
{signals_text}

Primary location context: {location} (Karachi)

Return this exact JSON structure:
{{
  "crisis_type": "flood or heatwave or accident or road_block",
  "location": "specific Karachi neighbourhood or road (e.g. Lyari, Clifton, SITE Industrial Area, M9 Motorway, Shahrah-e-Faisal)",
  "latitude": 24.8607,
  "longitude": 67.0100,
  "confidence_score": 0.85,
  "severity": "low or medium or high or critical",
  "reasoning": "explanation of why this is classified as this crisis type and severity"
}}

Rules:
- crisis_type must be exactly one of: flood, heatwave, accident, road_block
- severity must be exactly one of: low, medium, high, critical
- confidence_score must be a float between 0.0 and 1.0
- ALL coordinates must be within Karachi city bounds: latitude 24.74–25.10, longitude 66.75–67.25
- Common Karachi area coordinates: Lyari 24.860/67.010, Clifton 24.807/67.030, SITE 24.888/67.020, Korangi 24.827/67.125, Malir 24.897/67.198, Saddar 24.860/67.010, DHA 24.793/67.064, Gulshan 24.926/67.093, Orangi 24.945/67.010
- Return ONLY the JSON object, nothing else"""

    input_data = {"signals": signals, "location": location}

    try:
        result = _call_gemini(prompt)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await create_agent_log(db, {
            "crisis_id": None,
            "agent_number": 2,
            "agent_name": "Crisis Detection Agent",
            "input_data": input_data,
            "output_data": {"error": str(e)},
            "reasoning": "Detection failed",
            "duration_ms": duration_ms,
        })
        raise

    crisis = await create_crisis(db, {
        "crisis_type": result.get("crisis_type", "accident"),
        "location": result.get("location", location),
        "latitude": result.get("latitude"),
        "longitude": result.get("longitude"),
        "confidence_score": float(result.get("confidence_score", 0.5)),
        "severity": result.get("severity", "medium"),
        "status": "active",
    })

    duration_ms = int((time.time() - start_time) * 1000)
    output_data = {
        "crisis_id": crisis.id,
        "crisis_type": crisis.crisis_type.value if hasattr(crisis.crisis_type, 'value') else crisis.crisis_type,
        "location": crisis.location,
        "latitude": crisis.latitude,
        "longitude": crisis.longitude,
        "confidence_score": crisis.confidence_score,
        "severity": crisis.severity.value if hasattr(crisis.severity, 'value') else crisis.severity,
        "status": crisis.status.value if hasattr(crisis.status, 'value') else crisis.status,
    }

    await create_agent_log(db, {
        "crisis_id": crisis.id,
        "agent_number": 2,
        "agent_name": "Crisis Detection Agent",
        "input_data": input_data,
        "output_data": output_data,
        "reasoning": result.get("reasoning", ""),
        "duration_ms": duration_ms,
    })

    return output_data
