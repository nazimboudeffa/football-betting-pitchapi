"""Strategie Ratio de Rangs : le rang de l'adversaire pondere les cotes de la ligue.

Chaque strategie est autonome : son modele et sa conversion sont dans ce seul fichier.
Le classement est reconstruit a partir des resultats de la saison (avant la date du match).

Principe : un rang petit = une bonne equipe. Le ratio brut est
    rang(B) / (rang(A) + rang(B)).
Il est applique aux probabilites domicile / exterieur observees dans la ligue,
afin de conserver l'avantage du terrain. Le nul reste fixe a la frequence de la
ligue. Tant que les equipes ont peu joue, le ratio est ramene vers 0.5 (equipe
neutre) pour eviter des cotes extremes en debut de saison.
"""

from __future__ import annotations

from typing import Iterable

from football_betting_pitchapi.strategies import base_rows

NAME = "Ratio de Rangs"
DESCRIPTION = (
    "Ratio des rangs (rang adverse / somme des rangs) applique aux probabilites "
    "domicile / exterieur de la ligue, nul = frequence de la ligue, "
    "cote = 1 / prob (sans marge)."
)

PRIOR_MATCHES = 8.0  # poids de la moyenne de la ligue pour les frequences over 2.5 et BTTS
FULL_CONFIDENCE_MATCHES = 10  # matchs a partir desquels le ratio est pleinement pris en compte

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


def _blended_rate(team_count: int, played: int, league_rate: float) -> float:
    """Frequence d'une equipe tiree vers la moyenne de la ligue si peu de matchs."""
    return (team_count + PRIOR_MATCHES * league_rate) / (played + PRIOR_MATCHES)


def _empty_bucket(name: str) -> dict:
    bucket = _team_bucket()
    bucket.update({"name": name, "form": [], "rank": None})
    return bucket


def rank_ratio(rank_home: int, rank_away: int) -> float:
    """Part brute de l'equipe a domicile : rang adverse / somme des rangs (rang petit = fort)."""
    total = rank_home + rank_away
    if total <= 0:
        return 0.5
    return rank_away / total


def analyze_match(
    fixtures: Iterable[dict],
    home_id: int | None,
    away_id: int | None,
    home_name: str,
    away_name: str,
    before_date: str | None = None,
) -> dict:
    """Produit les probabilites du match a partir du ratio des rangs."""
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

    # 1N2 : nul = frequence de la ligue. Le ratio des rangs pondere les cotes
    # domicile / exterieur observees, ce qui conserve l'avantage du terrain.
    p_draw = rates["draw"]
    if known_home and known_away:
        raw_ratio = rank_ratio(home["rank"], away["rank"])
        sample = min(home["played"], away["played"])
        confidence = min(1.0, sample / FULL_CONFIDENCE_MATCHES)
        # 0.5 = equipes de force egale ; on n'applique le ratio qu'avec de l'echantillon.
        weight = 0.5 + (raw_ratio - 0.5) * confidence
    else:
        raw_ratio = 0.5
        weight = 0.5
    w_home = rates["home"] * weight
    w_away = rates["away"] * (1 - weight)
    decisive = w_home + w_away
    if decisive > 0:
        home_share = w_home / decisive
    else:
        home_share = 0.5 if not (known_home and known_away) else raw_ratio
    p_home = (1 - p_draw) * home_share
    p_away = (1 - p_draw) * (1 - home_share)

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
        "model_name": "Ratio de Rangs",
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
        "rank_ratio_home": _round(raw_ratio),
        "rank_weight": _round(weight),
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
        row["signal"] = "Ratio de rangs"
    return rows
