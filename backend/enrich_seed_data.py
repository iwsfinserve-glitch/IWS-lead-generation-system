"""
enrich_seed_data.py
Enriches database with:
- Manager-subordinate links (rahul, sneha, vikram -> manager anish)
- Sample pending LeadUpdateRequest records
- Sample pending LeadTransferRequest records
"""

import asyncio
import sys
import os
from datetime import datetime, date, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text
from app.core.config import settings
from app.db.base import User, Lead, LeadUpdateRequest, LeadTransferRequest, Notification
from app.models.enums import UserRole

async def enrich():
    engine = create_async_engine(settings.DATABASE_URL)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        # Find manager
        mgr_res = await db.execute(select(User).where(User.username == "anish@iwsfinserve.com"))
        manager = mgr_res.scalar_one_or_none()
        if not manager:
            mgr_res2 = await db.execute(select(User).where(User.role == UserRole.manager))
            manager = mgr_res2.scalars().first()

        if not manager:
            print("No manager found in database!")
            return

        print(f"Using Manager: {manager.id} ({manager.username})")

        # Update sales reps to have this manager_id
        await db.execute(
            text(f"UPDATE users SET manager_id = {manager.id} WHERE role = 'sales_rep'")
        )
        await db.commit()
        print("Updated sales reps with manager_id.")

        # Get some leads and reps
        reps_res = await db.execute(select(User).where(User.role == UserRole.sales_rep))
        reps = reps_res.scalars().all()
        rep_rahul = next((r for r in reps if "rahul" in (r.username or "")), reps[0] if reps else None)
        rep_sneha = next((r for r in reps if "sneha" in (r.username or "")), reps[1] if len(reps) > 1 else None)
        rep_vikram = next((r for r in reps if "vikram" in (r.username or "")), reps[2] if len(reps) > 2 else None)

        leads_res = await db.execute(select(Lead))
        leads = leads_res.scalars().all()

        if leads and rep_rahul:
            # Assign some leads specifically to Rahul
            leads[0].assigned_rep_id = rep_rahul.id
            if len(leads) > 1:
                leads[1].assigned_rep_id = rep_rahul.id
            if len(leads) > 2 and rep_sneha:
                leads[2].assigned_rep_id = rep_sneha.id
            if len(leads) > 3 and rep_vikram:
                leads[3].assigned_rep_id = rep_vikram.id
            await db.commit()
            print("Assigned leads to reps.")

            # Create sample pending LeadUpdateRequest if none exists
            req_check = await db.execute(select(LeadUpdateRequest).where(LeadUpdateRequest.status == "pending"))
            existing_reqs = req_check.scalars().all()
            if not existing_reqs:
                lead1 = leads[0]
                update_req1 = LeadUpdateRequest(
                    lead_id=lead1.id,
                    requested_by_id=rep_rahul.id,
                    manager_id=manager.id,
                    current_email=lead1.email or "old.client@example.com",
                    proposed_email="anil.shetty.direct@gmail.com",
                    current_phone=lead1.phone_number or "+91 98234 56701",
                    proposed_phone="+91 98234 99999",
                    current_address=lead1.address or "Porvorim, Goa",
                    proposed_address="Villa 4B, Emerald Palms, Porvorim, Goa",
                    reason="Client updated their primary business mobile number and official correspondence address during portfolio consultation.",
                    status="pending",
                    created_at=datetime.now(timezone.utc),
                )
                db.add(update_req1)

                if len(leads) > 2 and rep_sneha:
                    lead2 = leads[2]
                    update_req2 = LeadUpdateRequest(
                        lead_id=lead2.id,
                        requested_by_id=rep_sneha.id,
                        manager_id=manager.id,
                        current_email=lead2.email or "kavita.pai@outlook.com",
                        proposed_email="kavita.architect@studio-pai.com",
                        current_phone=lead2.phone_number or "+91 98234 56702",
                        proposed_phone="+91 98234 88888",
                        reason="Client requested communication on their newly established architectural firm email ID.",
                        status="pending",
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(update_req2)

                await db.commit()
                print("Created sample pending LeadUpdateRequest records.")

            # Create sample pending LeadTransferRequest if none exists
            trans_check = await db.execute(select(LeadTransferRequest).where(LeadTransferRequest.status == "pending"))
            existing_trans = trans_check.scalars().all()
            if not existing_trans and len(leads) > 3 and rep_vikram and rep_rahul:
                lead3 = leads[3]
                transfer_req = LeadTransferRequest(
                    lead_id=lead3.id,
                    from_user_id=rep_vikram.id,
                    to_user_id=rep_rahul.id,
                    reason="Client requested Senior Wealth Advisor consultation for high-net-worth portfolio restructuring (>5 Cr).",
                    status="pending",
                    created_at=datetime.now(timezone.utc),
                )
                db.add(transfer_req)
                await db.commit()
                print("Created sample pending LeadTransferRequest.")

    await engine.dispose()
    print("Database enrichment complete!")

if __name__ == "__main__":
    asyncio.run(enrich())
