import sys
import time
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

# Package directory.
ROOT = Path(__file__).resolve().parent
PKG_DIR = ROOT / "football_betting_pitchapi"
if "football_betting_pitchapi" not in sys.modules:
    _pkg = types.ModuleType("football_betting_pitchapi")
    _pkg.__path__ = [str(PKG_DIR)]
    _pkg.__file__ = str(PKG_DIR / "__init__.py")
    sys.modules["football_betting_pitchapi"] = _pkg

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDialog,
)

from football_betting_pitchapi.strategies import StrategyCatalog, load_strategies, strategies_dir
from football_betting_pitchapi import ai as ai_module
from pitchapi_data import (
    PitchAPIError,
    get_configured_seasons,
    get_default_season,
    get_target_leagues,
    get_league_matches,
)


TARGET_SEASONS = get_configured_seasons()


def format_match_label(m: dict) -> str:
    date = m.get("date", "N/A")
    time_str = m.get("time")
    team1 = m.get("team1", m.get("home_team", "?"))
    team2 = m.get("team2", m.get("away_team", "?"))
    score = m.get("score")

    ft = None
    if isinstance(score, dict):
        ft = score.get("ft")
    elif isinstance(score, list) and len(score) >= 2:
        ft = score[:2]

    if isinstance(ft, list) and len(ft) == 2 and ft[0] is not None and ft[1] is not None:
        score_txt = f"{ft[0]}-{ft[1]}"
    else:
        score_txt = "vs"

    round_name = m.get("round")
    prefix = f"[{round_name}] " if round_name else ""
    dt = f"{date} {time_str}" if time_str else date
    return f"{prefix}{dt}  |  {team1} {score_txt} {team2}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Football Betting Matrix (PyQt6) - PitchAPI")
        self.resize(1200, 720)

        self.fixtures: List[dict] = []
        self.current_match: Optional[dict] = None
        self.catalog: StrategyCatalog = load_strategies(strategies_dir(Path(__file__).resolve().parent))
        self.leagues: List[dict] = []
        self._initializing = True

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Controls (top bar)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Saison:"))
        self.season_combo = QComboBox()
        self.season_combo.addItems(TARGET_SEASONS)
        default_season = get_default_season()
        idx = self.season_combo.findText(default_season)
        if idx >= 0:
            self.season_combo.setCurrentIndex(idx)
        controls.addWidget(self.season_combo)

        controls.addWidget(QLabel("Ligue:"))
        self.league_combo = QComboBox()
        controls.addWidget(self.league_combo, 1)

        self.btn_reload = QPushButton("Recharger")
        controls.addWidget(self.btn_reload)

        controls.addStretch(1)
        root.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: matches list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Matchs (sélectionne un match):"))
        self.matches_list = QListWidget()
        left_layout.addWidget(self.matches_list)
        splitter.addWidget(left)

        # Right: odds table + strategy controls
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 8)

        strat_row = QHBoxLayout()
        strat_row.addWidget(QLabel("Stratégie:"))
        self.strategy_combo = QComboBox()
        self._populate_strategies()
        strat_row.addWidget(self.strategy_combo, 1)
        self.btn_ai = QPushButton("Analyser avec l'IA (llama.app)")
        strat_row.addWidget(self.btn_ai)
        right_layout.addLayout(strat_row)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setChildrenCollapsible(False)

        odds_widget = QWidget()
        odds_layout = QVBoxLayout(odds_widget)
        odds_layout.setContentsMargins(0, 0, 0, 0)
        odds_layout.addWidget(QLabel("Cotes calculées:"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Marché", "Proba", "Cote", "Signal"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(120)
        odds_layout.addWidget(self.table, 1)
        self.details_label = QLabel("Choisis une saison, une ligue, un match, puis une stratégie.")
        self.details_label.setWordWrap(True)
        self.details_label.setMaximumHeight(60)
        odds_layout.addWidget(self.details_label)
        right_splitter.addWidget(odds_widget)

        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.addWidget(QLabel("Infos match (PitchAPI) :"))
        self.info_table = QTableWidget(0, 2)
        self.info_table.setHorizontalHeaderLabels(["Info", "Valeur"])
        self.info_table.horizontalHeader().setStretchLastSection(True)
        self.info_table.setMinimumHeight(120)
        self.info_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        info_layout.addWidget(self.info_table, 1)
        right_splitter.addWidget(info_widget)

        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)
        right_layout.addWidget(right_splitter, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, 1)

        self.status_label = QLabel("Prêt.")
        root.addWidget(self.status_label)

        # Signals
        self.season_combo.currentTextChanged.connect(self.on_season_changed)
        self.league_combo.currentIndexChanged.connect(self.on_league_changed)
        self.matches_list.currentRowChanged.connect(self.on_match_selected)
        self.btn_ai.clicked.connect(self.on_analyze_ai)
        self.strategy_combo.currentIndexChanged.connect(lambda _: self.on_strategy_changed())
        self.btn_reload.clicked.connect(self.reload_data)

        # Init
        self.load_leagues()
        self._initializing = False

    def _populate_strategies(self):
        self.strategy_combo.clear()
        if self.catalog.strategies:
            for s in self.catalog.strategies:
                self.strategy_combo.addItem(s.name, s.id)
        else:
            self.strategy_combo.addItem("(aucune stratégie trouvée)", "")

    def set_status(self, text: str):
        self.status_label.setText(text)
        QApplication.processEvents()

    def load_leagues(self):
        self.league_combo.blockSignals(True)
        self.league_combo.clear()
        self.leagues = []
        try:
            self.set_status("Chargement des ligues PitchAPI...")
            leagues = get_target_leagues()
            self.leagues = leagues
            if not leagues:
                self.league_combo.addItem("(aucune des 5 ligues trouvée)", "")
                self.league_combo.setEnabled(False)
                self.set_status("Aucune ligue cible trouvée via PitchAPI.")
            else:
                for league in leagues:
                    name = league.get("name", "Ligue")
                    country = league.get("country_code") or ""
                    label = f"{name} ({country})" if country else name
                    self.league_combo.addItem(label, league.get("id"))
                self.league_combo.setEnabled(True)
                self.set_status(f"{len(leagues)} ligue(s) PitchAPI chargée(s).")
        except PitchAPIError as e:
            self.league_combo.addItem("(erreur PitchAPI)", "")
            self.league_combo.setEnabled(False)
            self.set_status("Erreur PitchAPI.")
            QMessageBox.warning(self, "PitchAPI", str(e))
        except Exception as e:
            self.league_combo.addItem("(erreur)", "")
            self.league_combo.setEnabled(False)
            self.set_status("Erreur lors du chargement des ligues.")
            QMessageBox.critical(self, "Erreur", str(e))
        finally:
            self.league_combo.blockSignals(False)

        if self.leagues:
            self.on_league_changed()

    def reload_data(self):
        self.catalog = load_strategies(strategies_dir(Path(__file__).resolve().parent))
        self._populate_strategies()
        self.load_leagues()

    def on_season_changed(self, _season: str):
        if self.leagues:
            self.on_league_changed()

    def _match_sort_key(self, match: dict) -> str:
        pitch = match.get("pitchapi") or {}
        raw = pitch.get("match") or {}
        return str(raw.get("time_utc") or match.get("fixture", {}).get("date") or match.get("date") or "")

    def _is_finished_match(self, match: dict) -> bool:
        status = str((match.get("fixture") or {}).get("status", {}).get("short") or "").lower()
        if status in {"finished", "ft", "aet", "pen", "after_extra_time", "after_penalties", "completed"}:
            return True
        score = match.get("score") or {}
        ft = score.get("ft") if isinstance(score, dict) else None
        return isinstance(ft, list) and len(ft) == 2 and ft[0] is not None and ft[1] is not None

    def _default_match_row(self, fixtures: List[dict]) -> int:
        if not fixtures:
            return -1
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        played = [i for i, m in enumerate(fixtures) if self._is_finished_match(m)]
        if played:
            return max(played, key=lambda i: self._match_sort_key(fixtures[i]))

        upcoming = [i for i, m in enumerate(fixtures) if self._match_sort_key(m) >= now_utc]
        if upcoming:
            return min(upcoming, key=lambda i: self._match_sort_key(fixtures[i]))
        return len(fixtures) - 1

    def on_league_changed(self, *_args):
        league_id = self.league_combo.currentData()
        season = self.season_combo.currentText()
        if not league_id:
            self.matches_list.clear()
            self.fixtures = []
            self.current_match = None
            self.update_info_panel()
            self.table.setRowCount(0)
            return

        self.set_status(f"Chargement des matchs: {self.league_combo.currentText()} {season} ...")
        try:
            matches = get_league_matches(str(league_id), season, status="all")
            # Tri chronologique, puis par heure
            matches.sort(key=lambda m: (str(m.get("date") or ""), str(m.get("time") or "")))
            self.fixtures = matches
        except PitchAPIError as e:
            self.fixtures = []
            self.matches_list.clear()
            self.current_match = None
            self.update_info_panel()
            self.table.setRowCount(0)
            self.set_status("Erreur PitchAPI lors du chargement des matchs.")
            QMessageBox.warning(self, "PitchAPI", str(e))
            return
        except Exception as e:
            self.fixtures = []
            self.matches_list.clear()
            self.current_match = None
            self.update_info_panel()
            self.table.setRowCount(0)
            self.set_status("Erreur lors du chargement des matchs.")
            QMessageBox.critical(self, "Erreur", str(e))
            return

        self.matches_list.clear()
        for m in self.fixtures:
            self.matches_list.addItem(QListWidgetItem(format_match_label(m)))

        if self.fixtures:
            target_row = self._default_match_row(self.fixtures)
            self.matches_list.setCurrentRow(target_row)
            item = self.matches_list.item(target_row)
            if item is not None:
                self.matches_list.scrollToItem(item)
        else:
            self.current_match = None
            self.update_info_panel()
            self.table.setRowCount(0)

        self.set_status(f"{self.league_combo.currentText()} {season} — {len(self.fixtures)} match(s) chargés.")

    def on_match_selected(self, row: int):
        if row < 0 or row >= len(self.fixtures):
            self.current_match = None
            self.update_info_panel()
            self.table.setRowCount(0)
            return
        self.current_match = self.fixtures[row]
        self.update_info_panel()
        self.update_odds_table()

    def on_strategy_changed(self):
        if self.current_match is None:
            return
        self.update_odds_table()

    def update_info_panel(self):
        self.info_table.setRowCount(0)
        if not self.current_match:
            self.info_table.insertRow(0)
            self.info_table.setItem(0, 0, QTableWidgetItem("PitchAPI"))
            self.info_table.setItem(0, 1, QTableWidgetItem("Sélectionne un match."))
            return

        m = self.current_match
        pitch = m.get("pitchapi") or {}
        raw = pitch.get("match") or {}
        league = pitch.get("league") or {}
        season = pitch.get("season") or self.season_combo.currentText()

        status = (m.get("fixture") or {}).get("status", {}).get("short") or raw.get("status") or "-"
        score_home = (m.get("goals") or {}).get("home")
        score_away = (m.get("goals") or {}).get("away")
        score_txt = f"{score_home}-{score_away}" if score_home is not None and score_away is not None else "-"

        items = [
            ("Source", "PitchAPI (api.pitchapi.dev)"),
            ("Ligue", league.get("name") or self.league_combo.currentText()),
            ("Saison", season),
            ("Date", m.get("date") or "-"),
            ("Heure UTC", m.get("time") or "-"),
            ("Statut", str(status)),
            ("Score", score_txt),
            ("Round", str(m.get("round") or "-")),
            ("ID match", str((m.get("fixture") or {}).get("id") or raw.get("id") or "-")),
            ("ID domicile", str(((m.get("teams") or {}).get("home") or {}).get("id") or "-")),
            ("ID extérieur", str(((m.get("teams") or {}).get("away") or {}).get("id") or "-")),
        ]
        for k, v in items:
            r = self.info_table.rowCount()
            self.info_table.insertRow(r)
            self.info_table.setItem(r, 0, QTableWidgetItem(str(k)))
            self.info_table.setItem(r, 1, QTableWidgetItem(str(v)))

    def update_odds_table(self):
        self.table.setRowCount(0)
        if not self.current_match:
            return
        if not self.catalog.strategies:
            return
        strategy_id = self.strategy_combo.currentData()
        strategy = self.catalog.get(strategy_id) if strategy_id else self.catalog.probability_model()
        if strategy is None:
            return

        m = self.current_match
        home_name = m.get("team1") or (m.get("teams") or {}).get("home", {}).get("name") or "Home"
        away_name = m.get("team2") or (m.get("teams") or {}).get("away", {}).get("name") or "Away"
        date = m.get("date")
        home_id = ((m.get("teams") or {}).get("home") or {}).get("id")
        away_id = ((m.get("teams") or {}).get("away") or {}).get("id")

        prob_strategy = self.catalog.probability_model()
        if not (prob_strategy and prob_strategy.analyze):
            self.table.insertRow(0)
            self.table.setItem(0, 0, QTableWidgetItem("Info"))
            self.table.setItem(0, 1, QTableWidgetItem("-"))
            self.table.setItem(0, 2, QTableWidgetItem("-"))
            self.table.setItem(0, 3, QTableWidgetItem("Aucune stratégie d'analyse (analyze)."))
            return
        try:
            analysis = prob_strategy.analyze(
                fixtures=self.fixtures,
                home_id=home_id,
                away_id=away_id,
                home_name=home_name,
                away_name=away_name,
                before_date=date,
            )
        except Exception as e:
            self.table.insertRow(0)
            self.table.setItem(0, 0, QTableWidgetItem("Erreur"))
            self.table.setItem(0, 1, QTableWidgetItem("-"))
            self.table.setItem(0, 2, QTableWidgetItem("-"))
            self.table.setItem(0, 3, QTableWidgetItem(str(e)))
            return
        probs = analysis.get("probabilities") if isinstance(analysis, dict) else None
        if not probs:
            return
        try:
            rows = strategy.run(probs, context={"match": m})
        except Exception as e:
            self.table.insertRow(0)
            self.table.setItem(0, 0, QTableWidgetItem("Erreur"))
            self.table.setItem(0, 1, QTableWidgetItem("-"))
            self.table.setItem(0, 2, QTableWidgetItem("-"))
            self.table.setItem(0, 3, QTableWidgetItem(str(e)))
            return
        for r in rows:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(str(r.get("label", ""))))
            prob_val = r.get("prob", "")
            if isinstance(prob_val, (int, float)):
                prob_str = f"{prob_val * 100:.1f}%"
            else:
                try:
                    prob_str = f"{float(prob_val) * 100:.1f}%"
                except (TypeError, ValueError):
                    prob_str = str(prob_val)
            self.table.setItem(row_idx, 1, QTableWidgetItem(prob_str))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(r.get("odd", ""))))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(r.get("signal", "") or "")))
        self.details_label.setText(f"{home_name} vs {away_name} ({date}) — Stratégie: {strategy.name}")

    def _build_ai_analysis_payload(self) -> Optional[dict]:
        if not self.current_match:
            QMessageBox.information(self, "Info", "Sélectionne un match d'abord.")
            return None
        if not self.catalog.strategies:
            QMessageBox.warning(self, "Aucune stratégie", "Aucune stratégie trouvée dans user_strategies/.")
            return None

        strategy_id = self.strategy_combo.currentData()
        strategy = self.catalog.get(strategy_id) if strategy_id else self.catalog.probability_model()
        if strategy is None:
            QMessageBox.warning(self, "Stratégie", "Aucune stratégie disponible.")
            return None

        m = self.current_match
        home_name = m.get("team1") or (m.get("teams") or {}).get("home", {}).get("name") or "Home"
        away_name = m.get("team2") or (m.get("teams") or {}).get("away", {}).get("name") or "Away"
        date = m.get("date")
        home_id = ((m.get("teams") or {}).get("home") or {}).get("id")
        away_id = ((m.get("teams") or {}).get("away") or {}).get("id")

        prob_strategy = self.catalog.probability_model()
        if not (prob_strategy and prob_strategy.analyze):
            QMessageBox.warning(self, "Stratégie", "Aucune stratégie avec analyze() trouvée (ex: Poisson/Ratio).")
            return None
        try:
            analysis = prob_strategy.analyze(
                fixtures=self.fixtures,
                home_id=home_id,
                away_id=away_id,
                home_name=home_name,
                away_name=away_name,
                before_date=date,
            )
        except Exception as e:
            QMessageBox.warning(self, "Erreur analyse", f"Erreur lors du calcul des probabilités:\n{e}")
            return None
        probs = analysis.get("probabilities") if isinstance(analysis, dict) else None
        if not probs:
            QMessageBox.warning(self, "Probabilités", "Impossible de calculer les probabilités pour ce match.")
            return None

        try:
            rows = strategy.run(probs, context={"match": m})
        except Exception as e:
            QMessageBox.warning(self, "Erreur stratégie", f"Erreur lors de l'évaluation:\n{e}")
            return None

        payload = {
            "match": {"home": home_name, "away": away_name, "date": date},
            "model": analysis,
            "strategy": {"id": strategy.id, "name": strategy.name, "rows": rows},
            "league": self.league_combo.currentText(),
            "season": self.season_combo.currentText(),
            "source": "pitchapi.dev",
        }
        home_info = (analysis or {}).get("home") or {}
        away_info = (analysis or {}).get("away") or {}
        payload["teams_form"] = {
            "home": {
                "name": home_name,
                "form": home_info.get("form", []),
                "rank": home_info.get("rank"),
                "played": home_info.get("played"),
            },
            "away": {
                "name": away_name,
                "form": away_info.get("form", []),
                "rank": away_info.get("rank"),
                "played": away_info.get("played"),
            },
        }
        if "n_teams" in (analysis or {}):
            payload["standings_context"] = {
                "n_teams": analysis.get("n_teams"),
                "reliability": analysis.get("reliability"),
                "sample_matches": analysis.get("sample_matches"),
                "league_rates": analysis.get("league_rates"),
            }
        return payload

    def on_analyze_ai(self):
        payload = self._build_ai_analysis_payload()
        if payload is None:
            return

        try:
            models = ai_module.list_models()
        except Exception as e:
            QMessageBox.warning(self, "llama.app", str(e))
            return
        if not models:
            QMessageBox.warning(
                self,
                "llama.app",
                "Aucun modèle trouvé. Lance `llama serve` avec un modèle "
                "(ex: llama serve -hf ggml-org/gemma-4-e4b-it-GGUF:Q4_0).",
            )
            return

        context = ai_module.build_context(payload)
        default_prompt = ai_module.DEFAULT_PROMPT + "\n\n--- DONNEES ---\n" + context

        dlg = QDialog(self)
        dlg.setWindowTitle("Analyse IA (llama.app)")
        dlg.resize(900, 700)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel("Modèle llama.app:"))
        model_cb = QComboBox()
        model_cb.addItems(models)
        layout.addWidget(model_cb)

        layout.addWidget(QLabel("Prompt:"))
        prompt_edit = QTextEdit()
        prompt_edit.setPlainText(default_prompt)
        prompt_edit.setMinimumHeight(180)
        layout.addWidget(prompt_edit)

        layout.addWidget(QLabel("Raisonnement / Résultat:"))
        result_edit = QTextEdit()
        result_edit.setReadOnly(True)
        result_edit.setPlaceholderText("Le résultat de l'analyse s'affichera ici.")
        layout.addWidget(result_edit, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton("Annuler")
        btn_run = QPushButton("Lancer l'analyse")
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_run)
        layout.addLayout(btn_row)

        def do_run():
            model = model_cb.currentText().strip()
            prompt = prompt_edit.toPlainText().strip()
            if not model:
                QMessageBox.warning(dlg, "llama.app", "Choisis un modèle.")
                return
            if not prompt:
                QMessageBox.warning(dlg, "Prompt", "Le prompt est vide.")
                return
            result_edit.setPlainText("Analyse en cours (llama.app)...")
            btn_run.setEnabled(False)
            btn_cancel.setEnabled(False)
            QApplication.processEvents()
            try:
                result = ai_module.ask_llama_app(prompt, model=model)
                result_edit.setPlainText(result)
                self.details_label.setText(
                    f"{payload['match']['home']} vs {payload['match']['away']} — Analyse IA terminée ({model})."
                )
                self.set_status("Analyse IA terminée.")
            except Exception as e:
                result_edit.setPlainText(f"Erreur IA: {e}")
                QMessageBox.warning(dlg, "Erreur IA", str(e))
            finally:
                btn_run.setEnabled(True)
                btn_cancel.setEnabled(True)

        btn_run.clicked.connect(do_run)
        btn_cancel.clicked.connect(dlg.reject)

        dlg.exec()


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
