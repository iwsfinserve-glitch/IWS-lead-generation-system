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
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime, date, timedelta, timezone

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base, User, LeadSource, Lead, LeadTimeline, Appointment, Task
from app.models.ai_insight import LeadAIInsight
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
        force_seed = "--force" in sys.argv
        existing = await db.execute(text("SELECT count(*) FROM users"))
        count = existing.scalar()
        if count and count > 2 and not force_seed:
            print(f"⚠️  Database already has {count} users — skipping seed to avoid duplicates.")
            print("   Run with --force to clear tables and re-seed: python seed_demo.py --force")
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
        await db.execute(text("DELETE FROM lead_ai_insights"))
        await db.execute(text("DELETE FROM leads"))
        await db.execute(text("DELETE FROM lead_sources"))
        await db.execute(text("DELETE FROM users"))
        await db.commit()

        db.add_all([admin, manager, rep_rahul, rep_sneha, rep_vikram])
        await db.flush()
        print(f"✅ Users created: {admin.id}, {manager.id}, {rep_rahul.id}, {rep_sneha.id}, {rep_vikram.id}")

        # 2. LEAD SOURCES  (6 acquisition channels)
        sources = [
            LeadSource(name="Existing Client Referral", priority="high"),
            LeadSource(name="Wealth Management Seminar", priority="high"),
            LeadSource(name="Corporate Salary Program", priority="medium"),
            LeadSource(name="Partner Referral", priority="high"),
            LeadSource(name="Website Enquiry", priority="medium"),
            LeadSource(name="LinkedIn Outreach", priority="low"),
        ]
        db.add_all(sources)
        await db.flush()
        print(f"✅ Lead Sources created: {[s.name for s in sources]}")

        src_client_ref, src_seminar, src_corporate, src_partner_ref, src_web, src_linkedin = sources

        # 3. LEADS  (12 leads across all pipeline stages)
        leads = [
            # ── NEW leads ──
            Lead(
                name="Anil Shetty", profession="Business Owner",
                email="anil.shetty@gmail.com", phone_number="9823456701",
                address="Alto Porvorim, Goa",
                status=LeadStatus.new, source_id=src_client_ref.id,
                assigned_rep_id=rep_rahul.id, last_contact=date.today(),
                ai_score=85.0, ai_score_label="hot", ai_score_updated_at=_ts(days_ago=1),
            ),
            Lead(
                name="Kavita Pai", profession="Architect",
                email="kavita.pai@outlook.com", phone_number="9823456702",
                address="Panaji, Goa",
                status=LeadStatus.new, source_id=src_seminar.id,
                assigned_rep_id=rep_sneha.id,
            ),
            Lead(
                name="Deepak Naik", profession="IT Consultant",
                email="deepak.n@techcorp.in", phone_number="9823456703",
                status=LeadStatus.new, source_id=src_web.id,
                assigned_rep_id=rep_vikram.id,
                ai_score=58.0, ai_score_label="warm", ai_score_updated_at=_ts(days_ago=3),
            ),

            # ── IN PROGRESS leads ──
            Lead(
                name="Meera Deshmukh", profession="Doctor",
                email="meera.d@gmail.com", phone_number="9823456704",
                address="Margao, Goa",
                status=LeadStatus.in_progress, source_id=src_partner_ref.id,
                assigned_rep_id=rep_rahul.id, last_contact=date.today() - timedelta(days=3),
                ai_score=88.0, ai_score_label="hot", ai_score_updated_at=_ts(days_ago=1),
            ),
            Lead(
                name="Rajesh Gawde", profession="Chartered Accountant",
                email="rajesh.g@caoffice.com", phone_number="9823456705",
                address="Mapusa, Goa",
                status=LeadStatus.in_progress, source_id=src_corporate.id,
                assigned_rep_id=rep_sneha.id, last_contact=date.today() - timedelta(days=1),
                ai_score=68.0, ai_score_label="warm", ai_score_updated_at=_ts(days_ago=1),
            ),

            # ── POTENTIAL leads ──
            Lead(
                name="Sanjay Verma", profession="Retired Navy Officer",
                email="sanjay.v@navy.gov.in", phone_number="9823456706",
                address="Vasco da Gama, Goa",
                status=LeadStatus.potential, source_id=src_partner_ref.id,
                assigned_rep_id=rep_rahul.id, last_contact=date.today() - timedelta(days=5),
                ai_score=94.0, ai_score_label="hot", ai_score_updated_at=_ts(days_ago=2),
            ),
            Lead(
                name="Priti Kamat", profession="Restaurant Owner",
                email="priti.k@gmail.com", phone_number="9823456707",
                address="Calangute, Goa",
                status=LeadStatus.potential, source_id=src_corporate.id,
                assigned_rep_id=rep_vikram.id, last_contact=date.today() - timedelta(days=2),
            ),

            # ── CONVERTED leads ──
            Lead(
                name="Vikrant Rane", profession="Logistics Entrepreneur",
                email="vikrant.r@ranegroup.com", phone_number="9823456708",
                address="Ponda, Goa",
                status=LeadStatus.converted_to_investor, source_id=src_client_ref.id,
                assigned_rep_id=rep_sneha.id, last_contact=date.today() - timedelta(days=10),
            ),
            Lead(
                name="Neha Prabhu", profession="NRI Tech Executive",
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
                ai_score=18.0, ai_score_label="cold", ai_score_updated_at=_ts(days_ago=5),
            ),
            Lead(
                name="Riya Fernandes", profession="Homemaker",
                email="riya.f@yahoo.com", phone_number="9823456711",
                status=LeadStatus.non_potential, source_id=src_corporate.id,
                assigned_rep_id=rep_sneha.id,
            ),
            Lead(
                name="Suresh Tendulkar", profession="Retired Teacher",
                email="suresh.t@gmail.com", phone_number="9823456712",
                address="Quepem, Goa",
                status=LeadStatus.in_progress, source_id=src_client_ref.id,
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
                event_metadata={"source": "Existing Client Referral", "note": "Referred by existing HNI client for ₹1.5 Cr PMS allocation"},
            ),
            LeadTimeline(
                lead_id=anil.id, user_id=rep_rahul.id,
                event_type="note", created_at=_ts(days_ago=5),
                event_metadata={"note": "Called — high interest in customized Portfolio Management Services (PMS) and equity/debt asset allocation."},
            ),

            # ── Meera's journey (in_progress) ──
            LeadTimeline(
                lead_id=meera.id, user_id=rep_rahul.id,
                event_type="lead_created", created_at=_ts(days_ago=14),
                event_metadata={"source": "Partner Referral", "referred_by": "Dr. Pradeep"},
            ),
            LeadTimeline(
                lead_id=meera.id, user_id=rep_rahul.id,
                event_type="status_change", created_at=_ts(days_ago=10),
                event_metadata={"old_status": "new", "new_status": "in_progress"},
            ),
            LeadTimeline(
                lead_id=meera.id, user_id=rep_rahul.id,
                event_type="note", created_at=_ts(days_ago=3),
                event_metadata={"note": "Shared retirement planning options and ₹50,000 monthly SIP advisory brochure. Comparing top-quartile mutual funds."},
            ),

            # ── Sanjay's journey (potential) ──
            LeadTimeline(
                lead_id=sanjay.id, user_id=rep_rahul.id,
                event_type="lead_created", created_at=_ts(days_ago=30),
                event_metadata={"source": "Partner Referral"},
            ),
            LeadTimeline(
                lead_id=sanjay.id, user_id=rep_rahul.id,
                event_type="status_change", created_at=_ts(days_ago=25),
                event_metadata={"old_status": "new", "new_status": "in_progress"},
            ),
            LeadTimeline(
                lead_id=sanjay.id, user_id=rep_rahul.id,
                event_type="appointment_booked", created_at=_ts(days_ago=20),
                event_metadata={"title": "Portfolio Review & Asset Allocation Strategy", "mode": "in_person"},
            ),
            LeadTimeline(
                lead_id=sanjay.id, user_id=rep_rahul.id,
                event_type="status_change", created_at=_ts(days_ago=15),
                event_metadata={"old_status": "in_progress", "new_status": "potential"},
            ),
            LeadTimeline(
                lead_id=sanjay.id, user_id=rep_rahul.id,
                event_type="note", created_at=_ts(days_ago=5),
                event_metadata={"note": "Wants to deploy ₹1.5 Cr surplus across fixed income bonds and balanced advantage mutual funds. Waiting for SEBI KYC verification."},
            ),

            # ── Vikrant's journey (converted!) ──
            LeadTimeline(
                lead_id=vikrant.id, user_id=rep_sneha.id,
                event_type="lead_created", created_at=_ts(days_ago=45),
                event_metadata={"source": "Existing Client Referral"},
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
                event_metadata={"title": "AIF Mandate Discussion", "mode": "in_person",
                                "location": "IWS FinServe Office, Panaji"},
            ),
            LeadTimeline(
                lead_id=vikrant.id, user_id=rep_sneha.id,
                event_type="status_change", created_at=_ts(days_ago=10),
                event_metadata={"old_status": "potential", "new_status": "converted_to_investor",
                                "note": "Signed Alternative Investment Fund (AIF) mandate for ₹2.8 Cr"},
            ),

            # ── Rajesh's journey ──
            LeadTimeline(
                lead_id=rajesh.id, user_id=rep_sneha.id,
                event_type="lead_created", created_at=_ts(days_ago=10),
                event_metadata={"source": "Corporate Salary Program"},
            ),
            LeadTimeline(
                lead_id=rajesh.id, user_id=rep_sneha.id,
                event_type="status_change", created_at=_ts(days_ago=7),
                event_metadata={"old_status": "new", "new_status": "in_progress"},
            ),
            LeadTimeline(
                lead_id=rajesh.id, user_id=rep_sneha.id,
                event_type="note", created_at=_ts(days_ago=1),
                event_metadata={"note": "Looking for tax-saving mutual funds (ELSS) and debt allocation. Shared 3 portfolio models."},
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
                                "note": "Student exploring financial concepts out of academic interest. No investment capital."},
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
                title="Portfolio Review & PMS Strategy Consultation",
                note="Client wants customized equity & fixed income asset allocation model",
                mode=AppointmentMode.in_person,
                location="IWS FinServe Office, Alto Porvorim",
                start_time=_future(days=2, hours=10),
                end_time=_future(days=2, hours=12),
            ),
            Appointment(
                lead_id=meera.id, user_id=rep_rahul.id,
                title="SIP Planning & Retirement Consultation",
                note="Discuss ₹50,000 monthly SIP structure across top-performing mutual funds",
                mode=AppointmentMode.online,
                start_time=_future(days=1, hours=14),
                end_time=_future(days=1, hours=15),
            ),
            Appointment(
                lead_id=rajesh.id, user_id=rep_sneha.id,
                title="Tax-Efficient Mutual Fund & ELSS Walkthrough",
                note="Review 3 ELSS and debt allocation models",
                mode=AppointmentMode.in_person,
                location="Mapusa Office, Goa",
                start_time=_future(days=3, hours=11),
                end_time=_future(days=3, hours=13),
            ),
            Appointment(
                lead_id=priti.id, user_id=rep_vikram.id,
                title="Follow-up Meeting — Asset Allocation & Surplus Discussion",
                note="She wants to deploy ₹60L surplus from restaurant business",
                mode=AppointmentMode.online,
                start_time=_future(days=4, hours=16),
                end_time=_future(days=4, hours=17),
            ),
            Appointment(
                lead_id=sanjay.id, user_id=rep_rahul.id,
                title="KYC Documentation & Nominee Verification",
                note="Complete SEBI/AMFI PAN, Aadhaar, and bank account linking",
                mode=AppointmentMode.in_person,
                location="IWS FinServe Office, Panaji",
                start_time=_future(days=5, hours=10),
                end_time=_future(days=5, hours=11),
            ),

            # Past (already happened)
            Appointment(
                lead_id=vikrant.id, user_id=rep_sneha.id,
                title="AIF Mandate Signing — Alternative Investments",
                note="Finalized ₹2.8 Cr AIF portfolio mandate signing",
                mode=AppointmentMode.in_person,
                location="IWS FinServe Office, Panaji",
                start_time=_ts(days_ago=10, hours_ago=4),
                end_time=_ts(days_ago=10, hours_ago=3),
            ),
            Appointment(
                lead_id=neha.id, user_id=rep_rahul.id,
                title="Virtual NRI Wealth Advisory & Portfolio Review",
                note="NRI client reviewed India-focused equity fund performance via Zoom",
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
                title="Send PMS brochure & 5-year XIRR report to Anil Shetty",
                notes="Include customized equity and debt allocation projections for ₹1.5 Cr portfolio",
                status="needsAction", due=date.today() + timedelta(days=1),
            ),
            Task(
                user_id=rep_rahul.id, assigned_by=manager.id,
                title="Follow up with Sanjay Verma on SEBI KYC verification",
                notes="Verify KRA KYC status and bank account mandate setup",
                status="needsAction", due=date.today() + timedelta(days=3),
            ),
            Task(
                user_id=rep_sneha.id, assigned_by=manager.id,
                title="Prepare comparative CAGR analysis for Rajesh Gawde",
                notes="Compare top 3 ELSS and balanced mutual funds with post-tax returns",
                status="needsAction", due=date.today() + timedelta(days=2),
            ),
            Task(
                user_id=rep_sneha.id, assigned_by=admin.id,
                title="Schedule wealth advisory calls for seminar attendees",
                notes="Batch of 5 leads from Wealth Management Seminar — schedule introductory calls this week",
                status="needsAction", due=date.today() + timedelta(days=5),
            ),
            Task(
                user_id=rep_vikram.id, assigned_by=manager.id,
                title="Call Suresh Tendulkar — monthly portfolio check-in",
                notes="Retired teacher looking at secure fixed income and retirement pension funds. Needs gentle follow-up.",
                status="needsAction", due=date.today(),
            ),
            Task(
                user_id=rep_vikram.id, assigned_by=admin.id,
                title="Update CRM risk profiling notes for Priti Kamat",
                notes="Add notes from last discovery call regarding liquidity needs and risk tolerance",
                status="needsAction", due=date.today() + timedelta(days=1),
            ),

            # Completed tasks
            Task(
                user_id=rep_sneha.id, assigned_by=manager.id,
                title="Collect SEBI/AMFI KYC documents from Vikrant Rane",
                notes="PAN, Aadhaar, cancelled cheque, and nominee details — needed for AIF onboarding",
                status="completed",
                completed_at=_ts(days_ago=12),
                due=date.today() - timedelta(days=12),
            ),
            Task(
                user_id=rep_rahul.id, assigned_by=admin.id,
                title="Send portfolio restructuring deck to Neha Prabhu",
                notes="Shared India-focused mutual fund portfolio presentation with Zoom invite",
                status="completed",
                completed_at=_ts(days_ago=16),
                due=date.today() - timedelta(days=15),
            ),
            Task(
                user_id=rep_vikram.id, assigned_by=manager.id,
                title="Disqualify non-potential general website inquiries",
                notes="Marked students and non-investors as non_potential with clear notes in timeline",
                status="completed",
                completed_at=_ts(days_ago=20),
                due=date.today() - timedelta(days=20),
            ),
        ]
        db.add_all(tasks)
        await db.flush()
        print(f"✅ Tasks created: {len(tasks)} (6 pending, 3 completed)")

        # ═════════════════════════════════════════════════════════════════
        # 7. AI INSIGHTS  (Seed AI Lead Scores & Best Time to Contact)
        # ═════════════════════════════════════════════════════════════════
        ai_insights = [
            # Anil Shetty — Score & Timing
            LeadAIInsight(
                lead_id=anil.id,
                insight_type="score",
                payload={
                    "score": 85,
                    "label": "hot",
                    "reasoning": "High-intent HNI profile (Business Owner) referred by an existing wealth management client, actively inquiring about a ₹1.5 Cr Portfolio Management Services (PMS) allocation.",
                    "key_signals": ["HNI Business Owner with high liquidity", "Referred by existing client for ₹1.5 Cr PMS", "Scheduled asset allocation review consultation"],
                    "suggested_next_action": "Prepare 5-year CAGR/XIRR performance projections for our top-tier PMS strategy before the consultation."
                },
                score=85.0,
                model_used="gemini-2.5-flash (seed)",
                generated_at=_ts(days_ago=1)
            ),
            LeadAIInsight(
                lead_id=anil.id,
                insight_type="contact_timing",
                payload={
                    "has_sufficient_data": True,
                    "suggested_days": ["Tuesday", "Thursday"],
                    "suggested_window": "10:00–12:00",
                    "confidence": "high",
                    "reasoning": "Interaction history indicates prompt responses during morning market hours on Tuesday and Thursday."
                },
                model_used="gemini-2.5-flash (seed)",
                generated_at=_ts(days_ago=1)
            ),
            # Meera Deshmukh — Score & Timing
            LeadAIInsight(
                lead_id=meera.id,
                insight_type="score",
                payload={
                    "score": 88,
                    "label": "hot",
                    "reasoning": "Partner-referred medical professional with verified monthly surplus looking for ₹50,000 monthly SIP and long-term retirement goal planning.",
                    "key_signals": ["Doctor seeking ₹50,000 monthly SIP setup", "Referred by partner network", "Active evaluation of mutual fund and retirement portfolios"],
                    "suggested_next_action": "Share comparative mutual fund performance deck and schedule an online SIP advisory session."
                },
                score=88.0,
                model_used="gemini-2.5-flash (seed)",
                generated_at=_ts(days_ago=1)
            ),
            LeadAIInsight(
                lead_id=meera.id,
                insight_type="contact_timing",
                payload={
                    "has_sufficient_data": True,
                    "suggested_days": ["Wednesday", "Friday"],
                    "suggested_window": "16:00–18:00",
                    "confidence": "medium",
                    "reasoning": "Client responds best in late afternoons or post-clinic hours on weekdays."
                },
                model_used="gemini-2.5-flash (seed)",
                generated_at=_ts(days_ago=1)
            ),
            # Sanjay Verma — Score & Timing
            LeadAIInsight(
                lead_id=sanjay.id,
                insight_type="score",
                payload={
                    "score": 94,
                    "label": "hot",
                    "reasoning": "Completed portfolio review meeting and currently finalizing SEBI/AMFI KYC documentation to deploy ₹1.5 Cr across bonds and balanced funds.",
                    "key_signals": ["Completed asset allocation review consultation", "Committed ₹1.5 Cr capital for fixed income and mutual funds", "SEBI KYC verification in progress"],
                    "suggested_next_action": "Follow up on KRA KYC completion and send the final investment portfolio mandate for signing."
                },
                score=94.0,
                model_used="gemini-2.5-flash (seed)",
                generated_at=_ts(days_ago=2)
            ),
            LeadAIInsight(
                lead_id=sanjay.id,
                insight_type="contact_timing",
                payload={
                    "has_sufficient_data": True,
                    "suggested_days": ["Monday", "Wednesday", "Friday"],
                    "suggested_window": "10:00–13:00",
                    "confidence": "high",
                    "reasoning": "Consistently available during morning hours on weekdays."
                },
                model_used="gemini-2.5-flash (seed)",
                generated_at=_ts(days_ago=2)
            ),
            # Rajesh Gawde — Score
            LeadAIInsight(
                lead_id=rajesh.id,
                insight_type="score",
                payload={
                    "score": 68,
                    "label": "warm",
                    "reasoning": "Chartered Accountant evaluating tax-efficient ELSS and debt mutual fund distribution models.",
                    "key_signals": ["Financial professional (CA) evaluating tax-saving options", "Requested comparative post-tax CAGR projections"],
                    "suggested_next_action": "Share customized ELSS vs. debt allocation model and schedule follow-up walkthrough."
                },
                score=68.0,
                model_used="gemini-2.5-flash (seed)",
                generated_at=_ts(days_ago=1)
            ),
            # Deepak Naik — Score
            LeadAIInsight(
                lead_id=deepak.id,
                insight_type="score",
                payload={
                    "score": 58,
                    "label": "warm",
                    "reasoning": "New inquiry submitted via website form. Needs discovery call to assess risk appetite and investment horizon.",
                    "key_signals": ["IT Consultant", "Submitted online financial planning inquiry"],
                    "suggested_next_action": "Initiate introductory discovery call to clarify investment horizon and liquidity profile."
                },
                score=58.0,
                model_used="gemini-2.5-flash (seed)",
                generated_at=_ts(days_ago=3)
            ),
            # Ganesh Sawant — Score
            LeadAIInsight(
                lead_id=ganesh.id,
                insight_type="score",
                payload={
                    "score": 18,
                    "label": "cold",
                    "reasoning": "Student exploring financial advisory concepts out of general interest without immediate investment surplus or capacity.",
                    "key_signals": ["Marked as non-potential (student)", "No investment capital or surplus income"],
                    "suggested_next_action": "Archive lead or enroll in quarterly financial literacy educational newsletter."
                },
                score=18.0,
                model_used="gemini-2.5-flash (seed)",
                generated_at=_ts(days_ago=5)
            ),
        ]
        db.add_all(ai_insights)
        await db.flush()
        print(f"✅ AI Insights created: {len(ai_insights)} seed score & contact timing analyses")

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
