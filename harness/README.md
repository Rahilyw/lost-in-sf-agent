# Harness: run the real agent without the lab

The lab backends (game MCP server, Agent42, Azure AI Search) are gone. This folder replaces them with
local stand-ins so the **real, unmodified** `agent.py` runs end to end, optionally on **real Microsoft
Foundry models**. Nothing in the parent folder is modified.

| File | Role |
|---|---|
| `fake_backends.py` | Game MCP server (7 missions), Agent42 (A2A JSON-RPC) and a fake Responses-API model server |
| `run_offline.py` | Points `agent.py` at the backends; `--foundry` uses real models; swaps only the Azure Search provider for a guide-backed retriever |
| `sf_world.py` | Landmarks and GPS from `SF_Guide.pdf`, live [Open-Meteo](https://open-meteo.com/) weather, travel-time model, retrieval |
| `check_world.py` | Sanity checks for the travel model (dry vs rain) |
| `data/sf_guide.txt` | Text extracted from `SF_Guide.pdf` |
| `.env.foundry` | **Yours, git-ignored.** Endpoint, key and deployment names for `--foundry` |

## What is real and what is fake

| Piece | Offline | `--foundry` |
|---|---|---|
| Main agent and city-guide LLM | Fake, rule-based | **Real** (Foundry `gpt-4.1-mini`) |
| `agent.py`, `agent_agent42.py`, `agent_city_guide.py`, `log.py` | Real | Real |
| Game server (MCP) | Fake, local | Fake, local |
| Agent42 (A2A) | Fake, local, live weather | Fake, local, live weather |
| Azure AI Search | Local retriever over the guide | Local retriever over the guide |

## Run

Terminal 1 (from the repo root):
```bash
python -W ignore harness/fake_backends.py
```
Terminal 2, offline:
```bash
python -W ignore harness/run_offline.py
```
Terminal 2, real Foundry models:
```bash
python -W ignore harness/run_offline.py --foundry
```
Commands: `START`, `HELP`, `HINT`, `STATUS`, `NEW`, or type an answer. `exit` quits.

State (`memory.json`, game save, logs, model request log) goes to `harness/work/`, which is
git-ignored. Your real `memory.json` and `logs/` are not touched. Set `HARNESS_PORT_BASE`
(default 8801) to use other ports; set it in both terminals.

## Foundry setup

1. Create an AIServices (Foundry) resource and a `gpt-4.1-mini` deployment:
   ```bash
   az group create -n rg-lost-in-sf -l eastus2
   az cognitiveservices account create -g rg-lost-in-sf -n lost-in-sf-foundry -l eastus2 --kind AIServices --sku S0 --custom-domain lost-in-sf-foundry --yes
   az cognitiveservices account deployment create -g rg-lost-in-sf -n lost-in-sf-foundry --deployment-name gpt-4.1-mini --model-name gpt-4.1-mini --model-version 2025-04-14 --model-format OpenAI --sku-name GlobalStandard --sku-capacity 50
   ```
2. Create `harness/.env.foundry`:
   ```env
   AZURE_OPENAI_ENDPOINT=https://lost-in-sf-foundry.cognitiveservices.azure.com
   AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1-mini
   CITY_GUIDE_AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4.1-mini
   ```
3. Append the key without printing it:
   ```powershell
   $k = az cognitiveservices account keys list -g rg-lost-in-sf -n lost-in-sf-foundry --query key1 -o tsv; Add-Content harness/.env.foundry "AZURE_OPENAI_API_KEY=$k"
   ```
4. Clean up when done: `az group delete -n rg-lost-in-sf`. Billing is per token, so an idle deployment costs nothing.

`agent.py` calls `load_dotenv(override=True)`. If a real `.env` exists in the repo root it overrides the
variables set here, so move it aside first.

## What the harness adds to the game

- **Missions built from `SF_Guide.pdf`:** Mission Dolores → Castro Theatre → de Young → China Beach → Fort Mason, with puzzles whose answers come from the guide (opening years, beach safety).
- **Live weather:** Agent42 calls Open-Meteo for the origin. Rain slows bikes and walkers, so it flips the best mode from bike to car on legs 2 and 3. `HARNESS_FORCE_RAIN=1` forces rain; `HARNESS_OFFLINE_WEATHER=1` assumes dry with no network call.
- **Scoring:** transport legs score `100 * best / chosen`; puzzles lose 25 per hint and 10 per wrong answer (minimum 25).
- **Persistence:** game progress survives restarts (`work/game_state.json`), so memory and game state agree.
- **Typed domain model:** `Mission = TransportLeg | Puzzle`, frozen dataclasses, and `Player.finished` derived from progress, so there is no "finished" flag that can disagree with the data.

## Live demo script (about 5 minutes, `--foundry`)

Reset to a clean game first:
```powershell
Remove-Item harness/work/memory.json, harness/work/game_state.json -ErrorAction SilentlyContinue
```

| # | You type | What happens | What to say |
|---|---|---|---|
| 1 | (starts) | Agent asks your name, then `register_player` and `save_player_id`, then `start_mission` | "The game state lives in the MCP server. The model only calls tools. It decides to save memory, which is a weakness I'd fix." |
| 2 | `exit`, rerun | "Welcome back, Rahil!" with no registration | "`PlayerContextProvider.before_run` reads `memory.json` and extends the instructions before each run. The model never has to remember anything." |
| 3 | `HELP` | `ask_agent42` call; live weather and three ETAs | "A2A: the coordinator delegates instead of reimplementing routing. Weather is live." |
| 4 | `bike` | Points awarded, puzzle mission appears | "`submit_answer` is an MCP tool; the score comes from the server, not the model." |
| 5 | `HELP` | `ask_city_guide` call: a sub-agent answers from the guide | "RAG context lives on the sub-agent, so the main agent doesn't pay retrieval tokens every turn. `as_tool` wraps the sub-agent." |
| 6 | `1999`, `HINT`, `1922` | Wrong, hint (costs 25), correct | "Scoring and hint cost are server rules." |
| 7 | open `harness/work/logs/session-*.log` | `TOOL CALL` and `TOOL RESULT` lines | "Middleware logs every call. Note `MODEL INPUT` shows what the player sent, not the system prompt or injected memory, which is a known gap." |

Optional, to show failure handling. Set the mode while the backends run, then type `HELP` on a transport mission:
```powershell
Set-Content harness/agent42_mode.txt http500    # or rpc_error
Set-Content harness/agent42_mode.txt ok         # reset
```
- `http500`: the framework catches the exception (`Function failed. Error: ...`) and the model degrades gracefully: "I am having trouble getting the travel advice right now."
- `rpc_error`: the JSON-RPC error body has no `result`, so `_call_agent42` returns `str(result)` (`{}`), and the model makes up a vague non-answer. **This is a silent failure.** Say: "I'd make the A2A response a typed union and raise on anything that isn't text."

Other modes: `ok | http500 | timeout | rpc_error | task_shape | non_text`.

Tips:
- The model is not deterministic. Rehearse once, and keep the offline mode as a fallback (`run_offline.py` with no flag).
- A model-service error (bad key, quota) is **not** caught: `agent.run` in the chat loop has no `try/except`, so the app exits with a traceback.
- Be upfront that the game server, Agent42 and search are stand-ins. What is real is your coordinator, tool wrapper, memory, middleware, and the model calls.

## Limits

- The offline model is rule-based. It exercises the plumbing, not the reasoning.
- The game prompt in `fake_backends.py` is a stand-in. The lab's real prompt is unknown.
- Search is a keyword retriever (IDF-weighted), not Azure AI Search or agentic retrieval.
- Fort Mason's coordinates are approximate; it is not in the guide.
- Weather is live from Open-Meteo (CC BY 4.0, no key).
