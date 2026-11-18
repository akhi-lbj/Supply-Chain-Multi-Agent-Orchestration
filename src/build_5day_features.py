import json
from pathlib import Path
import numpy as np
import pandas as pd

# Paths
cwd = Path.cwd()
PROJECT_ROOT = cwd.parent if cwd.name in {"src", "notebooks"} else cwd
DATA_DIR = PROJECT_ROOT / "data" / "processed"

# 1. Load contiguous historical data (before splitting)
source_file = DATA_DIR / "m5_features.parquet"
if not source_file.exists():
    source_file = DATA_DIR / "m5_sales_sample.parquet"

df = pd.read_parquet(source_file)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values(["item_id", "store_id", "date"]).reset_index(drop=True)

# 2. Compute Direct 5-Day Forward Target: sum(t+1 .. t+5)
HORIZON = 5
df["target_5d"] = (
    df.groupby(["item_id", "store_id"])["sales"]
    .transform(lambda s: s.iloc[::-1].rolling(HORIZON, min_periods=HORIZON).sum().iloc[::-1].shift(-1))
)

# 3. Compute Leakage-Free Features (strictly available at decision day t0)
# Day t0 actual sales
df["lag_0"] = df["sales"]
df["lag_7"] = df.groupby(["item_id", "store_id"])["sales"].shift(7)
df["lag_14"] = df.groupby(["item_id", "store_id"])["sales"].shift(14)

# Past cumulative consumption ending at t0
df["hist_sum_5d"] = (
    df.groupby(["item_id", "store_id"])["sales"]
    .transform(lambda s: s.rolling(HORIZON, min_periods=HORIZON).sum())
)
df["hist_mean_7d"] = (
    df.groupby(["item_id", "store_id"])["sales"]
    .transform(lambda s: s.rolling(7, min_periods=7).mean())
)
df["hist_mean_28d"] = (
    df.groupby(["item_id", "store_id"])["sales"]
    .transform(lambda s: s.rolling(28, min_periods=14).mean())
)

# 4. Seasonal Naïve 5-Day Baseline: past 5-day sum shifted by 7 days
df["seasonal_naive_5d"] = df.groupby(["item_id", "store_id"])["hist_sum_5d"].shift(7)

# 5. Drop unneeded 1-day rolling columns if present
cols_to_drop = [c for c in ["lag_1", "rolling_mean_7", "rolling_mean_28"] if c in df.columns]
df = df.drop(columns=cols_to_drop)

# Save full processed dataset
df.to_parquet(DATA_DIR / "m5_features_5d.parquet", index=False)

# 6. Apply Chronological Splits
# Drop warmup rows where 28-day history or forward target is unavailable
clean_df = df.dropna(subset=["target_5d", "seasonal_naive_5d", "hist_mean_28d"]).copy()

TRAIN_END = "2015-04-13"
VAL_START = "2015-04-14"
VAL_END = "2015-10-18"
TEST_START = "2015-10-19"

train_5d = clean_df[clean_df["date"] <= TRAIN_END].copy()
val_5d = clean_df[(clean_df["date"] >= VAL_START) & (clean_df["date"] <= VAL_END)].copy()
test_5d = clean_df[clean_df["date"] >= TEST_START].copy()

# Save split parquets
train_5d.to_parquet(DATA_DIR / "train_5d.parquet", index=False)
val_5d.to_parquet(DATA_DIR / "validation_5d.parquet", index=False)
test_5d.to_parquet(DATA_DIR / "test_5d.parquet", index=False)

# 7. Write updated metadata JSON
meta_5d = {
    "input_file": "m5_features_5d.parquet",
    "target": "target_5d",
    "horizon_days": 5,
    "feature_columns": [
        "item_id", "store_id", "day_of_week", "is_weekend", "month",
        "sell_price", "price_missing", "snap", "lag_0", "lag_7", "lag_14",
        "hist_sum_5d", "hist_mean_7d", "hist_mean_28d"
    ],
    "baseline_column": "seasonal_naive_5d",
    "identifier_columns": ["item_id", "store_id", "date"],
    "train_rows": len(train_5d),
    "val_rows": len(val_5d),
    "test_rows": len(test_5d)
}

with open(DATA_DIR / "split_metadata_5d.json", "w") as f:
    json.dump(meta_5d, f, indent=2)

print("Saved new 5-day parquet files and split_metadata_5d.json.")