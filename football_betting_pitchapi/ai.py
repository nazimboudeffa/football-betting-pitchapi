"""Analyse IA via llama.app (serveur local compatible OpenAI, optionnel)."""

from __future__ import annotations

import json
import os
from typing import Any

import requests


DEFAULT_LLAMA_APP_URL = "http://localhost:9931"
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


def normalize_url(url: str | None = None) -> str:
    value = (url or os.getenv("LLAMA_APP_URL", "") or "").strip().rstrip("/")
    return value or DEFAULT_LLAMA_APP_URL


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("LLAMA_APP_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str) and error.strip():
            return error.strip()
    except ValueError:
        pass
    return ""


def build_context(analysis: dict) -> str:
    payload: dict[str, Any] = analysis
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def list_models(base_url: str | None = None, timeout: float = LIST_TIMEOUT) -> list[str]:
    root = normalize_url(base_url)
    try:
        response = requests.get(f"{root}/v1/models", headers=_headers(), timeout=timeout)
        response.raise_for_status()
    except requests.ConnectionError as exc:
        raise AiError(f"llama.app n'est pas joignable sur {root}. Lancez `llama serve`.") from exc
    except requests.Timeout as exc:
        raise AiError(f"llama.app ({root}) met trop de temps a repondre.") from exc
    except requests.RequestException as exc:
        detail = _error_detail(getattr(exc, "response", None))
        raise AiError(f"Impossible de contacter llama.app : {detail or exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise AiError("Reponse llama.app invalide pour la liste des modeles.") from exc

    names: list[str] = []
    for item in payload.get("data") or []:
        model_id = item.get("id") if isinstance(item, dict) else None
        if isinstance(model_id, str) and model_id.strip():
            names.append(model_id.strip())
    return sorted(set(names))


def ask_llama_app(
    prompt: str,
    model: str,
    base_url: str | None = None,
    timeout: float = ASK_TIMEOUT,
) -> str:
    root = normalize_url(base_url)
    model_name = (model or "").strip()
    if not model_name:
        raise AiError("Choisissez un modele llama.app avant l'analyse.")

    body = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    try:
        response = requests.post(
            f"{root}/v1/chat/completions", json=body, headers=_headers(), timeout=timeout
        )
        response.raise_for_status()
    except requests.ConnectionError as exc:
        raise AiError(f"llama.app n'est pas joignable sur {root}. Lancez `llama serve`.") from exc
    except requests.Timeout as exc:
        raise AiError("llama.app met trop de temps a repondre. Reessayez.") from exc
    except requests.RequestException as exc:
        detail = _error_detail(getattr(exc, "response", None))
        raise AiError(f"Impossible de contacter llama.app : {detail or exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise AiError("Reponse llama.app invalide.") from exc

    choices = payload.get("choices") or []
    first = choices[0] if choices and isinstance(choices[0], dict) else {}
    content = (first.get("message") or {}).get("content") or first.get("text") or ""
    if not str(content).strip():
        raise AiError("llama.app a renvoye une reponse vide.")
    return str(content).strip()
