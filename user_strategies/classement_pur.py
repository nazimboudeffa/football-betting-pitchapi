"""Strategie Classement Pur : probabilites basees sur le rang au classement (sans Poisson).

Chaque strategie est autonome : son modele et sa conversion sont dans ce seul fichier.
Le classement est reconstruit a partir des resultats de la saison (avant la date du match).
"""

from __future__ import annotations

import math
from typing import Iterable

from football_betting_pitchapi.strategies import base_rows

NAME = "Classement Pur"
DESCRIPTION = (
    "Probabilites 1N2 deduites de l'ecart de rang au classement, "
    "over 2.5 et BTTS par frequences observees, cote = 1 / prob (sans marge)."
)

RANK_WEIGHT = 1.2  # impact de l'ecart de rang sur victoire domicile / exterieur
DRAW_WEIGHT = 0.6  # baisse de la probabilite de nul quand l'ecart de rang grandit
FULL_CONFIDENCE_MATCHES = 10  # matchs a partir desquels le rang est pleinement pris en compte
PRIOR_MATCHES = 8.0  # poids de la moyenne de la ligue pour les frequences par equipe

# Valeurs par defaut si aucune donnee n'est disponible.
DEFAULT_RATES = {"home": 0.44, "draw": 0.26, "away": 0.30, "over25": 0.52, "btts": 0.50}


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _team_id(value: object) -> int | None:
    """Convertit un identifiant d'equipe sans faire echouer l'analyse sur une donnee sale."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


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


def _team_bucket() -> dict:
    return {
        "name": "",
        "played": 0,
        "home_played": 0,
        "away_played": 0,
        "points": 0,
        "gf": 0,
        "ga": 0,
        "over25": 0,
        "btts": 0,
        "matches": [],
    }


def build_table(fixtures: Iterable[dict], before_date: str | None = None) -> dict:
    """Construit le classement et les frequences de la ligue avant une date donnee."""
    teams: dict[int, dict] = {}
    matches = 0
    home_wins = draws = away_wins = over25 = btts = 0

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
        home_id = _team_id(home.get("id"))
        away_id = _team_id(away.get("id"))
        if home_id is None or away_id is None:
            continue

        matches += 1
        is_over = home_goals + away_goals > 2
        is_btts = home_goals > 0 and away_goals > 0
        over25 += is_over
        btts += is_btts
        if home_goals > away_goals:
            home_wins += 1
        elif home_goals == away_goals:
            draws += 1
        else:
            away_wins += 1

        for team_id, name, scored, conceded, is_home in (
            (home_id, home.get("name", ""), home_goals, away_goals, True),
            (away_id, away.get("name", ""), away_goals, home_goals, False),
        ):
            bucket = teams.setdefault(team_id, _team_bucket())
            bucket["name"] = name or bucket["name"]
            bucket["played"] += 1
            if is_home:
                bucket["home_played"] += 1
            else:
                bucket["away_played"] += 1
            bucket["gf"] += scored
            bucket["ga"] += conceded
            bucket["points"] += 3 if scored > conceded else 1 if scored == conceded else 0
            bucket["over25"] += is_over
            bucket["btts"] += is_btts
            bucket["matches"].append({"date": date, "scored": scored, "conceded": conceded})

    for bucket in teams.values():
        bucket["matches"].sort(key=lambda match: match["date"])
        bucket["form"] = [
            "V" if match["scored"] > match["conceded"] else "N" if match["scored"] == match["conceded"] else "D"
            for match in bucket["matches"][-5:]
        ]

    # Classement : points par match, puis difference de buts par match, puis buts marques par match.
    # L'identifiant sert de dernier critere pour que les rangs soient deterministes.
    ranking = sorted(
        teams,
        key=lambda tid: (
            -teams[tid]["points"] / teams[tid]["played"],
            -(teams[tid]["gf"] - teams[tid]["ga"]) / teams[tid]["played"],
            -teams[tid]["gf"] / teams[tid]["played"],
            tid,
        ),
    )
    for position, team_id in enumerate(ranking, start=1):
        teams[team_id]["rank"] = position

    if matches:
        rates = {
            "home": home_wins / matches,
            "draw": draws / matches,
            "away": away_wins / matches,
            "over25": over25 / matches,
            "btts": btts / matches,
        }
    else:
        rates = dict(DEFAULT_RATES)

    return {"teams": teams, "matches": matches, "rates": rates, "n_teams": len(teams)}


def _rank_strength(rank: int, n_teams: int) -> float:
    """Convertit un rang en force dans [-1, 1] (1er = +1, dernier = -1)."""
    if n_teams < 2:
        return 0.0
    return (n_teams + 1 - 2 * rank) / (n_teams - 1)


def _blended_rate(team_count: int, played: int, league_rate: float) -> float:
    """Frequence d'une equipe tiree vers la moyenne de la ligue si peu de matchs."""
    return (team_count + PRIOR_MATCHES * league_rate) / (played + PRIOR_MATCHES)


def _empty_bucket(name: str) -> dict:
    bucket = _team_bucket()
    bucket.update({"name": name, "form": [], "rank": None})
    return bucket


def analyze_match(
    fixtures: Iterable[dict],
    home_id: int | None,
    away_id: int | None,
    home_name: str,
    away_name: str,
    before_date: str | None = None,
) -> dict:
    """Produit les probabilites du match a partir du classement."""
    table = build_table(fixtures, before_date=before_date)
    teams = table["teams"]
    rates = table["rates"]
    n_teams = table["n_teams"]

    parsed_home_id = _team_id(home_id)
    parsed_away_id = _team_id(away_id)
    home = teams.get(parsed_home_id) if parsed_home_id is not None else None
    away = teams.get(parsed_away_id) if parsed_away_id is not None else None
    known_home = home is not None
    known_away = away is not None
    home = home or _empty_bucket(home_name)
    away = away or _empty_bucket(away_name)

    # Ecart de rang, attenue tant que les equipes ont peu joue.
    if known_home and known_away:
        gap = (
            _rank_strength(home["rank"], n_teams) - _rank_strength(away["rank"], n_teams)
        ) / 2
        confidence = min(1.0, min(home["played"], away["played"]) / FULL_CONFIDENCE_MATCHES)
        gap *= confidence
    else:
        gap = 0.0

    # 1N2 : la base est la repartition de la ligue, deformee par l'ecart de rang.
    w_home = rates["home"] * math.exp(RANK_WEIGHT * gap)
    w_away = rates["away"] * math.exp(-RANK_WEIGHT * gap)
    w_draw = rates["draw"] * math.exp(-DRAW_WEIGHT * abs(gap))
    total = w_home + w_draw + w_away
    p_home, p_draw, p_away = w_home / total, w_draw / total, w_away / total

    # Over 2.5 et BTTS : moyenne des frequences des deux equipes (tirees vers la ligue).
    def pair_rate(key: str) -> float:
        values = []
        for bucket, known in ((home, known_home), (away, known_away)):
            if known:
                values.append(_blended_rate(bucket[key], bucket["played"], rates[key]))
            else:
                values.append(rates[key])
        return sum(values) / 2

    p_over25 = pair_rate("over25")
    p_btts = pair_rate("btts")

    sample = min(
        [bucket["played"] for bucket, known in ((home, known_home), (away, known_away)) if known]
        or [0]
    )
    if sample >= 12 and known_home and known_away:
        reliability = "bonne"
    elif sample >= 5 and known_home and known_away:
        reliability = "moyenne"
    else:
        reliability = "faible"

    def team_summary(bucket: dict, known: bool) -> dict:
        played = bucket.get("played", 0)
        return {
            "name": bucket.get("name"),
            "known": known,
            "rank": bucket.get("rank"),
            "points": bucket.get("points", 0),
            "points_per_match": _round(bucket.get("points", 0) / played) if played else 0.0,
            "played": played,
            "home_played": bucket.get("home_played", 0),
            "away_played": bucket.get("away_played", 0),
            "goals_for": bucket.get("gf", 0),
            "goals_against": bucket.get("ga", 0),
            "goal_diff": bucket.get("gf", 0) - bucket.get("ga", 0),
            "form": bucket.get("form", []),
        }

    return {
        "model_name": "Classement Pur",
        "probabilities": {
            "home": _round(p_home),
            "draw": _round(p_draw),
            "away": _round(p_away),
            "over25": _round(p_over25),
            "under25": _round(1 - p_over25),
            "btts_yes": _round(p_btts),
            "btts_no": _round(1 - p_btts),
        },
        # Ce modele ne produisant pas de matrice de scores, la liste est vide.
        "scores": [],
        "rank_home": home.get("rank"),
        "rank_away": away.get("rank"),
        "n_teams": n_teams,
        "rank_gap": _round(gap),
        "sample_matches": table["matches"],
        "reliability": reliability,
        "known_home": known_home,
        "known_away": known_away,
        "home": team_summary(home, known_home),
        "away": team_summary(away, known_away),
        "league_rates": {key: _round(value) for key, value in rates.items()},
        "before_date": before_date,
    }


# Nom attendu par le chargeur de strategies utilisateur.
analyze = analyze_match


def evaluate(probabilities: dict, context: dict | None = None) -> list[dict]:
    rows = base_rows(probabilities)
    for row in rows:
        row["signal"] = "Classement"
    return rows
