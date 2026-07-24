import asyncio
import sys
import os
from datetime import datetime, date, timedelta, timezone

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.config import settings
from app.db.base import User, LeadSource, Lead, LeadTimeline
from app.models.enums import LeadStatus

def _ts(days_ago: int = 0, hours_ago: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)

async def seed_existing_investors():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        # Fetch some users and sources
        users_result = await db.execute(select(User).limit(5))
        users = users_result.scalars().all()
        if not users:
            print("No users found. Please run seed_demo.py first.")
            return
            
        sources_result = await db.execute(select(LeadSource).limit(2))
        sources = sources_result.scalars().all()
        if not sources:
            print("No sources found.")
            return
            
        rep1 = users[1] if len(users) > 1 else users[0]
        rep2 = users[2] if len(users) > 2 else users[0]
        src1 = sources[0]
        
        # Create Existing Investors
        leads = [
            Lead(
                name="Amitabh Bachchan", profession="Actor",
                email="amitabh.b@example.com", phone_number="9876543210",
                address="Juhu, Mumbai",
                status=LeadStatus.existing_investor, source_id=src1.id,
                assigned_rep_id=rep1.id, last_contact=date.today() - timedelta(days=45),
            ),
            Lead(
                name="Sachin Tendulkar", profession="Sportsman",
                email="sachin.t@example.com", phone_number="9876543211",
                address="Bandra, Mumbai",
                status=LeadStatus.existing_investor, source_id=src1.id,
                assigned_rep_id=rep2.id, last_contact=date.today() - timedelta(days=30),
            )
        ]
        
        db.add_all(leads)
        await db.flush()
        
        # Add Timelines
        timelines = [
            LeadTimeline(
                lead_id=leads[0].id, user_id=rep1.id,
                event_type="status_change", created_at=_ts(days_ago=60),
                event_metadata={"old_status": "converted_to_investor", "new_status": "existing_investor", "changed_by": "monthly_rollover_job"}
            ),
            LeadTimeline(
                lead_id=leads[1].id, user_id=rep2.id,
                event_type="status_change", created_at=_ts(days_ago=40),
                event_metadata={"old_status": "converted_to_investor", "new_status": "existing_investor", "changed_by": "monthly_rollover_job"}
            ),
        ]
        db.add_all(timelines)
        await db.commit()
        print("✅ Added 2 Existing Investors successfully.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed_existing_investors())
