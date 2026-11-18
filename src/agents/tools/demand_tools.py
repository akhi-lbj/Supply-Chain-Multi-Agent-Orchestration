# src/agents/tools/demand_tools.py
from google.adk.tools import FunctionTool


def query_fastapi_disruption_service(item_id: str, store_id: str, available_stock: float) -> dict:
    """Invokes the local NEXUS 5-day disruption forecasting microservice."""
    import requests
    payload = {
        "decision_date": "2026-04-19",
        "delay_days": 5,
        "items": [{
            "item_id": item_id,
            "store_id": store_id,
            "available_stock": available_stock,
            "current_sales_t0": 4.0,
            "lag_7": 6.0,
            "lag_14": 5.0,
            "hist_sum_5d": 18.0,
            "hist_mean_7d": 4.5,
            "hist_mean_28d": 4.8,
            "sell_price": 8.99,
            "snap_flag": 0
        }]
    }
    try:
        response = requests.post("http://127.0.0.1:8000/forecast/disruption", json=payload, timeout=10)
        return response.json()
    except Exception as exc:
        return {"error": f"Failed to connect to forecasting service at http://127.0.0.1:8000: {exc}"}


forecast_tool = FunctionTool(query_fastapi_disruption_service)

