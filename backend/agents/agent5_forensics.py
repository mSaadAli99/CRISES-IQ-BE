import os
import json
import time
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from db.crud import create_agent_log
from llm_config import get_generative_model, call_gemini_json

logger = logging.getLogger(__name__)

async def run_forensic_agent(
    db: AsyncSession,
    image_path: str,
    report_text: str,
    reported_location: str,
    crisis_id: int | None = None,
) -> dict:
    """
    Multimodal Forensic Verification Agent.
    Analyzes uploaded proof photos for context accuracy and AI image generation synthesis markers.
    """
    start_time = time.time()
    
    # 1. Prepare GenAI Multimodal payload
    try:
        import google.generativeai as genai
    except ImportError:
        logger.error("google-generativeai is not installed")
        raise
        
    if not os.path.exists(image_path):
        logger.error(f"Forensic photo not found: {image_path}")
        return {
            "is_context_match": False,
            "context_match_reasoning": "Proof photo not found.",
            "ai_generation_probability": 0.0,
            "is_likely_ai_generated": False,
            "forensic_markers_found": [],
            "authenticity_score": 0.0
        }

    # Determine correct mime type
    ext = os.path.splitext(image_path)[1].lower()
    mime_type = "image/png" if ext == ".png" else "image/jpeg"
    
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    image_part = {
        "mime_type": mime_type,
        "data": img_bytes
    }

    prompt = f"""You are a digital forensics and AI image synthesis analysis agent for CrisisIQ.
    
    Analyze the attached proof photograph along with this metadata:
    - User reported text: "{report_text}"
    - Reported location context: {reported_location} (Karachi, Pakistan)
    
    Verify the following two aspects carefully:
    1. **Context Compatibility:** Does the image accurately portray the reported incident (e.g. flooded roads, car crash, traffic block, power outages)?
    2. **AI Synthesis Detection:** Check if the image displays structural inconsistencies typical of generative AI (e.g. melted text, unnatural shadow angles, physically impossible line/geometry blending, distorted anatomy, or typical airbrushed texture signatures).
    
    Return ONLY a valid JSON object matching this structure (no markdown, no backticks, no extra wrapper):
    {{
      "is_context_match": true,
      "context_match_reasoning": "Provide brief observational proof reasoning",
      "ai_generation_probability": 0.05,
      "is_likely_ai_generated": false,
      "forensic_markers_found": ["natural shadows", "clear structural lines"],
      "authenticity_score": 0.95
    }}
    """

    input_data = {
        "image_path": image_path,
        "report_text": report_text,
        "location": reported_location
    }

    try:
        model = get_generative_model()
        response = model.generate_content([prompt, image_part])
        raw = response.text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
    except Exception as e:
        logger.error(f"Multimodal forensic agent failed: {e}")
        duration_ms = int((time.time() - start_time) * 1000)
        
        err_res = {
            "is_context_match": True,  # Fallback to true if LLM error
            "context_match_reasoning": f"Forensic lookup bypass (Service Error: {str(e)}).",
            "ai_generation_probability": 0.0,
            "is_likely_ai_generated": False,
            "forensic_markers_found": ["bypass_due_to_error"],
            "authenticity_score": 0.70
        }
        
        await create_agent_log(db, {
            "crisis_id": crisis_id,
            "agent_number": 5,
            "agent_name": "Image Forensics Agent",
            "input_data": input_data,
            "output_data": err_res,
            "reasoning": f"Forensic analysis failed: {str(e)}",
            "duration_ms": duration_ms
        })
        return err_res

    duration_ms = int((time.time() - start_time) * 1000)
    
    # Save log in database
    await create_agent_log(db, {
        "crisis_id": crisis_id,
        "agent_number": 5,
        "agent_name": "Image Forensics Agent",
        "input_data": input_data,
        "output_data": result,
        "reasoning": result.get("context_match_reasoning", ""),
        "duration_ms": duration_ms
    })

    return result
