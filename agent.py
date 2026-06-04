"""Game play agent using Microsoft Agent Framework with Azure OpenAI."""

import asyncio
import json
import os
from pathlib import Path

from agent_agent42 import build_agent42_tool
from agent_city_guide import build_city_guide_tool
from agent_framework import Agent, ContextProvider, MCPStreamableHTTPTool, tool
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv
from log import build_logging_middleware, open_session_log

MEMORY_FILE = Path("memory.json")

load_dotenv(override=True)


class PlayerContextProvider(ContextProvider):
    async def before_run(self, *, agent, session, context, state) -> None:
        if MEMORY_FILE.exists():
            pid = json.loads(MEMORY_FILE.read_text()).get("player_id")
            if pid:
                context.extend_instructions(
                    self.source_id,
                    f"From memory: player_id: {pid}",
                )


@tool(description="Save the player_id returned after registration")
async def save_player_id(player_id: str) -> str:
    MEMORY_FILE.write_text(json.dumps({"player_id": player_id}))
    return f"Player ID {player_id} saved."


async def main() -> None:
    client = OpenAIChatClient(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        model=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
    )

    game_mcp = MCPStreamableHTTPTool(
        name="Gaming MCP Server",
        url=os.environ["GAME_MCP_URL"],
    )
    await game_mcp.connect()

    city_guide_search = None
    try:
        game_play_prompt = await game_mcp.get_prompt("game_play_prompt")
        log_path = open_session_log()
        print(f"Session log: {log_path}")
        agent_mw, chat_mw, function_mw = build_logging_middleware(log_path)
        agent42_tool = build_agent42_tool()
        guide_tool, city_guide_search = build_city_guide_tool()

        agent = Agent(
            client=client,
            name="Game Play Agent",
            instructions=game_play_prompt,
            tools=[game_mcp, save_player_id, agent42_tool, guide_tool],
            context_providers=[PlayerContextProvider(source_id="player-memory")],
            middleware=[agent_mw, chat_mw, function_mw],
        )

        print("Chat with Game Play Agent (type 'exit' or 'quit' to stop)\n")
        session = agent.create_session()
        response = await agent.run("start the game", session=session)
        print(f"Agent: {response.text}\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit"}:
                break
            response = await agent.run(user_input, session=session)
            print(f"Agent: {response.text}\n")
    finally:
        await game_mcp.close()
        if city_guide_search:
            await city_guide_search.close()


if __name__ == "__main__":
    asyncio.run(main())