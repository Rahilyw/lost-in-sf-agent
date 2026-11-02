# Offline harness

Runs the real `agent.py` with no Azure account and no lab servers. The lab backends are gone,
so this replaces them with local fakes. Nothing in the parent folder is modified.

| File | Role |
|---|---|
| `fake_backends.py` | Fake game MCP server, Agent42 (A2A) and "Azure OpenAI" (Responses API) |
| `run_offline.py` | Points `agent.py` at the fakes, swaps only the Azure Search provider for a guide-backed stub |
| `sf_world.py` | Landmarks and GPS from `SF_Guide.pdf`, live Open-Meteo weather, travel-time model, retrieval |
| `check_world.py` | Sanity checks for the travel model |
| `data/sf_guide.txt` | Text extracted from `SF_Guide.pdf` |

## Run

Terminal 1:
```bash
python -W ignore harness/fake_backends.py
```
Terminal 2:
```bash
python -W ignore harness/run_offline.py
```
Commands: `START`, `HELP`, `HINT`, `STATUS`, `NEW`, or type an answer. `exit` quits.

State (`memory.json`, game save, logs, model request log) goes to `harness/work/`, which is
git-ignored. Your real `memory.json` and `logs/` are not touched.

## Limits

- The model is rule-based, not an LLM. It exercises the plumbing, not the reasoning.
- The game prompt is a stand-in; the lab's real prompt is unknown.
- Weather is live from [Open-Meteo](https://open-meteo.com/) (CC BY 4.0, no key).
  `HARNESS_OFFLINE_WEATHER=1` disables the network call; `HARNESS_FORCE_RAIN=1` forces rain.
- Fort Mason's coordinates are approximate; it is not in the guide.

## Break Agent42 on purpose

Write one of `ok | http500 | timeout | rpc_error | task_shape | non_text` into
`harness/agent42_mode.txt` while the backends run.

Set `HARNESS_PORT_BASE` (default 8801) to use other ports.
