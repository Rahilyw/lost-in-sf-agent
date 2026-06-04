# Lost in SF Agent

An AI player agent that navigates the *Lost in San Francisco* quest game — built with the **Microsoft Agent Framework** at Microsoft Build 2026 (LAB530D).

The agent reasons through missions, calls specialist agents for help, retrieves knowledge from a city guide, and remembers its player session between runs.

---

## What It Does

The agent plays an interactive city quest game end-to-end:

1. **Starts or resumes a game session** using a saved player ID
2. **Solves transport missions** by consulting Agent42 for weather-aware route recommendations
3. **Answers city guide questions** by querying an Azure AI Search knowledge base over San Francisco content
4. **Logs every decision** — model input, tool calls, and responses — to a session log file

---

## Architecture

```
agent.py  (Game Play Agent)
├── MCP → game server          # picks up missions, submits answers
├── Tool: save_player_id       # writes player ID to memory.json
├── Tool: ask_agent42          # calls Agent42 via A2A for transport advice
├── Tool: ask_city_guide       # calls city guide specialist for RAG answers
├── ContextProvider: memory    # injects player ID before each model turn
└── Middleware: logging        # records every prompt, tool call, and response
```

### Specialist Agents

| File | Role | Protocol |
|------|------|----------|
| `agent_agent42.py` | Transport expert — compares car, bike, walking using live weather and traffic | A2A (JSON-RPC) |
| `agent_city_guide.py` | SF city knowledge — retrieves answers from Azure AI Search | RAG via Azure AI Search |
| `log.py` | Session logging middleware | — |

---

## Key Concepts Demonstrated

| Concept | How it's used |
|---------|--------------|
| **MCP** | Agent connects to the game server as an MCP client, loading the game prompt and calling game actions as tools |
| **A2A** | Agent calls Agent42 (a deployed peer agent) over the Agent-to-Agent protocol for transport recommendations |
| **RAG** | City guide specialist uses `AzureAISearchContextProvider` to ground answers in real San Francisco content |
| **Memory** | `PlayerContextProvider` reads `memory.json` and injects the player ID before each model turn |
| **Middleware** | Three middleware hooks log agent turns, model input, and tool calls to a per-session log file |

---

## Setup

### Prerequisites

- Python 3.10+
- Azure OpenAI deployment (`gpt-5.5` for main agent, `gpt-4.1-mini` for city guide)
- Azure AI Search with a city guide knowledge base
- Access to the game MCP server and Agent42

### Install dependencies

```bash
pip install agent-framework python-dotenv httpx
```

### Configure `.env`

Create a `.env` file in the project root (never commit this):

```env
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5.5
CITY_GUIDE_AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1-mini

GAME_MCP_URL=https://mcp.workshop.agentcon.dev/san-francisco/mcp
AGENT42_URL=https://agent42.workshop.agentcon.dev/

AZURE_SEARCH_ENDPOINT=https://<your-search>.search.windows.net
AZURE_SEARCH_KEY=<your-search-key>
AZURE_SEARCH_KNOWLEDGE_BASE_NAME=city-knowledgebase
```

---

## Running

### Play the full game
```bash
python agent.py
```

Type `HELP` when the game asks a question to let the agent consult its specialist tools. Type `exit` or `quit` to stop.

### Test Agent42 (transport specialist) standalone
```bash
python agent_agent42.py
```

### Test the city guide specialist standalone
```bash
python agent_city_guide.py
```

---

## Session Logs

Every run writes a log file to `logs/`. Open it to see exactly what the agent did:

```
[17:43:04] USER ->
[user] start the game

[17:43:07] TOOL CALL  begin_session
{"player_id": "PLR-760E28"}

[17:43:07] TOOL RESULT begin_session
{"status": "known_player", ...}

[17:43:09] AGENT <-
We found player_id PLR-760E28 for Rahil. Do you want to START?
```

---

## Project Structure

```
.
├── agent.py              # Main game play agent
├── agent_agent42.py      # Agent42 A2A transport specialist
├── agent_city_guide.py   # SF city guide RAG specialist
├── log.py                # Session logging middleware
├── .env                  # Local config (not committed)
├── .gitignore
└── logs/                 # Per-session log files (not committed)
```

---

## Built at Microsoft Build 2026

This project was built as part of **LAB530D — Engineering Agents that Reason, Act, and Adapt** at Microsoft Build 2026, using:

- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- Azure OpenAI (gpt-5.5, gpt-4.1-mini)
- Azure AI Search (Foundry IQ)
- MCP (Model Context Protocol)
- A2A (Agent-to-Agent protocol)
