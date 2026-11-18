# scripts/seed_postgres.py
"""
Seeds PostgreSQL database with UAE retail supply chain data from data/synthetic/*.csv
"""

import os
import sys
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv, find_dotenv
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import UUID

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(find_dotenv())

DEFAULT_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:5432/nexus_control_tower"
)
DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
SQL_INIT_FILE = PROJECT_ROOT / "scripts" / "init_control_tower_db.sql"


def ensure_database_exists(db_url: str):
    """Creates the target database if not already present."""
    url = sqlalchemy.engine.make_url(db_url)
    target_db = url.database

    admin_url = url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with admin_engine.connect() as conn:
        res = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :d"),
            {"d": target_db}
        ).fetchone()
        if not res:
            print(f"Database '{target_db}' does not exist. Creating...")
            conn.execute(text(f'CREATE DATABASE "{target_db}"'))
            print(f"Database '{target_db}' created successfully.")
        else:
            print(f"Database '{target_db}' already exists.")


def seed_all(db_url: str = None):
    url = db_url or DEFAULT_URL
    print(f"Connecting to PostgreSQL: {sqlalchemy.engine.make_url(url).render_as_string(hide_password=True)}")

    ensure_database_exists(url)

    engine = create_engine(url)

    # 1. Apply DDL schema
    print(f"Applying schema from {SQL_INIT_FILE.name}...")
    with open(SQL_INIT_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    with engine.begin() as conn:
        for stmt in schema_sql.split(";"):
            cleaned = stmt.strip()
            if cleaned:
                conn.execute(text(cleaned))
    print("Schema applied successfully.")

    # 2. Bulk load synthetic CSV files in order of foreign key dependencies
    tables_to_load = [
        ("locations", "locations.csv"),
        ("suppliers", "suppliers.csv"),
        ("products", "products.csv"),
        ("supplier_products", "supplier_products.csv"),
        ("inventory_balances", "inventory_balances.csv"),
    ]

    for table_name, csv_filename in tables_to_load:
        csv_path = DATA_DIR / csv_filename
        if not csv_path.exists():
            print(f"Warning: {csv_filename} not found, skipping.")
            continue

        df = pd.read_csv(csv_path)

        # Parse timestamps and UUIDs properly for PostgreSQL
        for col in df.columns:
            if col in ["created_at", "last_updated"]:
                df[col] = pd.to_datetime(df[col])

        dtypes = {c: UUID(as_uuid=True) for c in df.columns if c.endswith("_id")}

        with engine.begin() as conn:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            if count == 0:
                print(f"Loading {len(df):,} records into '{table_name}'...")
                df.to_sql(
                    table_name,
                    con=conn,
                    if_exists="append",
                    index=False,
                    dtype=dtypes,
                    chunksize=1000
                )
                print(f"  Successfully inserted {len(df):,} rows into '{table_name}'.")
            else:
                print(f"  Table '{table_name}' already contains {count:,} rows. Skipping insert.")

    print("\nPostgreSQL database seeding complete!")


if __name__ == "__main__":
    url_arg = sys.argv[1] if len(sys.argv) > 1 else None
    seed_all(url_arg)
