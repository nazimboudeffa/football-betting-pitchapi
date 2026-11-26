# Football Betting Matrix (PitchAPI)

Application PyQt6 pour afficher les matchs, calculer des probabilités/cotes via les stratégies locales, et lancer une analyse IA optionnelle avec llama.app.

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

### Analyse IA (llama.app)

L'analyse IA est optionnelle et passe par l'API locale compatible OpenAI de [llama.app](https://llama.app) (`llama serve`, par défaut sur `localhost:9931`) :

```powershell
llama serve -hf ggml-org/gemma-4-e4b-it-GGUF:Q4_0
```

Configuration optionnelle (variables d'environnement ou `.env`) :

- `LLAMA_APP_URL` : URL du serveur (défaut `http://localhost:9931`)
- `LLAMA_APP_API_KEY` : clé Bearer si le serveur a été lancé avec `--api-key`

Les modèles proposés dans l'interface sont ceux renvoyés par `GET /v1/models`.

## Lancement

```bash
python main.py
```

## Fonctionnement

- Chargement des 5 ligues cibles depuis PitchAPI.
- Chargement des matchs pour la saison sélectionnée (`status=all`).
- Les stratégies dans `user_strategies/` calculent probabilités/cotes à partir des matchs chargés.
- Panneau d'info match affiche les métadonnées PitchAPI (pas de bookmakers football-data.co.uk).
- Bouton d'analyse IA via llama.app local (optionnel).

## Notes

- Si la clé API est absente/invalide, l'UI affiche une erreur PitchAPI.
- Les stratégies existantes sont conservées et réutilisées avec les données normalisées PitchAPI.
