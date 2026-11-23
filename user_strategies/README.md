# Modeles et strategies utilisateur

Ce dossier est **hors du coeur du logiciel** : le package `football_betting_pitchapi`.
ne contient aucun calcul de probabilites. Il charge simplement les strategies
placees ici et leur demande le modele et les cotes affiches dans la page **Analyse**.

Les strategies sont detectees au demarrage, ou apres un clic sur **Recharger**
dans la page Analyse. Aucun redemarrage n'est necessaire.

## Contrat d'une strategie

Un fichier `ma_strategie.py` doit exposer :

```python
NAME = "Mon approche"                    # nom affiche dans la liste deroulante
DESCRIPTION = "Ce que fait la strategie" # texte d'aide sous la liste

def evaluate(probabilities, context=None):
    """Renvoie une liste de cotes (une par marche)."""
    ...

def analyze(fixtures, home_id, away_id, home_name, away_name, before_date=None):
    """Optionnel : renvoie les probabilites du match."""
    ...
```

- `evaluate()` est obligatoire : elle transforme les probabilites en cotes.
- `analyze()` est optionnelle : si elle est absente, le coeur utilise le premier
  modele trouve dans le dossier. Les strategies fournies l'implementent toutes.

Arguments de `evaluate()` :

- `probabilities` : `{"home": 0.51, "draw": 0.26, ...}` (probabilites du modele).
- `context` : dictionnaire reserve aux futures options (non utilise pour l'instant).

Chaque ligne renvoyee doit contenir au moins `label`, `prob` et `odd` (la cote
calculee, en decimal europeen). Les champs optionnels sont :

- `fair_odd` : cote juste de reference (`1 / prob`), affichee dans sa colonne ;
- `signal` : texte libre affiche dans la colonne « Signal » ;
- `highlight` : `True` pour mettre la ligne en evidence.

Les lignes invalides sont ignorees automatiquement.

Pour partir des cotes justes du modele sans les recalculer :

```python
from football_betting_pitchapi.strategies import base_rows

def evaluate(probabilities, context=None):
    rows = base_rows(probabilities)
    for row in rows:
        row["signal"] = "Reference"
    return rows
```

## Un fichier = une strategie autonome

Chaque fichier contient son propre modele (`analyze`) et sa propre conversion en
cotes (`evaluate`). `poisson_pur.py`, `poisson_prudent.py`, `classement_pur.py`
et `ratio_rangs.py` sont independants : aucun fichier de strategie n'importe un
autre fichier de strategie.

Le coeur ne connait aucun nom de modele : il appelle simplement `analyze()` de la
strategie active. Pour proposer un autre modele, creez un nouveau fichier avec son
propre `analyze()` et son `evaluate()`.

Un module invalide (erreur de syntaxe, `NAME` ou `evaluate()` manquant) est ignore :
il n'empeche pas le demarrage de l'application. Le nombre d'erreurs est indique sous
la liste des strategies.

## Exemples fournis

- `poisson_pur.py` : modele de Poisson, probabilites brutes converties en cotes
  `1 / probabilite`, sans marge (strategie par defaut).
- `poisson_prudent.py` : fichier autonome avec son propre modele de Poisson ; ne
  garde que les marches a au moins 45 % de probabilite, avec cote juste + 5 %.
- `classement_pur.py` : fichier autonome sans Poisson ; les probabilites 1N2
  dependent de l'ecart de rang au classement reconstruit avant le match. Les
  marches over 2.5 et BTTS utilisent les frequences observees, avec cote juste.
- `ratio_rangs.py` : fichier autonome sans Poisson ; le ratio rang adverse /
  somme des rangs pondere les probabilites domicile / exterieur de la ligue (pour
  garder l'avantage du terrain), avec amortissement en debut de saison.
