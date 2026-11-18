# src/api/control_tower.py
"""
FastAPI Router for NEXUS Control Tower Multi-Agent Disruption Lifecycle:
- POST /api/disruptions/trigger
- GET /api/disruptions
- POST /api/approvals/{approval_id}/action
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from google.genai import types
from google.adk.runners import InMemoryRunner

from src.api.schemas import (
    DisruptionTriggerRequest,
    DisruptionTriggerResponse,
    DisruptionSummarySchema,
    MitigationOptionSchema,
    DisruptionRecordResponse,
    ApprovalActionRequest,
    ApprovalActionResponse,
)
from src.api.scoring import MitigationScoringEngine
from src.api.store import ControlTowerStore
from src.agents.supervisor_agent import supervisor_agent
from src.agents.tools.inventory_tools import get_inventory_balances, check_warehouse_transfer_availability
from src.agents.tools.supplier_tools import evaluate_supplier_options
from src.agents.db import execute_inventory_transfer_sql, execute_emergency_po_sql

logger = logging.getLogger("nexus.control_tower")
router = APIRouter(prefix="/api", tags=["Control Tower"])


def _run_supervisor_swarm_background(incident_id: str, payload: DisruptionTriggerRequest):
    """
    Background worker that runs the ADK Supervisor Agent swarm and saves
    the resulting multi-agent operational executive briefing.
    """
    try:
        logger.info(f"Starting background supervisor swarm execution for incident {incident_id}...")
        prompt = (
            f"INCIDENT NOTIFICATION: Supplier {payload.delayed_supplier} has announced a "
            f"{payload.delay_days}-day delay on a shipment of {payload.delayed_units} units of {payload.sku_code} "
            f"destined for store {payload.store_id}.\n\n"
            f"Please execute the NEXUS Disruption Protocol:\n"
            f"1. Forecast 5-day demand and determine P90 stockout risk.\n"
            f"2. Audit store stock and check central warehouse surplus across DC_JAFZA, DC_AL_QUOZ, and DC_DIC.\n"
            f"3. Evaluate alternative suppliers, lead times, and expedited quotes.\n"
            f"4. Synthesize a structured operational decision briefing with Recovery Strategy Comparison and Action Approval Card."
        )

        runner = InMemoryRunner(agent=supervisor_agent)
        runner.auto_create_session = True
        session_id = f"nexus_bg_run_{uuid.uuid4().hex[:10]}"

        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)]
        )

        final_response_text = ""
        for event in runner.run(
            user_id="nexus_operations_lead",
            session_id=session_id,
            new_message=user_content
        ):
            if hasattr(event, "content") and event.content:
                for part in event.content.parts or []:
                    if getattr(part, "text", None) and not getattr(part, "thought", False):
                        final_response_text += part.text

        briefing = final_response_text.strip() or "Autonomous multi-agent analysis completed."
        ControlTowerStore.update_agent_briefing(incident_id, briefing, "COMPLETED")
        logger.info(f"Background supervisor swarm completed successfully for incident {incident_id}.")

    except Exception as exc:
        logger.error(f"Error executing background supervisor swarm for incident {incident_id}: {exc}", exc_info=True)
        ControlTowerStore.update_agent_briefing(incident_id, f"Supervisor execution encountered an error: {exc}", "FAILED")


@router.post(
    "/disruptions/trigger",
    response_model=DisruptionTriggerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger Multi-Agent Disruption Protocol"
)
def trigger_disruption(
    payload: DisruptionTriggerRequest,
    background_tasks: BackgroundTasks
):
    """
    Accepts disruption incident parameters, runs the Jev scoring matrix, creates
    a pending approval record, dispatches the Supervisor agent swarm in the background,
    and returns the incident summary with ranked mitigation scenarios.
    """
    incident_id = f"DIS-{uuid.uuid4().hex[:8].upper()}"
    approval_id = f"APP-{uuid.uuid4().hex[:8].upper()}"

    # 1. Inspect store inventory
    store_balances = get_inventory_balances(payload.sku_code, location_codes=[payload.store_id])
    store_net_stock = 0
    if store_balances and "net_free_stock" in store_balances[0]:
        store_net_stock = int(store_balances[0]["net_free_stock"])

    # 2. Inspect warehouse transfer options
    wh_avail = check_warehouse_transfer_availability(payload.sku_code, payload.delayed_units)
    wh_transfers = wh_avail.get("available_transfers", [])
    total_wh_surplus = wh_avail.get("total_wh_surplus", 0)

    # 3. Inspect alternative supplier options
    sup_eval = evaluate_supplier_options(payload.sku_code, delayed_supplier_code=payload.delayed_supplier)
    sup_options = sup_eval.get("backup_suppliers", [])
    if sup_eval.get("primary_supplier") and sup_eval["primary_supplier"].get("supplier_code") != payload.delayed_supplier:
        sup_options = [sup_eval["primary_supplier"]] + sup_options

    # 4. Evaluate and rank mitigation options
    ranked_options = MitigationScoringEngine.evaluate_and_rank(
        sku_code=payload.sku_code,
        store_id=payload.store_id,
        delayed_units=payload.delayed_units,
        delay_days=payload.delay_days,
        store_net_stock=store_net_stock,
        warehouse_transfers=wh_transfers,
        supplier_options=sup_options
    )

    # Estimated stockout window calculation
    if store_net_stock <= 20:
        stockout_window = "Day 1 (Within 12-18 hours) — CRITICAL"
    elif store_net_stock <= 60:
        stockout_window = "Day 2 (Within 24-36 hours) — HIGH RISK"
    else:
        stockout_window = f"Day 3-4 (Estimated burn rate exceeds on-hand safety buffer)"

    recommended_action = (
        ranked_options[0].title if ranked_options else "Review alternate sourcing"
    )

    disruption_summary = DisruptionSummarySchema(
        sku_code=payload.sku_code,
        store_id=payload.store_id,
        delayed_supplier=payload.delayed_supplier,
        delayed_units=payload.delayed_units,
        delay_days=payload.delay_days,
        store_net_free_stock=store_net_stock,
        warehouse_total_surplus=total_wh_surplus,
        estimated_stockout_window=stockout_window
    )

    default_payload = ranked_options[0].execution_payload if ranked_options else {}

    # 5. Persist to SQLite store
    ControlTowerStore.create_disruption(
        incident_id=incident_id,
        approval_id=approval_id,
        sku_code=payload.sku_code,
        store_id=payload.store_id,
        delayed_supplier=payload.delayed_supplier,
        delay_days=payload.delay_days,
        delayed_units=payload.delayed_units,
        estimated_stockout_window=stockout_window,
        affected_stores=[payload.store_id],
        recommended_action=recommended_action,
        disruption_summary=disruption_summary.model_dump(),
        ranked_options=[opt.model_dump() for opt in ranked_options],
        default_execution_payload=default_payload
    )

    # 6. Dispatch background multi-agent supervisor swarm
    background_tasks.add_task(_run_supervisor_swarm_background, incident_id, payload)

    return DisruptionTriggerResponse(
        incident_id=incident_id,
        approval_id=approval_id,
        status="ACTIVE",
        disruption_summary=disruption_summary,
        ranked_mitigation_options=[MitigationOptionSchema(**opt.model_dump()) for opt in ranked_options],
        recommended_action=recommended_action,
        agent_run_status="RUNNING"
    )


@router.get(
    "/disruptions",
    response_model=List[DisruptionRecordResponse],
    summary="List All Active and Resolved Disruptions"
)
def list_disruptions():
    """
    Returns all active and resolved disruptions, affected stores, and estimated stockout windows.
    """
    return ControlTowerStore.get_all_disruptions()


@router.post(
    "/approvals/{approval_id}/action",
    response_model=ApprovalActionResponse,
    summary="Action Pending Manager Approval"
)
def action_approval(approval_id: str, action: ApprovalActionRequest):
    """
    Accepts the human manager's decision (APPROVED or REJECTED, plus optional notes).
    If approved, triggers the downstream execution payload (e.g. dispatching transfer orders or issuing a PO).
    """
    existing_approval = ControlTowerStore.get_approval(approval_id)
    if not existing_approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval record {approval_id} not found."
        )

    if existing_approval["status"] != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Approval {approval_id} has already been actioned with decision '{existing_approval['decision']}'."
        )

    incident_id = existing_approval["incident_id"]
    execution_result = None

    if action.decision == "APPROVED":
        # Determine payload to execute
        payload_to_run = existing_approval.get("execution_payload", {})
        action_type = payload_to_run.get("action_type", "INTERNAL_TRANSFER")

        if action_type == "INTERNAL_TRANSFER":
            transfer_id = f"TRF-{uuid.uuid4().hex[:8].upper()}"
            db_sync = execute_inventory_transfer_sql(
                sku_code=payload_to_run.get("sku_code", ""),
                routes=payload_to_run.get("routes", []),
                destination_store_code=payload_to_run.get("destination_store", ""),
                transfer_reference=transfer_id
            )
            execution_result = {
                "order_type": "INTERNAL_TRANSFER_DISPATCH",
                "transfer_reference": transfer_id,
                "status": "DISPATCHED_TO_WMS",
                "dispatched_at": datetime.now(timezone.utc).isoformat(),
                "sku_code": payload_to_run.get("sku_code"),
                "destination_store": payload_to_run.get("destination_store"),
                "total_units": payload_to_run.get("total_units"),
                "fulfillment_routes": payload_to_run.get("routes", []),
                "estimated_arrival": "< 4 hours (Same-Day Express Road Transport)",
                "database_sync": db_sync
            }
            msg = f"Transfer order {transfer_id} dispatched to warehouse management system."
        else:
            po_id = f"PO-{uuid.uuid4().hex[:8].upper()}"
            db_sync = execute_emergency_po_sql(
                po_reference=po_id,
                supplier_code=payload_to_run.get("supplier_code", ""),
                sku_code=payload_to_run.get("sku_code", ""),
                units=payload_to_run.get("units", 0),
                unit_cost_aed=payload_to_run.get("unit_cost_aed", 0.0),
                freight_aed=payload_to_run.get("freight_aed", 0.0),
                total_amount_aed=payload_to_run.get("total_amount_aed", 0.0),
                delivery_eta_days=payload_to_run.get("delivery_eta_days", 3)
            )
            execution_result = {
                "order_type": "EMERGENCY_PURCHASE_ORDER",
                "po_reference": po_id,
                "status": "TRANSMITTED_TO_ERP",
                "issued_at": datetime.now(timezone.utc).isoformat(),
                "supplier_code": payload_to_run.get("supplier_code"),
                "supplier_name": payload_to_run.get("supplier_name"),
                "sku_code": payload_to_run.get("sku_code"),
                "units": payload_to_run.get("units"),
                "total_amount_aed": payload_to_run.get("total_amount_aed"),
                "expedited": payload_to_run.get("expedited", True),
                "expected_delivery_days": payload_to_run.get("delivery_eta_days"),
                "database_sync": db_sync
            }
            msg = f"Emergency Purchase Order {po_id} successfully issued to supplier."
    else:
        msg = f"Disruption mitigation rejected by manager. Incident marked as REJECTED."

    now = datetime.now(timezone.utc).isoformat()
    ControlTowerStore.action_approval(
        approval_id=approval_id,
        decision=action.decision,
        notes=action.notes or "",
        selected_option_id=action.selected_option_id or existing_approval.get("selected_option_id"),
        execution_payload=existing_approval.get("execution_payload", {}),
        execution_result=execution_result
    )

    return ApprovalActionResponse(
        approval_id=approval_id,
        incident_id=incident_id,
        decision=action.decision,
        status=action.decision,
        actioned_at=now,
        execution_result=execution_result,
        message=msg
    )
