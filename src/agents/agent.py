# src/agents/agent.py
"""Standard Google ADK Entrypoint.

Exposes `root_agent` for ADK runtime, `agents-cli run`, and eval harnesses.
"""
from src.agents.supervisor_agent import supervisor_agent, root_agent

__all__ = ["root_agent", "supervisor_agent"]

