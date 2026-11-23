"""Client minimal pour pitchapi.dev.

Ne récupère que des données PitchAPI (pas d'openfootball, pas de football-data.co.uk).
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    except OSError:
        return


_load_dotenv()

BASE_URL = "https://api.pitchapi.dev/v1"

# Cache simple en mémoire: (method, url, params_tuple) -> (ts, data)
_CACHE: Dict[Tuple[str, str, Tuple[Tuple[str, str], ...]], Tuple[float, Any]] = {}
_CACHE_TTL_SECONDS = 60 * 30

# Les 5 grands championnats européens (noms PitchAPI)
TARGET_LEAGUES = [
    ("Premier League", {"ENG", "GB-ENG", "EN"}, {"premier league"}),
    ("LaLiga", {"ESP", "ES"}, {"laliga", "la liga"}),
    ("Bundesliga", {"DEU", "GER", "DE"}, {"bundesliga"}),
    ("Serie A", {"ITA", "IT"}, {"serie a"}),
    ("Ligue 1", {"FRA", "FR"}, {"ligue 1"}),
]

def _season_code_to_label(value: str) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "/" in raw:
        parts = raw.split("/")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return f"{int(parts[0])}/{int(parts[1])}"
        return raw
    if raw.isdigit():
        year = int(raw)
        # Convention .env: 2026 => saison 2026/2027
        if year >= 1900:
            return f"{year}/{year + 1}"
    return None


def get_configured_seasons() -> List[str]:
    raw = os.getenv("PITCHAPI_SEASONS", "").strip()
    seasons: List[str] = []
    if raw:
        for part in raw.replace(";", ",").split(","):
            label = _season_code_to_label(part)
            if label and label not in seasons:
                seasons.append(label)
    if not seasons:
        seasons = ["2025/2026", "2026/2027"]
    return seasons


def get_default_season() -> str:
    seasons = get_configured_seasons()
    raw_default = os.getenv("APP_DEFAULT_SEASON", "").strip()
    mapped = _season_code_to_label(raw_default)
    if mapped and mapped in seasons:
        return mapped
    if mapped:
        return mapped

    # Fallback: saison en cours selon la date actuelle (saison européenne commence en été)
    now = datetime.now()
    start_year = now.year if now.month >= 7 else now.year - 1
    current = f"{start_year}/{start_year + 1}"
    if current in seasons:
        return current
    return seasons[0]


def get_app_timezone() -> str:
    return os.getenv("APP_TIMEZONE", "Europe/Paris").strip() or "Europe/Paris"


# Compatibilité interne
TARGET_SEASONS = get_configured_seasons()


class PitchAPIError(RuntimeError):
    pass


def get_api_key() -> str:
    key = (
        os.getenv("PITCHAPI_KEY")
        or os.getenv("PITCHAPI_API_KEY")
        or os.getenv("PITCH_API_KEY")
        or os.getenv("PITCH_KEY")
        or ""
    ).strip()
    if not key:
        raise PitchAPIError(
            "Clé API PitchAPI manquante. Définis la variable d'environnement PITCHAPI_KEY."
        )
    return key


def _request(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    params = params or {}
    url = f"{BASE_URL}{path}"
    key = get_api_key()
    cache_key = ("GET", url, tuple(sorted((str(k), str(v)) for k, v in params.items() if v is not None)))
    now = time.time()
    if cache_key in _CACHE:
        ts, data = _CACHE[cache_key]
        if now - ts < _CACHE_TTL_SECONDS:
            return data

    timeout_ms = os.getenv("PITCHAPI_TIMEOUT_MS", "").strip()
    try:
        timeout_s = max(1.0, float(timeout_ms) / 1000.0) if timeout_ms else 30.0
    except ValueError:
        timeout_s = 30.0
    resp = requests.get(url, headers={"X-API-KEY": key}, params=params, timeout=timeout_s)
    if resp.status_code >= 400:
        try:
            payload = resp.json()
        except Exception:
            payload = {"error": {"message": resp.text}}
        err = payload.get("error") or {}
        msg = err.get("message") or err.get("code") or resp.text
        raise PitchAPIError(f"PitchAPI {resp.status_code}: {msg}")

    payload = resp.json()
    data = payload.get("data", payload)
    _CACHE[cache_key] = (now, data)
    return data


def list_leagues() -> List[Dict[str, Any]]:
    data = _request("/leagues")
    leagues = data.get("leagues", data) if isinstance(data, dict) else data
    return leagues if isinstance(leagues, list) else []


def _league_matches_target(
    league: Dict[str, Any], target_name: str, countries: set[str], aliases: set[str]
) -> bool:
    name = str(league.get("name") or "").strip().lower()
    if name not in aliases and name != target_name.lower():
        return False
    country = str(league.get("country_code") or league.get("country") or "").strip().upper()
    # Si country_code est absent/inconnu, on accepte sur le nom/alias car la liste est ciblée.
    if not country:
        return True
    return country in countries


def get_target_leagues() -> List[Dict[str, Any]]:
    leagues = list_leagues()
    selected: List[Dict[str, Any]] = []
    for target_name, countries, aliases in TARGET_LEAGUES:
        match = None
        for league in leagues:
            if _league_matches_target(league, target_name, countries, aliases):
                match = league
                break
        if match is None:
            # fallback nom/alias seul
            for league in leagues:
                name = str(league.get("name") or "").strip().lower()
                if name == target_name.lower() or name in aliases:
                    match = league
                    break
        if match:
            selected.append(match)
    return selected


def get_league_matches(league_id: str, season: str, status: str = "all") -> List[Dict[str, Any]]:
    data = _request(f"/leagues/{league_id}/matches", params={"season": season, "status": status})
    if isinstance(data, dict):
        matches = data.get("matches", [])
        league_info = data.get("league", {})
    else:
        matches = data
        league_info = {}
    out = []
    for m in matches or []:
        out.append(normalize_match(m, league_info=league_info, season=season))
    return out


def normalize_match(match: Dict[str, Any], league_info: Optional[Dict[str, Any]] = None, season: str = "") -> Dict[str, Any]:
    """Normalise un match PitchAPI vers la forme attendue par l'UI/stratégies existantes."""
    home = match.get("home_team") or {}
    away = match.get("away_team") or {}
    home_name = home.get("name") or match.get("home_name") or "Home"
    away_name = away.get("name") or match.get("away_name") or "Away"
    home_id = home.get("id")
    away_id = away.get("id")

    score_home = match.get("score_home")
    score_away = match.get("score_away")
    ft = None
    if score_home is not None and score_away is not None:
        try:
            ft = [int(score_home), int(score_away)]
        except Exception:
            ft = None

    date_raw = match.get("date") or ""
    time_utc = match.get("time_utc") or ""
    date = str(date_raw)[:10]
    time_str = ""
    if time_utc and "T" in str(time_utc):
        try:
            time_str = str(time_utc).split("T", 1)[1].replace("Z", "")[:5]
        except Exception:
            time_str = ""

    status = match.get("status")
    round_name = match.get("round_name") or match.get("round")

    normalized = {
        # Champs utilisés par l'UI existante
        "date": date,
        "time": time_str,
        "team1": home_name,
        "team2": away_name,
        "round": round_name,
        "score": {"ft": ft} if ft else None,
        # Champs compatibles stratégies/openfootball-like
        "fixture": {
            "id": match.get("id"),
            "date": time_utc or date,
            "status": {"short": status},
        },
        "teams": {
            "home": {"id": home_id, "name": home_name},
            "away": {"id": away_id, "name": away_name},
        },
        "goals": {"home": score_home, "away": score_away},
        # Contexte PitchAPI brut
        "pitchapi": {
            "match": match,
            "league": league_info or {},
            "season": season,
        },
    }
    return normalized
