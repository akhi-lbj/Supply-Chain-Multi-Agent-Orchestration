# NEXUS Control Tower — Autonomous Supply Chain Multi-Agent Orchestration

**NEXUS Control Tower** is an end-to-end autonomous supply chain disruption resolution platform built with **Google Agent Development Kit (ADK)**, **IFM K2-Horizon (375B-A23B)**, **Liquid AI Decision Models (`d1.1`)**, **XGBoost Probabilistic Demand Forecasting**, **FastAPI**, and **PostgreSQL**.

When a supply chain disruption occurs (such as a vendor delay or logistics bottleneck across UAE retail stores and distribution centers), NEXUS orchestrates specialized AI agents to predict stockout risk at the 90th percentile (P90), audit real-time warehouse and store inventory, negotiate emergency purchase order quotes with alternative suppliers, and execute human-in-the-loop transactional mitigations.

---

## System Architecture

```mermaid
flowchart TB
    subgraph Client["User & Control Tower Interfaces"]
        UI["ADK Web UI / Operator Console"]
        API_CLIENT["REST API Client / Webhook Trigger"]
    end

    subgraph Guardrail["Security & Adversarial Defense Layer"]
        LIQUID["Liquid AI Decision Model (d1.1)\nbefore_model_callback Guardrail\n(Calibrated Prompt Injection & Jailbreak Filter)"]
    end

    subgraph Orchestration["Google ADK Multi-Agent Hierarchy (IFM K2-Horizon-375B)"]
        SUP["Supervisor Agent\n(Root Orchestrator & Decision Synthesizer)"]
        DEM["Demand Forecasting Agent\n(5-Day Horizon & P90 Risk Assessor)"]
        INV["Inventory Auditor Agent\n(Multi-Node Store & DC Stock Analyst)"]
        SUPP["Supplier Intelligence Agent\n(Vendor Reliability & Expedited PO Analyst)"]
    end

    subgraph Tools["Agent FunctionTools & Microservices"]
        T_DEM["query_fastapi_disruption_service\n(HTTP POST /forecast/disruption)"]
        T_INV1["get_store_inventory_baseline"]
        T_INV2["get_warehouse_surplus"]
        T_SUP1["get_delayed_supplier_profile"]
        T_SUP2["find_alternative_suppliers"]
        T_EXEC["Transactional Mitigation Engine\n(Inventory Transfer & Emergency PO)"]
    end

    subgraph DataAndML["Data, ML & Persistence Layer"]
        FASTAPI["FastAPI Service (:8000)\nControl Tower & Forecast Engine"]
        XGB["XGBoost 5-Day Pipelines\n• nexus_5d_mean_model.joblib\n• nexus_5d_p90_buffer.joblib"]
        PG[("PostgreSQL 18\n(nexus_control_tower)\n• locations & suppliers\n• products & supplier_products\n• inventory_balances\n• transfer_orders & purchase_orders")]
        SQLITE[("SQLite Audit Store\n(Disruption Runs & Approval Ledger)")]
    end

    UI -->|"User Prompt / Incident Alert"| LIQUID
    API_CLIENT -->|"POST /api/disruptions/trigger"| FASTAPI
    FASTAPI -->|"Autonomous Triage"| LIQUID

    LIQUID -->|"Blocked (Score >= 0.65)"| UI
    LIQUID -->|"Verified Safe (Score < 0.65)"| SUP

    SUP -->|"1. Assess Deficit"| DEM
    SUP -->|"2. Audit Network Stock"| INV
    SUP -->|"3. Source Alternatives"| SUPP

    DEM --> T_DEM
    T_DEM --> FASTAPI
    FASTAPI --> XGB

    INV --> T_INV1
    INV --> T_INV2
    T_INV1 --> PG
    T_INV2 --> PG

    SUPP --> T_SUP1
    SUPP --> T_SUP2
    T_SUP1 --> PG
    T_SUP2 --> PG

    FASTAPI --> SQLITE
    API_CLIENT -->|"POST /api/approvals/{id}/action"| T_EXEC
    T_EXEC -->|"ACID Row Mutation"| PG
    T_EXEC -->|"Audit Trail"| SQLITE
```

---

## End-to-End Disruption Resolution Workflow

```mermaid
sequenceDiagram
    autonumber
    actor Manager as Supply Chain Manager
    participant Guard as Liquid d1.1 Guardrail
    participant Sup as Supervisor Agent
    participant Dem as Demand Agent (XGBoost)
    participant Inv as Inventory Agent (PostgreSQL)
    participant Ven as Supplier Agent (PostgreSQL)
    participant DB as PostgreSQL / Control Tower API

    Manager->>Guard: Submit Disruption Notification (e.g. SUP_01 delayed 5 days on SKU_0001)
    Guard->>Guard: Evaluate state via POST /decisions/v1/systemone (Noul Gate)
    alt Prompt Injection Detected (>= 65% Confidence)
        Guard-->>Manager: 🛡️ SECURITY ALERT: Request Blocked
    else Legitimate Operational Input (< 65% Confidence)
        Guard->>Sup: Forward validated incident context
        Sup->>Dem: Request 5-day demand & P90 safety stock projection
        Dem->>DB: POST /forecast/disruption (Mean + P90 Quantile XGBoost)
        DB-->>Dem: Expected Demand, P90 Buffer, Stockout Risk & Shortage Units
        Dem-->>Sup: Return structured deficit payload

        Sup->>Inv: Audit affected store stock & central warehouse surplus
        Inv->>DB: SQL JOIN on inventory_balances & locations (DC_JAFZA, DC_AL_QUOZ, DC_DIC)
        DB-->>Inv: Store On-Hand, Reorder Point, & Allocatable DC Surplus
        Inv-->>Sup: Return network inventory availability

        Sup->>Ven: Evaluate delayed supplier & rank accredited alternatives
        Ven->>DB: SQL JOIN on suppliers & supplier_products
        DB-->>Ven: Lead times, reliability scores, MOQs, & expedited PO cost
        Ven-->>Sup: Return ranked vendor procurement quotes

        Sup-->>Manager: Synthesize Executive Briefing (Scenario A: DC Transfer vs Scenario B: Emergency PO)
        Manager->>DB: Approve Mitigation (POST /api/approvals/{approval_id}/action)
        DB->>DB: Execute ACID Transaction (Update inventory_balances / Insert transfer_orders or purchase_orders)
        DB-->>Manager: Return Dispatch Confirmation & Audit Reference
    end
```

---

## Key Capabilities

1. **Multi-Agent Orchestration with Google ADK & K2-Horizon**:
   - **Supervisor Agent** (`src/agents/supervisor_agent.py`): Coordinates root triage, delegates tasks across sub-agents, compares recovery scenarios (Warehouse Transfer vs. Expedited Vendor PO), and produces an actionable approval card.
   - **Demand Forecasting Agent** (`src/agents/demand_agent.py`): Calls the local FastAPI XGBoost microservice to predict 5-day expected sales and 90th-percentile (`P90`) safety demand buffers.
   - **Inventory Auditor Agent** (`src/agents/inventory_agent.py`): Queries live PostgreSQL tables for store-level stock baselines and distribution center (`DC_JAFZA`, `DC_AL_QUOZ`, `DC_DIC`) allocatable surplus above safety thresholds.
   - **Supplier Intelligence Agent** (`src/agents/supplier_agent.py`): Audits vendor reliability, lead-time penalties, minimum order quantities (MOQs), and total landed procurement costs in AED.

2. **Liquid AI (`d1.1`) Pre-Execution Security Guardrail**:
   - Implemented via Google ADK's `before_model_callback` (`src/agents/decision_callback.py`).
   - Evaluates incoming prompts in a single forward pass using calibrated probabilities (`Noul` question type) to block prompt injection, jailbreaking, and instruction overriding before reaching the LLM.

3. **Live PostgreSQL Transactional State & SQLite Audit Store**:
   - Seeded with UAE retail network topology: **23 locations** (20 stores + 3 distribution centers), **15 suppliers**, **495 products**, **990 supplier-product contracts**, and **11,385 inventory balances**.
   - Human-in-the-loop approvals trigger real ACID row mutations (`execute_inventory_transfer_sql` and `execute_emergency_po_sql` in `src/agents/db.py`), deducting warehouse stock, incrementing in-transit store inventory, and recording `transfer_orders` or `purchase_orders`.

---

## Repository Structure

```text
nexus-forecasting/
├── data/
│   └── synthetic/                  # UAE Retail synthetic relational CSVs for seeding
│       ├── locations.csv
│       ├── suppliers.csv
│       ├── products.csv
│       ├── supplier_products.csv
│       └── inventory_balances.csv
├── models/                         # Trained 5-day XGBoost forecasting pipelines
│   ├── nexus_5d_mean_model.joblib
│   └── nexus_5d_p90_buffer.joblib
├── scripts/                        # PostgreSQL DDL schema & automated seeding utility
│   ├── init_control_tower_db.sql
│   └── seed_postgres.py
├── src/
│   ├── agents/                     # Google ADK multi-agent system
│   │   ├── tools/                  # FunctionTools for Demand, Inventory, and Supplier agents
│   │   ├── agent.py                # ADK root_agent entrypoint
│   │   ├── config.py               # LiteLLM K2-Horizon setup & multi-turn reasoning patch
│   │   ├── db.py                   # SQLAlchemy PostgreSQL query & ACID transaction layer
│   │   ├── decision_callback.py    # Liquid d1.1 prompt injection guardrail
│   │   ├── demand_agent.py         # Demand Forecasting Agent
│   │   ├── inventory_agent.py      # Inventory Auditor Agent
│   │   ├── supplier_agent.py       # Supplier Intelligence Agent
│   │   └── supervisor_agent.py     # Root Supervisor Agent
│   ├── api/                        # FastAPI Control Tower & Forecast Engine
│   │   ├── control_tower.py        # Disruption trigger & manager approval endpoints
│   │   ├── main.py                 # FastAPI entrypoint & CORS middleware
│   │   ├── schemas.py              # Pydantic request/response schemas
│   │   ├── scoring.py              # Mitigation option ranking (cost, speed, reliability)
│   │   ├── service.py              # XGBoost inference engine
│   │   └── store.py                # SQLite control tower state & approval persistence
│   ├── build_5day_features.py      # 5-day rolling lag & price feature engineering
│   ├── preprocessing.py            # M5 raw data transformation pipeline
│   ├── feature_engineering.ipynb   # Exploratory feature engineering notebook
│   ├── seasonal_baseline.ipynb     # Baseline seasonal benchmark notebook
│   └── train_test.ipynb            # XGBoost Mean & P90 Quantile training notebook
├── tests/
│   └── test_control_tower_api.py   # End-to-end API & mitigation execution tests
├── .env.example                    # Environment variable template
├── pyproject.toml                  # Project dependencies (uv / PEP 621)
└── README.md
```

---

## Quick Start Guide

### 1. Prerequisites & Environment Setup

Clone the repository and install dependencies using `uv` (or `pip`):

```bash
git clone https://github.com/akhi-lbj/Supply-Chain-Multi-Agent-Orchestration.git
cd Supply-Chain-Multi-Agent-Orchestration
uv sync
```

Copy `.env.example` to `.env` and populate your API credentials:

```bash
cp .env.example .env
```

| Variable | Description |
| :--- | :--- |
| `IFM_API_KEY` | API key for IFM K2-Horizon (`IFM/K2-Horizon-375B-A23B`) |
| `IFM_API_BASE` | `https://api.ifm.ai/v1` |
| `LFM_API` | Liquid AI API key for `d1.1` decision guardrail (`https://api.liquid.ai/decisions`) |
| `DATABASE_URL` | PostgreSQL connection string (`postgresql://postgres:<password>@127.0.0.1:5432/nexus_control_tower`) |
| `LANGFUSE_SECRET_KEY` | *(Optional)* Langfuse OpenTelemetry tracing secret key |
| `LANGFUSE_PUBLIC_KEY` | *(Optional)* Langfuse OpenTelemetry tracing public key |

---

### 2. Initialize & Seed PostgreSQL

Ensure PostgreSQL is running locally, then run the automated seeding script to apply `scripts/init_control_tower_db.sql` and bulk-load the UAE retail dataset:

```bash
python scripts/seed_postgres.py
```

*(Note: If PostgreSQL is unavailable, `src/agents/db.py` automatically falls back to reading `data/synthetic/*.csv` so agents remain operational in offline environments.)*

---

### 3. Start the FastAPI Forecasting & Control Tower Server

Launch the FastAPI microservice on port `8000` (required by the Demand Forecasting Agent and REST Control Tower endpoints):

```bash
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Interactive Swagger docs are available at `http://127.0.0.1:8000/docs`.

---

### 4. Launch the Google ADK Web Interface

In a second terminal, start the interactive Google ADK Web UI on port `8080`:

```bash
adk web src --port 8080
```

Open `http://127.0.0.1:8080` in your browser, select the `agents` app, and submit a sample disruption notification:

> *"URGENT INCIDENT NOTIFICATION: Supplier SUP_01 has announced a 5-day supply delay affecting SKU_0001 at store STR_DXB_01. Please run the full disruption resolution protocol."*

---

## REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Health check and XGBoost artifact status |
| `POST` | `/forecast/disruption` | Execute 5-day Mean & P90 safety demand forecast for affected SKUs |
| `POST` | `/api/disruptions/trigger` | Trigger full multi-agent disruption analysis and generate ranked mitigation options |
| `GET` | `/api/disruptions` | List all active and historical disruption incidents and approval cards |
| `POST` | `/api/approvals/{approval_id}/action` | Approve, modify, or reject a proposed mitigation and commit PostgreSQL transactions |
