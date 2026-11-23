# Football Betting Matrix (PitchAPI)

Application PyQt6 pour afficher les matchs, calculer des probabilités/cotes via les stratégies locales, et lancer une analyse IA optionnelle avec Ollama.

## Source de données

- **Uniquement** [PitchAPI](https://pitchapi.dev) (`https://api.pitchapi.dev/v1`)
- Aucune donnée `openfootball`
- Aucune donnée `football-data.co.uk`

## Périmètre

- Saisons: `2025/2026`, `2026/2027`
- Ligues: les 5 grands championnats européens
  - Premier League (ENG)
  - La Liga (ESP)
  - Bundesliga (GER)
  - Serie A (ITA)
  - Ligue 1 (FRA)

## Prérequis

- Python 3.10+ recommandé
- Une clé API PitchAPI

## Installation

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuration

Définir la clé PitchAPI dans l'environnement:

```powershell
$env:PITCHAPI_KEY="pk_live_xxx"
```

L'application lit aussi `PITCHAPI_API_KEY`, `PITCH_API_KEY` ou `PITCH_KEY` en fallback.

## Lancement

```bash
python main.py
```

## Fonctionnement

- Chargement des 5 ligues cibles depuis PitchAPI.
- Chargement des matchs pour la saison sélectionnée (`status=all`).
- Les stratégies dans `user_strategies/` calculent probabilités/cotes à partir des matchs chargés.
- Panneau d'info match affiche les métadonnées PitchAPI (pas de bookmakers football-data.co.uk).
- Bouton d'analyse IA via Ollama local (optionnel).

## Notes

- Si la clé API est absente/invalide, l'UI affiche une erreur PitchAPI.
- Les stratégies existantes sont conservées et réutilisées avec les données normalisées PitchAPI.
