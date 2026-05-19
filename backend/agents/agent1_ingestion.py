import os
import json
import time
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from db.crud import create_agent_log

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
                logger.warning(f"Agent1 JSON parse failed (attempt 1), retrying. Raw: {response.text[:200]}")
                continue
            logger.error(f"Agent1 Gemini returned invalid JSON after retry: {response.text[:500]}")
            raise ValueError(f"Gemini returned invalid JSON: {str(e)}. Raw: {response.text[:300]}")
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Agent1 Gemini call failed (attempt 1): {e}")
                continue
            raise


async def run_ingestion_agent(
    db: AsyncSession,
    text: str,
    source_type: str,
    location: str,
    crisis_id: int | None = None,
) -> dict:
    start_time = time.time()

    prompt = f"""You are a crisis signal ingestion agent for CrisisIQ, an urban emergency response system focused exclusively on Karachi, Pakistan.

Analyze the following raw signal text and return ONLY a valid JSON object. No markdown, no backticks, no explanation.

Raw signal text: "{text}"
Source type: {source_type}
Provided location: {location}

Return this exact JSON structure:
{{
  "normalized_text": "cleaned English translation or original if already English",
  "language": "ur or en",
  "location": "specific Karachi neighbourhood/area extracted from text, or '{location}' if unclear",
  "source_type": "{source_type}",
  "reasoning": "brief explanation of normalization decisions"
}}

Rules:
- All signals are assumed to originate from Karachi, Pakistan — normalize location names to Karachi districts/areas (e.g. Lyari, Clifton, SITE, Korangi, Malir, North Nazimabad, Gulshan-e-Iqbal, Saddar, DHA, Orangi Town)
- If text is in Urdu, translate it to English for normalized_text and set language to "ur"
- If text is already English, keep it cleaned and set language to "en"
- Extract specific Karachi location names from the text if present
- Return ONLY the JSON object, nothing else"""

    input_data = {"text": text, "source_type": source_type, "location": location}

    try:
        result = _call_gemini(prompt)
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        err_str = str(e)
        is_quota = (
            "429" in err_str
            or "quota" in err_str.lower()
            or "ResourceExhausted" in err_str
        )
        if is_quota:
            logger.warning("Agent1 quota exceeded — using passthrough fallback: %s", err_str[:200])
            output_data = {
                "normalized_text": text,
                "language": "en",
                "location": location,
                "source_type": source_type,
            }
            await create_agent_log(db, {
                "crisis_id": crisis_id,
                "agent_number": 1,
                "agent_name": "Signal Ingestion Agent",
                "input_data": input_data,
                "output_data": output_data,
                "reasoning": "Gemini quota exceeded; stored raw signal without LLM normalization.",
                "duration_ms": duration_ms,
            })
            return output_data
        await create_agent_log(db, {
            "crisis_id": crisis_id,
            "agent_number": 1,
            "agent_name": "Signal Ingestion Agent",
            "input_data": input_data,
            "output_data": {"error": err_str},
            "reasoning": "Failed to process signal",
            "duration_ms": duration_ms,
        })
        raise

    duration_ms = int((time.time() - start_time) * 1000)
    output_data = {
        "normalized_text": result.get("normalized_text", text),
        "language": result.get("language", "en"),
        "location": result.get("location", location),
        "source_type": source_type,
    }

    await create_agent_log(db, {
        "crisis_id": crisis_id,
        "agent_number": 1,
        "agent_name": "Signal Ingestion Agent",
        "input_data": input_data,
        "output_data": output_data,
        "reasoning": result.get("reasoning", ""),
        "duration_ms": duration_ms,
    })

    return output_data
