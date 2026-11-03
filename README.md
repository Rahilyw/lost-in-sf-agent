# Lost in SF: AI Quest Agent

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Azure OpenAI](https://img.shields.io/badge/Azure_OpenAI-gpt--5.5-0078D4?logo=microsoft-azure&logoColor=white)
![Microsoft Agent Framework](https://img.shields.io/badge/Microsoft_Agent_Framework-1.7-5C2D91?logo=microsoft&logoColor=white)
![MCP](https://img.shields.io/badge/Protocol-MCP-FF6B35)
![A2A](https://img.shields.io/badge/Protocol-A2A-00B4D8)

A production-pattern AI agent that autonomously plays a city navigation quest — reasoning through missions, coordinating specialist sub-agents, and retrieving grounded knowledge from a vector search index.

Built at **Microsoft Build 2026** as a hands-on demonstration of four agentic patterns: **MCP, A2A, RAG, and persistent memory**.

---

## The Problem It Solves

Modern AI agents need more than a language model. They need to:
- **Act on external state** - not just chat, but operate tools that change the world
- **Delegate to specialists** - call other agents instead of reimplementing their logic
- **Answer from trusted sources** - retrieve grounded facts rather than hallucinate
- **Persist across sessions** - remember who they are between runs

This project demonstrates all four patterns working together in a single agent!!

---

## How It Works

The agent is dropped into San Francisco with one goal: reach Fort Mason before Build starts. It navigates the city by solving missions; each one either a transport decision or a city knowledge question.

```
┌─────────────────────────────────────────────────────┐
│                   Game Play Agent                    │
│                   (agent.py)                         │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │   MCP    │  │   A2A    │  │      RAG         │  │
│  │  Game    │  │ Agent42  │  │  City Guide      │  │
│  │  Server  │  │Transport │  │  Azure AI Search │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
│                                                      │
│  + Memory (player ID across runs)                    │
│  + Middleware (full session logging)                 │
└─────────────────────────────────────────────────────┘
```

### 1 — MCP (Model Context Protocol)
The agent connects to the game server as an MCP client. The game exposes its actions (start session, submit answer, advance mission) as MCP tools, and even serves the agent's system prompt over MCP — so the game and agent stay in sync automatically.

### 2 — A2A (Agent-to-Agent)
When the game asks *"car, bike, or walking?"*, the agent doesn't guess — it calls **Agent42**, a deployed peer agent, over the A2A protocol. Agent42 checks live weather and real-time traffic, computes all three routes, and returns a recommendation with a map link.

### 3 — RAG (Retrieval-Augmented Generation)
When the game asks a San Francisco trivia question, a city guide specialist agent queries an **Azure AI Search** knowledge base over the SF city guide. Answers are grounded in the actual source material, not model memory.

### 4 — Memory + Logging
A `ContextProvider` reads `memory.json` and injects the player ID into the agent's instructions before every turn — so the agent resumes the same session across restarts. Every model call, tool call, and response is captured in a timestamped log file for full observability.

---

## Demo

```
Chat with Game Play Agent (type 'exit' or 'quit' to stop)

Agent: We found player_id PLR-760E28 for Rahil. Do you want to START?

You: START
Agent: You wake up outside a taqueria on Valencia Street...
       What transport will you take: car, walking, or bike?

You: HELP
Agent: Weather: 19°C, clear sky, breezy

       Options:
       Car:     1.2 miles, 10 min + 5 min pickup wait
       Bike:    1.0 miles, 5 min
       Walking: 1.0 miles, 18 min

       Reasoning: Bike is fastest — dry weather, short trip, no pickup wait.
       Recommendation: bike

You: bike
Agent: You reach Hayes Valley. The vintage shop owner slides over a city
       guide. "Find the cocktail bar described as a neighborhood cocktail
       bar done right."

You: HELP
Agent: ABV on Valencia Street is described as a neighborhood cocktail bar done right.

You: ABV
Agent: Correct. Now get to Fort Mason — what transport will you take?
```

---

## Project Structure

```
.
├── agent.py              # Main game play agent — orchestrates all tools
├── agent_agent42.py      # Agent42 A2A client — transport recommendations
├── agent_city_guide.py   # City guide RAG specialist — Azure AI Search
├── log.py                # Session logging middleware
├── harness/              # Runs the agent without the lab: local game, Agent42, retrieval, Foundry mode
├── SF_Guide.pdf          # City guide the harness missions and retrieval are built from
├── .env                  # Secrets (never committed)
├── .gitignore
└── logs/                 # Per-session log files (never committed)
```

---

## Setup

### Prerequisites
- Python 3.10+
- Azure OpenAI (`gpt-5.5` and `gpt-4.1-mini` deployments)
- Azure AI Search knowledge base with San Francisco city guide content

### Install
```bash
pip install agent-framework python-dotenv httpx
```

### Configure `.env`
```env
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5.5
CITY_GUIDE_AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1-mini

GAME_MCP_URL=https://mcp.workshop.agentcon.dev/san-francisco/mcp
AGENT42_URL=https://agent42.workshop.agentcon.dev/

AZURE_SEARCH_ENDPOINT=https://<your-search>.search.windows.net
AZURE_SEARCH_KEY=<your-query-key>
AZURE_SEARCH_KNOWLEDGE_BASE_NAME=city-knowledgebase
```

### Run
```bash
python agent.py
```

Type `HELP` during any mission to trigger the specialist agents. Type `exit` to stop.

---

## Run It Without the Lab

The lab's game server, Agent42 and search index were hosted by Microsoft and are gone. The [`harness/`](harness/) folder replaces them so the **real, unmodified** `agent.py` still runs end to end:

| Lab piece | Harness replacement |
|---|---|
| Game MCP server | Local FastMCP server: 7 missions built from `SF_Guide.pdf` (landmarks, GPS, opening years, beach safety) |
| Agent42 (A2A) | Local A2A server that routes with haversine distance and **live weather from [Open-Meteo](https://open-meteo.com/)** (no API key), so rain flips the best transport from bike to car |
| Azure AI Search | Local retriever over the guide text (the Azure provider is swapped out) |
| Azure OpenAI | Either a rule-based fake model, or **real Microsoft Foundry models** with `--foundry` |

```bash
python -W ignore harness/fake_backends.py              # terminal 1: game server + Agent42
python -W ignore harness/run_offline.py                # terminal 2: offline, fake model
python -W ignore harness/run_offline.py --foundry      # terminal 2: real Foundry models
```

`--foundry` reads `harness/.env.foundry` (git-ignored; endpoint, key and deployment names). State, memory and logs go to `harness/work/`, so your real `memory.json` and `logs/` are never touched. Setup, the live-demo script and the Agent42 failure modes are in [`harness/README.md`](harness/README.md).

### Demo it on real Foundry models

You need `harness/.env.foundry` with `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT_NAME` and `CITY_GUIDE_AZURE_OPENAI_DEPLOYMENT_NAME` ([how to create it](harness/README.md#foundry-setup)). Run everything from the repo root.

1. **Optional: reset to a fresh game.** Clears the saved player and progress so the demo starts with registration:
   ```bash
   rm -f harness/work/memory.json harness/work/game_state.json
   ```
2. **Terminal 1: start the fake backends.** Wait for `fake backends up: mcp:8801  agent42:8802  model:8803`.
   ```bash
   python -W ignore harness/fake_backends.py
   ```
3. **Terminal 2: start the agent on Foundry.** You should see `[harness] REAL models: https://...`, then the agent asks your name (or welcomes you back).
   ```bash
   python -W ignore harness/run_offline.py --foundry
   ```
4. **Play the demo.** A good order: give your name → `exit` and rerun to show memory → `HELP` (Agent42 over A2A, live weather) → `bike` → `HELP` (city guide over RAG) → a wrong answer, `HINT`, then `1922`. Then open `harness/work/logs/session-*.log` to show the logged tool calls. The full talk track is in [`harness/README.md`](harness/README.md#live-demo-script-about-5-minutes---foundry).

Commands: `START`, `HELP`, `HINT`, `STATUS`, `NEW`, or type an answer. `exit` quits.

**If something goes wrong**
- `harness/.env.foundry is missing: ...`: one of the four variables is empty.
- Traceback on an auth or quota error: model-service errors are not caught, so the app exits. Check the key and that the Foundry resource and deployment still exist.
- Ports in use: set the same `HARNESS_PORT_BASE` (for example `9801`) in both terminals.
- Wrong endpoint used: a `.env` in the repo root overrides `.env.foundry`, because `agent.py` calls `load_dotenv(override=True)`. Move it aside first.
- To show rain flipping the recommendation from bike to car, start terminal 1 with `HARNESS_FORCE_RAIN=1`.
- The model is not deterministic, so rehearse once. Keep the offline mode (`run_offline.py` with no flag) as a fallback.

---

## Session Logs

Every run produces a structured log in `logs/` showing the full reasoning chain. This excerpt is from a real run on Foundry (`gpt-4.1-mini`):

```
[16:21:10] USER ->
[user] HELP

[16:21:10] MODEL INPUT (post context providers) ->
[user] HELP

[16:21:12] TOOL CALL  ask_agent42
{"question": "What is the fastest way to get from Mission Dolores to Castro Theatre today given the weather, using walk, bike, or car?"}

[16:21:16] TOOL RESULT ask_agent42
Weather at Mission Dolores: overcast, 17C, wind 1 km/h, rain 0.0 mm (live, Open-Meteo.com). ... Recommendation: bike

[16:21:21] AGENT <-
The fastest way ... is by bike. ... Which transport do you choose? Car, walking, or bike?
```

`MODEL INPUT` is logged once per `agent.run`, and shows the messages the player sent. The system prompt and the memory injected by the `ContextProvider` are not in it.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent framework | [Microsoft Agent Framework 1.7](https://github.com/microsoft/agent-framework) |
| LLM | Azure OpenAI gpt-5.5 / gpt-4.1-mini |
| Tool protocol | MCP (Model Context Protocol) |
| Agent protocol | A2A (Agent-to-Agent) |
| Knowledge retrieval | Azure AI Search (Foundry IQ) |
| Memory | JSON file + ContextProvider |
| Observability | Custom middleware (agent, chat, function hooks) |

---

*Built at Microsoft Build 2026 — LAB530D: Engineering Agents that Reason, Act, and Adapt*
