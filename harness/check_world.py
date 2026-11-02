"""Sanity checks for the travel model and the welcome text. Run: python check_world.py"""

from __future__ import annotations

import asyncio
import os

import fake_backends as fb
from sf_world import LANDMARKS, all_etas, fastest, fetch_weather, route_km

LEGS = [
    ("Mission Dolores", "Castro Theatre"),
    ("Castro Theatre", "de Young Museum"),
    ("de Young Museum", "China Beach"),
    ("China Beach", "Fort Mason"),
]


async def show(label: str) -> dict[tuple[str, str], str]:
    best: dict[tuple[str, str], str] = {}
    for a, b in LEGS:
        origin, destination = LANDMARKS[a], LANDMARKS[b]
        etas = all_etas(route_km(origin, destination), await fetch_weather(origin))
        best[(a, b)] = fastest(etas)
        print(f"{label:4} {a:16} -> {b:16} best={best[(a, b)]:7} {etas}")
    return best


os.environ["HARNESS_OFFLINE_WEATHER"] = "1"  # deterministic dry baseline
dry = asyncio.run(show("dry"))
os.environ.pop("HARNESS_OFFLINE_WEATHER")
os.environ["HARNESS_FORCE_RAIN"] = "1"
rain = asyncio.run(show("rain"))
print("flipped by rain:", [leg for leg in LEGS if dry[leg] != rain[leg]])

fb.players["PLR-T"] = fb.Player("Test", mission_index=len(fb.MISSIONS))
print(fb.begin_session("PLR-T"))
fb.players["PLR-T"].mission_index = 2
print(fb.begin_session("PLR-T"))
