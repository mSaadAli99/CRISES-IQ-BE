import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from db.base import get_db
from agents.agent1_ingestion import run_ingestion_agent
from agents.agent2_detection import run_detection_agent
from agents.agent3_analysis import run_analysis_agent
from agents.agent4_planner import run_planner_agent
from db.crud import create_signal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["seed"])

DEMO_SCENARIOS = [
    {
        "name": "Urban Flood in Lyari Karachi",
        "signals": [
            {
                "text": "Lyari mein paani bhar gaya hai, ghar ke andar aa raha hai! Madad chahiye",
                "source_type": "social_media",
                "location": "Lyari Karachi",
                "latitude": 24.8607,
                "longitude": 67.0100,
            },
            {
                "text": "Lyari River overflowing — streets in Lyari, Orangi Town completely submerged. Families trapped on rooftops. Edhi and Chhipa teams needed urgently.",
                "source_type": "social_media",
                "location": "Lyari Karachi",
                "latitude": 24.8607,
                "longitude": 67.0100,
            },
            {
                "text": "Rainfall alert: 95mm recorded in past 3 hours in Karachi. Flash flood risk CRITICAL for Lyari, Orangi Town, SITE Industrial Area, Korangi.",
                "source_type": "weather",
                "location": "Karachi",
                "latitude": 24.8607,
                "longitude": 67.0100,
            },
        ],
    },
    {
        "name": "Heatwave in SITE and Saddar Karachi",
        "signals": [
            {
                "text": "Karachi mein garmi ki wajah se log behosh ho rahe hain. SITE Industrial Area mein 5 workers hospital pohanche.",
                "source_type": "social_media",
                "location": "SITE Industrial Area Karachi",
                "latitude": 24.8877,
                "longitude": 67.0200,
            },
            {
                "text": "Temperature hitting 47°C in Karachi today. Multiple heat stroke cases reported in SITE area and Saddar. Edhi ambulances overwhelmed.",
                "source_type": "social_media",
                "location": "Saddar Karachi",
                "latitude": 24.8560,
                "longitude": 67.0100,
            },
            {
                "text": "Heat Advisory: Karachi — temperature forecast 46-49°C for next 72 hours. Humidity 72%. Extreme health risk for outdoor workers.",
                "source_type": "weather",
                "location": "Karachi",
                "latitude": 24.8607,
                "longitude": 67.0100,
            },
            {
                "text": "EDO Health Karachi: 18 heat stroke patients admitted to Civil Hospital and Abbasi Shaheed Hospital since morning. Requesting emergency cooling centers in SITE.",
                "source_type": "form",
                "location": "Civil Hospital Karachi",
                "latitude": 24.8680,
                "longitude": 67.0100,
            },
        ],
    },
    {
        "name": "Road Accident on Shahrah-e-Faisal Karachi",
        "signals": [
            {
                "text": "Shahrah-e-Faisal par badi accident ho gayi — 3 gariyan takra gayi hain. Raasta band hai.",
                "source_type": "social_media",
                "location": "Shahrah-e-Faisal Karachi",
                "latitude": 24.8756,
                "longitude": 67.0613,
            },
            {
                "text": "Multi-vehicle pileup on Shahrah-e-Faisal near Nursery. 5 cars involved, road completely blocked both directions. Karachi Traffic Police on scene.",
                "source_type": "social_media",
                "location": "Shahrah-e-Faisal near Nursery Karachi",
                "latitude": 24.8756,
                "longitude": 67.0613,
            },
            {
                "text": "Traffic jam extending 8km on Shahrah-e-Faisal. Commuters advised to use Korangi Road or University Road as alternate routes.",
                "source_type": "traffic",
                "location": "Shahrah-e-Faisal Karachi",
                "latitude": 24.8756,
                "longitude": 67.0613,
            },
        ],
    },
]


@router.post("/seed")
async def seed_database(db: AsyncSession = Depends(get_db)):
    results = []

    for scenario in DEMO_SCENARIOS:
        try:
            saved_signals = []
            normalized_signals = []

            try:
                # Try running the full agentic AI pipeline
                for sig_data in scenario["signals"]:
                    agent1_out = await run_ingestion_agent(
                        db=db,
                        text=sig_data["text"],
                        source_type=sig_data["source_type"],
                        location=sig_data["location"],
                    )

                    signal = await create_signal(db, {
                        "text": sig_data["text"],
                        "normalized_text": agent1_out.get("normalized_text"),
                        "language": agent1_out.get("language", "en"),
                        "source_type": sig_data["source_type"],
                        "location": agent1_out.get("location", sig_data["location"]),
                        "latitude": sig_data.get("latitude"),
                        "longitude": sig_data.get("longitude"),
                    })
                    saved_signals.append(signal)
                    normalized_signals.append(agent1_out)

                location = scenario["signals"][0]["location"]
                crisis_data = await run_detection_agent(db=db, signals=normalized_signals, location=location)
                report_data = await run_analysis_agent(db=db, crisis=crisis_data, signals=normalized_signals)
                actions_data = await run_planner_agent(db=db, situation_report=report_data, crisis=crisis_data)

                results.append({
                    "scenario": scenario["name"],
                    "status": "success",
                    "crisis_id": crisis_data.get("crisis_id"),
                    "signals_created": len(saved_signals),
                    "actions_created": len(actions_data),
                })
            except Exception as pipeline_err:
                logger.warning(f"AI pipeline failed, falling back to direct database seed: {pipeline_err}")
                
                # Bypassing AI agents: direct SQL insert for robust demo seeding
                from db.models import Crisis, SituationReport, Action, CrisisTypeEnum, SeverityEnum, CrisisStatusEnum, ActionTypeEnum, ActionStatusEnum
                
                # Determine type and severity based on scenario name
                name_lower = scenario["name"].lower()
                c_type = CrisisTypeEnum.flood
                if "heatwave" in name_lower:
                    c_type = CrisisTypeEnum.heatwave
                elif "accident" in name_lower:
                    c_type = CrisisTypeEnum.accident

                # Create direct Crisis record
                first_sig = scenario["signals"][0]
                db_crisis = Crisis(
                    crisis_type=c_type,
                    location=first_sig["location"],
                    latitude=first_sig.get("latitude"),
                    longitude=first_sig.get("longitude"),
                    confidence_score=0.92,
                    severity=SeverityEnum.critical if "flood" in name_lower or "heatwave" in name_lower else SeverityEnum.medium,
                    status=CrisisStatusEnum.active
                )
                db.add(db_crisis)
                await db.flush()

                # Create direct Situation Report
                db_report = SituationReport(
                    crisis_id=db_crisis.id,
                    severity_level=db_crisis.severity,
                    affected_area=db_crisis.location,
                    impact_estimate="High impact on transport and public health" if c_type == CrisisTypeEnum.heatwave else "Severe localized disruptions",
                    reasoning=f"Direct seed fallback for {scenario['name']}."
                )
                db.add(db_report)

                # Create direct Actions
                actions_to_create = []
                if c_type == CrisisTypeEnum.flood:
                    actions_to_create = [
                        ("Deploy Rerouting Agent", ActionTypeEnum.reroute),
                        ("Alert Emergency Rescue Services", ActionTypeEnum.dispatch),
                        ("Send SMS broadcast warning to nearby area", ActionTypeEnum.alert)
                    ]
                elif c_type == CrisisTypeEnum.heatwave:
                    actions_to_create = [
                        ("Open public cooling centers in Sadar & SITE", ActionTypeEnum.dispatch),
                        ("Send heat advisory broadcast SMS", ActionTypeEnum.alert)
                    ]
                else:
                    actions_to_create = [
                        ("Dispatch traffic control team", ActionTypeEnum.dispatch),
                        ("Coordinate alternate route rerouting", ActionTypeEnum.reroute)
                    ]

                for desc, act_type in actions_to_create:
                    db_action = Action(
                        crisis_id=db_crisis.id,
                        action_type=act_type,
                        description=desc,
                        status=ActionStatusEnum.simulated,
                        simulation_result={"success": True, "impact_score": 8.5},
                        before_metrics={"traffic_delay_mins": 25},
                        after_metrics={"traffic_delay_mins": 10}
                    )
                    db.add(db_action)

                await db.commit()

                results.append({
                    "scenario": scenario["name"],
                    "status": "success_direct_seed",
                    "crisis_id": db_crisis.id,
                    "signals_created": len(saved_signals),
                    "actions_created": len(actions_to_create),
                })

        except Exception as e:
            logger.error(f"Seed failed for scenario '{scenario['name']}': {e}")
            results.append({
                "scenario": scenario["name"],
                "status": "failed",
                "error": str(e),
            })

    return {
        "message": "Database seeded successfully",
        "results": results,
    }
