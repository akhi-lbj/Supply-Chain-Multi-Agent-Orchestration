# src/api/store.py
"""
SQLite-backed persistent repository for NEXUS Control Tower disruptions,
approvals, and downstream execution payloads.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from src.agents.config import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "control_tower.db"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS disruptions (
            incident_id TEXT PRIMARY KEY,
            approval_id TEXT UNIQUE,
            sku_code TEXT NOT NULL,
            store_id TEXT NOT NULL,
            delayed_supplier TEXT NOT NULL,
            delay_days INTEGER NOT NULL,
            delayed_units INTEGER NOT NULL,
            status TEXT NOT NULL, -- ACTIVE, RESOLVED, REJECTED
            created_at TEXT NOT NULL,
            estimated_stockout_window TEXT NOT NULL,
            affected_stores TEXT NOT NULL, -- JSON list
            recommended_action TEXT NOT NULL,
            disruption_summary TEXT NOT NULL, -- JSON dict
            ranked_options TEXT NOT NULL, -- JSON list
            agent_briefing TEXT,
            agent_run_status TEXT NOT NULL DEFAULT 'PENDING' -- PENDING, RUNNING, COMPLETED, FAILED
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            incident_id TEXT NOT NULL,
            status TEXT NOT NULL, -- PENDING, APPROVED, REJECTED
            decision TEXT,
            manager_notes TEXT,
            selected_option_id TEXT,
            created_at TEXT NOT NULL,
            actioned_at TEXT,
            execution_payload TEXT, -- JSON dict
            execution_result TEXT -- JSON dict
        );
        """)
        conn.commit()


# Initialize on import
init_db()


class ControlTowerStore:
    @staticmethod
    def create_disruption(
        incident_id: str,
        approval_id: str,
        sku_code: str,
        store_id: str,
        delayed_supplier: str,
        delay_days: int,
        delayed_units: int,
        estimated_stockout_window: str,
        affected_stores: List[str],
        recommended_action: str,
        disruption_summary: Dict[str, Any],
        ranked_options: List[Dict[str, Any]],
        default_execution_payload: Dict[str, Any]
    ):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO disruptions (
                incident_id, approval_id, sku_code, store_id, delayed_supplier,
                delay_days, delayed_units, status, created_at, estimated_stockout_window,
                affected_stores, recommended_action, disruption_summary, ranked_options,
                agent_briefing, agent_run_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                incident_id,
                approval_id,
                sku_code,
                store_id,
                delayed_supplier,
                delay_days,
                delayed_units,
                "ACTIVE",
                now,
                estimated_stockout_window,
                json.dumps(affected_stores),
                recommended_action,
                json.dumps(disruption_summary),
                json.dumps(ranked_options),
                None,
                "RUNNING"
            ))

            cursor.execute("""
            INSERT INTO approvals (
                approval_id, incident_id, status, decision, manager_notes,
                selected_option_id, created_at, actioned_at, execution_payload, execution_result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                approval_id,
                incident_id,
                "PENDING",
                None,
                None,
                ranked_options[0]["option_id"] if ranked_options else None,
                now,
                None,
                json.dumps(default_execution_payload),
                None
            ))
            conn.commit()

    @staticmethod
    def update_agent_briefing(incident_id: str, briefing: str, status: str = "COMPLETED"):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE disruptions
            SET agent_briefing = ?, agent_run_status = ?
            WHERE incident_id = ?
            """, (briefing, status, incident_id))
            conn.commit()

    @staticmethod
    def get_all_disruptions() -> List[Dict[str, Any]]:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
            SELECT d.*, a.status as approval_status, a.decision as approval_decision
            FROM disruptions d
            LEFT JOIN approvals a ON d.approval_id = a.approval_id
            ORDER BY d.created_at DESC
            """)
            rows = cursor.fetchall()
            results = []
            for r in rows:
                results.append({
                    "incident_id": r["incident_id"],
                    "approval_id": r["approval_id"],
                    "sku_code": r["sku_code"],
                    "store_id": r["store_id"],
                    "delayed_supplier": r["delayed_supplier"],
                    "delay_days": r["delay_days"],
                    "delayed_units": r["delayed_units"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "estimated_stockout_window": r["estimated_stockout_window"],
                    "affected_stores": json.loads(r["affected_stores"]),
                    "recommended_action": r["recommended_action"],
                    "approval_status": r["approval_status"] or "PENDING",
                    "disruption_summary": json.loads(r["disruption_summary"]),
                    "ranked_options": json.loads(r["ranked_options"]),
                    "agent_run_status": r["agent_run_status"],
                    "agent_briefing": r["agent_briefing"]
                })
            return results

    @staticmethod
    def get_approval(approval_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "approval_id": row["approval_id"],
                "incident_id": row["incident_id"],
                "status": row["status"],
                "decision": row["decision"],
                "manager_notes": row["manager_notes"],
                "selected_option_id": row["selected_option_id"],
                "created_at": row["created_at"],
                "actioned_at": row["actioned_at"],
                "execution_payload": json.loads(row["execution_payload"]) if row["execution_payload"] else {},
                "execution_result": json.loads(row["execution_result"]) if row["execution_result"] else None
            }

    @staticmethod
    def action_approval(
        approval_id: str,
        decision: str,
        notes: str,
        selected_option_id: Optional[str],
        execution_payload: Dict[str, Any],
        execution_result: Optional[Dict[str, Any]]
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        disruption_status = "RESOLVED" if decision == "APPROVED" else "REJECTED"
        approval_status = decision

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # Find incident
            cursor.execute("SELECT incident_id FROM approvals WHERE approval_id = ?", (approval_id,))
            row = cursor.fetchone()
            if not row:
                return False
            incident_id = row[0]

            cursor.execute("""
            UPDATE approvals
            SET status = ?, decision = ?, manager_notes = ?, selected_option_id = ?,
                actioned_at = ?, execution_payload = ?, execution_result = ?
            WHERE approval_id = ?
            """, (
                approval_status,
                decision,
                notes,
                selected_option_id,
                now,
                json.dumps(execution_payload),
                json.dumps(execution_result) if execution_result else None,
                approval_id
            ))

            cursor.execute("""
            UPDATE disruptions
            SET status = ?
            WHERE incident_id = ?
            """, (disruption_status, incident_id))

            conn.commit()
            return True

