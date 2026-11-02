"""Offline stand-ins for everything the Build lab hosted. Not part of the repo.

Three local servers, one process (ports are HARNESS_PORT_BASE, +1, +2; default 8801):
  :8801/mcp                  fake game MCP server  (tools + game_play_prompt)
  :8802/                     fake Agent42          (A2A JSON-RPC message/send)
  :8803/openai/v1/responses  fake "Azure OpenAI"   (rule-based, scripted tool calls)

The fake model is NOT an LLM: it follows fixed rules so runs are deterministic.
It exercises the plumbing (tools, memory, middleware, A2A call, sub-agent), not reasoning.
The game prompt below is a stand-in I wrote; the lab's real prompt is unknown.

The game is built from SF_Guide.pdf (landmarks, GPS, trivia). Agent42 uses live weather from
Open-Meteo. Environment switches: HARNESS_FORCE_RAIN=1 (demo the recommendation flipping),
HARNESS_OFFLINE_WEATHER=1 (no network).

Switch Agent42's behaviour while running by writing a mode into agent42_mode.txt:
  ok | http500 | timeout | rpc_error | task_shape | non_text
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

import uvicorn
from mcp.server.fastmcp import FastMCP
from sf_world import (
    LANDMARKS,
    Landmark,
    all_etas,
    fastest,
    fetch_weather,
    landmarks_in,
    parse_mode,
    rank_sentences,
    route_km,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

HERE = Path(__file__).resolve().parent
MODE_FILE = HERE / "agent42_mode.txt"
REQUEST_LOG = HERE / "work" / "model_requests.jsonl"
STATE_FILE = HERE / "work" / "game_state.json"

PORT_BASE: Final = int(os.environ.get("HARNESS_PORT_BASE", "8801"))
MCP_PORT, AGENT42_PORT, MODEL_PORT = PORT_BASE, PORT_BASE + 1, PORT_BASE + 2

# ---------------------------------------------------------------- game domain


@dataclass(frozen=True)
class TransportLeg:
    origin: Landmark
    destination: Landmark


@dataclass(frozen=True)
class Puzzle:
    location: Landmark
    question: str
    accepted: tuple[str, ...]  # lowercase substrings that count as correct
    hint: str


Mission = TransportLeg | Puzzle

_L = LANDMARKS
MISSIONS: Final[tuple[Mission, ...]] = (
    TransportLeg(_L["Mission Dolores"], _L["Castro Theatre"]),
    Puzzle(
        _L["Castro Theatre"],
        "In what year was the Castro Theatre originally built?",
        ("1922",),
        "A 1920s movie palace. The guide's Activities section has the date.",
    ),
    TransportLeg(_L["Castro Theatre"], _L["de Young Museum"]),
    Puzzle(
        _L["de Young Museum"],
        "In what year did the de Young Museum open?",
        ("1895",),
        "It is a long-operating museum inside Golden Gate Park.",
    ),
    TransportLeg(_L["de Young Museum"], _L["China Beach"]),
    Puzzle(
        _L["China Beach"],
        "What is the most dangerous place for rip currents in San Francisco?",
        ("ocean beach", "ocean"),
        "Not China Beach: that is the only safe-to-swim beach. Think of the Pacific side.",
    ),
    TransportLeg(_L["China Beach"], _L["Fort Mason"]),
)
POINTS_PER_MISSION: Final = 100
MAX_SCORE: Final = POINTS_PER_MISSION * len(MISSIONS)


@dataclass
class Player:
    name: str
    mission_index: int = 0
    score: int = 0
    minutes: float = 0.0
    wrong_attempts: int = 0  # on the current puzzle
    hints_used: int = 0  # on the current puzzle

    @property
    def finished(self) -> bool:
        return self.mission_index >= len(MISSIONS)


def _load_players() -> dict[str, Player]:
    try:
        return {pid: Player(**data) for pid, data in json.loads(STATE_FILE.read_text()).items()}
    except (OSError, ValueError, TypeError):
        return {}


players: dict[str, Player] = _load_players()


def _save() -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps({pid: asdict(p) for pid, p in players.items()}))


def _prompt_for(player: Player) -> str:
    """Text of the player's current mission, or the final summary once the quest is done."""
    if player.finished:
        rank = (
            "Local legend" if player.score >= 0.85 * MAX_SCORE
            else "Seasoned explorer" if player.score >= 0.6 * MAX_SCORE
            else "Tourist"
        )
        return (
            f"Quest complete! You reached Fort Mason in {player.minutes:.0f} min with "
            f"{player.score}/{MAX_SCORE} points. Rank: {rank}. Say NEW to play again."
        )
    number = f"Mission {player.mission_index + 1}/{len(MISSIONS)} - "
    match MISSIONS[player.mission_index]:
        case TransportLeg(origin, destination):
            return (
                f"{number}You are at {origin.name}. Next stop: {destination.name}, about "
                f"{route_km(origin, destination):.1f} km away. "
                "What transport will you take: car, walking, or bike?"
            )
        case Puzzle(location, question, _, _):
            return f"{number}You arrive at {location.name}. A local challenges you. Puzzle: {question}"


def _advance(player: Player) -> None:
    player.mission_index += 1
    player.wrong_attempts = 0
    player.hints_used = 0
    _save()


UNKNOWN_PLAYER: Final = "Unknown player_id (no saved game). Register a new player instead."

mcp = FastMCP("Fake Gaming MCP Server", host="127.0.0.1", port=MCP_PORT)

# Written for a real LLM: the rule-based fake model ignores it, a Foundry model follows it.
GAME_PROMPT: Final = """\
You are the host of a San Francisco quest game. The game state lives in the game tools, never in \
your head: call a tool for every game action and relay what it returns.

Starting
- If memory gives a player_id, call begin_session(player_id). Otherwise ask the player for their \
name, call register_player(name), then call save_player_id with the returned player_id, then \
call start_mission.
- If begin_session says the player is unknown, register them as above.

Commands (case-insensitive)
- START: call start_mission and show the mission text.
- STATUS: call get_status.
- HINT: call get_hint. Warn once that puzzle hints cost points.
- NEW: ask for confirmation, then call restart_game.
- HELP: look at the current mission. For a transport mission call ask_agent42 with a question that \
names the origin, destination and the travel modes (walk, bike, car) and asks which is fastest \
today given the weather. For a puzzle call ask_city_guide with the puzzle question. Relay the \
advice but do NOT name the final answer; the player must choose.
- Anything else is an answer: call submit_answer(player_id, answer). For a transport mission the \
answer is one of walk, bike or car.

Rules
- Never reveal a puzzle answer or invent mission text, scores or player ids.
- Use the tool result as the source of truth, and keep replies short.
"""


@mcp.prompt(name="game_play_prompt")
def game_play_prompt() -> str:
    return GAME_PROMPT


@mcp.tool()
def register_player(name: str) -> str:
    """Register a new player and return their player_id."""
    player_id = f"PLR-{uuid.uuid4().hex[:6].upper()}"
    players[player_id] = Player(name)
    _save()
    return f"Registered {name}. player_id: {player_id}. Say START to begin."


@mcp.tool()
def begin_session(player_id: str) -> str:
    """Resume a session for an existing player."""
    player = players.get(player_id)
    if player is None:
        return UNKNOWN_PLAYER
    progress = (
        "You have finished the quest"
        if player.finished
        else f"You are on mission {player.mission_index + 1}/{len(MISSIONS)}"
    )
    return (
        f"Welcome back, {player.name}! player_id: {player_id}. {progress}, "
        f"score {player.score}. Say START to continue."
    )


@mcp.tool()
def start_mission(player_id: str) -> str:
    """Return the player's current mission text."""
    player = players.get(player_id)
    return UNKNOWN_PLAYER if player is None else _prompt_for(player)


@mcp.tool()
def get_status(player_id: str) -> str:
    """Report score and progress."""
    player = players.get(player_id)
    if player is None:
        return UNKNOWN_PLAYER
    done = min(player.mission_index, len(MISSIONS))
    return (
        f"{player.name}: {done}/{len(MISSIONS)} missions done, "
        f"score {player.score}/{MAX_SCORE}, {player.minutes:.0f} min elapsed."
    )


@mcp.tool()
def get_hint(player_id: str) -> str:
    """Give a hint for the current mission (puzzle hints cost 25 points)."""
    player = players.get(player_id)
    if player is None:
        return UNKNOWN_PLAYER
    if player.finished:
        return "The quest is complete. Say NEW to play again."
    match MISSIONS[player.mission_index]:
        case Puzzle(hint=hint):
            player.hints_used += 1
            _save()
            return f"Hint: {hint} (-25 points)"
        case TransportLeg():
            return "Hint: say HELP. Agent42 checks live weather and compares all three options."


@mcp.tool()
def restart_game(player_id: str) -> str:
    """Reset progress and score for this player."""
    player = players.get(player_id)
    if player is None:
        return UNKNOWN_PLAYER
    players[player_id] = Player(player.name)
    _save()
    return "Fresh start! " + _prompt_for(players[player_id])


@mcp.tool()
async def submit_answer(player_id: str, answer: str) -> str:
    """Submit an answer for the current mission."""
    player = players.get(player_id)
    if player is None:
        return UNKNOWN_PLAYER
    if player.finished:
        return f"The quest is already complete ({player.score}/{MAX_SCORE}). Say NEW to play again."
    match MISSIONS[player.mission_index]:
        case TransportLeg() as leg:
            return await _answer_leg(player, leg, answer)
        case Puzzle() as puzzle:
            return _answer_puzzle(player, puzzle, answer)


async def _answer_leg(player: Player, leg: TransportLeg, answer: str) -> str:
    mode = parse_mode(answer)
    if mode is None:
        return f"'{answer.strip()}' is not a transport option. Choose car, walking, or bike. (No penalty.)"
    weather = await fetch_weather(leg.origin)
    etas = all_etas(route_km(leg.origin, leg.destination), weather)
    best = fastest(etas)
    points = round(POINTS_PER_MISSION * etas[best] / etas[mode])
    player.score += points
    player.minutes += etas[mode]
    _advance(player)
    verdict = "the fastest choice!" if mode == best else f"fastest was {best} at {etas[best]} min"
    return (
        f"You travel by {mode}: {etas[mode]} min, {verdict} +{points} points. "
        f"Weather was {weather.describe()}. {_prompt_for(player)}"
    )


def _answer_puzzle(player: Player, puzzle: Puzzle, answer: str) -> str:
    text = answer.strip().lower()
    if text.endswith("?"):
        return "That sounds like a question for your guide. Say HELP to ask it. (No penalty.)"
    if any(accepted in text for accepted in puzzle.accepted):
        points = max(25, POINTS_PER_MISSION - 25 * player.hints_used - 10 * player.wrong_attempts)
        player.score += points
        _advance(player)
        return f"Correct! +{points} points. {_prompt_for(player)}"
    player.wrong_attempts += 1
    _save()
    reply = f"Not quite (attempt {player.wrong_attempts}). Say HINT for a clue or HELP to ask your guide."
    if player.wrong_attempts >= 3:
        reply += f" Here is a free hint: {puzzle.hint}"
    return reply


# ---------------------------------------------------------------- fake Agent42


async def _transport_advice(question: str) -> str:
    places = landmarks_in(question)
    if len(places) < 2:
        known = ", ".join(LANDMARKS)
        return f"I need an origin and a destination I know. I cover: {known}."
    origin, destination = places[0], places[1]
    weather = await fetch_weather(origin)
    km = route_km(origin, destination)
    etas = all_etas(km, weather)
    return (
        f"Weather at {origin.name}: {weather.describe()}. "
        f"Route {origin.name} to {destination.name}: about {km:.1f} km. "
        f"Car: {etas['car']} min (includes 5 min pickup wait). "
        f"Bike: {etas['bike']} min. Walking: {etas['walking']} min. "
        f"Recommendation: {fastest(etas)}"
    )


async def agent42(request: Request) -> Response:
    mode = MODE_FILE.read_text().strip() if MODE_FILE.exists() else "ok"
    body: dict[str, Any] = await request.json()
    rpc_id = body.get("id")
    question = _text_of(body.get("params", {}).get("message", {}).get("parts", []))

    if mode == "http500":
        return Response("boom", status_code=500)
    if mode == "timeout":
        await asyncio.sleep(70)  # client timeout is 60s
    if mode == "rpc_error":
        return JSONResponse(
            {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": "weather API down"}}
        )
    if mode == "task_shape":  # valid A2A Task: text is under artifacts, not result.parts
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "kind": "task",
                    "status": {"state": "completed"},
                    "artifacts": [{"parts": [{"kind": "text", "text": "Recommendation: bike"}]}],
                },
            }
        )
    if mode == "non_text":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"kind": "message", "parts": [{"kind": "data", "data": {"mode": "bike"}}]},
            }
        )
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "kind": "message",
                "role": "agent",
                "messageId": uuid.uuid4().hex,
                "parts": [{"kind": "text", "text": await _transport_advice(question)}],
            },
        }
    )


# ---------------------------------------------------------------- fake model


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def _output_text(item: dict[str, Any]) -> str:
    out = item.get("output", "")
    return out if isinstance(out, str) else _text_of(out)


def _message(text: str) -> dict[str, Any]:
    return {
        "id": f"msg_{uuid.uuid4().hex[:8]}",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"fc_{uuid.uuid4().hex[:8]}",
        "type": "function_call",
        "call_id": f"call_{uuid.uuid4().hex[:8]}",
        "name": name,
        "arguments": json.dumps(args),
        "status": "completed",
    }


def _new_items(body: dict[str, Any]) -> list[dict[str, Any]]:
    raw = body.get("input", [])
    return [{"role": "user", "content": raw}] if isinstance(raw, str) else list(raw)


# The real service keeps history server-side and the framework only sends new items plus
# previous_response_id, so the fake must do the same.
conversations: dict[str, list[dict[str, Any]]] = {}

_MISSION_MARK = re.compile(r"Mission \d+/\d+ - ")


def _current_mission(items: list[dict[str, Any]]) -> str | None:
    """Latest mission text the model has seen, or None if the quest is over or not started."""
    for item in reversed(items):
        if item.get("type") == "function_call_output":
            text = _output_text(item)
        elif item.get("role") == "assistant":
            text = _text_of(item.get("content"))
        else:
            continue
        if "Quest complete" in text or "already complete" in text:
            return None
        marks = list(_MISSION_MARK.finditer(text))
        if marks:
            return text[marks[-1].start():]
    return None


def _help_call(mission: str) -> dict[str, Any]:
    if "Puzzle:" in mission:
        return _call("ask_city_guide", {"question": mission.split("Puzzle:", 1)[1].strip()})
    places = landmarks_in(mission)
    return _call(
        "ask_agent42",
        {
            "question": f"What is the best way to get from {places[0].name} to {places[1].name}: "
            "car, bike, or walking?"
        },
    )


def decide(body: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    system_text = _text_of(body.get("instructions") or "") + "".join(
        _text_of(i.get("content")) for i in items if i.get("role") in {"system", "developer"}
    )
    # What an LLM would see: the latest player id mentioned anywhere in its context.
    all_text = system_text + "\n" + "\n".join(
        _output_text(i) if i.get("type") == "function_call_output" else _text_of(i.get("content"))
        for i in items
    )

    # Sub-agent (city guide) turn: answer only from the injected search context.
    if "city guide questions" in system_text:
        question = next(
            (_text_of(i.get("content")) for i in reversed(items) if i.get("role") == "user"), ""
        )
        context_lines = re.findall(r"^- (.+)$", system_text, flags=re.M)
        best = rank_sentences(question, context_lines, top=1)
        return [_message(best[0] if best else "I could not find that in the guide.")]

    pids = re.findall(r"PLR-\w+", all_text)
    pid = pids[-1] if pids else ""
    last = items[-1]

    if last.get("type") == "function_call_output":
        call_id = last.get("call_id")
        name = next(
            (i.get("name") for i in items if i.get("type") == "function_call" and i.get("call_id") == call_id),
            "?",
        )
        output = _output_text(last)
        if name == "register_player":
            new_id = re.search(r"PLR-\w+", output)
            return [_call("save_player_id", {"player_id": new_id.group(0) if new_id else ""})]
        if name == "begin_session" and output.startswith("Unknown player_id"):
            return [_call("register_player", {"name": "Rahil"})]  # stale memory: start over
        if name == "save_player_id":
            return [_message("Registered and saved. Say START to begin.")]
        return [_message(output)]  # everything else: relay the tool's text verbatim

    user_text = _text_of(last.get("content")).strip()
    command = user_text.upper()
    if user_text.lower() == "start the game":
        return [_call("begin_session", {"player_id": pid})] if pid else [_call("register_player", {"name": "Rahil"})]
    if command == "START":
        return [_call("start_mission", {"player_id": pid})]
    if command == "HINT":
        return [_call("get_hint", {"player_id": pid})]
    if command == "STATUS":
        return [_call("get_status", {"player_id": pid})]
    if command == "NEW":
        return [_call("restart_game", {"player_id": pid})]
    if command == "HELP":
        mission = _current_mission(items)
        if mission is None:
            return [_message("There is no active mission. Say START, or NEW for a fresh game.")]
        return [_help_call(mission)]
    return [_call("submit_answer", {"player_id": pid, "answer": user_text})]


async def responses(request: Request) -> Response:
    body: dict[str, Any] = await request.json()
    REQUEST_LOG.parent.mkdir(exist_ok=True)
    with REQUEST_LOG.open("a", encoding="utf-8") as file:
        file.write(json.dumps(body, default=str) + "\n")
    items = conversations.get(body.get("previous_response_id") or "", []) + _new_items(body)
    output = decide(body, items)
    response_id = f"resp_{uuid.uuid4().hex[:8]}"
    conversations[response_id] = items + output
    done: dict[str, Any] = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": body.get("model", "fake"),
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }
    if body.get("stream"):  # the as_tool sub-agent streams; the main agent does not
        return StreamingResponse(_sse(done), media_type="text/event-stream")
    return JSONResponse(done)


def _sse(done: dict[str, Any]) -> Iterator[str]:
    seq = 0

    def emit(event: dict[str, Any]) -> str:
        nonlocal seq
        event["sequence_number"] = seq
        seq += 1
        return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

    yield emit({"type": "response.created", "response": {**done, "status": "in_progress", "output": []}})
    for index, item in enumerate(done["output"]):
        if item["type"] == "message":
            text = item["content"][0]["text"]
            part = {"type": "output_text", "text": "", "annotations": []}
            yield emit({"type": "response.output_item.added", "output_index": index,
                        "item": {**item, "status": "in_progress", "content": []}})
            yield emit({"type": "response.content_part.added", "item_id": item["id"],
                        "output_index": index, "content_index": 0, "part": part})
            yield emit({"type": "response.output_text.delta", "item_id": item["id"],
                        "output_index": index, "content_index": 0, "delta": text})
            yield emit({"type": "response.output_text.done", "item_id": item["id"],
                        "output_index": index, "content_index": 0, "text": text})
            yield emit({"type": "response.content_part.done", "item_id": item["id"],
                        "output_index": index, "content_index": 0, "part": item["content"][0]})
        else:  # function_call
            yield emit({"type": "response.output_item.added", "output_index": index,
                        "item": {**item, "status": "in_progress", "arguments": ""}})
            yield emit({"type": "response.function_call_arguments.delta", "item_id": item["id"],
                        "output_index": index, "delta": item["arguments"]})
            yield emit({"type": "response.function_call_arguments.done", "item_id": item["id"],
                        "output_index": index, "name": item["name"], "arguments": item["arguments"]})
        yield emit({"type": "response.output_item.done", "output_index": index, "item": item})
    yield emit({"type": "response.completed", "response": done})


# ---------------------------------------------------------------- run all three


async def main() -> None:
    apps: list[tuple[Any, int]] = [
        (mcp.streamable_http_app(), MCP_PORT),
        (Starlette(routes=[Route("/", agent42, methods=["POST"])]), AGENT42_PORT),
        (Starlette(routes=[Route("/openai/v1/responses", responses, methods=["POST"])]), MODEL_PORT),
    ]
    servers = [
        uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        for app, port in apps
    ]
    print(f"fake backends up: mcp:{MCP_PORT}  agent42:{AGENT42_PORT}  model:{MODEL_PORT}", flush=True)
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
