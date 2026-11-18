# src/agents/supervisor_agent.py
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner, print_event
from google.genai import types

from src.agents.config import get_k2_horizon_model, create_session_id
from src.agents.demand_agent import demand_forecasting_agent
from src.agents.inventory_agent import inventory_agent
from src.agents.supplier_agent import supplier_agent
from src.agents.decision_callback import liquid_prompt_injection_guardrail

SUPERVISOR_SESSION_ID = create_session_id("nexus_supervisor_run")
k2_horizon_model = get_k2_horizon_model(SUPERVISOR_SESSION_ID)

supervisor_instruction = """
You are the NEXUS Control Tower Supervisor Agent. You lead the autonomous resolution of supply chain disruptions.

When a disruption notification is received (e.g., supplier delay):
1. Query `demand_forecasting_agent` to forecast 5-day demand and determine the P90 stockout risk and deficit.
2. Query `inventory_agent` to audit on-hand store inventory and check central warehouse surplus (DC_JAFZA, DC_AL_QUOZ, DC_DIC).
3. Query `supplier_intelligence_agent` to evaluate alternative suppliers, lead times, and expedited emergency PO quotes.
4. SYNTHESIZE all findings into a structured operational decision briefing with:
   - Disruption Summary (SKU, delayed vendor, affected stores, delay duration)
   - Operational Deficit (Store on-hand stock vs P90 5-day demand vs Shortage units)
   - Recovery Strategy Comparison:
     * Scenario A: Emergency Warehouse Transfer (lead time, warehouse origin, logistics viability)
     * Scenario B: Alternate Supplier Emergency Purchase Order (cost, lead time, vendor reliability)
   - Recommended Action (Justify cost vs speed)
   - Action Approval Card: Explicitly state the exact action pending Supply Chain Manager sign-off.
"""

# ------------------------------------------------------------------------------
# Supervisor (Root) Agent Definition
# ------------------------------------------------------------------------------
supervisor_agent = Agent(
    name="supervisor_agent",
    description="Central NEXUS Control Tower supervisor orchestrating autonomous supply chain disruption resolution.",
    model=k2_horizon_model,
    instruction=supervisor_instruction,
    sub_agents=[
        demand_forecasting_agent.clone(),
        inventory_agent.clone(),
        supplier_agent.clone(),
    ],
    before_model_callback=liquid_prompt_injection_guardrail
)

# Standard ADK convention
root_agent = supervisor_agent

# ------------------------------------------------------------------------------
# Standalone Execution Harness
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    disruption_alert = (
        "INCIDENT NOTIFICATION: Supplier SUP_01 (Al Ain Farms) has announced a 5-day delay on a shipment "
        "of 500 units of SKU_0001 destined for store STR_DXB_01 (Dubai Mall Flagship). "
        "Investigate the operational impact, determine stockout severity, analyze warehouse transfer availability, "
        "evaluate backup suppliers, and recommend the optimal recovery plan."
    )

    print(f"Triggering Full Multi-Agent NEXUS Disruption Protocol [Session: {SUPERVISOR_SESSION_ID}]...\n")
    runner = InMemoryRunner(agent=supervisor_agent)
    runner.auto_create_session = True
    user_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=disruption_alert)]
    )

    print("\n--- Multi-Agent Execution Flow ---")
    final_response = []
    for event in runner.run(
        user_id="nexus_operations_lead",
        session_id=SUPERVISOR_SESSION_ID,
        new_message=user_message
    ):
        print_event(event, verbose=True)
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text and not getattr(part, "thought", False):
                    final_response.append(part.text)

    briefing = "".join(final_response).strip()
    print("\n======================= NEXUS EXECUTIVE BRIEFING =======================")
    print(briefing)
