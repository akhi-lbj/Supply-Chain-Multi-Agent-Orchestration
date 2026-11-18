# scripts/seed_uae_retail_data.py
import csv
import json
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
DATA_DIR.mkdir(parents=True, exist_ok=True)

random.seed(42)

# ==============================================================================
# 1. ENTITY CONFIGURATIONS (UAE Supply Chain Network)
# ==============================================================================

WAREHOUSES = [
    {
        "location_code": "DC_JAFZA",
        "name": "Jebel Ali Regional Hub",
        "type": "WAREHOUSE",
        "emirate": "Dubai",
        "address": "JAFZA South Zone 1, Jebel Ali, Dubai",
        "capacity_pallets": 15000,
    },
    {
        "location_code": "DC_AL_QUOZ",
        "name": "Al Quoz Central Distribution Center",
        "type": "WAREHOUSE",
        "emirate": "Dubai",
        "address": "Al Quoz Industrial Area 3, Dubai",
        "capacity_pallets": 8000,
    },
    {
        "location_code": "DC_DIC",
        "name": "Dubai Industrial City Logistics Buffer",
        "type": "WAREHOUSE",
        "emirate": "Dubai",
        "address": "Dubai Industrial City, Saih Shuaib 2, Dubai",
        "capacity_pallets": 20000,
    },
]

STORE_NAMES = [
    ("STR_DXB_01", "Dubai Mall Flagship", "Downtown Dubai, Dubai"),
    ("STR_DXB_02", "Mall of the Emirates Hypermarket", "Al Barsha 1, Dubai"),
    ("STR_DXB_03", "City Centre Mirdif", "Mirdif, Dubai"),
    ("STR_DXB_04", "Dubai Hills Mall", "Dubai Hills Estate, Dubai"),
    ("STR_DXB_05", "Dubai Festival City", "Festival City, Dubai"),
    ("STR_DXB_06", "Deira City Centre", "Deira, Dubai"),
    ("STR_DXB_07", "Ibn Battuta Mall", "Jebel Ali Village, Dubai"),
    ("STR_DXB_08", "Al Barsha South Community Store", "Al Barsha South, Dubai"),
    ("STR_DXB_09", "Jumeirah Beach Residence (JBR)", "The Walk, JBR, Dubai"),
    ("STR_DXB_10", "Dubai Silicon Oasis Express", "DSO Central, Dubai"),
    ("STR_DXB_11", "Al Karama Market Hub", "Al Karama, Dubai"),
    ("STR_DXB_12", "Al Nahda Urban Market", "Al Nahda 2, Dubai"),
    ("STR_DXB_13", "Bur Dubai Superstore", "Al Mankhool, Bur Dubai"),
    ("STR_DXB_14", "Motor City Community Hub", "Detroit Road, Motor City, Dubai"),
    ("STR_DXB_15", "Jumeirah Village Circle (JVC)", "District 10, JVC, Dubai"),
    ("STR_SHJ_01", "City Centre Sharjah", "Al Nahda Street, Sharjah"),
    ("STR_SHJ_02", "Al Majaz Waterfront Store", "Al Majaz 2, Sharjah"),
    ("STR_SHJ_03", "Muwaileh Commercial Hub", "University City Road, Sharjah"),
    ("STR_AUH_01", "Yas Mall Hyperstore", "Yas Island, Abu Dhabi"),
    ("STR_AUH_02", "Al Wahda Central", "Hazaa Bin Zayed Street, Abu Dhabi"),
]

SUPPLIERS = [
    ("SUP_01", "Al Ain Farms Dairy & Poultry", "Al Ain, UAE", 2, 0.98),
    ("SUP_02", "National Food Products Co (NFPC)", "Dubai, UAE", 2, 0.95),
    ("SUP_03", "Gulf Food Industries (Americana)", "Sharjah, UAE", 3, 0.92),
    ("SUP_04", "Agthia Group Logistics", "Abu Dhabi, UAE", 2, 0.96),
    ("SUP_05", "Dabur Regional Distribution", "JAFZA, Dubai", 4, 0.90),
    ("SUP_06", "Unilever GCC Logistics", "Dubai Industrial City, UAE", 5, 0.94),
    ("SUP_07", "Nestle Middle East Distribution", "Technopark, Dubai", 4, 0.97),
    ("SUP_08", "Mondelez Middle East Hub", "Bahrain/UAE Corridor", 6, 0.89),
    ("SUP_09", "IFFCO Gulf Consumer Brands", "Sharjah, UAE", 3, 0.93),
    ("SUP_10", "P&G Arabian Peninsula Distribution", "JAFZA, Dubai", 5, 0.91),
    ("SUP_11", "Al Rawabi Dairy Co", "Al Khawaneej, Dubai", 1, 0.99),
    ("SUP_12", "Emirates Refreshments (Jeema)", "Dibba/Dubai, UAE", 2, 0.94),
    ("SUP_13", "Reckitt Benckiser Middle East", "Al Quoz, Dubai", 4, 0.92),
    ("SUP_14", "Henkel GCC Supply Chain", "Dubai Media City/DIC, UAE", 4, 0.90),
    ("SUP_15", "Global Trade Importers Ltd", "Port Khalid, Sharjah", 7, 0.86),
]

CATEGORIES = [
    ("CAT_DAIRY", "Dairy & Chilled Beverages", 0.08),
    ("CAT_BAKERY", "Fresh Bakery & Breads", 0.12),
    ("CAT_FMCG_DRY", "Ambient Grocery & Dry Goods", 0.18),
    ("CAT_BEVERAGE", "Water, Juices & Soft Drinks", 0.15),
    ("CAT_PERSONAL", "Personal Care & Hygiene", 0.28),
    ("CAT_HOME", "Household Cleaning & Detergents", 0.24),
]

# ==============================================================================
# 2. GENERATION LOGIC
# ==============================================================================

def generate_network_data():
    # A. Locations (Stores + Warehouses)
    locations = []
    for wh in WAREHOUSES:
        locations.append({
            "location_id": str(uuid.uuid4()),
            "location_code": wh["location_code"],
            "name": wh["name"],
            "location_type": wh["type"],
            "emirate": wh["emirate"],
            "address": wh["address"],
            "capacity_pallets": wh["capacity_pallets"],
            "created_at": datetime.now().isoformat()
        })
    for code, name, addr in STORE_NAMES:
        emirate = "Abu Dhabi" if "AUH" in code else ("Sharjah" if "SHJ" in code else "Dubai")
        locations.append({
            "location_id": str(uuid.uuid4()),
            "location_code": code,
            "name": name,
            "location_type": "STORE",
            "emirate": emirate,
            "address": addr,
            "capacity_pallets": random.randint(200, 600),
            "created_at": datetime.now().isoformat()
        })

    # B. Suppliers
    suppliers = []
    for s_code, s_name, s_addr, s_lead, s_sla in SUPPLIERS:
        suppliers.append({
            "supplier_id": str(uuid.uuid4()),
            "supplier_code": s_code,
            "name": s_name,
            "origin_address": s_addr,
            "standard_lead_days": s_lead,
            "contracted_sla_rate": s_sla,
            "reliability_score": round(s_sla * random.uniform(0.96, 1.02), 3),
            "created_at": datetime.now().isoformat()
        })

    # C. Products (500 SKUs across categories)
    products = []
    supplier_products = []
    
    sku_counter = 1
    for cat_code, cat_name, base_margin in CATEGORIES:
        skus_in_cat = 85 if cat_code in ["CAT_FMCG_DRY", "CAT_DAIRY", "CAT_BEVERAGE"] else 80
        for _ in range(skus_in_cat):
            sku_code = f"SKU_{sku_counter:04d}"
            cost_aed = round(random.uniform(3.5, 65.0), 2)
            retail_aed = round(cost_aed / (1.0 - base_margin + random.uniform(-0.03, 0.03)), 2)
            shelf_life = random.choice([7, 14, 21]) if cat_code in ["CAT_DAIRY", "CAT_BAKERY"] else random.choice([180, 360, 720])
            
            p_id = str(uuid.uuid4())
            products.append({
                "product_id": p_id,
                "sku_code": sku_code,
                "name": f"{cat_name.split()[0]} Item #{sku_counter:04d}",
                "category_code": cat_code,
                "cost_price_aed": cost_aed,
                "retail_price_aed": retail_aed,
                "shelf_life_days": shelf_life,
                "is_active": True,
                "created_at": datetime.now().isoformat()
            })
            
            # Map to 1 primary and 1 alternate supplier
            chosen_supps = random.sample(suppliers, 2)
            supplier_products.append({
                "supplier_product_id": str(uuid.uuid4()),
                "supplier_id": chosen_supps[0]["supplier_id"],
                "product_id": p_id,
                "is_primary": True,
                "lead_time_days": chosen_supps[0]["standard_lead_days"],
                "unit_cost_aed": cost_aed
            })
            supplier_products.append({
                "supplier_product_id": str(uuid.uuid4()),
                "supplier_id": chosen_supps[1]["supplier_id"],
                "product_id": p_id,
                "is_primary": False,
                "lead_time_days": chosen_supps[1]["standard_lead_days"] + 2, # Expedited/backup SLA
                "unit_cost_aed": round(cost_aed * 1.08, 2) # Alternate supplier premium
            })
            sku_counter += 1

    # D. Inventory Balances (Stores & DCs)
    inventory_balances = []
    for loc in locations:
        is_dc = loc["location_type"] == "WAREHOUSE"
        for prod in products:
            if is_dc:
                on_hand = random.randint(150, 1200)
                safety_target = random.randint(200, 400)
            else:
                on_hand = random.randint(5, 45)
                safety_target = random.randint(10, 25)

            inventory_balances.append({
                "balance_id": str(uuid.uuid4()),
                "location_id": loc["location_id"],
                "product_id": prod["product_id"],
                "available_stock": on_hand,
                "allocated_stock": random.randint(0, int(on_hand * 0.15)),
                "safety_stock_threshold": safety_target,
                "last_updated": datetime.now().isoformat()
            })

    # Save to CSV
    def save_csv(filename, data_list):
        if not data_list:
            return
        keys = data_list[0].keys()
        with open(DATA_DIR / filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data_list)
        print(f"Generated: {filename} ({len(data_list):,} records)")

    save_csv("locations.csv", locations)
    save_csv("suppliers.csv", suppliers)
    save_csv("products.csv", products)
    save_csv("supplier_products.csv", supplier_products)
    save_csv("inventory_balances.csv", inventory_balances)


if __name__ == "__main__":
    generate_network_data()
    print("UAE Retail Synthetic Network generation complete.")