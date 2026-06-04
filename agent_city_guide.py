"""City guide specialist agent for San Francisco knowledge-base questions."""

import asyncio
import os

from agent_framework import Agent
from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv


def build_city_guide_agent():
    client = OpenAIChatClient(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        model=os.environ["CITY_GUIDE_AZURE_OPENAI_DEPLOYMENT_NAME"],
    )

    # Search context belongs here, so the main game agent does not spend RAG tokens on every turn.
    search_context_provider = AzureAISearchContextProvider(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        knowledge_base_name=os.environ["AZURE_SEARCH_KNOWLEDGE_BASE_NAME"],
        api_key=os.environ["AZURE_SEARCH_KEY"],
        mode="agentic",
    )

    guide_agent = Agent(
        client=client,
        name="San Francisco City Guide Agent",
        instructions=(
            "Answer San Francisco city guide questions using the provided search context. "
            "Keep answers brief and return only the answer needed by the game."
        ),
        context_providers=[search_context_provider],
    )
    return guide_agent, search_context_provider


def build_city_guide_tool():
    guide_agent, search_context_provider = build_city_guide_agent()

    # The main game agent calls this tool only for city guide questions.
    guide_tool = guide_agent.as_tool(
        name="ask_city_guide",
        description=(
            "Ask the San Francisco city guide knowledge base a question."
        ),
        arg_name="question",
        arg_description="The city guide question to answer.",
    )
    return guide_tool, search_context_provider


async def main() -> None:
    load_dotenv(override=True)

    question = "What is the name of the cocktail bar that was founded in 1907?"
    guide_agent, search_context_provider = build_city_guide_agent()

    try:
        response = await guide_agent.run(question)
        print(response.text)
    finally:
        await search_context_provider.close()


if __name__ == "__main__":
    asyncio.run(main())