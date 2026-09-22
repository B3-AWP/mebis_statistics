# CLAUDE.md

Leitfaden für Claude Code in diesem Repository.

## Worum es geht

Lehrkräfte-Werkzeuge für Mebis/BYCS-Moodle-Kurse an einer Berufsschule
(Fachinformatik). Vier Teile, die sich denselben Stammdatensatz teilen:

| Teil | Einstieg | Zweck |
|---|---|---|
| **Export** | `scripts/export_data.py` | Scrapet Moodle per Selenium → eine JSON-Datei je Lauf |
| **Dashboard** | `scripts/start_dashboard.py` | Flask + Vanilla-JS-Frontend, wertet den Export aus |
| **Report** | `scripts/generate_reports.py` | Schüler-Übersichts-PDFs aus dem Export |
| **Exam** | `scripts/scrape_exams.py`, `scripts/generate_pdfs.py` | Quiz-Versuche scrapen → individuelle Korrektur-PDFs |

Sprache: Code, Kommentare, Docstrings und Logs sind **deutsch** (mit
englischen Fachbegriffen und teils englischen Bezeichnern in Altbeständen).
Neuer Code folgt dem deutschen Stil der umgebenden Datei.

Die ausführliche Bedienanleitung steht in [README.md](README.md), die
Begründung der Architektur in [REFACTORING_PLAN.md](REFACTORING_PLAN.md),
die Historie in [CHANGELOG.md](CHANGELOG.md).

## Das Wichtigste zuerst: `plan.json`

Stammdaten — Kurse, Pflichtaufgaben, geplante Stunden je Aufgabe,
Schulwochenkalender, Klassenzuordnung, Notenschlüssel — stehen **nicht** im
Repo und **nicht** in der `.env`, sondern in einer Planungsdatei, die mit dem
Schüler-Dashboard geteilt wird:

```
../AEuP12/BYCS_Lernplattform_Dashboard/plan.json     # Default
PLAN_JSON_PATH=...                                    # override in config/.env
```

Eine lokale Kopie ist bewusst nicht vorgesehen: zwei Wahrheiten wären genau
das Problem, das die geteilte Datei löst. Ohne `plan.json` startet weder
Export noch Dashboard.

Daraus folgen die Regeln, an denen sich fast jede Änderung messen lassen muss:

- **Der Plan bestimmt den Nenner.** Eine Aufgabe ist Pflichtaufgabe, weil ihre
  `cmid` im Plan steht — nicht wegen einer Moodle-Kategorie.
- Eine Plan-Aufgabe, die in Moodle fehlt, **bleibt im Nenner** und gilt als
  nicht begonnen. Das Backend warnt beim Laden
  ([`_warne_bei_planabweichung`](src/dashboard/backend.py#L589)), statt sie
  stillschweigend zu entfernen — sonst würde eine veraltete `cmid` das Soll
  aller Klassen dauerhaft verzerren.
- Eine Moodle-Aufgabe ohne Plan-Eintrag zählt nicht.

### Zwei unabhängige Schema-Versionen

Leicht zu verwechseln — es sind verschiedene Dinge:

| Konstante | Wert | Gilt für |
|---|---|---|
| `plan_loader.SCHEMA_VERSION` | **4** | `plan.json` (`schemaVersion`) |
| `exporter.EXPORT_SCHEMA_VERSION` / `backend.EXPORT_SCHEMA_VERSION` | **2** | Export-JSON (`schema`) |

Beide werden hart geprüft; Altformate werden **abgelehnt, nicht migriert**.
Ändert sich das Exportformat, müssen [exporter.py:41](src/export/exporter.py#L41)
und [backend.py:41](src/dashboard/backend.py#L41) gemeinsam angehoben werden —
plus die Assertion in [tests/run_refactoring_tests.sh](tests/run_refactoring_tests.sh).

### Rechenregeln (nicht „vereinfachen")

```
Ist   = Σ Stunden abgegebener Aufgaben / Σ Stunden aller Aufgaben
Soll  = Σ Stunden der Blockwochen 1..w / Σ Stunden aller Wochen
Delta = (Ist − Soll) × Σ Stunden gesamt        → Unterrichtsstunden
```

- **Quantität ist stundengewichtet**, Soll folgt dem Wochenkalender (Woche 1
  hat 10 Stunden, die übrigen 14) — eine lineare Näherung `Woche / Anzahl`
  wäre schon innerhalb eines Halbjahres falsch.
- **Innerhalb einer laufenden Blockwoche zählt nur der gehaltene Anteil**,
  sofern die Klasse ein `stundenraster` hat (`klassenZuRaster` ordnet zu;
  mehrere Klassen dürfen sich eines teilen, auch über Schienen hinweg). Das
  Raster gibt die *Form* der Verteilung auf Mo–Fr, die Wochensumme der
  Schiene die *Höhe* — anteilig gerechnet, damit die verkürzte Woche 1
  (10 statt 14 Stunden) nicht mehr ausweist als sie hat. Tage außerhalb
  `start`–`ende` zählen nicht. Ohne Raster zählt die angebrochene Woche
  ganz, also exakt wie vor der Einführung.
- **Qualität bleibt bewusst ungewichtet**: schlichter Durchschnitt der
  Bewertungen.
- **Mitarbeitsnote = (Quantität + Qualität) / 2**, wobei die Quantität
  dafür **bei 100 % gekappt** wird. In ihrer eigenen Spalte steht der
  ungekappte Wert (über 100 % = dem Plan voraus) — ein Vorsprung soll
  sichtbar sein, aber keine schwache Qualität rechnerisch ausgleichen.
- Die Funktionen in [src/common/plan_loader.py](src/common/plan_loader.py)
  (`soll_anteil`, `aktuelle_woche`, `verteile_unterrichtsstunden`) sind **1:1
  aus `js/bilanz.js` des Schüler-Dashboards portiert** und per Test gegen
  dessen Werte abgesichert. Divergiert die Python-Seite, zeigen Schüler- und
  Lehrkräfte-Dashboard unterschiedliche Zahlen. Formeln also nur ändern, wenn
  die JS-Referenz mitgeht.
- Die Rechenpfade existieren **doppelt** — Python im Backend, JS im Frontend
  ([dashboard.js](src/dashboard/static/dashboard.js), u.a. `sollAnteil`,
  `calculateQuantitaet`, `calculateMitarbeitsnote`). Beim Ändern einer Formel
  immer beide Seiten prüfen.

### Begriffe

- **Halbjahr = Moodle-Kurs**, keine Notenstufe. Zwei Kurse je Schuljahr mit je
  eigener Aufgabenliste; der Umschalter im Dashboard wählt einen Kurs. Je
  Halbjahr gibt es *eine* Mitarbeitsnote aus Quantität und Qualität.
  Der Umschalter wechselt **nur den Datensatz, nicht die Darstellung**:
  „Gesamt" (steht vorne, immer wählbar) fasst alle Kurse zusammen, ein
  Halbjahr zeigt genau seinen Kurs — in allen drei Stellungen dieselbe
  Tabelle mit denselben sieben Spalten (Quantität Pflicht, Delta, Note,
  Qualität, Eingereichte Aufgaben, Note Pflichtaufgaben, Mitarbeitsnote).
  Bei „Alle Klassen" steht unabhängig davon der Klassenvergleich. Alles in
  [`generateGroupProgressTable`](src/dashboard/static/dashboard.js), per
  Test abgesichert.
- **Gruppe = Klasse.** Seit 2026/27 gibt es keine Team-Ebene mehr. Moodle
  liefert Gruppennamen in wechselnder Form (`K - IFA12A (6072)`,
  `IFA12A - Team 3`, `IFA12A`); das Kürzel zieht
  [`extract_group_prefix`](src/common/group_utils.py#L17) per Muster heraus —
  nie per Präfix bis zum ersten Trenner.
- **Schiene** = Blockwochen-Kalender. Klassen ohne Eintrag in
  `klassenZuSchiene` haben kein Soll und werden übersprungen.
- **LNW** = Leistungsnachweis (benoteter Test), **Pflichtaufgabe** = im Plan
  geführte Aufgabe.
- **Zeitangabe im Aufgabentitel.** Moodle nennt im Namen die reine
  Bearbeitungszeit („Quiz HTML Grundlagen (20 Min)"); gerechnet wird aber
  mit den `stunden` aus `plan.json`. Das Backend schreibt die Titel deshalb
  beim Laden einmal zentral um
  ([`_titel_auf_planstunden_umstellen`](src/dashboard/backend.py)) — danach
  steht überall dieselbe Zahl, mit der auch die Quantität rechnet.
  Aktivitäten ohne Plan-Eintrag behalten ihren Moodle-Titel, dort gibt es
  keine Planstunden. Die Umschreibung ist idempotent und per
  [tests/test_titel_planstunden.py](tests/test_titel_planstunden.py)
  abgesichert.

## Aufbau

```
scripts/        dünne CLI-Wrapper (sys.path-Setup + main()), *.bat/*.cmd daneben
src/
  common/       plan_loader.py (Stammdaten + Rechnen), group_utils.py
  dashboard/    backend.py (Flask, ~1.8k Z.) + static/ (dashboard.js ~5.4k Z.)
  export/       exporter.py (Selenium-Scraper, ~2.2k Z.)
  report/       report_generator.py (ReportLab)
  exam/         scraper.py, pdf_generator.py, utils.py  → eigene README.md
config/         config_manager.py (nur .env), logger_config.py, .env (nicht in Git)
tests/
data/           quiz_data/, LNW/, report/, export/  — alles gitignored
```

Datenfluss:

```
plan.json ─┐
           ├─→ exporter.py ──→ EXPORT_FOLDER/output_<timestamp>.json ──┐
Moodle ────┘                                                           │
                                          ┌────────────────────────────┤
                                     backend.py (/api/data)       report_generator.py
                                          │                            │
                                     dashboard.js                 data/report/{Klasse}/
```

Das Backend liest stets die **neueste** `output_*.json` im `EXPORT_FOLDER`
([`find_latest_file`](src/dashboard/backend.py#L58), Glob `output_*.json` —
Testexporte heißen `test_output_*.json` und werden dadurch nicht gefunden).

## Konventionen

- **Immer vom Projekt-Root ausführen.** `backend.py` und `exporter.py` machen
  selbst `sys.path.insert` + `os.chdir(_project_root)`; relative Pfade wie
  `config/exclude_names.txt` setzen den Root als CWD voraus.
- Konfiguration nur über `config/.env`, gelesen durch den Singleton
  `config_manager`. **Keine Kurs- oder Aufgaben-IDs in die `.env`** — die
  gehören in `plan.json`.
- Logging über `config.logger_config.get_logger(name)`, nicht `print`.
  Vorgefertigt: `backend_logger`, `api_logger`, `data_logger`.
- `get_plan()` cacht den Plan prozessweit; im Test mit `reload=True` oder
  explizitem `pfad` arbeiten.
- Frontend ist **Vanilla JS ohne Build-Schritt** — Dateien in
  `src/dashboard/static/` werden direkt ausgeliefert. Kein npm, kein Bundler.
- **Farben, Abstände und Schriftgrößen kommen aus den Design-Tokens** in
  `:root` von [style.css](src/dashboard/static/css/style.css)
  (`--accent`, `--class-accent`, `--surface*`, `--line*`, `--text-*`,
  `--font-mono`). Keine neuen Hex-Werte in Regeln oder Inline-Styles.
  Das Layout ist flach: Rahmen statt Schatten, keine Farbverläufe, kein
  Hover-Anheben. Zahlen in Tabellen und Kennzahlen laufen in `--font-mono`
  mit `tabular-nums`, damit Kommastellen in Flucht stehen.
- Selenium-Scraping ist langsam und flaky: `retry`-Decorator und
  `PhaseTimer` in [exporter.py](src/export/exporter.py) nutzen, statt neue
  Wartelogik zu erfinden. Ein voller Export dauert ~6–7 min je Kurs.
- Keine Testdaten oder Exporte committen — `data/` ist vollständig gitignored
  und enthält echte Schülernamen.

## Befehle

```bash
# Setup
python -m venv venv && venv\Scripts\activate     # Windows
pip install -r requirements.txt

# Export (erforderlich, bevor das Dashboard etwas zeigt)
python scripts/export_data.py
python scripts/export_data.py --test             # 5 Aktivitäten je Typ

# Dashboard → http://localhost:5555
python scripts/start_dashboard.py

# Berichte / Exams
python scripts/generate_reports.py [--cutoff-date YYYY-MM-DD]
python scripts/scrape_exams.py [--max-workers 5] [--since-date TT.MM.JJJJ]
python scripts/generate_pdfs.py [--only-incorrect]
```

### Tests

```bash
bash tests/run_refactoring_tests.sh     # die maßgebliche Suite, 4 Stufen
python -m unittest tests.test_plan_loader
```

`run_refactoring_tests.sh` prüft plan_loader (inkl. Abgleich mit der
JS-Referenz) → Fixture-Erzeugung → Backend-API → Frontend-Rechenpfade.
Stufe 1 läuft ohne Weiteres; Stufen 2–4 brauchen eine erreichbare `plan.json`,
Stufe 4 zusätzlich **Node**. [tests/test_frontend.js](tests/test_frontend.js)
lädt `dashboard.js` in eine DOM-Attrappe — kein Browser nötig.

## Bekannte Altlasten

Nicht „aufräumen" ohne Rückfrage, aber auch nicht als Vorbild nehmen:

- [tests/run_tests.py](tests/run_tests.py) und
  [tests/test_grade_calculator.py](tests/test_grade_calculator.py) stammen aus
  einer früheren Struktur und **brechen beim Import**
  (`logger_config`, `backend.models.grade` existieren nicht mehr). Maßgeblich
  ist `run_refactoring_tests.sh`.
- [scripts/start_dashboard.bat](scripts/start_dashboard.bat) und
  [scripts/export_data.cmd](scripts/export_data.cmd) rufen
  `python start_dashboard.py` bzw. `python ./export_data.py` ohne Pfad auf —
  das funktioniert nur, wenn das CWD `scripts/` ist, was den Imports
  widerspricht. Der Python-Aufruf vom Root aus ist der verlässliche Weg.
- [src/exam/README.md](src/exam/README.md) ist lesenswert für die
  Quiz-Datenstruktur, nennt in Beispielen aber noch alte Modulnamen
  (`exam_scraper.py` statt `scripts/scrape_exams.py`) und die entfallene
  Team-Ebene.
- `EXPORT_CHECKLISTS = False` in [exporter.py:44](src/export/exporter.py#L44)
  schaltet den Checklisten-Export ab; die Auswertungspfade dafür existieren im
  Backend und Frontend weiterhin.

## Arbeitsweise

- **Dokumentation aktuell halten.** Jede Änderung am Verhalten schließt die
  passende Doku mit ein — [README.md](README.md) für die Bedienung,
  [CHANGELOG.md](CHANGELOG.md) für die Historie, diese Datei für Regeln und
  Architektur. Das gehört in denselben Arbeitsschritt, nicht in ein „später".
- **Nicht committen.** Änderungen im Working Tree liegen lassen; `git commit`
  und `git push` macht der Nutzer selbst. Ohne ausdrückliche Aufforderung also
  keine Commits, keine Branches, keine Tags.
