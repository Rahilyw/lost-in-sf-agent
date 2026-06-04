# Lost in SF — AI Quest Agent

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Azure OpenAI](https://img.shields.io/badge/Azure_OpenAI-gpt--5.5-0078D4?logo=microsoft-azure&logoColor=white)
![Microsoft Agent Framework](https://img.shields.io/badge/Microsoft_Agent_Framework-1.7-5C2D91?logo=microsoft&logoColor=white)
![MCP](https://img.shields.io/badge/Protocol-MCP-FF6B35)
![A2A](https://img.shields.io/badge/Protocol-A2A-00B4D8)
![Built at Microsoft Build 2026](https://img.shields.io/badge/Microsoft_Build_2026-LAB530D-FFB900?logo=microsoft&logoColor=white)

A production-pattern AI agent that autonomously plays a city navigation quest — reasoning through missions, coordinating specialist sub-agents, and retrieving grounded knowledge from a vector search index.

Built at **Microsoft Build 2026 (LAB530D)** as a hands-on demonstration of four agentic patterns: **MCP, A2A, RAG, and persistent memory**.

---

## The Problem It Solves

Modern AI agents need more than a language model. They need to:
- **Act on external state** — not just chat, but operate tools that change the world
- **Delegate to specialists** — call other agents instead of reimplementing their logic
- **Answer from trusted sources** — retrieve grounded facts rather than hallucinate
- **Persist across sessions** — remember who they are between runs

This project demonstrates all four patterns working together in a single coherent agent.

---

## How It Works

The agent is dropped into San Francisco with one goal: reach Fort Mason before Build starts. It navigates the city by solving missions — each one either a transport decision or a city knowledge question.

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

### Pattern 1 — MCP (Model Context Protocol)
The agent connects to the game server as an MCP client. The game exposes its actions (start session, submit answer, advance mission) as MCP tools, and even serves the agent's system prompt over MCP — so the game and agent stay in sync automatically.

### Pattern 2 — A2A (Agent-to-Agent)
When the game asks *"car, bike, or walking?"*, the agent doesn't guess — it calls **Agent42**, a deployed peer agent, over the A2A protocol. Agent42 checks live weather and real-time traffic, computes all three routes, and returns a recommendation with a map link.

### Pattern 3 — RAG (Retrieval-Augmented Generation)
When the game asks a San Francisco trivia question, a city guide specialist agent queries an **Azure AI Search** knowledge base over the SF city guide. Answers are grounded in the actual source material, not model memory.

### Pattern 4 — Memory + Logging
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

## Session Logs

Every run produces a structured log in `logs/` showing the full reasoning chain:

```
[17:43:04] USER ->
[user] start the game

[17:43:07] MODEL INPUT (post context providers) ->
[user] start the game
[system] From memory: player_id: PLR-760E28

[17:43:07] TOOL CALL  begin_session
{"player_id": "PLR-760E28"}

[17:43:09] AGENT <-
We found player_id PLR-760E28 for Rahil. Do you want to START?
```

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
