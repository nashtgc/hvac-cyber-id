"""HTTP + A2A client wrapper for the worker connection.

Note: the httpx.AsyncClient is created per-call inside send_message rather than
at __init__ time. This is deliberate: the connection object is constructed at
module import time (inside the asyncio.run that builds root_agent), and any
AsyncClient created there is bound to that import-time loop. ADK web's serving
loop is a *different* loop, so a long-lived client would fail with "Future
attached to a different loop" or silent hangs. The cost is one new TCP
connection per worker call — acceptable for the demo's traffic profile.
"""

import httpx
from a2a.client import A2AClient
from a2a.types import AgentCard, SendMessageRequest, SendMessageResponse
from dotenv import load_dotenv

load_dotenv()


class RemoteAgentConnection:
    """Encapsulates A2A client construction pointed at one worker agent."""

    def __init__(self, agent_card: AgentCard, agent_url: str):
        self.card = agent_card
        self.agent_url = agent_url

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_message(self, message_request: SendMessageRequest) -> SendMessageResponse:
        async with httpx.AsyncClient(timeout=30) as client:
            a2a_client = A2AClient(client, self.card, url=self.agent_url)
            return await a2a_client.send_message(message_request)
