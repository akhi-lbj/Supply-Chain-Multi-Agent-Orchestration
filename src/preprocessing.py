
from pathlib import Path

import pandas as pd

# --------------------------------------------------
# 1. Paths
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

SALES_FILE = RAW / "sales_train_validation.csv"
CALENDAR_FILE = RAW / "calendar.csv"
PRICES_FILE = RAW / "sell_prices.csv"

OUTPUT_FILE = PROCESSED / "m5_sales_sample.parquet"

# Number of products for our initial experiment
N_PRODUCTS = 20
CHUNK_SIZE = 1000


def main():

    PROCESSED.mkdir(parents=True, exist_ok=True)

    print("Starting M5 preprocessing...")

    # --------------------------------------------------
    # 2. Identify a manageable product sample
    # --------------------------------------------------

    metadata_cols = [
        "id",
        "item_id",
        "dept_id",
        "cat_id",
        "store_id",
        "state_id",
    ]

    metadata = pd.read_csv(
        SALES_FILE,
        usecols=metadata_cols
    )

    selected_items = (
        metadata["item_id"]
        .drop_duplicates()
        .head(N_PRODUCTS)
        .tolist()
    )

    print(f"Selected products: {len(selected_items)}")

    # --------------------------------------------------
    # 3. Read selected sales rows in chunks
    # --------------------------------------------------

    day_cols = [
        col for col in pd.read_csv(
            SALES_FILE,
            nrows=0
        ).columns
        if col.startswith("d_")
    ]

    usecols = metadata_cols + day_cols

    selected_chunks = []

    for chunk in pd.read_csv(
        SALES_FILE,
        usecols=usecols,
        chunksize=CHUNK_SIZE
    ):

        filtered = chunk[
            chunk["item_id"].isin(selected_items)
        ]

        if not filtered.empty:
            selected_chunks.append(filtered)

    sales = pd.concat(
        selected_chunks,
        ignore_index=True
    )

    print("Selected sales rows:", len(sales))

    # --------------------------------------------------
    # 4. Convert wide format to long format
    # --------------------------------------------------

    sales_long = sales.melt(
        id_vars=metadata_cols,
        value_vars=day_cols,
        var_name="d",
        value_name="sales"
    )

    sales_long["sales"] = sales_long["sales"].astype("int32")

    print("Long format shape:", sales_long.shape)

    # --------------------------------------------------
    # 5. Load calendar data
    # --------------------------------------------------

    calendar = pd.read_csv(CALENDAR_FILE)

    calendar["date"] = pd.to_datetime(
        calendar["date"]
    )

    calendar_cols = [
        "d",
        "date",
        "wm_yr_wk",
        "weekday",
        "wday",
        "month",
        "year",
        "event_name_1",
        "event_type_1",
        "event_name_2",
        "event_type_2",
        "snap_CA",
        "snap_TX",
        "snap_WI",
    ]

    calendar = calendar[calendar_cols]

    # --------------------------------------------------
    # 6. Join sales with calendar
    # --------------------------------------------------

    data = sales_long.merge(
        calendar,
        on="d",
        how="left",
        validate="many_to_one"
    )

    # --------------------------------------------------
    # 7. Load and join selling prices
    # --------------------------------------------------

    prices = pd.read_csv(PRICES_FILE)

    data = data.merge(
        prices,
        on=["item_id", "store_id", "wm_yr_wk"],
        how="left",
        validate="many_to_one"
    )
    # Identify missing prices
    data["price_missing"] = data["sell_price"].isna().astype("int8")

    # --------------------------------------------------
    # 8. Basic validation
    # --------------------------------------------------

    print("\nValidation results")

    print("Total observations:", len(data))
    print("Unique products:", data["item_id"].nunique())
    print("Unique stores:", data["store_id"].nunique())

    print("Missing dates:", data["date"].isna().sum())
    print("Missing prices:", data["sell_price"].isna().sum())
    print("Missing sales:", data["sales"].isna().sum())

    # Sort chronologically
    data = data.sort_values(
        ["item_id", "store_id", "date"]
    ).reset_index(drop=True)

    # --------------------------------------------------
    # 9. Add source traceability
    # --------------------------------------------------

    data["data_source"] = "M5"

    data["source_record_id"] = (
        data["id"] + "_" + data["d"]
    )

    # --------------------------------------------------
    # 10. Save processed dataset
    # --------------------------------------------------

    data.to_parquet(
        OUTPUT_FILE,
        index=False
    )

    print("\nPreprocessing completed!")
    print("Saved to:", OUTPUT_FILE)

    print("\nFinal dataset preview:")
    print(data.head())

    print("\nFinal columns:")
    print(data.columns.tolist())


if __name__ == "__main__":
    main()
