import time
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from db.crud import create_agent_log, create_situation_report
from llm_config import call_gemini_json

logger = logging.getLogger(__name__)


async def run_analysis_agent(
    db: AsyncSession,
    crisis: dict,
    signals: list[dict],
) -> dict:
    start_time = time.time()
    crisis_id = crisis.get("crisis_id")

    signals_summary = "\n".join([
        f"- [{s.get('source_type', 'unknown')}] {s.get('normalized_text', '')}"
        for s in signals
    ])

    prompt = f"""You are a situation analysis agent for CrisisIQ, an urban emergency response system focused exclusively on Karachi, Pakistan.

Perform a detailed analysis of this crisis and generate a situation report. Return ONLY valid JSON.

Crisis details:
- Type: {crisis.get('crisis_type')}
- Location: {crisis.get('location')} (Karachi)
- Severity: {crisis.get('severity')}
- Confidence: {crisis.get('confidence_score')}

Related signals:
{signals_summary}

Return this exact JSON structure:
{{
  "severity_level": "low or medium or high or critical",
  "affected_area": "specific Karachi districts/roads affected (e.g. 'Lyari, Orangi Town, SITE Industrial Area')",
  "impact_estimate": "estimated residents/commuters affected and specific Karachi infrastructure at risk",
  "reasoning": "detailed analysis referencing Karachi's urban layout, drainage issues, traffic patterns",
  "recommended_actions": [
    {{
      "action_type": "reroute or dispatch or alert or ticket",
      "description": "specific action with Karachi roads, agencies, and contact details"
    }}
  ]
}}

Rules:
- severity_level must be exactly one of: low, medium, high, critical
- recommended_actions should have 3-5 specific, actionable items for Karachi emergency context
- action_type must be exactly one of: reroute, dispatch, alert, ticket
- Reference Karachi-specific agencies: Edhi Foundation, Chhipa, KMC, KDA, KWSB, Karachi Metropolitan Corporation, Rangers, Sindh Police, PDMA Sindh, 1122, Civil Hospital, Jinnah Hospital, Abbasi Shaheed Hospital
- Reference Karachi roads: Shahrah-e-Faisal, M9 Motorway, Northern Bypass, Super Highway, Hub River Road, Korangi Road, University Road
- Return ONLY the JSON object, nothing else"""

    input_data = {"crisis": crisis, "signals_count": len(signals)}

    try:
        result = call_gemini_json(prompt, agent_label="Agent3")
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await create_agent_log(db, {
            "crisis_id": crisis_id,
            "agent_number": 3,
            "agent_name": "Situation Analysis Agent",
            "input_data": input_data,
            "output_data": {"error": str(e)},
            "reasoning": "Analysis failed",
            "duration_ms": duration_ms,
        })
        raise

    report = await create_situation_report(db, {
        "crisis_id": crisis_id,
        "severity_level": result.get("severity_level", crisis.get("severity", "medium")),
        "affected_area": result.get("affected_area", crisis.get("location", "")),
        "impact_estimate": result.get("impact_estimate", "Unknown"),
        "reasoning": result.get("reasoning", ""),
    })

    duration_ms = int((time.time() - start_time) * 1000)
    output_data = {
        "report_id": report.id,
        "severity_level": report.severity_level.value if hasattr(report.severity_level, 'value') else report.severity_level,
        "affected_area": report.affected_area,
        "impact_estimate": report.impact_estimate,
        "reasoning": report.reasoning,
        "recommended_actions": result.get("recommended_actions", []),
    }

    await create_agent_log(db, {
        "crisis_id": crisis_id,
        "agent_number": 3,
        "agent_name": "Situation Analysis Agent",
        "input_data": input_data,
        "output_data": output_data,
        "reasoning": result.get("reasoning", ""),
        "duration_ms": duration_ms,
    })

    return output_data
