"""Agent42 transport specialist tool for movement missions."""

import asyncio
import os
import uuid

import httpx
from agent_framework import tool
from dotenv import load_dotenv

load_dotenv(override=True)


async def _call_agent42(question: str) -> str:
    """Call Agent42 using the A2A message/send JSON-RPC protocol."""
    url = os.environ["AGENT42_URL"].rstrip("/")
    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": str(uuid.uuid4()),
        "params": {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [{"kind": "text", "text": question}],
            }
        },
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    result = data.get("result", {})
    for part in result.get("parts", []):
        if part.get("kind") == "text":
            return part["text"]
    return str(result)


def build_agent42_tool():
    @tool(description=(
        "Ask Agent42 for the best way to get from one place to another. "
        "Pass a full natural-language question including origin and destination."
    ))
    async def ask_agent42(question: str) -> str:
        """The transport question to send to Agent42."""
        return await _call_agent42(question)

    return ask_agent42


async def main() -> None:
    question = "What is the best way to get from the Ferry Building to Golden Gate Park?"
    result = await _call_agent42(question)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
