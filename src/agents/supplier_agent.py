# src/agents/supplier_agent.py
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
from src.agents.tools.supplier_tools import (
    evaluate_supplier_options,
    calculate_procurement_quote,
    supplier_eval_tool,
    procurement_quote_tool,
)

AGENT_SESSION_ID = create_session_id("nexus_supplier_agent")
k2_horizon_model = get_k2_horizon_model(AGENT_SESSION_ID)

# ------------------------------------------------------------------------------
# Supplier Intelligence Agent Definition
# ------------------------------------------------------------------------------
supplier_agent = Agent(
    name="supplier_intelligence_agent",
    description="Specialized agent that evaluates vendor reliability, lead times, and generates procurement quotes for backup suppliers.",
    mode="single_turn",
    model=k2_horizon_model,
    instruction=(
        "You are the NEXUS Supplier Intelligence Agent. You evaluate vendor reliability, "
        "lead times, SLA compliance, and procurement pricing. When primary suppliers face delays, "
        "you identify contracted backup suppliers, compare expedited versus standard delivery options, "
        "and provide costed purchase order quotes."
    ),
    tools=[supplier_eval_tool, procurement_quote_tool]
)

# ------------------------------------------------------------------------------
# Standalone Execution Harness
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    test_query = (
        "Evaluate backup suppliers for SKU_0001 when primary supplier SUP_01 is delayed. "
        "Get a procurement quote for 30 units."
    )
    print(f"Triggering ADK Supplier Agent run [Session: {AGENT_SESSION_ID}]...")
    runner = InMemoryRunner(agent=supplier_agent)
    runner.auto_create_session = True
    user_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=test_query)]
    )

    print("\n--- Agent Execution Flow ---")
    final_response = []
    for event in runner.run(
        user_id="nexus_procurement_lead",
        session_id=AGENT_SESSION_ID,
        new_message=user_message
    ):
        print_event(event, verbose=True)
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text and not getattr(part, "thought", False):
                    final_response.append(part.text)

    synthesis = "".join(final_response).strip()
    print("\n=================== SUPPLIER QUOTE & EVALUATION ===================")
    print(synthesis)
