"""Grid Load Agent: LangGraph worker agent serving mock grid-load telemetry.

Part of the hvac-cyber-id multi-agent A2A demo. Pivoted from the Google A2A
codelab Stock Info Agent template. Mock data only; v2 will wire EIA Open Data
(US RTO/ISO) and AESO/IESO public feeds (Canadian ISOs).
"""

import random
from collections.abc import AsyncIterable
from datetime import datetime
from typing import Any, Literal

import pandas as pd
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

memory = MemorySaver()

# North American Balancing Authorities the agent serves.
# US RTO/ISO + Canadian ISO operators that publish hourly load data.
BALANCING_AUTHORITIES = [
    "PJM",           # PJM Interconnection (13 US states + DC)
    "MISO",          # Midcontinent ISO (15 US states + Manitoba)
    "ERCOT",         # Electric Reliability Council of Texas
    "CAISO",         # California ISO
    "SPP",           # Southwest Power Pool
    "NYISO",         # New York ISO
    "ISO-NE",        # ISO New England
    "AESO",          # Alberta Electric System Operator (Canada)
    "IESO",          # Ontario Independent Electricity System Operator (Canada)
]

# Mock hourly grid load in MW. v1 = synthetic only.
# Ranges grounded in EIA Open Data hourly demand averages (US BAs) and
# AESO/IESO public dashboards (Canadian ISOs). See docs/data.md.
_MW_RANGES = {
    "PJM":     (65_000, 145_000),
    "MISO":    (65_000, 130_000),
    "ERCOT":   (35_000, 85_000),
    "CAISO":   (22_000, 50_000),
    "SPP":     (25_000, 55_000),
    "NYISO":   (16_000, 32_000),
    "ISO-NE":  (12_000, 26_000),
    "AESO":    (9_500, 12_500),
    "IESO":    (12_000, 25_000),
}


def _mock_load(ba: str) -> float:
    low, high = _MW_RANGES[ba]
    return round(random.uniform(low, high), 1)


mock_grid_data = pd.DataFrame({
    "balancing_authority": BALANCING_AUTHORITIES,
    "current_load_mw": [_mock_load(ba) for ba in BALANCING_AUTHORITIES],
    "as_of_utc": [datetime.utcnow().isoformat(timespec="seconds") + "Z"] * len(BALANCING_AUTHORITIES),
})


@tool
def get_grid_load_by_balancing_authority(ba: str) -> str:
    """Return the current grid load in MW for a supported North American Balancing Authority.

    Args:
        ba: The BA code (e.g., 'PJM', 'ERCOT', 'CAISO', 'AESO', 'IESO').

    Returns:
        A human-readable string with the current load and as-of timestamp,
        or an error message if the BA is unsupported.
    """
    try:
        ba = ba.upper().strip()
        if ba not in BALANCING_AUTHORITIES:
            return (
                f"'{ba}' is not in the supported North American Balancing Authority list. "
                f"Supported BAs: {', '.join(BALANCING_AUTHORITIES)}."
            )
        row = mock_grid_data[mock_grid_data["balancing_authority"] == ba].iloc[0]
        return (
            f"Current grid load in {ba}: {row['current_load_mw']} MW "
            f"(as of {row['as_of_utc']}, mock data)."
        )
    except Exception as e:
        return f"Error fetching grid load: {e}"


class ResponseFormat(BaseModel):
    """Structured response for A2A executor."""
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


class GridLoadAgent:
    """LangGraph worker that returns current grid-load telemetry for North American Balancing Authorities."""

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    SYSTEM_INSTRUCTION = (
        "You are a grid-load telemetry assistant for North American Balancing Authorities "
        "(US RTO/ISOs and Canadian ISOs). "
        "Your sole purpose is to use the 'get_grid_load_by_balancing_authority' tool to answer "
        "queries about current electrical grid load (MW) for supported BAs. "
        "Respond only to grid-load queries for valid BAs in the supported list. "
        "If the user asks about an unsupported BA or an unrelated topic, politely "
        "decline and remind them you only serve grid-load queries for supported NA Balancing Authorities. "
        "Do not invent grid-load values. Always call the tool. "
        "Set response status to 'input_required' if the user must clarify a BA. "
        "Set response status to 'error' on tool failure. "
        "Set response status to 'completed' on a successful lookup."
    )

    def __init__(self):
        self.model = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
        self.tools = [get_grid_load_by_balancing_authority]
        self.graph = create_react_agent(
            self.model,
            tools=self.tools,
            checkpointer=memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=ResponseFormat,
        )

    def invoke(self, query: str, context_id: str):
        config: RunnableConfig = {"configurable": {"thread_id": context_id}}
        self.graph.invoke({"messages": [("user", query)]}, config)
        return self.get_agent_response(config)

    async def stream(self, query: str, context_id: str) -> AsyncIterable[dict[str, Any]]:
        inputs = {"messages": [("user", query)]}
        config: RunnableConfig = {"configurable": {"thread_id": context_id}}

        for item in self.graph.stream(inputs, config, stream_mode="values"):
            message = item["messages"][-1]
            if isinstance(message, AIMessage) and message.tool_calls:
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": "Querying grid-load telemetry...",
                }
            elif isinstance(message, ToolMessage):
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": "Aggregating grid-load reading...",
                }

        yield self.get_agent_response(config)

    def get_agent_response(self, config):
        state = self.graph.get_state(config)
        sr = state.values.get("structured_response")
        if sr and isinstance(sr, ResponseFormat):
            if sr.status == "completed":
                return {"is_task_complete": True, "require_user_input": False, "content": sr.message}
            return {"is_task_complete": False, "require_user_input": True, "content": sr.message}
        return {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "Unable to process grid-load query. Please specify a supported NA Balancing Authority (e.g., PJM, ERCOT, CAISO).",
        }
