# src/agents/inventory_agent.py
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
from src.agents.tools.inventory_tools import (
    get_inventory_balances,
    check_warehouse_transfer_availability,
    inventory_balance_tool,
    warehouse_transfer_tool,
)

AGENT_SESSION_ID = create_session_id("nexus_inv_agent")
k2_horizon_model = get_k2_horizon_model(AGENT_SESSION_ID)

# ------------------------------------------------------------------------------
# Inventory Agent Definition
# ------------------------------------------------------------------------------
inventory_agent = Agent(
    name="inventory_agent",
    description="Specialized agent that audits store inventory balances, net free stock, and warehouse safety stock for emergency transfers.",
    mode="single_turn",
    model=k2_horizon_model,
    instruction=(
        "You are the NEXUS Inventory Agent. Your responsibility is to inspect "
        "on-hand inventory, net free stock, and warehouse safety stock across UAE "
        "stores and distribution centers. You evaluate store-level stockout deficits "
        "and determine whether central warehouses (DC_JAFZA, DC_AL_QUOZ, DC_DIC) "
        "can support emergency stock transfers."
    ),
    tools=[inventory_balance_tool, warehouse_transfer_tool]
)

# ------------------------------------------------------------------------------
# Standalone Execution Harness
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    test_query = (
        "Check stock levels for SKU_0001 at store STR_DXB_01 and verify if "
        "regional distribution centers have 25 surplus units to transfer."
    )
    print(f"Triggering ADK Inventory Agent run [Session: {AGENT_SESSION_ID}]...")
    runner = InMemoryRunner(agent=inventory_agent)
    runner.auto_create_session = True
    user_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=test_query)]
    )

    print("\n--- Agent Execution ---")
    final_response = []
    for event in runner.run(
        user_id="nexus_operator",
        session_id=AGENT_SESSION_ID,
        new_message=user_message
    ):
        print_event(event, verbose=True)
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text and not getattr(part, "thought", False):
                    final_response.append(part.text)

    print("\nInventory Agent Output:\n", "".join(final_response).strip())
