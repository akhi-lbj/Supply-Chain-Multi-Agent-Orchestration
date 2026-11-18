# src/agents/config.py
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
import litellm
from google.adk.models.lite_llm import LiteLlm
import google.adk.models.lite_llm as _lite_llm_mod

# Locate project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SYNTHETIC_DATA_DIR = PROJECT_ROOT / "data" / "synthetic"

# Load environment configuration from .env
load_dotenv(find_dotenv())

# Observability via Langfuse OpenTelemetry
litellm.success_callback = ["langfuse_otel"]
litellm.failure_callback = ["langfuse_otel"]

# ------------------------------------------------------------------------------
# Patch Google ADK LiteLLM for IFM K2-Horizon Multi-Turn Reasoning Compliance
# IFM requires a 'reasoning_content' field on each assistant turn in history.
# ------------------------------------------------------------------------------
_orig_assistant_message = _lite_llm_mod._assistant_message


def _ifm_compatible_assistant_message(
    *,
    content,
    tool_calls=None,
    reasoning_content=None,
    thinking_blocks=None
):
    if not reasoning_content:
        reasoning_content = "Step-by-step operational reasoning completed."
    return _orig_assistant_message(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=reasoning_content,
        thinking_blocks=thinking_blocks,
    )


_lite_llm_mod._assistant_message = _ifm_compatible_assistant_message


def create_session_id(prefix: str = "nexus") -> str:
    """Generates a stable unique session ID for agent runs."""
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def get_k2_horizon_model(session_id: str | None = None) -> LiteLlm:
    """Configures and returns the LiteLLM K2 Horizon endpoint instance."""
    session = session_id or create_session_id("nexus_run")
    return LiteLlm(
        model=f"openai/{os.getenv('IFM_MODEL', 'IFM/K2-Horizon-375B-A23B')}",
        api_base=os.getenv("IFM_API_BASE", "https://api.ifm.ai/v1"),
        api_key=os.getenv("IFM_API_KEY"),
        extra_headers={"X-Session-ID": session},
        chat_template_kwargs={"reasoning_effort": "high"}
    )
