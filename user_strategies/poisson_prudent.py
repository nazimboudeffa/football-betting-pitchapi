"""Strategie prudente autonome : modele Poisson + cote avec marge.

Chaque strategie est autonome : son modele et sa conversion sont dans ce seul fichier.
"""

from __future__ import annotations

import math
from typing import Iterable

from football_betting_pitchapi.strategies import base_rows

NAME = "Poisson Prudent"
DESCRIPTION = (
    "Marches >= 45 % de probabilite, cote juste + 5 % de marge "
    "(modele Poisson inclus)."
)

MAX_GOALS = 9


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _shrink(ratio: float, sample: int, prior_weight: float = 6.0) -> float:
    """Regularisation vers 1 pour eviter les extremes sur petits echantillons."""
    if sample <= 0:
        return 1.0
    return (ratio * sample + prior_weight) / (sample + prior_weight)


def _team_bucket() -> dict:
    return {
        "name": "",
        "played": 0,
        "gf": 0,
        "ga": 0,
        "home_played": 0,
        "home_gf": 0,
        "home_ga": 0,
        "away_played": 0,
        "away_gf": 0,
        "away_ga": 0,
        "matches": [],
    }


def _goal_pair(fixture: dict) -> tuple[int, int] | None:
    goals = fixture.get("goals") or {}
    home = goals.get("home")
    away = goals.get("away")
    if home is None or away is None:
        return None
    try:
        return int(home), int(away)
    except (TypeError, ValueError):
        return None


def build_season_stats(fixtures: Iterable[dict], before_date: str | None = None) -> dict:
    """Agrege les statistiques d'une saison, eventuellement avant une date donnee."""
    teams: dict[int, dict] = {}
    matches = 0
    total_home_goals = 0
    total_away_goals = 0
    usable: list[dict] = []

    for fixture in fixtures:
        fixture_block = fixture.get("fixture") or {}
        date = fixture_block.get("date") or fixture.get("date") or ""
        if before_date and date[:10] >= before_date:
            continue
        pair = _goal_pair(fixture)
        if pair is None:
            continue
        home_goals, away_goals = pair
        teams_block = fixture.get("teams") or {
            "home": fixture.get("home") or {},
            "away": fixture.get("away") or {},
        }
        home = teams_block.get("home") or {}
        away = teams_block.get("away") or {}
        home_id = home.get("id")
        away_id = away.get("id")
        if home_id is None or away_id is None:
            continue

        matches += 1
        total_home_goals += home_goals
        total_away_goals += away_goals
        usable.append(fixture)

        for team_id, name, scored, conceded, is_home in (
            (home_id, home.get("name", ""), home_goals, away_goals, True),
            (away_id, away.get("name", ""), away_goals, home_goals, False),
        ):
            bucket = teams.setdefault(int(team_id), _team_bucket())
            bucket["name"] = name or bucket["name"]
            bucket["played"] += 1
            bucket["gf"] += scored
            bucket["ga"] += conceded
            if is_home:
                bucket["home_played"] += 1
                bucket["home_gf"] += scored
                bucket["home_ga"] += conceded
            else:
                bucket["away_played"] += 1
                bucket["away_gf"] += scored
                bucket["away_ga"] += conceded
            bucket["matches"].append(
                {
                    "date": date,
                    "opponent": away.get("name") if is_home else home.get("name"),
                    "scored": scored,
                    "conceded": conceded,
                    "home": is_home,
                }
            )

    avg_home = total_home_goals / matches if matches else 1.35
    avg_away = total_away_goals / matches if matches else 1.15

    for bucket in teams.values():
        bucket["matches"].sort(key=lambda m: m["date"])
        bucket["form"] = []
        for match in reversed(bucket["matches"][-5:]):
            if match["scored"] > match["conceded"]:
                bucket["form"].insert(0, "V")
            elif match["scored"] == match["conceded"]:
                bucket["form"].insert(0, "N")
            else:
                bucket["form"].insert(0, "D")

        hp = bucket["home_played"]
        ap = bucket["away_played"]
        bucket["attack_home"] = _shrink((bucket["home_gf"] / hp) / avg_home, hp) if hp else 1.0
        bucket["defense_home"] = _shrink((bucket["home_ga"] / hp) / avg_away, hp) if hp else 1.0
        bucket["attack_away"] = _shrink((bucket["away_gf"] / ap) / avg_away, ap) if ap else 1.0
        bucket["defense_away"] = _shrink((bucket["away_ga"] / ap) / avg_home, ap) if ap else 1.0

    return {
        "teams": teams,
        "matches": matches,
        "avg_home": avg_home,
        "avg_away": avg_away,
        "total_home_goals": total_home_goals,
        "total_away_goals": total_away_goals,
        "fixtures": usable,
    }


def poisson_matrix(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = MAX_GOALS,
) -> list[list[float]]:
    home_probs = [
        math.exp(-lambda_home) * lambda_home**k / math.factorial(k)
        for k in range(max_goals + 1)
    ]
    away_probs = [
        math.exp(-lambda_away) * lambda_away**k / math.factorial(k)
        for k in range(max_goals + 1)
    ]
    matrix = [[hp * ap for ap in away_probs] for hp in home_probs]

    # Redistribue la masse tronquee pour que la somme reste egale a 1.
    total = sum(sum(row) for row in matrix)
    if total > 0:
        matrix = [[value / total for value in row] for row in matrix]
    return matrix


def probabilities_from_matrix(matrix: list[list[float]]) -> dict:
    p_home = p_draw = p_away = 0.0
    p_over25 = p_btts = 0.0
    scores: list[dict] = []
    for h, row in enumerate(matrix):
        for a, prob in enumerate(row):
            if h > a:
                p_home += prob
            elif h == a:
                p_draw += prob
            else:
                p_away += prob
            if h + a > 2.5:
                p_over25 += prob
            if h > 0 and a > 0:
                p_btts += prob
            scores.append({"score": f"{h}-{a}", "home": h, "away": a, "prob": prob})

    scores.sort(key=lambda s: s["prob"], reverse=True)
    return {
        "home": p_home,
        "draw": p_draw,
        "away": p_away,
        "over25": p_over25,
        "under25": 1 - p_over25,
        "btts_yes": p_btts,
        "btts_no": 1 - p_btts,
        "scores": scores[:8],
    }


def _empty_bucket(name: str) -> dict:
    bucket = _team_bucket()
    bucket.update(
        {
            "name": name,
            "attack_home": 1.0,
            "defense_home": 1.0,
            "attack_away": 1.0,
            "defense_away": 1.0,
            "form": [],
        }
    )
    return bucket


def analyze_match(
    fixtures: Iterable[dict],
    home_id: int | None,
    away_id: int | None,
    home_name: str,
    away_name: str,
    before_date: str | None = None,
) -> dict:
    """Produit les probabilites du match a partir des resultats de la saison."""
    stats = build_season_stats(fixtures, before_date=before_date)
    teams = stats["teams"]
    home = teams.get(int(home_id)) if home_id is not None else None
    away = teams.get(int(away_id)) if away_id is not None else None
    known_home = home is not None
    known_away = away is not None
    home = home or _empty_bucket(home_name)
    away = away or _empty_bucket(away_name)

    lambda_home = stats["avg_home"] * home.get("attack_home", 1.0) * away.get("defense_away", 1.0)
    lambda_away = stats["avg_away"] * away.get("attack_away", 1.0) * home.get("defense_home", 1.0)
    lambda_home = min(5.5, max(0.15, lambda_home))
    lambda_away = min(5.5, max(0.15, lambda_away))

    matrix = poisson_matrix(lambda_home, lambda_away)
    probs = probabilities_from_matrix(matrix)

    sample_sizes = []
    if known_home:
        sample_sizes.append(home["played"])
    if known_away:
        sample_sizes.append(away["played"])
    sample = min(sample_sizes) if sample_sizes else 0
    if sample >= 12 and known_home and known_away:
        reliability = "bonne"
    elif sample >= 5 and known_home and known_away:
        reliability = "moyenne"
    else:
        reliability = "faible"

    def team_summary(bucket: dict, known: bool) -> dict:
        return {
            "name": bucket.get("name"),
            "known": known,
            "played": bucket.get("played", 0),
            "goals_for": bucket.get("gf", 0),
            "goals_against": bucket.get("ga", 0),
            "home_played": bucket.get("home_played", 0),
            "away_played": bucket.get("away_played", 0),
            "form": bucket.get("form", []),
            "attack_home": _round(bucket.get("attack_home", 1.0), 3),
            "defense_home": _round(bucket.get("defense_home", 1.0), 3),
            "attack_away": _round(bucket.get("attack_away", 1.0), 3),
            "defense_away": _round(bucket.get("defense_away", 1.0), 3),
        }

    return {
        "model_name": "Poisson Prudent",
        "probabilities": {
            "home": _round(probs["home"]),
            "draw": _round(probs["draw"]),
            "away": _round(probs["away"]),
            "over25": _round(probs["over25"]),
            "under25": _round(probs["under25"]),
            "btts_yes": _round(probs["btts_yes"]),
            "btts_no": _round(probs["btts_no"]),
        },
        "scores": [
            {"score": s["score"], "prob": _round(s["prob"])}
            for s in probs["scores"]
        ],
        "lambda_home": _round(lambda_home),
        "lambda_away": _round(lambda_away),
        "expected_total": _round(lambda_home + lambda_away),
        "sample_matches": stats["matches"],
        "reliability": reliability,
        "known_home": known_home,
        "known_away": known_away,
        "home": team_summary(home, known_home),
        "away": team_summary(away, known_away),
        "league_avg_home": _round(stats["avg_home"]),
        "league_avg_away": _round(stats["avg_away"]),
        "before_date": before_date,
    }


# Nom attendu par le chargeur de strategies utilisateur.
analyze = analyze_match


MIN_PROB = 0.45
MARGIN = 0.05


def evaluate(probabilities: dict, context: dict | None = None) -> list[dict]:
    rows = [row for row in base_rows(probabilities) if row["prob"] >= MIN_PROB]
    for row in rows:
        row["odd"] = round(row["fair_odd"] * (1 + MARGIN), 2)
        row["signal"] = f"Marge +{MARGIN * 100:.0f} %"
        row["highlight"] = True
    rows.sort(key=lambda row: row["odd"], reverse=True)
    return rows
