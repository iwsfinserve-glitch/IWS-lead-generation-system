import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.core.config import settings

async def main():
    engine = create_async_engine(str(settings.DATABASE_URL))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check Leads
        result = await session.execute(text("SELECT id, name, phone_number, assigned_rep_id FROM leads"))
        leads = result.fetchall()
        print(f"Leads ({len(leads)}):", leads)
        
        # Check Messages
        result = await session.execute(text("SELECT id, lead_id, sender_phone, receiver_phone, content, status FROM whatsapp_messages"))
        messages = result.fetchall()
        print(f"Messages ({len(messages)}):", messages)
        
        # Check Notifications
        result = await session.execute(text("SELECT id, user_id, title, notification_type FROM notifications"))
        notifications = result.fetchall()
        print(f"Notifications ({len(notifications)}):", notifications)

asyncio.run(main())