# src/agents/db.py
"""
Database connection and query layer for NEXUS Control Tower agents.
Provides SQLAlchemy engine, SQL-based agent queries, and transactional state mutations.
Falls back safely to local CSVs if PostgreSQL is unreachable.
"""

import os
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import pandas as pd
from dotenv import load_dotenv, find_dotenv
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.agents.config import SYNTHETIC_DATA_DIR

load_dotenv(find_dotenv())
logger = logging.getLogger("nexus.db")

_ENGINE: Optional[Engine] = None
_DB_AVAILABLE: Optional[bool] = None


def get_engine() -> Optional[Engine]:
    """Returns singleton SQLAlchemy engine or None if DB is offline."""
    global _ENGINE, _DB_AVAILABLE
    if _ENGINE is not None:
        return _ENGINE

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        _DB_AVAILABLE = False
        return None

    try:
        engine = create_engine(db_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        _ENGINE = engine
        _DB_AVAILABLE = True
        logger.info("Successfully connected to PostgreSQL database.")
        return _ENGINE
    except Exception as exc:
        logger.warning(f"PostgreSQL connection failed ({exc}). Falling back to local data layer.")
        _DB_AVAILABLE = False
        return None


def is_db_connected() -> bool:
    global _DB_AVAILABLE
    if _DB_AVAILABLE is None:
        get_engine()
    return bool(_DB_AVAILABLE)


# ==============================================================================
# SQL QUERY IMPLEMENTATIONS (Replacing pandas .merge)
# ==============================================================================

def query_inventory_balances_sql(sku_code: str, location_codes: List[str] = None) -> List[Dict[str, Any]]:
    """SQL query against inventory_balances joining products and locations."""
    engine = get_engine()
    if not engine:
        return _query_inventory_balances_csv(sku_code, location_codes)

    query = """
        SELECT
            p.sku_code,
            p.name AS product_name,
            l.location_code,
            l.name AS location_name,
            l.location_type,
            b.available_stock,
            b.allocated_stock,
            b.safety_stock_threshold,
            (b.available_stock - b.allocated_stock) AS net_free_stock
        FROM inventory_balances b
        JOIN products p ON b.product_id = p.product_id
        JOIN locations l ON b.location_id = l.location_id
        WHERE p.sku_code = :sku_code
    """
    params: Dict[str, Any] = {"sku_code": sku_code}
    if location_codes:
        query += " AND l.location_code = ANY(:location_codes)"
        params["location_codes"] = location_codes

    try:
        with engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().fetchall()
            if not rows:
                return [{"error": f"SKU {sku_code} not found in catalog or no balances recorded."}]
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error(f"SQL inventory balance query failed: {exc}, falling back to CSV.")
        return _query_inventory_balances_csv(sku_code, location_codes)


def query_supplier_options_sql(sku_code: str, delayed_supplier_code: str = None) -> Dict[str, Any]:
    """SQL query against supplier_products joining suppliers and products."""
    engine = get_engine()
    if not engine:
        return _query_supplier_options_csv(sku_code, delayed_supplier_code)

    query = """
        SELECT
            p.sku_code,
            p.name AS product_name,
            s.supplier_code,
            s.name AS supplier_name,
            s.origin_address,
            sp.is_primary,
            sp.lead_time_days,
            sp.unit_cost_aed,
            s.reliability_score,
            s.contracted_sla_rate
        FROM supplier_products sp
        JOIN suppliers s ON sp.supplier_id = s.supplier_id
        JOIN products p ON sp.product_id = p.product_id
        WHERE p.sku_code = :sku_code
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(query), {"sku_code": sku_code}).mappings().fetchall()
            if not rows:
                return {"error": f"SKU {sku_code} not found."}

            product_name = rows[0]["product_name"]
            primary_supplier = None
            backup_suppliers = []

            for r in rows:
                data = {
                    "supplier_code": r["supplier_code"],
                    "supplier_name": r["supplier_name"],
                    "origin_address": r["origin_address"],
                    "is_primary": bool(r["is_primary"]),
                    "lead_time_days": int(r["lead_time_days"]),
                    "unit_cost_aed": float(r["unit_cost_aed"]),
                    "reliability_score": float(r["reliability_score"]),
                    "contracted_sla_rate": float(r["contracted_sla_rate"]),
                }
                if r["is_primary"]:
                    primary_supplier = data
                else:
                    backup_suppliers.append(data)

            return {
                "sku_code": sku_code,
                "product_name": product_name,
                "delayed_supplier": delayed_supplier_code,
                "primary_supplier": primary_supplier,
                "backup_suppliers": backup_suppliers
            }
    except Exception as exc:
        logger.error(f"SQL supplier query failed: {exc}, falling back to CSV.")
        return _query_supplier_options_csv(sku_code, delayed_supplier_code)


# ==============================================================================
# TRANSACTIONAL STATE UPDATES (Transfers & Emergency POs)
# ==============================================================================

def execute_inventory_transfer_sql(
    sku_code: str,
    routes: List[Dict[str, Any]],
    destination_store_code: str,
    transfer_reference: str
) -> Dict[str, Any]:
    """
    Atomically decrements available DC stock and records an official transfer order.
    """
    engine = get_engine()
    if not engine:
        return {"status": "SKIPPED_OFFLINE", "message": "Database offline; state update simulated."}

    try:
        with engine.begin() as conn:
            for idx, route in enumerate(routes):
                origin_dc = route.get("origin")
                units = route.get("units", 0)
                if not origin_dc or units <= 0:
                    continue

                leg_ref = f"{transfer_reference}-{idx + 1}" if len(routes) > 1 else transfer_reference

                # 1. Decrement DC available stock
                conn.execute(text("""
                    UPDATE inventory_balances
                    SET available_stock = available_stock - :units,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE location_id = (SELECT location_id FROM locations WHERE location_code = :dc)
                      AND product_id = (SELECT product_id FROM products WHERE sku_code = :sku)
                      AND available_stock >= :units
                """), {"units": units, "dc": origin_dc, "sku": sku_code})

                # 2. Increment destination store available stock
                conn.execute(text("""
                    UPDATE inventory_balances
                    SET available_stock = available_stock + :units,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE location_id = (SELECT location_id FROM locations WHERE location_code = :store)
                      AND product_id = (SELECT product_id FROM products WHERE sku_code = :sku)
                """), {"units": units, "store": destination_store_code, "sku": sku_code})

                # 3. Insert into transfer_orders audit table
                conn.execute(text("""
                    INSERT INTO transfer_orders (
                        transfer_id, transfer_reference, sku_code,
                        origin_location_code, destination_store_code, units, status
                    ) VALUES (:id, :ref, :sku, :origin, :dest, :units, 'DISPATCHED_TO_WMS')
                """), {
                    "id": str(uuid.uuid4()),
                    "ref": leg_ref,
                    "sku": sku_code,
                    "origin": origin_dc,
                    "dest": destination_store_code,
                    "units": units
                })

        logger.info(f"Inventory transfer {transfer_reference} committed to PostgreSQL.")
        return {"status": "COMMITTED", "transfer_reference": transfer_reference}
    except Exception as exc:
        logger.error(f"Failed to commit inventory transfer to database: {exc}")
        return {"status": "ERROR", "error": str(exc)}


def execute_emergency_po_sql(
    po_reference: str,
    supplier_code: str,
    sku_code: str,
    units: int,
    unit_cost_aed: float,
    freight_aed: float,
    total_amount_aed: float,
    delivery_eta_days: int
) -> Dict[str, Any]:
    """
    Inserts emergency purchase order into purchase_orders table.
    """
    engine = get_engine()
    if not engine:
        return {"status": "SKIPPED_OFFLINE", "message": "Database offline; state update simulated."}

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO purchase_orders (
                    po_id, po_reference, supplier_id, sku_code, units,
                    unit_cost_aed, freight_aed, total_amount_aed, is_expedited,
                    status, delivery_eta_days
                ) VALUES (
                    :id, :ref, (SELECT supplier_id FROM suppliers WHERE supplier_code = :supp),
                    :sku, :units, :cost, :freight, :total, TRUE, 'ISSUED', :eta
                )
            """), {
                "id": str(uuid.uuid4()),
                "ref": po_reference,
                "supp": supplier_code,
                "sku": sku_code,
                "units": units,
                "cost": unit_cost_aed,
                "freight": freight_aed,
                "total": total_amount_aed,
                "eta": delivery_eta_days
            })
        logger.info(f"Emergency PO {po_reference} committed to PostgreSQL.")
        return {"status": "COMMITTED", "po_reference": po_reference}
    except Exception as exc:
        logger.error(f"Failed to commit purchase order to database: {exc}")
        return {"status": "ERROR", "error": str(exc)}


# ==============================================================================
# CSV FALLBACKS (Used if DB is unreachable)
# ==============================================================================

def _query_inventory_balances_csv(sku_code: str, location_codes: List[str] = None) -> List[Dict[str, Any]]:
    products_df = pd.read_csv(SYNTHETIC_DATA_DIR / "products.csv")
    locations_df = pd.read_csv(SYNTHETIC_DATA_DIR / "locations.csv")
    balances_df = pd.read_csv(SYNTHETIC_DATA_DIR / "inventory_balances.csv")

    product_match = products_df[products_df["sku_code"] == sku_code]
    if product_match.empty:
        return [{"error": f"SKU {sku_code} not found in catalog."}]
    product_id = product_match.iloc[0]["product_id"]

    merged = balances_df[balances_df["product_id"] == product_id].merge(
        locations_df, on="location_id", how="inner"
    )
    if location_codes:
        merged = merged[merged["location_code"].isin(location_codes)]

    results = []
    for _, row in merged.iterrows():
        results.append({
            "sku_code": sku_code,
            "product_name": product_match.iloc[0]["name"],
            "location_code": row["location_code"],
            "location_name": row["name"],
            "location_type": row["location_type"],
            "available_stock": int(row["available_stock"]),
            "allocated_stock": int(row["allocated_stock"]),
            "safety_stock_threshold": int(row["safety_stock_threshold"]),
            "net_free_stock": int(row["available_stock"] - row["allocated_stock"])
        })
    return results


def _query_supplier_options_csv(sku_code: str, delayed_supplier_code: str = None) -> Dict[str, Any]:
    products_df = pd.read_csv(SYNTHETIC_DATA_DIR / "products.csv")
    suppliers_df = pd.read_csv(SYNTHETIC_DATA_DIR / "suppliers.csv")
    supp_prod_df = pd.read_csv(SYNTHETIC_DATA_DIR / "supplier_products.csv")

    prod = products_df[products_df["sku_code"] == sku_code]
    if prod.empty:
        return {"error": f"SKU {sku_code} not found."}

    prod_id = prod.iloc[0]["product_id"]
    merged = supp_prod_df[supp_prod_df["product_id"] == prod_id].merge(
        suppliers_df, on="supplier_id", how="inner"
    )

    primary_supplier = None
    backup_suppliers = []

    for _, row in merged.iterrows():
        supp_data = {
            "supplier_code": row["supplier_code"],
            "supplier_name": row["name"],
            "origin_address": row["origin_address"],
            "is_primary": bool(row["is_primary"]),
            "lead_time_days": int(row["lead_time_days"]),
            "unit_cost_aed": float(row["unit_cost_aed"]),
            "reliability_score": float(row["reliability_score"]),
            "contracted_sla_rate": float(row["contracted_sla_rate"])
        }
        if row["is_primary"]:
            primary_supplier = supp_data
        else:
            backup_suppliers.append(supp_data)

    return {
        "sku_code": sku_code,
        "product_name": prod.iloc[0]["name"],
        "delayed_supplier": delayed_supplier_code,
        "primary_supplier": primary_supplier,
        "backup_suppliers": backup_suppliers
    }

