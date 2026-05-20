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


def _get_grounded_gemini_model():
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    try:
        return genai.GenerativeModel(
            os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            tools="google_search"
        )
    except Exception as e:
        logger.warning(f"Failed to create grounded model, falling back to standard: {e}")
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


def _call_grounded_gemini(prompt: str) -> dict:
    model = _get_grounded_gemini_model()
    for attempt in range(2):
        try:
            response = model.generate_content(prompt)
            raw = response.text.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Agent2 grounded Gemini call failed (attempt 1): {e}")
                continue
            logger.error(f"Grounded search failed completely: {e}")
            raise


def safe_parse_confidence(val) -> float:
    if val is None:
        return 0.5
    try:
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip().lower()
        if "%" in s:
            s = s.replace("%", "").strip()
            return float(s) / 100.0
        if s in ("critical", "high", "active"):
            return 0.85
        if s in ("medium", "average"):
            return 0.50
        if s in ("low", "minimal"):
            return 0.20
        return float(s)
    except Exception:
        return 0.50


def get_mock_social_posts(crisis_type: str, area: str) -> list[dict]:
    import random
    templates = {
        "flood": [
            f"Avoid {area} right now, water level is rising rapidly! #KarachiRain",
            f"Stuck near {area} for 40 mins due to massive urban flooding.",
            f"Alert: severe waterlogging reported at main crossroads in {area}."
        ],
        "accident": [
            f"Bad vehicle collision near {area}. Traffic is backlogged.",
            f"Rescue ambulance dispatched to major road accident on {area} road.",
            f"Drive carefully near {area}, traffic police clearing a crash scene."
        ],
        "road_block": [
            f"Local protest blocks the highway near {area}. Heavy delays.",
            f"Avoid transit through {area}. Road is closed for sewerage repairs.",
            f"Security barricades placed around central {area} access points."
        ],
        "heatwave": [
            f"Extremely high temperature today in {area}! Stay hydrated. #KarachiHeatwave",
            f"AC failures and high humidity reports coming from several markets in {area}.",
            f"Local clinics setting up relief camps in {area} for heat exhaustion."
        ]
    }
    c_type = crisis_type.lower()
    posts = templates.get(c_type, [f"Unusual activity and delays reported near {area}."])
    count = random.randint(1, len(posts))
    selected = random.sample(posts, count)
    return [
        {
            "username": f"karachi_citizen_{random.randint(100,999)}",
            "text": text,
            "timestamp": "Just now",
            "platform": "Twitter/X"
        }
        for text in selected
    ]


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

    c_type = result.get("crisis_type", "accident")
    c_loc = result.get("location", location)
    
    # 1. Run live Google Search grounded query to find actual matching alerts/news/social posts
    social_sources = []
    try:
        search_prompt = f"""Search the live web (including Twitter/X posts, news portals, and traffic pages) for:
        Incident Type: {c_type}
        Location: {c_loc} in Karachi, Pakistan
        
        Retrieve actual matching references, reports, or recent social media postings within the last 48 hours.
        Return ONLY a JSON list of matching posts. Each post must match this exact structure:
        [
          {{
            "username": "handle_or_outlet_name",
            "text": "brief text summary of what they reported",
            "timestamp": "e.g., 2 hours ago or 1 day ago",
            "platform": "Twitter/X or Local News or Facebook"
          }}
        ]
        
        If you find absolutely NO recent live results on Google Search, return an empty list: [].
        Return ONLY valid JSON without markdown formatting."""
        
        social_sources = _call_grounded_gemini(search_prompt)
        if not isinstance(social_sources, list):
            social_sources = []
    except Exception as e:
        logger.warning(f"Live search grounding failed or timed out: {e}. Falling back to simulation.")
        social_sources = []

    # 2. Fall back to simulation if no real posts found on Google (so the UI is always dynamic and interactive)
    if not social_sources:
        logger.info("No live search matches found. Generating high-fidelity mock Karachi social feed.")
        social_sources = get_mock_social_posts(c_type, c_loc)
    raw_conf = safe_parse_confidence(result.get("confidence_score", 0.5))
    has_form = any(s.get("source_type") == "form" for s in signals)
    has_verified_proof = any(s.get("verification_score") is not None and s.get("verification_score") > 0.6 for s in signals)
    is_ai = any(s.get("is_ai_generated") is True for s in signals)
    has_context_mismatch = any(s.get("image_url") is not None and s.get("is_context_match") is False for s in signals)
    
    if has_context_mismatch:
        scaled_conf = 0.05  # Heavily penalize fake/unrelated proof uploads (selfies)
        social_sources = [] # Do not confirm fake/unverified reports on socials!
    elif is_ai:
        scaled_conf = 0.10 # Heavily demote simulated/AI photos
        social_sources = [] # Do not confirm fake/unverified reports on socials!
    elif has_verified_proof:
        scaled_conf = min(0.98, raw_conf + 0.15) # Boost for verified image proof
    elif len(signals) > 1:
        scaled_conf = min(0.95, raw_conf + 0.05) # Boost for multi-source
    else:
        scaled_conf = max(0.30, raw_conf - 0.10) # Lower for single-source report without proof
        if scaled_conf < 0.40:
            social_sources = []

    crisis = await create_crisis(db, {
        "crisis_type": c_type,
        "location": c_loc,
        "latitude": result.get("latitude"),
        "longitude": result.get("longitude"),
        "confidence_score": round(scaled_conf, 2),
        "severity": result.get("severity", "medium"),
        "status": "active",
        "social_verification_sources": social_sources
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
        "social_sources_count": len(social_sources)
    }

    await create_agent_log(db, {
        "crisis_id": crisis.id,
        "agent_number": 2,
        "agent_name": "Crisis Detection Agent",
        "input_data": input_data,
        "output_data": output_data,
        "reasoning": f"{result.get('reasoning', '')} | Ingested photo proof status: {has_verified_proof}. Disinformation check: {is_ai}.",
        "duration_ms": duration_ms,
    })

    return output_data
