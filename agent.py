"""Game play agent using Microsoft Agent Framework, Azure OpenAI, and MCP."""

import asyncio
import os

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

load_dotenv(override=True)


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

    try:
        game_play_prompt = await game_mcp.get_prompt("game_play_prompt")

        agent = Agent(
            client=client,
            name="Game Play Agent",
            instructions=game_play_prompt,
            tools=[game_mcp],
        )

        session = agent.create_session()
        response = await agent.run("start the game", session=session)
        print(response.text)
    finally:
        await game_mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
