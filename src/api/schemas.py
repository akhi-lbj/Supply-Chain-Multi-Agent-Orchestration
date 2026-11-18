# src/api/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date
import uuid


class DisruptionQueryItem(BaseModel):
    item_id: str = Field(..., example="HOBBIES_1_004")
    store_id: str = Field(..., example="CA_1")
    available_stock: float = Field(..., ge=0, example=15.0)
    current_sales_t0: float = Field(0.0, ge=0, description="Actual sales on decision day t0")
    lag_7: float = Field(0.0, ge=0, description="Sales 7 days prior to t0")
    lag_14: float = Field(0.0, ge=0, description="Sales 14 days prior to t0")
    hist_sum_5d: float = Field(0.0, ge=0, description="Cumulative sales in past 5 days")
    hist_mean_7d: float = Field(0.0, ge=0, description="7-day rolling average at t0")
    hist_mean_28d: float = Field(0.0, ge=0, description="28-day rolling average at t0")
    sell_price: Optional[float] = Field(None, ge=0, example=8.99)
    snap_flag: int = Field(0, ge=0, le=1, example=0)


class DisruptionForecastRequest(BaseModel):
    decision_date: date = Field(..., example="2026-04-19")
    delay_days: int = Field(5, ge=1, le=14, description="Disruption delay window")
    items: List[DisruptionQueryItem]


class DisruptionForecastItemResult(BaseModel):
    item_id: str
    store_id: str
    available_stock: float
    expected_5d_demand: float
    p90_safety_demand: float
    stockout_risk: bool
    shortage_units: float


class DisruptionForecastResponse(BaseModel):
    forecast_run_id: str
    decision_date: date
    horizon_days: int
    total_skus_evaluated: int
    stockouts_detected: int
    results: List[DisruptionForecastItemResult]


# --- NEXUS Control Tower Multi-Agent Lifecycle Schemas ---

class DisruptionTriggerRequest(BaseModel):
    sku_code: str = Field(..., example="SKU_0001", description="Target SKU experiencing disruption")
    store_id: str = Field(..., example="STR_DXB_01", description="Affected retail store node")
    delayed_supplier: str = Field(..., example="SUP_01", description="Delayed vendor code")
    delay_days: int = Field(5, ge=1, le=30, example=5, description="Expected delivery delay in days")
    delayed_units: Optional[int] = Field(500, ge=1, example=500, description="Shipment order quantity delayed")


class MitigationOptionSchema(BaseModel):
    option_id: str
    scenario_type: str
    title: str
    source_entity: str
    lead_time_hours: float
    total_cost_aed: float
    reliability_score: float
    stockout_risk_mitigated_pct: float
    rank: int
    rationale: str
    execution_payload: Dict[str, Any]


class DisruptionSummarySchema(BaseModel):
    sku_code: str
    store_id: str
    delayed_supplier: str
    delayed_units: int
    delay_days: int
    store_net_free_stock: int
    warehouse_total_surplus: int
    estimated_stockout_window: str


class DisruptionTriggerResponse(BaseModel):
    incident_id: str
    approval_id: str
    status: str = "ACTIVE"
    disruption_summary: DisruptionSummarySchema
    ranked_mitigation_options: List[MitigationOptionSchema]
    recommended_action: str
    agent_run_status: str = "RUNNING"


class DisruptionRecordResponse(BaseModel):
    incident_id: str
    approval_id: str
    sku_code: str
    store_id: str
    delayed_supplier: str
    delay_days: int
    delayed_units: int
    status: str
    created_at: str
    estimated_stockout_window: str
    affected_stores: List[str]
    recommended_action: str
    approval_status: str
    disruption_summary: Dict[str, Any]
    ranked_options: List[Dict[str, Any]]
    agent_run_status: str
    agent_briefing: Optional[str] = None


class ApprovalActionRequest(BaseModel):
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$", example="APPROVED", description="Manager decision")
    notes: Optional[str] = Field("", example="Approved emergency DC transfer order for Dubai Mall flagship.")
    selected_option_id: Optional[str] = Field(None, example="OPT-WH-TRANSFER", description="Option ID to execute if approving")


class ApprovalActionResponse(BaseModel):
    approval_id: str
    incident_id: str
    decision: str
    status: str
    actioned_at: str
    execution_result: Optional[Dict[str, Any]] = None
    message: str
