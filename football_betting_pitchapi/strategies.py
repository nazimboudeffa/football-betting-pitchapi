"""Chargement des strategies utilisateur (copie/adaptée)."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

STRATEGY_DIR_NAME = "user_strategies"

Evaluate = Callable[[dict, dict | None], list[dict]]
Analyze = Callable[..., dict]
REQUIRED_FIELDS = ("label", "prob", "odd")
MARKET_LABELS = {
    "home": "Victoire domicile",
    "draw": "Match nul",
    "away": "Victoire exterieur",
    "over25": "Plus de 2.5 buts",
    "under25": "Moins de 2.5 buts",
    "btts_yes": "Les deux equipes marquent",
    "btts_no": "Les deux equipes ne marquent pas",
}


@dataclass(frozen=True)
class Strategy:
    id: str
    name: str
    description: str
    evaluate: Evaluate
    analyze: Analyze | None = None

    def run(self, probabilities: dict, context: dict | None = None) -> list[dict]:
        raw = self.evaluate(probabilities, context or {})
        rows: list[dict] = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            if not all(field in item for field in REQUIRED_FIELDS):
                continue
            try:
                row = {
                    **item,
                    "prob": float(item["prob"]),
                    "odd": float(item["odd"]),
                }
            except (TypeError, ValueError):
                continue
            row.setdefault("fair_odd", None)
            row.setdefault("signal", None)
            row.setdefault("highlight", False)
            rows.append(row)
        return rows


@dataclass(frozen=True)
class StrategyCatalog:
    strategies: tuple[Strategy, ...] = ()
    errors: tuple[str, ...] = ()

    def get(self, strategy_id: str) -> Strategy | None:
        for strategy in self.strategies:
            if strategy.id == strategy_id:
                return strategy
        return self.strategies[0] if self.strategies else None

    def probability_model(self) -> Strategy | None:
        for strategy in self.strategies:
            if strategy.analyze is not None:
                return strategy
        return None


def model_odds(probabilities: dict) -> list[dict]:
    results: list[dict] = []
    for key, label in MARKET_LABELS.items():
        prob = probabilities.get(key)
        if prob is None or prob <= 0:
            continue
        fair = round(1.0 / float(prob), 3)
        results.append(
            {
                "key": key,
                "label": label,
                "prob": round(float(prob), 4),
                "fair_odd": fair,
                "odd": fair,
            }
        )
    return results


def base_rows(probabilities: dict) -> list[dict]:
    rows = model_odds(probabilities)
    for row in rows:
        row["signal"] = None
        row["highlight"] = False
    return rows


def strategies_dir(config_root: Path) -> Path:
    return Path(config_root) / STRATEGY_DIR_NAME


def _load_module(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Import de module impossible pour {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def load_strategies(directory: Path) -> StrategyCatalog:
    directory = Path(directory)
    if not directory.is_dir():
        return StrategyCatalog()

    directory_str = str(directory.resolve())
    if directory_str not in sys.path:
        sys.path.insert(0, directory_str)

    strategies: list[Strategy] = []
    errors: list[str] = []
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            if not path.read_text(encoding="utf-8").strip():
                continue
        except OSError:
            pass
        module_name = f"_user_strategy_{path.stem}"
        try:
            module = _load_module(path, module_name)
            name = getattr(module, "NAME", None)
            evaluate = getattr(module, "evaluate", None)
            if not isinstance(name, str) or not name.strip():
                raise ValueError("NAME manquant ou invalide")
            if not callable(evaluate):
                raise ValueError("fonction evaluate() manquante")
            analyze = getattr(module, "analyze", None)
            if analyze is not None and not callable(analyze):
                raise ValueError("analyze() present mais non appelable")
            strategies.append(
                Strategy(
                    id=path.stem,
                    name=name.strip(),
                    description=str(getattr(module, "DESCRIPTION", "") or ""),
                    evaluate=evaluate,
                    analyze=analyze,
                )
            )
        except Exception as exc:
            errors.append(f"{path.name} : {exc}")

    return StrategyCatalog(tuple(strategies), tuple(errors))
