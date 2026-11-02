"""Domain model shared by the fake game server and the fake Agent42. Not part of the repo.

Landmarks and GPS points come from SF_Guide.pdf. Weather is live from Open-Meteo
(free, no API key, CC BY 4.0 - attribution is printed with every live reading).
"""

from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, get_args

import httpx

Mode = Literal["walking", "bike", "car"]
MODES: Final[tuple[Mode, ...]] = get_args(Mode)


@dataclass(frozen=True)
class Landmark:
    name: str
    lat: float
    lon: float


LANDMARKS: Final[dict[str, Landmark]] = {
    landmark.name: landmark
    for landmark in (
        Landmark("Mission Dolores", 37.76438, -122.42682),
        Landmark("Castro Theatre", 37.76201, -122.43470),
        Landmark("de Young Museum", 37.77147, -122.46868),
        Landmark("China Beach", 37.78766, -122.49112),
        # Not in the guide: approximate, added so the quest ends where the lab game does.
        Landmark("Fort Mason", 37.8066, -122.4312),
    )
}


def landmarks_in(text: str) -> list[Landmark]:
    """Known landmarks mentioned in `text`, in the order they first appear."""
    lowered = text.lower()
    hits = [(lowered.find(landmark.name.lower()), landmark) for landmark in LANDMARKS.values()]
    # key= matters: tuples tying on -1 would otherwise fall through to comparing Landmarks.
    return [landmark for index, landmark in sorted(hits, key=lambda hit: hit[0]) if index >= 0]


# ------------------------------------------------------------------ travel model

# Straight-line distance understates street distance; one flat factor keeps the model simple.
ROUTE_FACTOR: Final = 1.3
_SPEED_KMH: Final[dict[Mode, float]] = {"walking": 5.0, "bike": 15.0, "car": 20.0}
_CAR_PICKUP_WAIT_MIN: Final = 5.0


def route_km(origin: Landmark, destination: Landmark) -> float:
    """Haversine distance scaled by ROUTE_FACTOR."""
    lat1, lat2 = math.radians(origin.lat), math.radians(destination.lat)
    d_lat = lat2 - lat1
    d_lon = math.radians(destination.lon - origin.lon)
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a)) * ROUTE_FACTOR


@dataclass(frozen=True)
class Weather:
    temperature_c: float
    precipitation_mm: float
    wind_kmh: float
    summary: str
    is_wet: bool
    live: bool  # False when assumed or forced, so callers never present a guess as a reading

    def describe(self) -> str:
        source = " (live, Open-Meteo.com)" if self.live else ""
        return (
            f"{self.summary}, {self.temperature_c:.0f}C, wind {self.wind_kmh:.0f} km/h, "
            f"rain {self.precipitation_mm:.1f} mm{source}"
        )


_ASSUMED_DRY: Final = Weather(16.0, 0.0, 10.0, "mild and dry (assumed: live weather unavailable)", False, False)
_FORCED_RAIN: Final = Weather(11.0, 2.4, 28.0, "heavy rain (forced by HARNESS_FORCE_RAIN)", True, False)


def _describe_code(code: int) -> tuple[str, bool]:
    """WMO weather code -> (summary, is_wet)."""
    if code == 0:
        return "clear sky", False
    if code in (1, 2):
        return "partly cloudy", False
    if code == 3:
        return "overcast", False
    if code in (45, 48):
        return "fog", False
    if 51 <= code <= 57:
        return "drizzle", True
    if 61 <= code <= 67 or 80 <= code <= 82:
        return "rain", True
    if 71 <= code <= 77 or code in (85, 86):
        return "snow", True
    if code >= 95:
        return "thunderstorm", True
    return "mixed weather", False


_CACHE_SECONDS: Final = 600  # free tier is generous, but there is no reason to re-ask every turn
_cache: dict[str, tuple[float, Weather]] = {}


async def fetch_weather(at: Landmark) -> Weather:
    """Live conditions at a landmark; degrades to an explicitly-assumed value, never raises."""
    if os.environ.get("HARNESS_FORCE_RAIN"):
        return _FORCED_RAIN
    if os.environ.get("HARNESS_OFFLINE_WEATHER"):
        return _ASSUMED_DRY
    cached = _cache.get(at.name)
    if cached and time.monotonic() - cached[0] < _CACHE_SECONDS:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": at.lat,
                    "longitude": at.lon,
                    "current": "temperature_2m,precipitation,weather_code,wind_speed_10m",
                },
            )
            response.raise_for_status()
            current = response.json()["current"]
        summary, wet_by_code = _describe_code(int(current["weather_code"]))
        precipitation = float(current["precipitation"])
        weather = Weather(
            temperature_c=float(current["temperature_2m"]),
            precipitation_mm=precipitation,
            wind_kmh=float(current["wind_speed_10m"]),
            summary=summary,
            is_wet=wet_by_code or precipitation >= 0.1,
            live=True,
        )
    except (httpx.HTTPError, KeyError, ValueError):
        return _ASSUMED_DRY
    _cache[at.name] = (time.monotonic(), weather)
    return weather


def eta_minutes(mode: Mode, km: float, weather: Weather) -> float:
    speed = _SPEED_KMH[mode]
    if mode == "bike":
        if weather.is_wet:
            speed *= 0.7
        if weather.wind_kmh > 35:
            speed *= 0.8
    elif mode == "walking" and weather.is_wet:
        speed *= 0.9
    minutes = km / speed * 60
    if mode == "car":
        minutes += _CAR_PICKUP_WAIT_MIN
    return round(minutes, 1)


def all_etas(km: float, weather: Weather) -> dict[Mode, float]:
    return {mode: eta_minutes(mode, km, weather) for mode in MODES}


def fastest(etas: dict[Mode, float]) -> Mode:
    return min(etas, key=etas.__getitem__)


_ALIASES: Final[dict[str, Mode]] = {
    "walk": "walking", "walking": "walking", "foot": "walking", "on foot": "walking",
    "bike": "bike", "biking": "bike", "bicycle": "bike", "cycle": "bike", "cycling": "bike",
    "car": "car", "drive": "car", "driving": "car", "taxi": "car", "cab": "car",
}


def parse_mode(text: str) -> Mode | None:
    return _ALIASES.get(text.strip().lower().rstrip(".!"))


# ------------------------------------------------------------------ guide retrieval

_TOKEN: Final = re.compile(r"[a-z0-9]+")
_STOP: Final = frozenset(
    "the a an of in on at to is are was were what which who when where how does did do for "
    "and or by with from this that it its as be".split()
)


def load_guide_sentences(path: Path) -> list[str]:
    """SF_Guide.pdf text -> cleaned sentences (addresses, phones and GPS noise removed)."""
    text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
    text = re.sub(r"\d[\w .'#-]*?, San Francisco, CA \d{5}, USA", "", text)
    text = re.sub(r"GPS: N[\d.]+, W[\d.]+", "", text)
    text = re.sub(r"Phone: \+1 [\d ]+", "", text)
    text = re.sub(r"(?<=[a-z)]) [A-Z] (?=[A-Z])", " ", text)  # stray A-Z map markers
    sentences = (s.strip() for s in re.split(r"(?<=[.!?]) ", text))
    return [s for s in sentences if len(s) > 20]


def rank_sentences(query: str, sentences: list[str], top: int = 3) -> list[str]:
    """Keyword retrieval with inverse-document-frequency weights and prefix matching."""
    terms = [t for t in _TOKEN.findall(query.lower()) if t not in _STOP and len(t) >= 3]
    docs = [set(_TOKEN.findall(s.lower())) for s in sentences]

    def matches(term: str, doc: set[str]) -> bool:
        return any(w == term or (len(term) >= 4 and w.startswith(term)) for w in doc)

    n = len(sentences)
    weight = {
        t: math.log((n + 1) / (sum(matches(t, d) for d in docs) + 1)) + 0.1 for t in terms
    }
    scored = sorted(
        ((sum(weight[t] for t in terms if matches(t, d)), -len(s), s) for s, d in zip(sentences, docs)),
        reverse=True,
    )
    return [s for score, _, s in scored[:top] if score > 0]
