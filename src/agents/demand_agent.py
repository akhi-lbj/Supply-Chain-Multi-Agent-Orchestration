# src/agents/demand_agent.py
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
from src.agents.tools.demand_tools import query_fastapi_disruption_service, forecast_tool

AGENT_SESSION_ID = create_session_id("nexus_disruption_run")
k2_horizon_model = get_k2_horizon_model(AGENT_SESSION_ID)

# ------------------------------------------------------------------------------
# Demand Forecasting Agent Definition
# ------------------------------------------------------------------------------
demand_forecasting_agent = Agent(
    name="demand_forecasting_agent",
    description="Specialized agent that forecasts 5-day cumulative demand and calculates P90 safety stock deficits during supply chain disruptions.",
    mode="single_turn",
    model=k2_horizon_model,
    instruction=(
        "You are the NEXUS Demand Forecasting Agent. When a supplier disruption occurs, "
        "inspect the affected product and store, trigger the forecasting tool to retrieve "
        "expected demand and P90 safety buffers, and report whether a stockout risk exists."
    ),
    tools=[forecast_tool]
)

# ------------------------------------------------------------------------------
# Standalone Execution Harness
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    disruption_event = (
        "Supplier SUP_01 reported a 5-day shipment delay for HOBBIES_1_004 to store CA_3. "
        "Current store inventory is 10 units. Evaluate the disruption impact."
    )
    
    print(f"Triggering ADK Agent run [Session: {AGENT_SESSION_ID}]...")
    runner = InMemoryRunner(agent=demand_forecasting_agent)
    runner.auto_create_session = True
    user_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=disruption_event)]
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

    print("\nAgent Synthesis:\n", "".join(final_response).strip())
