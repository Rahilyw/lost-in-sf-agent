"""Per-session conversation and tool logging for the workshop agent."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_framework import agent_middleware, chat_middleware, function_middleware

LOGS_DIR = Path(__file__).resolve().parent / "logs"


def open_session_log() -> Path:
    LOGS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = LOGS_DIR / f"session-{stamp}-{uuid.uuid4().hex[:6]}.log"
    path.write_text(f"# Session log started {datetime.now().isoformat()}\n\n")
    return path


def _append(path: Path, header: str, body: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    with path.open("a", encoding="utf-8") as file:
        file.write(f"[{ts}] {header}\n{body.rstrip()}\n\n")


def _truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def _stringify(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, default=str, ensure_ascii=False)
    except Exception:
        return repr(value)


def _format_messages(messages) -> str:
    parts: list[str] = []
    for message in messages or []:
        role = getattr(message, "role", "?")
        text = "".join(
            (getattr(content, "text", "") or "")
            for content in getattr(message, "contents", []) or []
        )
        if text:
            parts.append(f"[{role}] {text}")
    return "\n".join(parts)


def build_logging_middleware(log_path: Path):
    @agent_middleware
    async def log_agent(context, call_next):
        text = _format_messages(context.messages)
        if text:
            _append(log_path, "USER ->", _truncate(text))

        await call_next()

        result = getattr(context, "result", None)
        out = getattr(result, "text", None)
        if out:
            _append(log_path, "AGENT <-", _truncate(out))

    @chat_middleware
    async def log_chat(context, call_next):
        text = _format_messages(context.messages)
        if text:
            _append(log_path, "MODEL INPUT (post context providers) ->", _truncate(text))
        await call_next()

    @function_middleware
    async def log_function(context, call_next):
        function_name = getattr(getattr(context, "function", None), "name", "?")
        arguments = getattr(context, "arguments", {}) or {}
        _append(log_path, f"TOOL CALL  {function_name}", _truncate(_stringify(arguments)))

        await call_next()

        result = getattr(context, "result", None)
        _append(log_path, f"TOOL RESULT {function_name}", _truncate(_stringify(result)))

    return log_agent, log_chat, log_function