import base64
from email.message import EmailMessage
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import logging

from app.db.session import get_db
from app.db.base import User, Lead, LeadTimeline
from app.api.dependencies import get_current_user
from app.services.google_sync import get_google_credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["Emails"])

class EmailSendRequest(BaseModel):
    lead_id: int
    subject: str
    body: str

@router.post("/send")
async def send_email(
    payload: EmailSendRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_email = current_user.email or current_user.username
    if not user_email:
        raise HTTPException(
            status_code=400,
            detail="Your account must have an email address set up for sending emails."
        )

    # Validate lead
    result = await db.execute(select(Lead).where(Lead.id == payload.lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    if not lead.email:
        raise HTTPException(status_code=400, detail="The selected lead does not have an email address.")

    creds = get_google_credentials(current_user)
    if not creds:
        raise HTTPException(
            status_code=400,
            detail="Google account not connected or authorization expired. Please connect your Google account in Settings."
        )

    # Prepare email message
    message = EmailMessage()
    message.set_content(payload.body)
    message["To"] = lead.email
    message["From"] = user_email
    message["Subject"] = payload.subject

    # encoded message
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    create_message = {"raw": encoded_message}

    try:
        service = build("gmail", "v1", credentials=creds)
        sent_message = service.users().messages().send(userId="me", body=create_message).execute()
        
        # Log to timeline
        timeline_entry = LeadTimeline(
            lead_id=lead.id,
            user_id=current_user.id,
            event_type="email_sent",
            event_metadata={
                "subject": payload.subject,
                "body": payload.body,
                "sent_to": lead.email,
                "gmail_message_id": sent_message.get("id")
            }
        )
        db.add(timeline_entry)
        await db.commit()
        return {"status": "success", "message_id": sent_message.get("id")}
        
    except HttpError as error:
        error_details = str(error)
        logger.error(f"Gmail API error: {error_details}")
        if error.resp.status == 403 and "insufficientPermissions" in error_details:
             raise HTTPException(
                 status_code=403, 
                 detail="Insufficient permissions to send email. Ensure you have authorized Gmail access with the send scope."
             )
        raise HTTPException(status_code=500, detail=f"Failed to send email via Google API. Try reconnecting your Google account.")
    except Exception as e:
        logger.error(f"Unexpected error in send_email: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred while sending the email.")


@router.get("/history/{lead_id}")
async def get_email_history(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(LeadTimeline)
        .where(LeadTimeline.lead_id == lead_id)
        .where(LeadTimeline.event_type == "email_sent")
        .order_by(LeadTimeline.created_at.desc())
    )
    history = result.scalars().all()
    return [
        {
            "id": item.id,
            "created_at": item.created_at,
            "subject": item.event_metadata.get("subject"),
            "body": item.event_metadata.get("body"),
            "sent_to": item.event_metadata.get("sent_to"),
            "user_id": item.user_id,
        }
        for item in history
    ]
