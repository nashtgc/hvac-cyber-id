"""Uvicorn entrypoint for the Grid Load Agent A2A server (port 10004)."""

import logging
import sys

import uvicorn
from dotenv import load_dotenv

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from app.agent import GridLoadAgent
from app.agent_executor import GridLoadAgentExecutor

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    host = "localhost"
    port = 10004

    try:
        capabilities = AgentCapabilities(streaming=True, pushNotifications=False)
        skill = AgentSkill(
            id="grid_load_lookup",
            name="NA Grid Load Lookup",
            description="Returns current electrical grid load in MW for supported North American Balancing Authorities (US RTO/ISO + Canadian ISO).",
            tags=["grid", "energy", "telemetry", "critical-infrastructure", "north-america", "us", "canada", "balancing-authority"],
            examples=[
                "What is the current grid load in PJM?",
                "Compare grid load between ERCOT and CAISO.",
                "Show load for AESO and IESO.",
            ],
        )
        agent_card = AgentCard(
            name="Grid Load Agent",
            description="Serves current grid-load telemetry (MW) for North American Balancing Authorities (US + Canada).",
            url=f"http://{host}:{port}/",
            version="0.1.0",
            defaultInputModes=GridLoadAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=GridLoadAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        request_handler = DefaultRequestHandler(
            agent_executor=GridLoadAgentExecutor(),
            task_store=InMemoryTaskStore(),
        )
        server = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
        uvicorn.run(server.build(), host=host, port=port)

    except Exception as e:
        logger.error(f"Grid Load Agent server failed to start: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
