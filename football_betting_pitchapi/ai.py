"""Analyse IA via Ollama local (optionnel)."""

from __future__ import annotations

import json
from typing import Any

import requests


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_PROMPT = (
    "Analyse ce match en te basant uniquement sur les donnees ci-dessous. "
    "Prends en compte la forme recente des equipes (champ 'teams_form.form', ex: V/N/D) et leur classement "
    "(rangs, context de classement) quand ils sont fournis. "
    "Decris les probabilites du modele, compare les cotes estimees, "
    "et rappelle qu'aucun resultat n'est garanti. Ne donne pas de conseil de pari."
)
LIST_TIMEOUT = 5.0
ASK_TIMEOUT = 300.0


class AiError(Exception):
    pass


def normalize_url(url: str | None) -> str:
    value = (url or "").strip().rstrip("/")
    return value or DEFAULT_OLLAMA_URL


def build_context(analysis: dict) -> str:
    payload: dict[str, Any] = analysis
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def list_models(base_url: str | None = None, timeout: float = LIST_TIMEOUT) -> list[str]:
    root = normalize_url(base_url)
    try:
        response = requests.get(f"{root}/api/tags", timeout=timeout)
        response.raise_for_status()
    except requests.ConnectionError as exc:
        raise AiError(f"Ollama n'est pas joignable sur {root}. Lancez `ollama serve`.") from exc
    except requests.Timeout as exc:
        raise AiError(f"Ollama ({root}) met trop de temps a repondre.") from exc
    except requests.RequestException as exc:
        raise AiError(f"Impossible de contacter Ollama : {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise AiError("Reponse Ollama invalide pour la liste des modeles.") from exc

    names: list[str] = []
    for item in payload.get("models") or []:
        name = item.get("name") or item.get("model")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return sorted(set(names))


def ask_ollama(
    prompt: str,
    model: str,
    base_url: str | None = None,
    timeout: float = ASK_TIMEOUT,
) -> str:
    root = normalize_url(base_url)
    model_name = (model or "").strip()
    if not model_name:
        raise AiError("Choisissez un modele Ollama avant l'analyse.")

    body = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    try:
        response = requests.post(f"{root}/api/chat", json=body, timeout=timeout)
        response.raise_for_status()
    except requests.ConnectionError as exc:
        raise AiError(f"Ollama n'est pas joignable sur {root}. Lancez `ollama serve`.") from exc
    except requests.Timeout as exc:
        raise AiError("Ollama met trop de temps a repondre. Reessayez.") from exc
    except requests.RequestException as exc:
        raise AiError(f"Impossible de contacter Ollama : {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise AiError("Reponse Ollama invalide.") from exc

    content = (payload.get("message") or {}).get("content") or payload.get("response") or ""
    if not str(content).strip():
        raise AiError("Ollama a renvoye une reponse vide.")
    return str(content).strip()
