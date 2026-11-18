# src/api/service.py
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import uuid
from src.api.schemas import DisruptionForecastRequest, DisruptionForecastResponse, DisruptionForecastItemResult

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = PROJECT_ROOT / "models"
MEAN_MODEL_PATH = MODEL_DIR / "nexus_5d_mean_model.joblib"
P90_MODEL_PATH = MODEL_DIR / "nexus_5d_p90_buffer.joblib"


class ForecastEngine:
    def __init__(self):
        self.mean_pipeline = None
        self.p90_pipeline = None

    def load_artifacts(self):
        if not MEAN_MODEL_PATH.exists() or not P90_MODEL_PATH.exists():
            raise FileNotFoundError("Model artifacts not found in models/ directory.")
        self.mean_pipeline = joblib.load(MEAN_MODEL_PATH)
        self.p90_pipeline = joblib.load(P90_MODEL_PATH)

    def predict_disruption(self, payload: DisruptionForecastRequest) -> DisruptionForecastResponse:
        run_id = str(uuid.uuid4())
        records = []
        metadata = []

        d = pd.to_datetime(payload.decision_date)
        day_of_week = d.dayofweek
        is_weekend = 1 if day_of_week in [5, 6] else 0
        month = d.month

        for item in payload.items:
            price_missing = 1 if item.sell_price is None or np.isnan(item.sell_price) else 0
            sell_price = 0.0 if price_missing else float(item.sell_price)

            records.append({
                "item_id": item.item_id,
                "store_id": item.store_id,
                "day_of_week": day_of_week,
                "is_weekend": is_weekend,
                "month": month,
                "sell_price": sell_price,
                "price_missing": price_missing,
                "snap": item.snap_flag,
                "lag_0": item.current_sales_t0,
                "lag_7": item.lag_7,
                "lag_14": item.lag_14,
                "hist_sum_5d": item.hist_sum_5d,
                "hist_mean_7d": item.hist_mean_7d,
                "hist_mean_28d": item.hist_mean_28d
            })
            metadata.append({
                "item_id": item.item_id,
                "store_id": item.store_id,
                "available_stock": item.available_stock
            })

        input_df = pd.DataFrame(records)

        # Batch prediction
        raw_mean = self.mean_pipeline.predict(input_df)
        raw_p90 = self.p90_pipeline.predict(input_df)

        expected_demand = np.clip(np.round(raw_mean, 2), 0, None)
        p90_demand = np.clip(np.round(raw_p90, 2), 0, None)

        results = []
        stockout_count = 0

        for i, meta in enumerate(metadata):
            exp_val = float(expected_demand[i])
            p90_val = float(p90_demand[i])
            stock = meta["available_stock"]

            is_stockout = stock < p90_val
            shortage = round(max(0.0, p90_val - stock), 2)
            if is_stockout:
                stockout_count += 1

            results.append(DisruptionForecastItemResult(
                item_id=meta["item_id"],
                store_id=meta["store_id"],
                available_stock=stock,
                expected_5d_demand=exp_val,
                p90_safety_demand=p90_val,
                stockout_risk=is_stockout,
                shortage_units=shortage
            ))

        return DisruptionForecastResponse(
            forecast_run_id=run_id,
            decision_date=payload.decision_date,
            horizon_days=payload.delay_days,
            total_skus_evaluated=len(payload.items),
            stockouts_detected=stockout_count,
            results=results
        )


forecast_engine = ForecastEngine()