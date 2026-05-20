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

    prompt = f"""You are a strict digital forensics and image verification agent for CrisisIQ, a crisis response system.

Your job is to determine TWO things about the attached photograph:

────────────────────────────────────────────
TASK 1 — CONTEXT MATCH (most important)
────────────────────────────────────────────
The user claims: "{report_text}"
Location context: {reported_location} (Karachi, Pakistan)

Does this image ACTUALLY SHOW evidence of the reported crisis?

BE EXTREMELY STRICT. Ask yourself:
- Does the image show an actual emergency scene (flood, accident, fire, road blockage, etc.)?
- Or is it just a selfie, portrait, random photo, food, meme, screenshot, or unrelated image?
- A photo of a person's face / selfie is NEVER valid proof of any crisis.
- A photo of a normal street, building, or room is NOT proof of a crisis.
- The image must show VISIBLE, CLEAR evidence of the specific crisis type being reported.

If the image does not clearly depict the reported crisis, set is_context_match to FALSE.

────────────────────────────────────────────
TASK 2 — AI GENERATION DETECTION
────────────────────────────────────────────
Check for AI-generated image markers:
- Warped text, melted fingers, impossible geometry
- Unnatural lighting/shadows, airbrushed textures
- Inconsistent perspective or physically impossible scenes

────────────────────────────────────────────
SCORING RULES
────────────────────────────────────────────
authenticity_score combines BOTH tasks:
- If image is a selfie/portrait/unrelated → authenticity_score must be 0.05 to 0.15
- If image is related but unclear/ambiguous → authenticity_score 0.20 to 0.40
- If image shows the crisis but may be AI-generated → authenticity_score 0.15 to 0.30
- If image clearly shows real evidence of the reported crisis → authenticity_score 0.70 to 0.95
- NEVER give authenticity_score above 0.40 if is_context_match is false

Return ONLY a valid JSON object (no markdown, no backticks):
{{
  "is_context_match": false,
  "context_match_reasoning": "This is a selfie/portrait photo showing a person's face. It contains zero evidence of the reported crisis.",
  "ai_generation_probability": 0.05,
  "is_likely_ai_generated": false,
  "forensic_markers_found": ["human face", "no crisis evidence visible"],
  "authenticity_score": 0.10
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
        
        # Enforce scoring consistency: if not context match, cap authenticity
        if not result.get("is_context_match", False):
            result["authenticity_score"] = min(
                result.get("authenticity_score", 0.1), 0.20
            )
            logger.info(
                "Forensic agent: image does NOT match reported crisis. "
                "Capped authenticity_score to %.2f. Reason: %s",
                result["authenticity_score"],
                result.get("context_match_reasoning", "N/A")
            )
        
    except Exception as e:
        logger.error(f"Multimodal forensic agent failed: {e}")
        duration_ms = int((time.time() - start_time) * 1000)
        
        # On error, default to NOT trusting the image
        err_res = {
            "is_context_match": False,
            "context_match_reasoning": f"Forensic analysis failed (Service Error: {str(e)}). Defaulting to unverified.",
            "ai_generation_probability": 0.0,
            "is_likely_ai_generated": False,
            "forensic_markers_found": ["analysis_failed"],
            "authenticity_score": 0.15
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
