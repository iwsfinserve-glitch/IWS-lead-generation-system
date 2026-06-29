"""
seed_demo.py — Populates the database with rich demo data for presentation.

This script DOES NOT drop/recreate tables. It inserts records into the
existing schema so your Alembic state stays clean. Run it once.

Usage:
    python seed_demo.py          (from backend/ dir, with .venv active)
"""

import asyncio
import sys
import os
from datetime import datetime, date, timedelta, timezone

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base, User, LeadSource, Lead, LeadTimeline, Appointment, Task
from app.models.enums import UserRole, LeadStatus, AppointmentMode


def _ts(days_ago: int = 0, hours_ago: int = 0) -> datetime:
    """Helper to produce a timezone-aware datetime in the past."""
    return datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)


def _future(days: int = 0, hours: int = 0) -> datetime:
    """Helper to produce a timezone-aware datetime in the future."""
    return datetime.now(timezone.utc) + timedelta(days=days, hours=hours)


async def seed():
    print(f"Connecting to: {settings.DATABASE_URL}")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        # ── Safety check: skip if data already exists ─────────────────
        existing = await db.execute(text("SELECT count(*) FROM users"))
        count = existing.scalar()
        if count and count > 2:
            print(f"⚠️  Database already has {count} users — skipping seed to avoid duplicates.")
            print("   If you want to re-seed, manually truncate the tables first.")
            await engine.dispose()
            return

        # 1. USERS  (1 admin, 1 manager, 3 sales reps)
        admin = User(
            name="Samyak Jain", email="admin@example.com",
            hashed_password=hash_password("admin123"), role=UserRole.admin,
        )
        manager = User(
            name="Priya Naik", email="priya@iwsfinserve.com",
            hashed_password=hash_password("manager123"), role=UserRole.manager,
        )
        rep_rahul = User(
            name="Rahul Desai", email="rahul@iwsfinserve.com",
            hashed_password=hash_password("rahul123"), role=UserRole.sales_rep,
        )
        rep_sneha = User(
            name="Sneha Kamat", email="sneha@iwsfinserve.com",
            hashed_password=hash_password("sneha123"), role=UserRole.sales_rep,
        )
        rep_vikram = User(
            name="Vikram Prabhu", email="vikram@iwsfinserve.com",
            hashed_password=hash_password("vikram123"), role=UserRole.sales_rep,
        )

        # Delete old seed users first (clean slate for users)
        await db.execute(text("DELETE FROM tasks"))
        await db.execute(text("DELETE FROM appointments"))
        await db.execute(text("DELETE FROM lead_timeline"))
        await db.execute(text("DELETE FROM leads"))
        await db.execute(text("DELETE FROM lead_sources"))
        await db.execute(text("DELETE FROM users"))
        await db.commit()

        db.add_all([admin, manager, rep_rahul, rep_sneha, rep_vikram])
        await db.flush()
        print(f"✅ Users created: {admin.id}, {manager.id}, {rep_rahul.id}, {rep_sneha.id}, {rep_vikram.id}")

        # 2. LEAD SOURCES  (6 acquisition channels)
        sources = [
            LeadSource(name="MCA ROC Data", priority="high"),
            LeadSource(name="Goa RERA", priority="high"),
            LeadSource(name="Walk-in", priority="medium"),
            LeadSource(name="Referral", priority="high"),
            LeadSource(name="Website Enquiry", priority="medium"),
            LeadSource(name="LinkedIn Outreach", priority="low"),
        ]
        db.add_all(sources)
        await db.flush()
        print(f"✅ Lead Sources created: {[s.name for s in sources]}")

        src_mca, src_rera, src_walkin, src_referral, src_web, src_linkedin = sources

        # 3. LEADS  (12 leads across all pipeline stages)
        leads = [
            # ── NEW leads ──
            Lead(
                name="Anil Shetty", profession="Business Owner",
                email="anil.shetty@gmail.com", phone_number="9823456701",
                address="Alto Porvorim, Goa",
                status=LeadStatus.new, source_id=src_mca.id,
                assigned_rep_id=rep_rahul.id, last_contact=date.today(),
            ),
            Lead(
                name="Kavita Pai", profession="Architect",
                email="kavita.pai@outlook.com", phone_number="9823456702",
                address="Panaji, Goa",
                status=LeadStatus.new, source_id=src_rera.id,
                assigned_rep_id=rep_sneha.id,
            ),
            Lead(
                name="Deepak Naik", profession="IT Consultant",
                email="deepak.n@techcorp.in", phone_number="9823456703",
                status=LeadStatus.new, source_id=src_web.id,
                assigned_rep_id=rep_vikram.id,
            ),

            # ── IN PROGRESS leads ──
            Lead(
                name="Meera Deshmukh", profession="Doctor",
                email="meera.d@gmail.com", phone_number="9823456704",
                address="Margao, Goa",
                status=LeadStatus.in_progress, source_id=src_referral.id,
                assigned_rep_id=rep_rahul.id, last_contact=date.today() - timedelta(days=3),
            ),
            Lead(
                name="Rajesh Gawde", profession="Chartered Accountant",
                email="rajesh.g@caoffice.com", phone_number="9823456705",
                address="Mapusa, Goa",
                status=LeadStatus.in_progress, source_id=src_walkin.id,
                assigned_rep_id=rep_sneha.id, last_contact=date.today() - timedelta(days=1),
            ),

            # ── POTENTIAL leads ──
            Lead(
                name="Sanjay Verma", profession="Retired Navy Officer",
                email="sanjay.v@navy.gov.in", phone_number="9823456706",
                address="Vasco da Gama, Goa",
                status=LeadStatus.potential, source_id=src_referral.id,
                assigned_rep_id=rep_rahul.id, last_contact=date.today() - timedelta(days=5),
            ),
            Lead(
                name="Priti Kamat", profession="Restaurant Owner",
                email="priti.k@gmail.com", phone_number="9823456707",
                address="Calangute, Goa",
                status=LeadStatus.potential, source_id=src_walkin.id,
                assigned_rep_id=rep_vikram.id, last_contact=date.today() - timedelta(days=2),
            ),

            # ── CONVERTED leads ──
            Lead(
                name="Vikrant Rane", profession="Real Estate Developer",
                email="vikrant.r@ranegroup.com", phone_number="9823456708",
                address="Ponda, Goa",
                status=LeadStatus.converted_to_investor, source_id=src_mca.id,
                assigned_rep_id=rep_sneha.id, last_contact=date.today() - timedelta(days=10),
            ),
            Lead(
                name="Neha Prabhu", profession="NRI Investor",
                email="neha.p@gmail.com", phone_number="+1-408-555-0199",
                address="San Jose, CA (Goa Origin)",
                status=LeadStatus.converted_to_investor, source_id=src_linkedin.id,
                assigned_rep_id=rep_rahul.id, last_contact=date.today() - timedelta(days=15),
            ),

            # ── NON-POTENTIAL leads ──
            Lead(
                name="Ganesh Sawant", profession="Student",
                email="ganesh.s@college.edu", phone_number="9823456710",
                status=LeadStatus.non_potential, source_id=src_web.id,
                assigned_rep_id=rep_vikram.id, last_contact=date.today() - timedelta(days=20),
            ),
            Lead(
                name="Riya Fernandes", profession="Homemaker",
                email="riya.f@yahoo.com", phone_number="9823456711",
                status=LeadStatus.non_potential, source_id=src_walkin.id,
                assigned_rep_id=rep_sneha.id,
            ),
            Lead(
                name="Suresh Tendulkar", profession="Retired Teacher",
                email="suresh.t@gmail.com", phone_number="9823456712",
                address="Quepem, Goa",
                status=LeadStatus.in_progress, source_id=src_mca.id,
                assigned_rep_id=rep_vikram.id, last_contact=date.today() - timedelta(days=7),
            ),
        ]
        db.add_all(leads)
        await db.flush()
        print(f"✅ Leads created: {len(leads)} leads across all pipeline stages")

        # Give them short aliases for readability below
        (anil, kavita, deepak, meera, rajesh, sanjay,
         priti, vikrant, neha, ganesh, riya, suresh) = leads

        # 4. LEAD TIMELINE  (audit trail showing realistic activity)
        timeline_entries = [
            # ── Anil's journey ──
            LeadTimeline(
                lead_id=anil.id, user_id=rep_rahul.id,
                event_type="lead_created", created_at=_ts(days_ago=7),
                event_metadata={"source": "MCA ROC Data", "note": "Imported from MCA batch"},
            ),
            LeadTimeline(
                lead_id=anil.id, user_id=rep_rahul.id,
                event_type="note", created_at=_ts(days_ago=5),
                event_metadata={"note": "Called — interested in residential plots in North Goa."},
            ),

            # ── Meera's journey (in_progress) ──
            LeadTimeline(
                lead_id=meera.id, user_id=rep_rahul.id,
                event_type="lead_created", created_at=_ts(days_ago=14),
                event_metadata={"source": "Referral", "referred_by": "Dr. Pradeep"},
            ),
            LeadTimeline(
                lead_id=meera.id, user_id=rep_rahul.id,
                event_type="status_change", created_at=_ts(days_ago=10),
                event_metadata={"old_status": "new", "new_status": "in_progress"},
            ),
            LeadTimeline(
                lead_id=meera.id, user_id=rep_rahul.id,
                event_type="note", created_at=_ts(days_ago=3),
                event_metadata={"note": "Sent project brochure. She is comparing with 2 other developers."},
            ),

            # ── Sanjay's journey (potential) ──
            LeadTimeline(
                lead_id=sanjay.id, user_id=rep_rahul.id,
                event_type="lead_created", created_at=_ts(days_ago=30),
                event_metadata={"source": "Referral"},
            ),
            LeadTimeline(
                lead_id=sanjay.id, user_id=rep_rahul.id,
                event_type="status_change", created_at=_ts(days_ago=25),
                event_metadata={"old_status": "new", "new_status": "in_progress"},
            ),
            LeadTimeline(
                lead_id=sanjay.id, user_id=rep_rahul.id,
                event_type="appointment_booked", created_at=_ts(days_ago=20),
                event_metadata={"title": "Site Visit — Dona Paula Project", "mode": "in_person"},
            ),
            LeadTimeline(
                lead_id=sanjay.id, user_id=rep_rahul.id,
                event_type="status_change", created_at=_ts(days_ago=15),
                event_metadata={"old_status": "in_progress", "new_status": "potential"},
            ),
            LeadTimeline(
                lead_id=sanjay.id, user_id=rep_rahul.id,
                event_type="note", created_at=_ts(days_ago=5),
                event_metadata={"note": "Wants to invest ₹1.5 Cr. Waiting for bank pre-approval."},
            ),

            # ── Vikrant's journey (converted!) ──
            LeadTimeline(
                lead_id=vikrant.id, user_id=rep_sneha.id,
                event_type="lead_created", created_at=_ts(days_ago=45),
                event_metadata={"source": "MCA ROC Data"},
            ),
            LeadTimeline(
                lead_id=vikrant.id, user_id=rep_sneha.id,
                event_type="status_change", created_at=_ts(days_ago=40),
                event_metadata={"old_status": "new", "new_status": "in_progress"},
            ),
            LeadTimeline(
                lead_id=vikrant.id, user_id=rep_sneha.id,
                event_type="status_change", created_at=_ts(days_ago=30),
                event_metadata={"old_status": "in_progress", "new_status": "potential"},
            ),
            LeadTimeline(
                lead_id=vikrant.id, user_id=rep_sneha.id,
                event_type="appointment_booked", created_at=_ts(days_ago=25),
                event_metadata={"title": "Investment Discussion", "mode": "in_person",
                                "location": "IWS Office, Panaji"},
            ),
            LeadTimeline(
                lead_id=vikrant.id, user_id=rep_sneha.id,
                event_type="status_change", created_at=_ts(days_ago=10),
                event_metadata={"old_status": "potential", "new_status": "converted_to_investor",
                                "note": "Signed MOU for ₹2.8 Cr"},
            ),

            # ── Rajesh's journey ──
            LeadTimeline(
                lead_id=rajesh.id, user_id=rep_sneha.id,
                event_type="lead_created", created_at=_ts(days_ago=10),
                event_metadata={"source": "Walk-in"},
            ),
            LeadTimeline(
                lead_id=rajesh.id, user_id=rep_sneha.id,
                event_type="status_change", created_at=_ts(days_ago=7),
                event_metadata={"old_status": "new", "new_status": "in_progress"},
            ),
            LeadTimeline(
                lead_id=rajesh.id, user_id=rep_sneha.id,
                event_type="note", created_at=_ts(days_ago=1),
                event_metadata={"note": "Looking for commercial property under ₹80L. Shared 3 listings."},
            ),

            # ── Ganesh (non-potential) ──
            LeadTimeline(
                lead_id=ganesh.id, user_id=rep_vikram.id,
                event_type="lead_created", created_at=_ts(days_ago=25),
                event_metadata={"source": "Website Enquiry"},
            ),
            LeadTimeline(
                lead_id=ganesh.id, user_id=rep_vikram.id,
                event_type="status_change", created_at=_ts(days_ago=20),
                event_metadata={"old_status": "new", "new_status": "non_potential",
                                "note": "Student, no purchase intent. Just exploring."},
            ),
        ]
        db.add_all(timeline_entries)
        await db.flush()
        print(f"✅ Timeline entries created: {len(timeline_entries)} audit events")

        # ═════════════════════════════════════════════════════════════════
        # 5. APPOINTMENTS  (upcoming, past, and in-progress)
        # ═════════════════════════════════════════════════════════════════
        appointments = [
            # Upcoming
            Appointment(
                lead_id=anil.id, user_id=rep_rahul.id,
                title="Site Visit — Dona Paula Luxury Villas",
                note="Client wants to see 3BHK sea-facing units",
                mode=AppointmentMode.in_person,
                location="Dona Paula, Goa",
                start_time=_future(days=2, hours=10),
                end_time=_future(days=2, hours=12),
            ),
            Appointment(
                lead_id=meera.id, user_id=rep_rahul.id,
                title="Investment Consultation Call",
                note="Discuss portfolio diversification options",
                mode=AppointmentMode.online,
                start_time=_future(days=1, hours=14),
                end_time=_future(days=1, hours=15),
            ),
            Appointment(
                lead_id=rajesh.id, user_id=rep_sneha.id,
                title="Commercial Property Walkthrough",
                note="Show Mapusa commercial listings",
                mode=AppointmentMode.in_person,
                location="Mapusa, Goa",
                start_time=_future(days=3, hours=11),
                end_time=_future(days=3, hours=13),
            ),
            Appointment(
                lead_id=priti.id, user_id=rep_vikram.id,
                title="Follow-up Meeting — Budget Discussion",
                note="She wants to see properties under ₹60L",
                mode=AppointmentMode.online,
                start_time=_future(days=4, hours=16),
                end_time=_future(days=4, hours=17),
            ),
            Appointment(
                lead_id=sanjay.id, user_id=rep_rahul.id,
                title="Document Submission — Bank Pre-Approval",
                note="Help with HDFC home loan application",
                mode=AppointmentMode.in_person,
                location="IWS Office, Panaji",
                start_time=_future(days=5, hours=10),
                end_time=_future(days=5, hours=11),
            ),

            # Past (already happened)
            Appointment(
                lead_id=vikrant.id, user_id=rep_sneha.id,
                title="MOU Signing — Ponda Residency",
                note="Final investment signing ₹2.8 Cr",
                mode=AppointmentMode.in_person,
                location="IWS Office, Panaji",
                start_time=_ts(days_ago=10, hours_ago=4),
                end_time=_ts(days_ago=10, hours_ago=3),
            ),
            Appointment(
                lead_id=neha.id, user_id=rep_rahul.id,
                title="Virtual Tour — Assagao Villas",
                note="NRI client wants virtual walkthrough",
                mode=AppointmentMode.online,
                start_time=_ts(days_ago=15, hours_ago=6),
                end_time=_ts(days_ago=15, hours_ago=5),
            ),
        ]
        db.add_all(appointments)
        await db.flush()
        print(f"✅ Appointments created: {len(appointments)} (5 upcoming, 2 past)")

        # ═════════════════════════════════════════════════════════════════
        # 6. TASKS  (mix of pending and completed)
        # ═════════════════════════════════════════════════════════════════
        tasks = [
            # Pending tasks
            Task(
                user_id=rep_rahul.id, assigned_by=manager.id,
                title="Send project brochure to Anil Shetty",
                notes="Include pricing sheet and floor plans for Phase 2",
                status="needsAction", due=date.today() + timedelta(days=1),
            ),
            Task(
                user_id=rep_rahul.id, assigned_by=manager.id,
                title="Follow up with Sanjay Verma on bank pre-approval",
                notes="Check HDFC loan status, expected by Friday",
                status="needsAction", due=date.today() + timedelta(days=3),
            ),
            Task(
                user_id=rep_sneha.id, assigned_by=manager.id,
                title="Prepare comparative analysis for Rajesh Gawde",
                notes="Compare 3 commercial properties in Mapusa, include ROI projections",
                status="needsAction", due=date.today() + timedelta(days=2),
            ),
            Task(
                user_id=rep_sneha.id, assigned_by=admin.id,
                title="Schedule site visit for new RERA leads",
                notes="Batch of 5 leads from RERA data — schedule visits this week",
                status="needsAction", due=date.today() + timedelta(days=5),
            ),
            Task(
                user_id=rep_vikram.id, assigned_by=manager.id,
                title="Call Suresh Tendulkar — weekly check-in",
                notes="Retired teacher, looking at Quepem properties. Needs gentle follow-up.",
                status="needsAction", due=date.today(),
            ),
            Task(
                user_id=rep_vikram.id, assigned_by=admin.id,
                title="Update CRM notes for Priti Kamat",
                notes="Add meeting notes from last call about budget preferences",
                status="needsAction", due=date.today() + timedelta(days=1),
            ),

            # Completed tasks
            Task(
                user_id=rep_sneha.id, assigned_by=manager.id,
                title="Collect KYC documents from Vikrant Rane",
                notes="PAN, Aadhaar, and address proof — needed for MOU",
                status="completed",
                completed_at=_ts(days_ago=12),
                due=date.today() - timedelta(days=12),
            ),
            Task(
                user_id=rep_rahul.id, assigned_by=admin.id,
                title="Send virtual tour link to Neha Prabhu",
                notes="She is in San Jose, needs Zoom invite + recorded tour link",
                status="completed",
                completed_at=_ts(days_ago=16),
                due=date.today() - timedelta(days=15),
            ),
            Task(
                user_id=rep_vikram.id, assigned_by=manager.id,
                title="Disqualify non-potential web leads from last batch",
                notes="Mark as non_potential with reason in timeline",
                status="completed",
                completed_at=_ts(days_ago=20),
                due=date.today() - timedelta(days=20),
            ),
        ]
        db.add_all(tasks)
        await db.flush()
        print(f"✅ Tasks created: {len(tasks)} (6 pending, 3 completed)")

        # ═════════════════════════════════════════════════════════════════
        # COMMIT EVERYTHING
        # ═════════════════════════════════════════════════════════════════
        await db.commit()
        print("\n" + "=" * 60)
        print("🎉  DEMO SEED COMPLETE — Summary")
        print("=" * 60)
        print(f"   Users:          5  (1 admin, 1 manager, 3 sales reps)")
        print(f"   Lead Sources:   6")
        print(f"   Leads:         12  (3 new, 3 in_progress, 2 potential, 2 converted, 2 non_potential)")
        print(f"   Timeline:      {len(timeline_entries)}  audit trail entries")
        print(f"   Appointments:   {len(appointments)}  (5 upcoming, 2 past)")
        print(f"   Tasks:          {len(tasks)}  (6 pending, 3 completed)")
        print("=" * 60)
        print("\n📋  Login credentials:")
        print("   Admin:     admin@example.com       / admin123")
        print("   Manager:   priya@iwsfinserve.com   / manager123")
        print("   Rep 1:     rahul@iwsfinserve.com   / rahul123")
        print("   Rep 2:     sneha@iwsfinserve.com   / sneha123")
        print("   Rep 3:     vikram@iwsfinserve.com  / vikram123")

    await engine.dispose()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(seed())
