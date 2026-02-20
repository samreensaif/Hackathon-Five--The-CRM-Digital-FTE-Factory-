"""
Database Initialisation Script
================================
Connects to PostgreSQL using DATABASE_URL, applies database/schema.sql,
and verifies that all expected tables exist.

Run this once from the Render Shell after the first deployment:

    python database/init_db.py

It is safe to re-run: every CREATE TABLE and CREATE INDEX in schema.sql
uses IF NOT EXISTS, so existing data is never touched.
"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

# Tables created by schema.sql — used to verify success
EXPECTED_TABLES = [
    "customers",
    "customer_identifiers",
    "conversations",
    "messages",
    "tickets",
    "knowledge_base",
    "channel_configs",
    "agent_metrics",
    "message_queue",
]


async def init_database() -> bool:
    """Apply schema.sql to the target database.

    Returns:
        True if all tables are present after execution, False otherwise.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        return False

    # Mask password in log output
    safe_url = database_url.split("@")[-1] if "@" in database_url else database_url
    print(f"Connecting to PostgreSQL at {safe_url} ...")

    schema_path = Path(__file__).parent / "schema.sql"
    if not schema_path.exists():
        print(f"ERROR: schema.sql not found at {schema_path}")
        return False

    sql = schema_path.read_text(encoding="utf-8")
    print(f"Read schema.sql ({len(sql):,} bytes, {sql.count(chr(10))+1} lines)")

    conn = None
    try:
        conn = await asyncpg.connect(database_url)
        print("Connected.")

        # Enable pgvector extension (required for knowledge_base embeddings)
        print("Enabling pgvector extension ...")
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            print("  pgvector: OK")
        except Exception as e:
            print(f"  pgvector: WARNING — {e}")
            print("  (pgvector is optional; knowledge base search will be disabled)")

        # Execute the full schema
        print("Applying schema.sql ...")
        await conn.execute(sql)
        print("  schema.sql: executed successfully")

        # Verify expected tables exist
        print("Verifying tables ...")
        rows = await conn.fetch(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        )
        existing = {r["tablename"] for r in rows}

        all_ok = True
        for table in EXPECTED_TABLES:
            status = "OK" if table in existing else "MISSING"
            print(f"  {table}: {status}")
            if status == "MISSING":
                all_ok = False

        if all_ok:
            print(f"\nDatabase initialised successfully — {len(EXPECTED_TABLES)} tables ready.")
        else:
            print("\nWARNING: Some tables are missing. Check the output above.")

        return all_ok

    except asyncpg.PostgresError as e:
        print(f"PostgreSQL error: {e}")
        return False
    except OSError as e:
        print(f"Connection error: {e}")
        return False
    finally:
        if conn:
            await conn.close()
            print("Connection closed.")


if __name__ == "__main__":
    success = asyncio.run(init_database())
    sys.exit(0 if success else 1)
