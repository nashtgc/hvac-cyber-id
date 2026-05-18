"""Host Agent (Google ADK) orchestrating the Grid Load Agent over A2A protocol.

Why no asyncio.run at module load: ADK web imports this module from inside its
own event loop, so a top-level `asyncio.run(...)` raises RuntimeError("cannot be
called from a running event loop") and yields a None root_agent. Instead, the
worker AgentCard fetch is lazy — it happens on the first send_message tool call,
inside whatever loop is actually serving the request.
"""

import json
import uuid
from datetime import datetime
from typing import Any, AsyncIterable

import httpx
from a2a.client import A2ACardResolver
from a2a.types import AgentCard, MessageSendParams, SendMessageRequest, SendMessageResponse
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .remote_agent_connection import RemoteAgentConnection

load_dotenv()

WORKER_URL = "http://localhost:10004"


class HostAgent:
    """Orchestrates grid-load telemetry retrieval by delegating to the Grid Load Agent."""

    def __init__(self, remote_agent_url: str = WORKER_URL):
        self.remote_agent_url = remote_agent_url
        self.remote_agent_connection: RemoteAgentConnection | None = None
        self.remote_agent_card: AgentCard | None = None
        self._agent = self.create_agent()
        self._user_id = "host_agent"
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    async def _ensure_connected(self) -> None:
        """Lazy worker discovery. Safe to call from any async context."""
        if self.remote_agent_connection is not None:
            return
        async with httpx.AsyncClient(timeout=30) as client:
            resolver = A2ACardResolver(client, self.remote_agent_url)
            card = await resolver.get_agent_card()
        self.remote_agent_card = card
        self.remote_agent_connection = RemoteAgentConnection(
            agent_card=card, agent_url=self.remote_agent_url
        )

    def create_agent(self) -> Agent:
        return Agent(
            model="gemini-2.5-flash",
            name="Host_Agent",
            instruction=self.root_instruction,
            description=(
                "Host Agent that orchestrates grid-load telemetry retrieval "
                "for North American Balancing Authorities by delegating to a worker Grid Load Agent over A2A."
            ),
            tools=[self.send_message],
        )

    def root_instruction(self, context: ReadonlyContext) -> str:
        if self.remote_agent_card is not None:
            agent_info = (
                f'{{"name": "{self.remote_agent_card.name}", '
                f'"description": "{self.remote_agent_card.description}"}}'
            )
        else:
            agent_info = (
                f'{{"name": "Grid Load Agent (not yet discovered)", '
                f'"description": "Worker at {self.remote_agent_url}; AgentCard fetched on first delegation."}}'
            )
        return f"""
        **Role:** You are the Host Agent for the hvac-cyber-id multi-agent demo.
        You coordinate grid-load telemetry retrieval by delegating to a worker Grid Load Agent.

        **Core Directives:**

        * **Understand Request:** Identify which North American Balancing Authority (or authorities)
          the user asks about. Supported BAs are US RTO/ISOs (PJM, MISO, ERCOT, CAISO, SPP, NYISO,
          ISO-NE) and Canadian ISOs (AESO, IESO).
        * **Delegate:** Use the `send_message` tool to ask the worker Grid Load Agent for the load
          in each named BA. Phrase the request plainly, e.g.,
          "What is the current grid load in PJM?".
        * **Aggregate:** Collect worker responses and present them as a clean bullet list or table.
        * **Be honest:** v1 returns mock telemetry. Mention "mock data" when the worker says so.
        * **Refuse out of scope:** If the query is not about NA grid load, politely decline
          and explain you only orchestrate grid-load telemetry retrieval for supported BAs.
        * **Tool reliance:** Only use `send_message`. Do not invent grid-load values.

        **Today (YYYY-MM-DD):** {datetime.now().strftime('%Y-%m-%d')}

        <Available Worker Agent>
        {agent_info}
        </Available Worker Agent>
        """

    async def stream(self, query: str, session_id: str) -> AsyncIterable[dict[str, Any]]:
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name, user_id=self._user_id, session_id=session_id,
        )
        content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name, user_id=self._user_id, state={}, session_id=session_id,
            )
        async for event in self._runner.run_async(
            user_id=self._user_id, session_id=session.id, new_message=content,
        ):
            if event.is_final_response():
                text = ""
                if event.content and event.content.parts and event.content.parts[0].text:
                    text = "\n".join([p.text for p in event.content.parts if p.text])
                yield {"is_task_complete": True, "content": text}
            else:
                yield {"is_task_complete": False, "updates": "Host Agent is delegating..."}

    async def send_message(self, task: str, tool_context: ToolContext):
        """Delegate a query to the worker Grid Load Agent over A2A.

        Note: taskId/contextId are NOT sent on the first call — the worker
        rejects requests that name a taskId it doesn't know about. We only
        attach them when continuing an established task (which the worker's
        TaskStore returns on the first response, persisted to ADK state).
        """
        await self._ensure_connected()
        assert self.remote_agent_connection is not None
        state = tool_context.state
        message_id = str(uuid.uuid4())

        msg: dict[str, Any] = {
            "role": "user",
            "parts": [{"type": "text", "text": task}],
            "messageId": message_id,
        }
        # Only re-use taskId/contextId if we've already established them.
        if state.get("task_id"):
            msg["taskId"] = state["task_id"]
        if state.get("context_id"):
            msg["contextId"] = state["context_id"]

        message_request = SendMessageRequest(
            id=message_id, params=MessageSendParams.model_validate({"message": msg})
        )
        send_response: SendMessageResponse = await self.remote_agent_connection.send_message(
            message_request
        )
        json_content = json.loads(send_response.root.model_dump_json(exclude_none=True))

        # Persist the task/context ids the worker returned, so a follow-up
        # tool call inside the same session can continue the same task.
        result = json_content.get("result") or {}
        if result.get("id"):
            state["task_id"] = result["id"]
        if result.get("contextId"):
            state["context_id"] = result["contextId"]

        # Extract text/data parts from completed artifacts.
        resp: list[dict[str, Any]] = []
        for artifact in result.get("artifacts") or []:
            for part in artifact.get("parts") or []:
                resp.append(part)
        return resp


# Synchronous module-level construction. No asyncio.run, no event loop required.
# The Agent object that ADK needs is created here; the worker AgentCard is
# fetched lazily on the first send_message call inside the serving loop.
_host_instance = HostAgent(remote_agent_url=WORKER_URL)
root_agent = _host_instance.create_agent()
