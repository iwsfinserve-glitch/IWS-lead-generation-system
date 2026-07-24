# # import asyncio
# # from sqlalchemy import text
# # from app.db.session import async_session_factory

# # async def check():
# #     async with async_session_factory() as session:
# #         try:
# #             result = await session.execute(text('SELECT version_num FROM alembic_version'))
# #             rows = result.fetchall()
# #             print('alembic_version rows:', rows)
# #         except Exception as e:
# #             print('Error:', e)

# # asyncio.run(check())

# # fix_alembic.py (put this in your backend/ root)
# import asyncio
# from sqlalchemy import text
# from sqlalchemy.ext.asyncio import create_async_engine
# from app.core.config import settings

# async def fix():
#     engine = create_async_engine(settings.DATABASE_URL, echo=True)
    
#     async with engine.begin() as conn:
#         # Create the alembic_version table manually
#         await conn.execute(text("""
#             CREATE TABLE IF NOT EXISTS alembic_version (
#                 version_num VARCHAR(32) NOT NULL,
#                 CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
#             )
#         """))
        
#         # Delete any existing rows (clean slate)
#         await conn.execute(text("DELETE FROM alembic_version"))
        
#         # Insert your current revision
#         await conn.execute(text(
#             "INSERT INTO alembic_version (version_num) VALUES ('d3b93a5786d4')"
#         ))
        
#         # Verify
#         result = await conn.execute(text("SELECT version_num FROM alembic_version"))
#         print("alembic_version now contains:", result.fetchall())
    
#     await engine.dispose()

# asyncio.run(fix())

# fix_alembic.py (put this in your backend/ root)
# import asyncio
# from sqlalchemy import text
# from sqlalchemy.ext.asyncio import create_async_engine
# from app.core.config import settings

# async def fix():
#     engine = create_async_engine(settings.DATABASE_URL)
#     async with engine.begin() as conn:
#         # Create the alembic_version table manually
#         await conn.execute(text("""
#             CREATE TABLE IF NOT EXISTS alembic_version (
#                 version_num VARCHAR(32) NOT NULL,
#                 CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
#             )
#         """))
#         # Stamp it with your current revision
#         await conn.execute(text("""
#             INSERT INTO alembic_version (version_num)
#             VALUES ('d3b93a5786d4')
#             ON CONFLICT DO NOTHING
#         """))
#         print("Done. alembic_version table created and stamped.")

# asyncio.run(fix())

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def verify():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        rows = result.fetchall()
        print("Current Alembic revision:", rows)
    await engine.dispose()

asyncio.run(verify())
