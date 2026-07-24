import asyncio
import os
import sys
from datetime import datetime, timezone
import pandas as pd
import asyncpg
import math
import numpy as np

DB_URL = "postgresql://postgres:XyTkrlTmPqpBGyCRPAlTTdiFOHguwvOa@sakura.proxy.rlwy.net:26561/railway"
EXCEL_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test1.xlsx")

def clean_text(text):
    if pd.isna(text) or text is None:
        return None
    return str(text).strip()

async def main():
    if not os.path.exists(EXCEL_FILE):
        print(f"Error: {EXCEL_FILE} not found.")
        return

    print("Loading Excel file...")
    # Read excel file
    df = pd.read_excel(EXCEL_FILE)
    print(f"Loaded {len(df)} rows. Columns: {list(df.columns)}")
    
    print("Connecting to database...")
    conn = await asyncpg.connect(DB_URL)
    
    # 1. Sync Sources
    unique_sources = df['Source'].dropna().unique()
    print(f"Syncing {len(unique_sources)} sources...")
    
    for s_name in unique_sources:
        s_name_clean = s_name.strip()
        if not s_name_clean:
            continue
        # Insert if not exists
        await conn.execute("""
            INSERT INTO lead_sources (name, priority, created_at)
            VALUES ($1, 'medium', $2)
            ON CONFLICT (name) DO NOTHING
        """, s_name_clean, datetime.now(timezone.utc))
        
    # Fetch sources map
    sources_records = await conn.fetch("SELECT id, name FROM lead_sources")
    source_lookup = {r['name'].lower(): r['id'] for r in sources_records}

    # 2. Process and insert rows
    records_to_insert = []
    
    for idx, row in df.iterrows():
        # Clean Name
        name = clean_text(row.get("Name"))
        if not name:
            name = "Unknown"

        # Profession
        profession = clean_text(row.get("Profession"))

        # Phone No.
        mobile = row.get("Phone No.")
        if pd.isna(mobile):
            phone_number = None
        else:
            if isinstance(mobile, float):
                phone_number = str(int(mobile)) if not math.isnan(mobile) else None
            else:
                phone_number = str(mobile).strip()
                
        if phone_number and len(phone_number) > 50:
            phone_number = phone_number[:50]
                
        # Email
        email = row.get("Email")
        if pd.isna(email):
            email = None
        else:
            email = str(email).strip().lower()
            
        # Address
        address = clean_text(row.get("Address"))
            
        # DOB
        raw_dob = row.get("DOB")
        dob = None
        if not pd.isna(raw_dob):
            try:
                dt = pd.to_datetime(raw_dob, errors='coerce')
                if not pd.isna(dt):
                    dob = dt.date()
            except Exception:
                pass
                
        # Source ID
        source_name = clean_text(row.get("Source"))
        source_id = None
        if source_name:
            source_id = source_lookup.get(source_name.lower())

        status = "unassigned"
        assigned_rep_id = None
        created_at = datetime.now(timezone.utc)
        
        records_to_insert.append((
            name, profession, email, phone_number, address, dob, status, assigned_rep_id, source_id, created_at
        ))

    print(f"Prepared {len(records_to_insert)} records for insertion.")
    
    # Bulk insert
    query = """
    INSERT INTO leads (name, profession, email, phone_number, address, dob, status, assigned_rep_id, source_id, created_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    """
    
    try:
        await conn.executemany(query, records_to_insert)
        print("Insertion complete.")
    except Exception as e:
        print(f"Error during insertion: {e}")
        
    await conn.close()
    print("Done.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
