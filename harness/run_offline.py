"""Run the REAL agent.py against the fake backends. Repo code is not modified.

Isolation: cwd is harness/work, so memory.json lands there (not your real one),
and log.LOGS_DIR is redirected so session logs land in harness/work/logs.
Only the Azure AI Search provider is swapped for a stub that retrieves from SF_Guide.pdf.
"""

from __future__ import annotations

import asyncio
import os
import sys
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore")

HARNESS = Path(__file__).resolve().parent
REPO = Path(os.environ.get("LOST_IN_SF_REPO", HARNESS.parent))  # the harness lives inside the repo
WORK = HARNESS / "work"
WORK.mkdir(exist_ok=True)
os.chdir(WORK)

PORT_BASE = int(os.environ.get("HARNESS_PORT_BASE", "8801"))
USE_FOUNDRY = "--foundry" in sys.argv

# --foundry: real models from Microsoft Foundry, read from harness/.env.foundry (git-ignored).
# Without it, the same four variables point at the fake model server.
MODEL_VARS = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "CITY_GUIDE_AZURE_OPENAI_DEPLOYMENT_NAME",
)
if USE_FOUNDRY:
    from dotenv import dotenv_values

    foundry = {k: v for k, v in dotenv_values(HARNESS / ".env.foundry").items() if v}
    missing = [k for k in MODEL_VARS if k not in foundry]
    if missing:
        sys.exit(f"[harness] harness/.env.foundry is missing: {', '.join(missing)}")
    model_env = {k: foundry[k] for k in MODEL_VARS}
    print(f"[harness] REAL models: {model_env['AZURE_OPENAI_ENDPOINT']}")
else:
    model_env = dict(
        AZURE_OPENAI_ENDPOINT=f"http://127.0.0.1:{PORT_BASE + 2}",
        AZURE_OPENAI_API_KEY="fake-key",
        AZURE_OPENAI_DEPLOYMENT_NAME="fake-main-model",
        CITY_GUIDE_AZURE_OPENAI_DEPLOYMENT_NAME="fake-guide-model",
    )
os.environ.update(
    model_env,
    GAME_MCP_URL=f"http://127.0.0.1:{PORT_BASE}/mcp",
    AGENT42_URL=f"http://127.0.0.1:{PORT_BASE + 1}/",
    AZURE_SEARCH_ENDPOINT="http://unused",
    AZURE_SEARCH_KEY="unused",
    AZURE_SEARCH_KNOWLEDGE_BASE_NAME="unused",
)

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HARNESS))

import agent_city_guide  # noqa: E402
import log  # noqa: E402
from agent_framework import ContextProvider  # noqa: E402
from sf_world import load_guide_sentences, rank_sentences  # noqa: E402

log.LOGS_DIR = WORK / "logs"
GUIDE = load_guide_sentences(HARNESS / "data" / "sf_guide.txt")


class FakeSearchProvider(ContextProvider):
    """Stands in for AzureAISearchContextProvider: retrieves guide sentences for the question."""

    def __init__(self, **_: Any) -> None:
        super().__init__(source_id="fake-search")

    async def before_run(self, *, agent: Any, session: Any, context: Any, state: Any) -> None:
        query = " ".join(
            "".join(getattr(c, "text", "") or "" for c in message.contents)
            for message in context.input_messages
        )
        hits = rank_sentences(query, GUIDE, top=3)
        if hits:
            context.extend_instructions(
                self.source_id, "Search context:\n" + "\n".join(f"- {s}" for s in hits)
            )

    async def close(self) -> None:
        return None


agent_city_guide.AzureAISearchContextProvider = FakeSearchProvider  # type: ignore[misc]

import agent  # noqa: E402

if __name__ == "__main__":
    print("[harness] commands: START, HELP (Agent42 or city guide), HINT, STATUS, NEW, exit")
    model_note = "models are real (Foundry)" if USE_FOUNDRY else "fake model follows fixed rules"
    print(f"[harness] {model_note}; weather is live from Open-Meteo.com\n")
    asyncio.run(agent.main())
