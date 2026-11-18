# src/agents/tools/supplier_tools.py
from typing import Dict, Any
from google.adk.tools import FunctionTool
from src.agents.db import query_supplier_options_sql


def evaluate_supplier_options(sku_code: str, delayed_supplier_code: str = None) -> Dict[str, Any]:
    """
    Evaluates contracted suppliers for a given SKU via SQL query, separating primary from 
    qualified alternative/backup suppliers, their lead times, and unit costs.
    """
    return query_supplier_options_sql(sku_code=sku_code, delayed_supplier_code=delayed_supplier_code)


def calculate_procurement_quote(
    sku_code: str, 
    supplier_code: str, 
    units: int, 
    expedited: bool = False
) -> Dict[str, Any]:
    """
    Calculates procurement costs, freight premiums, and ETA for a purchase order.
    """
    supp_opts = evaluate_supplier_options(sku_code)
    all_supps = ([supp_opts["primary_supplier"]] if supp_opts.get("primary_supplier") else []) + supp_opts.get("backup_suppliers", [])

    target = next((s for s in all_supps if s and s.get("supplier_code") == supplier_code), None)
    if not target:
        return {"error": f"Supplier {supplier_code} not contracted for {sku_code}"}

    base_cost = target["unit_cost_aed"] * units
    # Expedited freight surcharge: +15% cost, cuts lead time by 1 day (min 1 day)
    freight_surcharge = round(base_cost * 0.15, 2) if expedited else 0.0
    lead_days = max(1, target["lead_time_days"] - (1 if expedited else 0))
    total_cost = round(base_cost + freight_surcharge, 2)

    return {
        "sku_code": sku_code,
        "supplier_code": supplier_code,
        "supplier_name": target["supplier_name"],
        "order_units": units,
        "base_cost_aed": base_cost,
        "expedited_freight_aed": freight_surcharge,
        "total_cost_aed": total_cost,
        "estimated_lead_days": lead_days,
        "reliability_score": target["reliability_score"]
    }


supplier_eval_tool = FunctionTool(evaluate_supplier_options)
procurement_quote_tool = FunctionTool(calculate_procurement_quote)
