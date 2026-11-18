
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

file_path = ROOT / "data" / "processed" / "m5_sales_sample.parquet"
df = pd.read_parquet(file_path)

# Overall missing-price statistics
missing = df["sell_price"].isna()

print("\n--- Overall price statistics ---")
print("Total rows:", len(df))
print("Missing prices:", missing.sum())
print("Missing percentage:", round(missing.mean() * 100, 2), "%")

# Are there sales despite missing prices?
print("\n--- Missing prices vs sales ---")

missing_price_rows = df[missing]

print("Missing price + zero sales:",
      (missing_price_rows["sales"] == 0).sum())

print("Missing price + positive sales:",
      (missing_price_rows["sales"] > 0).sum())

# Missing prices by product and store
print("\n--- Missing prices by product/store ---")

summary = (
    df.groupby(["item_id", "store_id"])
    .agg(
        total_rows=("sales", "size"),
        missing_prices=("sell_price", lambda x: x.isna().sum()),
        first_date=("date", "min"),
        last_date=("date", "max"),
    )
    .reset_index()
)

summary["missing_percentage"] = (
    summary["missing_prices"] / summary["total_rows"] * 100
).round(2)

print(
    summary.sort_values(
        "missing_percentage",
        ascending=False
    ).to_string(index=False)
)

# Inspect the missing-price date range
print("\n--- Missing-price date range ---")

print("First missing date:", missing_price_rows["date"].min())
print("Last missing date:", missing_price_rows["date"].max())

# First date with a recorded price per product/store
availability = (
    df.groupby(["item_id", "store_id"])
    .apply(
        lambda group: group.loc[
            group["sell_price"].notna(), "date"
        ].min(),
        include_groups=False
    )
    .rename("first_price_date")
    .reset_index()
)

print(availability.to_string(index=False)) 

# Show positive sales with missing prices
print("\n--- Examples: positive sales but missing prices ---")

print(
    missing_price_rows.loc[
        missing_price_rows["sales"] > 0,
        ["item_id", "store_id", "date", "sales", "wm_yr_wk"]
    ].head(20).to_string(index=False)
)
