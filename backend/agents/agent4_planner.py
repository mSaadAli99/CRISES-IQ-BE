import time
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from db.crud import create_agent_log, create_action
from llm_config import call_gemini_json

logger = logging.getLogger(__name__)


def _simulate_reroute(action_desc: str, location: str) -> tuple[dict, dict]:
    before = {
        "avg_speed_kmh": 12,
        "congestion_level": "severe",
        "estimated_delay_min": 45,
        "affected_roads": [location],
        "vehicles_affected": 2400,
    }
    after = {
        "avg_speed_kmh": 38,
        "congestion_level": "light",
        "estimated_delay_min": 8,
        "alternate_routes_activated": 2,
        "vehicles_rerouted": 1800,
    }
    return before, after


def _simulate_dispatch(action_desc: str, location: str) -> tuple[dict, dict]:
    before = {
        "response_units_on_scene": 0,
        "estimated_response_time_min": None,
        "casualties_receiving_aid": 0,
    }
    after = {
        "response_units_on_scene": 4,
        "estimated_response_time_min": 7,
        "casualties_receiving_aid": 18,
        "units_dispatched": ["Rescue 1122 Unit A", "Ambulance B-7", "Fire Brigade F-3", "NDMA Rapid Team"],
    }
    return before, after


def _simulate_alert(action_desc: str, location: str) -> tuple[dict, dict]:
    before = {
        "public_awareness_pct": 5,
        "alerts_sent": 0,
        "evacuation_compliance_pct": 0,
    }
    after = {
        "public_awareness_pct": 78,
        "alerts_sent": 45000,
        "sms_alerts": 38000,
        "push_notifications": 7000,
        "evacuation_compliance_pct": 62,
        "media_broadcasts": 3,
    }
    return before, after


def _simulate_ticket(action_desc: str, location: str) -> tuple[dict, dict]:
    before = {
        "ticket_status": "not_created",
        "assigned_department": None,
        "estimated_resolution_hours": None,
    }
    after = {
        "ticket_id": f"CIQ-{int(time.time()) % 100000}",
        "ticket_status": "created",
        "priority": "P1-Critical",
        "assigned_department": "NDMA / CDA Emergency Cell",
        "estimated_resolution_hours": 6,
        "escalation_chain": ["District Commissioner", "PDMA", "Federal NDMA"],
    }
    return before, after


_SIMULATORS = {
    "reroute": _simulate_reroute,
    "dispatch": _simulate_dispatch,
    "alert": _simulate_alert,
    "ticket": _simulate_ticket,
}


async def run_planner_agent(
    db: AsyncSession,
    situation_report: dict,
    crisis: dict,
) -> list[dict]:
    start_time = time.time()
    crisis_id = crisis.get("crisis_id")
    location = crisis.get("location", "")

    recommended = situation_report.get("recommended_actions", [])
    actions_text = "\n".join([
        f"- [{a.get('action_type')}] {a.get('description')}"
        for a in recommended
    ])

    prompt = f"""You are an action planning agent for CrisisIQ, an urban emergency response system focused exclusively on Karachi, Pakistan.

Given the situation report, generate detailed executable action plans with simulation results. Return ONLY valid JSON.

Crisis: {crisis.get('crisis_type')} at {location}, Karachi (severity: {crisis.get('severity')})
Situation: {situation_report.get('impact_estimate')}

Recommended actions:
{actions_text}

Return this exact JSON structure:
{{
  "actions": [
    {{
      "action_type": "reroute or dispatch or alert or ticket",
      "description": "detailed Karachi-specific action with agency names, road names, hospital names, and contact numbers",
      "simulation_result": {{
        "success": true,
        "message": "brief simulation outcome",
        "confidence": 0.92
      }}
    }}
  ],
  "reasoning": "overall planning rationale for Karachi context"
}}

Rules:
- Include all recommended action types (reroute, dispatch, alert, ticket)
- Use Karachi-specific agencies: Edhi (115), Chhipa (1020), KMC, KDA, KWSB, Sindh Police (15), Rangers, PDMA Sindh, Civil Hospital, Jinnah Hospital, Abbasi Shaheed Hospital, Karachi Metropolitan Corporation
- Use Karachi-specific roads for rerouting: Shahrah-e-Faisal, M9 Motorway, Northern Bypass, Super Highway, Hub River Road, Korangi Road, University Road, Lyari Expressway
- simulation_result.confidence must be between 0.5 and 0.99
- Return ONLY the JSON object, nothing else"""

    input_data = {
        "situation_report_id": situation_report.get("report_id"),
        "recommended_actions_count": len(recommended),
    }

    try:
        result = call_gemini_json(prompt, agent_label="Agent4")
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        await create_agent_log(db, {
            "crisis_id": crisis_id,
            "agent_number": 4,
            "agent_name": "Action Planner Agent",
            "input_data": input_data,
            "output_data": {"error": str(e)},
            "reasoning": "Planning failed",
            "duration_ms": duration_ms,
        })
        raise

    saved_actions = []
    for action_data in result.get("actions", []):
        action_type = action_data.get("action_type", "ticket")
        simulator = _SIMULATORS.get(action_type, _simulate_ticket)
        before_metrics, after_metrics = simulator(action_data.get("description", ""), location)

        action = await create_action(db, {
            "crisis_id": crisis_id,
            "action_type": action_type,
            "description": action_data.get("description", ""),
            "status": "simulated",
            "simulation_result": action_data.get("simulation_result", {}),
            "before_metrics": before_metrics,
            "after_metrics": after_metrics,
        })

        saved_actions.append({
            "id": action.id,
            "action_type": action_type,
            "description": action.description,
            "status": "simulated",
            "simulation_result": action.simulation_result,
            "before_metrics": action.before_metrics,
            "after_metrics": action.after_metrics,
        })

    duration_ms = int((time.time() - start_time) * 1000)
    output_data = {
        "actions_created": len(saved_actions),
        "actions": saved_actions,
    }

    await create_agent_log(db, {
        "crisis_id": crisis_id,
        "agent_number": 4,
        "agent_name": "Action Planner Agent",
        "input_data": input_data,
        "output_data": output_data,
        "reasoning": result.get("reasoning", ""),
        "duration_ms": duration_ms,
    })

    return saved_actions
