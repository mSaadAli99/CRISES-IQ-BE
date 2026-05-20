import time
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from db.crud import create_agent_log
from llm_config import call_gemini_json

logger = logging.getLogger(__name__)


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
        result = call_gemini_json(prompt, agent_label="Agent1")
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
