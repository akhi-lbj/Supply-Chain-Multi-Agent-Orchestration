-- scripts/init_control_tower_db.sql
-- NEXUS Control Tower PostgreSQL Schema

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Locations (Distribution Centers & Retail Stores)
CREATE TABLE IF NOT EXISTS locations (
    location_id UUID PRIMARY KEY,
    location_code VARCHAR(32) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    location_type VARCHAR(32) NOT NULL, -- 'WAREHOUSE' or 'STORE'
    emirate VARCHAR(64),
    address TEXT,
    capacity_pallets INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Suppliers
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id UUID PRIMARY KEY,
    supplier_code VARCHAR(32) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    origin_address TEXT,
    standard_lead_days INTEGER NOT NULL,
    contracted_sla_rate NUMERIC(5, 4),
    reliability_score NUMERIC(5, 4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Products / Catalog
CREATE TABLE IF NOT EXISTS products (
    product_id UUID PRIMARY KEY,
    sku_code VARCHAR(32) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    category_code VARCHAR(64),
    cost_price_aed NUMERIC(10, 2) NOT NULL,
    retail_price_aed NUMERIC(10, 2) NOT NULL,
    shelf_life_days INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Supplier-Product Mapping (Lead times & contracted unit pricing)
CREATE TABLE IF NOT EXISTS supplier_products (
    supplier_product_id UUID PRIMARY KEY,
    supplier_id UUID NOT NULL REFERENCES suppliers(supplier_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    lead_time_days INTEGER NOT NULL,
    unit_cost_aed NUMERIC(10, 2) NOT NULL,
    CONSTRAINT uq_supplier_product UNIQUE (supplier_id, product_id)
);

-- 5. Inventory Balances (Live stock levels across DCs and Stores)
CREATE TABLE IF NOT EXISTS inventory_balances (
    balance_id UUID PRIMARY KEY,
    location_id UUID NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    available_stock INTEGER NOT NULL CHECK (available_stock >= 0),
    allocated_stock INTEGER NOT NULL DEFAULT 0 CHECK (allocated_stock >= 0),
    safety_stock_threshold INTEGER NOT NULL DEFAULT 0 CHECK (safety_stock_threshold >= 0),
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_location_product UNIQUE (location_id, product_id)
);

-- 6. Emergency Purchase Orders
CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id UUID PRIMARY KEY,
    po_reference VARCHAR(64) UNIQUE NOT NULL,
    supplier_id UUID REFERENCES suppliers(supplier_id),
    sku_code VARCHAR(32) NOT NULL,
    units INTEGER NOT NULL,
    unit_cost_aed NUMERIC(10, 2) NOT NULL,
    freight_aed NUMERIC(10, 2) DEFAULT 0.00,
    total_amount_aed NUMERIC(10, 2) NOT NULL,
    is_expedited BOOLEAN DEFAULT TRUE,
    status VARCHAR(32) NOT NULL DEFAULT 'ISSUED', -- 'ISSUED', 'CONFIRMED', 'DELIVERED', 'CANCELLED'
    delivery_eta_days INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Internal Warehouse Transfers
CREATE TABLE IF NOT EXISTS transfer_orders (
    transfer_id UUID PRIMARY KEY,
    transfer_reference VARCHAR(64) UNIQUE NOT NULL,
    sku_code VARCHAR(32) NOT NULL,
    origin_location_code VARCHAR(32) NOT NULL,
    destination_store_code VARCHAR(32) NOT NULL,
    units INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'DISPATCHED_TO_WMS', -- 'DISPATCHED_TO_WMS', 'IN_TRANSIT', 'RECEIVED'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for lightning-fast agent query joins
CREATE INDEX IF NOT EXISTS idx_inv_location_product ON inventory_balances (location_id, product_id);
CREATE INDEX IF NOT EXISTS idx_supp_prod_product ON supplier_products (product_id);
CREATE INDEX IF NOT EXISTS idx_prod_sku ON products (sku_code);
CREATE INDEX IF NOT EXISTS idx_loc_code ON locations (location_code);
CREATE INDEX IF NOT EXISTS idx_supp_code ON suppliers (supplier_code);

