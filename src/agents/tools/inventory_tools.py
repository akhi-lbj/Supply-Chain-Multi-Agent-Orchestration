# src/agents/tools/inventory_tools.py
from typing import Dict, List, Any
from google.adk.tools import FunctionTool
from src.agents.db import query_inventory_balances_sql


def get_inventory_balances(sku_code: str, location_codes: List[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieves current stock levels, allocated stock, and safety thresholds
    across retail stores and distribution centers for a given SKU via SQL query.
    """
    return query_inventory_balances_sql(sku_code=sku_code, location_codes=location_codes)


def check_warehouse_transfer_availability(sku_code: str, required_units: int) -> Dict[str, Any]:
    """
    Checks if central distribution centers (DC_JAFZA, DC_AL_QUOZ, DC_DIC)
    have surplus stock available for immediate emergency store transfer.
    """
    wh_balances = get_inventory_balances(
        sku_code, location_codes=["DC_JAFZA", "DC_AL_QUOZ", "DC_DIC"]
    )

    available_transfers = []
    total_wh_surplus = 0

    for wh in wh_balances:
        if "net_free_stock" not in wh:
            continue
        surplus = max(0, wh["net_free_stock"] - wh["safety_stock_threshold"])
        if surplus > 0:
            available_transfers.append({
                "warehouse_code": wh["location_code"],
                "warehouse_name": wh["location_name"],
                "surplus_units": surplus,
                "location_code": wh["location_code"],
                "transferrable_surplus": surplus
            })
            total_wh_surplus += surplus

    return {
        "sku_code": sku_code,
        "required_units": required_units,
        "can_fulfill_from_warehouses": total_wh_surplus >= required_units,
        "total_warehouse_surplus": total_wh_surplus,
        "total_wh_surplus": total_wh_surplus,
        "available_transfers": available_transfers,
        "surplus_breakdown": available_transfers
    }


inventory_balance_tool = FunctionTool(get_inventory_balances)
warehouse_transfer_tool = FunctionTool(check_warehouse_transfer_availability)
