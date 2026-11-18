# src/api/scoring.py
"""
NEXUS Control Tower — Mitigation Evaluation & Ranking Engine.
Evaluates and ranks disruption recovery scenarios (Warehouse Emergency Transfer vs.
Expedited Supplier PO vs. Standard PO) based on lead time, landed cost, and reliability.
"""

from typing import List, Dict, Any
from pydantic import BaseModel, Field


class MitigationOption(BaseModel):
    option_id: str
    scenario_type: str  # "WAREHOUSE_TRANSFER", "EXPEDITED_PO", "STANDARD_PO"
    title: str
    source_entity: str
    lead_time_hours: float
    total_cost_aed: float
    reliability_score: float  # 0.0 - 1.0
    stockout_risk_mitigated_pct: float  # 0 - 100%
    rank: int = 1
    execution_payload: Dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class MitigationScoringEngine:
    """
    Ranks supply chain disruption recovery scenarios based on:
      1. Immediate speed / lead time to prevent store stockout.
      2. Landed fulfillment cost.
      3. Supplier/facility historical reliability.
    """

    @classmethod
    def evaluate_and_rank(
        cls,
        sku_code: str,
        store_id: str,
        delayed_units: int,
        delay_days: int,
        store_net_stock: int,
        warehouse_transfers: List[Dict[str, Any]],
        supplier_options: List[Dict[str, Any]],
    ) -> List[MitigationOption]:
        options: List[MitigationOption] = []

        # 1. Scenario A: Emergency Warehouse Transfer (if DC surplus exists)
        total_wh_surplus = sum(wh.get("transferrable_surplus", 0) for wh in warehouse_transfers)
        if total_wh_surplus > 0:
            units_to_transfer = min(delayed_units, total_wh_surplus)
            coverage_pct = min(100.0, round((units_to_transfer / max(delayed_units, 1)) * 100, 1))

            sorted_wh = sorted(
                warehouse_transfers,
                key=lambda x: x.get("transferrable_surplus", 0),
                reverse=True
            )
            sources_summary = ", ".join([
                f"{w['location_code']} ({min(w['transferrable_surplus'], delayed_units)} units)"
                for w in sorted_wh if w.get("transferrable_surplus", 0) > 0
            ])

            options.append(MitigationOption(
                option_id="OPT-WH-TRANSFER",
                scenario_type="WAREHOUSE_TRANSFER",
                title="Scenario A: Emergency Distribution Center Transfer",
                source_entity=sources_summary or "Central Distribution Centers",
                lead_time_hours=4.0,  # Same-day road transit in UAE < 4 hours
                total_cost_aed=250.0,  # Fixed emergency dispatch logistics
                reliability_score=0.98,
                stockout_risk_mitigated_pct=coverage_pct,
                execution_payload={
                    "action_type": "INTERNAL_TRANSFER",
                    "sku_code": sku_code,
                    "destination_store": store_id,
                    "total_units": units_to_transfer,
                    "routes": [
                        {
                            "origin": w["location_code"],
                            "units": min(w["transferrable_surplus"], units_to_transfer),
                            "estimated_dispatch_window": "Immediate (Within 4 hours)"
                        }
                        for w in sorted_wh if w.get("transferrable_surplus", 0) > 0
                    ]
                },
                rationale="Fastest resolution (<4 hrs) utilizing on-hand regional warehouse surplus with minimal freight cost and 98% execution certainty."
            ))

        # 2. Scenario B: Alternate Supplier Purchase Orders
        for idx, sup in enumerate(supplier_options[:3]):
            sup_code = sup.get("supplier_code", f"SUP_ALT_{idx+1}")
            sup_name = sup.get("supplier_name", "Alternate Supplier")
            unit_cost = sup.get("unit_cost_aed", 10.0)
            reliability = sup.get("reliability_score", 0.88)

            # Expedited Option
            expedited_days = sup.get("expedited_lead_days", 3)
            expedited_freight = sup.get("expedited_freight_aed", round(delayed_units * unit_cost * 0.15, 2))
            expedited_total_cost = round((delayed_units * unit_cost) + expedited_freight, 2)
            exp_coverage = 100.0 if expedited_days < delay_days else 60.0

            options.append(MitigationOption(
                option_id=f"OPT-EXP-{sup_code}",
                scenario_type="EXPEDITED_PO",
                title=f"Scenario B: Expedited Emergency PO ({sup_name})",
                source_entity=f"{sup_code} — {sup_name}",
                lead_time_hours=float(expedited_days * 24),
                total_cost_aed=expedited_total_cost,
                reliability_score=reliability,
                stockout_risk_mitigated_pct=exp_coverage,
                execution_payload={
                    "action_type": "PURCHASE_ORDER",
                    "supplier_code": sup_code,
                    "supplier_name": sup_name,
                    "sku_code": sku_code,
                    "units": delayed_units,
                    "unit_cost_aed": unit_cost,
                    "freight_aed": expedited_freight,
                    "total_amount_aed": expedited_total_cost,
                    "expedited": True,
                    "delivery_eta_days": expedited_days
                },
                rationale=f"Expedited external purchase order arriving in {expedited_days} days, beating the {delay_days}-day vendor delay window."
            ))

        # Rank options:
        # Priority 1: Warehouse Transfer (if available, it's lowest lead time & lowest cost)
        # Priority 2+: Sorted by lowest lead time, then lowest cost
        options.sort(
            key=lambda x: (
                0 if x.scenario_type == "WAREHOUSE_TRANSFER" else 1,
                x.lead_time_hours,
                x.total_cost_aed
            )
        )

        for rank, opt in enumerate(options, start=1):
            opt.rank = rank

        return options


# Alias for backward compatibility
JevScoringEngine = MitigationScoringEngine
