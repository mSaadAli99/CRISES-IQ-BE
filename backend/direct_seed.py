import asyncio
import os
import sys
from dotenv import load_dotenv

# Add current directory to path so we can import db modules
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)

# Load the backend's .env file explicitly before any other imports
load_dotenv(os.path.join(backend_dir, ".env"))

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from db.base import DATABASE_URL
from db.models import Crisis, SituationReport, Action, Signal, CrisisTypeEnum, SeverityEnum, CrisisStatusEnum, ActionTypeEnum, ActionStatusEnum, SourceTypeEnum, LanguageEnum

async def seed():
    print(f"Connecting to database: {DATABASE_URL}")
    engine = create_async_engine(DATABASE_URL)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as db:
        # Clear existing data first to ensure clean state
        print("Clearing existing tables...")
        await db.execute(delete(Action))
        await db.execute(delete(SituationReport))
        await db.execute(delete(Signal))
        await db.execute(delete(Crisis))
        await db.commit()
        
        print("Seeding database with Karachi crises...")
        
        # 1. Urban Flood in Lyari
        flood_crisis = Crisis(
            crisis_type=CrisisTypeEnum.flood,
            location="Lyari, Karachi",
            latitude=24.8607,
            longitude=67.0100,
            confidence_score=0.95,
            severity=SeverityEnum.critical,
            status=CrisisStatusEnum.active
        )
        db.add(flood_crisis)
        await db.flush()
        
        flood_report = SituationReport(
            crisis_id=flood_crisis.id,
            severity_level=SeverityEnum.critical,
            affected_area="Lyari and Orangi Town",
            impact_estimate="Over 10,000 households affected. Critical infrastructure submerged.",
            reasoning="Persistent heavy rainfall of 95mm in 3 hours caused Lyari River to overflow, trapping residents on rooftops."
        )
        db.add(flood_report)
        
        flood_signals = [
            Signal(text="Lyari mein paani bhar gaya hai, ghar ke andar aa raha hai! Madad chahiye", normalized_text="Water is flooding in Lyari, entering houses! Need help", language=LanguageEnum.ur, source_type=SourceTypeEnum.social_media, location="Lyari Karachi", latitude=24.8607, longitude=67.0100),
            Signal(text="Lyari River overflowing — streets completely submerged. Families trapped.", normalized_text="Lyari River overflowing — streets completely submerged. Families trapped.", language=LanguageEnum.en, source_type=SourceTypeEnum.social_media, location="Lyari Karachi", latitude=24.8607, longitude=67.0100)
        ]
        for sig in flood_signals:
            db.add(sig)
            
        flood_actions = [
            Action(crisis_id=flood_crisis.id, action_type=ActionTypeEnum.reroute, description="Deploy Rerouting Agent for Lyari traffic corridors", status=ActionStatusEnum.simulated, simulation_result={"success": True, "impact_score": 9.0}, before_metrics={"delay_mins": 45}, after_metrics={"delay_mins": 15}),
            Action(crisis_id=flood_crisis.id, action_type=ActionTypeEnum.dispatch, description="Dispatch Pakistan Navy & Edhi rescue boats to Lyari sector", status=ActionStatusEnum.executed, simulation_result={"success": True}, before_metrics={"deployed": False}, after_metrics={"deployed": True}),
            Action(crisis_id=flood_crisis.id, action_type=ActionTypeEnum.alert, description="Broadcast SMS alert to Lyari & Orangi residents to move to higher ground", status=ActionStatusEnum.executed)
        ]
        for act in flood_actions:
            db.add(act)
            
        # 2. Heatwave in Saddar & SITE
        heat_crisis = Crisis(
            crisis_type=CrisisTypeEnum.heatwave,
            location="SITE Industrial Area, Karachi",
            latitude=24.8877,
            longitude=67.0200,
            confidence_score=0.88,
            severity=SeverityEnum.high,
            status=CrisisStatusEnum.active
        )
        db.add(heat_crisis)
        await db.flush()
        
        heat_report = SituationReport(
            crisis_id=heat_crisis.id,
            severity_level=SeverityEnum.high,
            affected_area="SITE and Saddar districts",
            impact_estimate="High threat to outdoor laborers and elderly. Risk of heatstroke casualties.",
            reasoning="Temperatures hitting 47°C with high humidity levels forecast for next 72 hours."
        )
        db.add(heat_report)
        
        heat_signals = [
            Signal(text="Karachi mein garmi ki wajah se log behosh ho rahe hain. SITE Industrial Area mein 5 workers hospital pohanche.", normalized_text="People are fainting due to heat in Karachi. 5 workers reached the hospital in SITE Industrial Area.", language=LanguageEnum.ur, source_type=SourceTypeEnum.social_media, location="SITE Industrial Area Karachi", latitude=24.8877, longitude=67.0200),
            Signal(text="Temperature hitting 47°C in Karachi today. Multiple heat stroke cases reported.", normalized_text="Temperature hitting 47°C in Karachi today. Multiple heat stroke cases reported.", language=LanguageEnum.en, source_type=SourceTypeEnum.social_media, location="Saddar Karachi", latitude=24.8560, longitude=67.0100)
        ]
        for sig in heat_signals:
            db.add(sig)
            
        heat_actions = [
            Action(crisis_id=heat_crisis.id, action_type=ActionTypeEnum.dispatch, description="Establish emergency cooling centers and water stations in Saddar and SITE", status=ActionStatusEnum.executed),
            Action(crisis_id=heat_crisis.id, action_type=ActionTypeEnum.alert, description="Issue mobile heatwave alert advising indoor staying during peak hours", status=ActionStatusEnum.executed)
        ]
        for act in heat_actions:
            db.add(act)
            
        # 3. Road Accident on Shahrah-e-Faisal
        accident_crisis = Crisis(
            crisis_type=CrisisTypeEnum.accident,
            location="Shahrah-e-Faisal near Nursery, Karachi",
            latitude=24.8756,
            longitude=67.0613,
            confidence_score=0.98,
            severity=SeverityEnum.medium,
            status=CrisisStatusEnum.active
        )
        db.add(accident_crisis)
        await db.flush()
        
        accident_report = SituationReport(
            crisis_id=accident_crisis.id,
            severity_level=SeverityEnum.medium,
            affected_area="Shahrah-e-Faisal arterial corridor",
            impact_estimate="Severe gridlock on Karachi's busiest commuter corridor. Emergency vehicles delayed.",
            reasoning="Multi-vehicle pileup near Nursery involving 5 cars, completely blocking traffic in both directions."
        )
        db.add(accident_report)
        
        accident_signals = [
            Signal(text="Shahrah-e-Faisal par badi accident ho gayi — 3 gariyan takra gayi hain.", normalized_text="Major accident on Shahrah-e-Faisal - 3 cars collided.", language=LanguageEnum.ur, source_type=SourceTypeEnum.social_media, location="Shahrah-e-Faisal Karachi", latitude=24.8756, longitude=67.0613)
        ]
        for sig in accident_signals:
            db.add(sig)
            
        accident_actions = [
            Action(crisis_id=accident_crisis.id, action_type=ActionTypeEnum.reroute, description="Reroute traffic via Korangi Road and University Road", status=ActionStatusEnum.executed, simulation_result={"success": True}, before_metrics={"commuters": 4500}, after_metrics={"commuters": 1200}),
            Action(crisis_id=accident_crisis.id, action_type=ActionTypeEnum.dispatch, description="Dispatch traffic police towing trucks to clear Nursery pileup", status=ActionStatusEnum.executed)
        ]
        for act in accident_actions:
            db.add(act)
            
        await db.commit()
        print("Database successfully seeded directly!")

if __name__ == "__main__":
    asyncio.run(seed())
