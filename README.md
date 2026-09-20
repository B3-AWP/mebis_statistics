# Dokumentation für die Mebis Statistik

## Inhaltsverzeichnis
- [Idee](#idee)
- [Wie das Dashboard rechnet](#wie-das-dashboard-rechnet)
- [Projektstruktur](#projektstruktur)
- [Voraussetzungen](#voraussetzungen)
- [Konfiguration](#konfiguration)
- [Verwendung](#verwendung)
- [Features](#features)
- [Troubleshooting](#troubleshooting)

## Idee
Dieses Projekt bietet mehrere Tools für die Arbeit mit Mebis-Kursen:
- **Dashboard**: Visualisiert den Lernfortschritt einer Klasse
- **Exam Scraper**: Scrapt Quiz-Daten und generiert individuelle PDFs für Schüler
- **Report-Generator**: Erstellt Schüler-Übersichtsberichte als PDF
- **Export**: Exportiert Kursdaten als JSON

---

## Wie das Dashboard rechnet

Zwei Entscheidungen prägen alles Weitere. Wer nur die Bedienung sucht,
kann diesen Abschnitt überspringen — wer die Zahlen verstehen will, nicht.

### `plan.json` ist die Stammdatenquelle

Kurse, Pflichtaufgaben, geplante Stunden, Schulwochenkalender und
Notenschlüssel stehen **nicht** in der `.env`, sondern in der Planungsdatei
`plan.json`. Sie wird mit dem Schüler-Dashboard geteilt, damit beide Seiten
dieselben Zahlen zeigen.

Daraus folgt: **Der Plan bestimmt, was zählt.**

- Eine Aufgabe ist genau dann Pflichtaufgabe, wenn ihre `cmid` im Plan steht —
  nicht, weil sie in einer bestimmten Moodle-Kategorie liegt.
- Eine Aufgabe, die im Plan steht, in Moodle aber fehlt, bleibt im Nenner und
  gilt als nicht begonnen. Das hält das Soll stabil, statt es bei jeder
  Kursänderung springen zu lassen. Das Dashboard **warnt beim Laden**, wenn
  solche Aufgaben auftauchen — dann ist zu prüfen, ob die `cmid` noch stimmt.
- Eine Aufgabe, die in Moodle existiert, aber nicht im Plan steht, zählt nicht
  für den Fortschritt.

### Quantität ist stundengewichtet

```
Ist   = Σ Stunden abgegebener Aufgaben / Σ Stunden aller Aufgaben
Soll  = Σ Stunden der Blockwochen 1..w / Σ Stunden aller Wochen
Delta = (Ist − Soll) × Σ Stunden gesamt        → in Unterrichtsstunden
```

Eine 10-Stunden-Aufgabe wiegt fünfmal so viel wie ein 2-Stunden-Quiz. Beim
bloßen Zählen wären beide gleich viel wert — mit teils umgekehrtem Ergebnis:

| | Aufgaben | Stunden | gezählt | gewichtet |
|---|---|---|---|---|
| Person A | 1 | 10 h | 7,1 % | **17,1 %** |
| Person B | 4 | 9 h | 28,6 % | **15,4 %** |

Das **Soll folgt dem Wochenkalender**, nicht der Wochennummer: Woche 1 hat
10 Stunden, die übrigen 14. Eine lineare Näherung (`Woche / Anzahl Wochen`)
wäre schon innerhalb eines Halbjahres falsch.

**Qualität bleibt bewusst ungewichtet** — der schlichte Durchschnitt der
Bewertungen. Eine gut gemachte kleine Aufgabe ist so viel wert wie eine gut
gemachte große. Nur die Quantität ist stundengewichtet.

Die Formeln sind aus `js/bilanz.js` des Schüler-Dashboards portiert und per
Test gegen dessen Werte abgesichert (`tests/test_plan_loader.py`).

### Halbjahre sind Kurse

Das Schuljahr besteht aus zwei Moodle-Kursen mit je eigener Aufgabenliste.
Der Halbjahr-Umschalter im Dashboard wählt einen Kurs — keine Notenstufe.
Ein noch gesperrter Kurs erscheint als deaktivierter Tab mit Freischaltdatum;
der Exporter überspringt ihn.

Je Halbjahr gibt es **eine** Mitarbeitsnote aus Quantität und Qualität.

### Klassen statt Teams

Gruppen sind Klassen; eine Team-Ebene gibt es nicht mehr. Die Moodle-Namen
kommen in unterschiedlicher Form (`K - IFA12A (6072)`, `IFA12A`); das
Klassenkürzel wird per Muster daraus gezogen. Klassen, die nicht in
`plan.json` stehen — im Kurs liegen auch fremde —, werden übersprungen.

---

## Projektstruktur

```
mebis_statistics/
├── scripts/               # CLI Entry Points
│   ├── export_data.py        # Daten-Export starten
│   ├── start_dashboard.py    # Dashboard starten
│   ├── generate_reports.py   # Schüler-Übersichtsberichte
│   ├── scrape_exams.py       # Exam-Scraper starten
│   ├── generate_pdfs.py      # PDF-Generator starten
│   └── *.bat/*.cmd           # Windows-Shortcuts
│
├── src/                   # Hauptcode
│   ├── common/               # Gemeinsame Utils
│   │   ├── plan_loader.py       # plan.json laden, Wochen-/Stundenrechnung
│   │   └── group_utils.py       # Klassenkürzel aus Gruppennamen
│   ├── dashboard/            # Dashboard-Module
│   │   ├── backend.py
│   │   └── static/              # HTML/JS/CSS
│   ├── export/               # Export-Module
│   │   ├── exporter.py
│   │   └── pdf_multi.py
│   ├── report/               # Schüler-Übersichtsberichte
│   │   └── report_generator.py
│   └── exam/                 # Exam-Scraper & PDF-Generator
│       ├── scraper.py
│       ├── pdf_generator.py
│       ├── utils.py
│       └── README.md
│
├── data/                  # Alle Daten (nicht in Git)
│   ├── quiz_data/            # Gescrapte Quiz-Daten
│   ├── LNW/                  # Generierte Quiz-PDFs
│   └── report/               # Schüler-Übersichtsberichte
│
├── config/                # Konfiguration
│   ├── .env                  # Credentials & Betrieb (nicht in Git)
│   ├── config_manager.py
│   └── logger_config.py
│
├── tests/                 # Tests
│   ├── test_plan_loader.py       # Plan, Wochen, Stunden (Python)
│   ├── test_frontend.js          # Rechenpfade des Dashboards (Node)
│   ├── make_fixture.py           # Testdaten aus der echten plan.json
│   └── run_refactoring_tests.sh  # alle vier Stufen
└── venv/                  # Python Virtual Environment
```

Die Planungsdatei `plan.json` liegt **außerhalb** dieses Repos, im
Schüler-Dashboard (`../AEuP12/BYCS_Lernplattform_Dashboard/plan.json`).

## Voraussetzungen
1. Python Virtual Environment erstellen:
```bash
python -m venv venv
```

2. Virtual Environment aktivieren:
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`

3. Abhängigkeiten installieren:
```bash
pip install -r requirements.txt
```

4. Zugriff auf `plan.json` sicherstellen (siehe Konfiguration).

## Konfiguration

Die Konfiguration verteilt sich auf zwei Dateien mit klarer Trennung:

| Datei | Inhalt |
|---|---|
| `plan.json` | **Stammdaten**: Kurse, Aufgaben, Stunden, Schulwochen, Klassen, Notenschlüssel |
| `config/.env` | **Betrieb**: Zugangsdaten, Pfade, Flask, Selenium |

Kurs- oder Aufgaben-IDs stehen also **nicht** mehr in der `.env`.

### 1. `.env` anlegen

Die Datei `config/.env` ist nicht in Git (sie enthält Zugangsdaten). Minimal
nötig sind:

```env
# Mebis Login-Daten (ERFORDERLICH)
MEBIS_USERNAME=dein_mebis_username
MEBIS_PASSWORD=dein_mebis_passwort

# Export-Ordner für die JSON-Dateien
EXPORT_FOLDER=data/export
```

**Hinweis zum Export-Ordner:**
- Kann ein absoluter Pfad sein (z.B. `G:\Meine Ablage\Exports_2026_27`)
- Bei relativem Pfad wird vom Projekt-Root ausgegangen
- Wird bei Bedarf automatisch erstellt
- Pro Schuljahr ein eigener Ordner erspart Verwechslungen

### 2. Pfad zur Planungsdatei

Ohne Angabe wird das Nachbar-Repo des Schüler-Dashboards erwartet:
`../AEuP12/BYCS_Lernplattform_Dashboard/plan.json`

Liegt die Datei woanders:

```env
PLAN_JSON_PATH=C:\Pfad\zu\plan.json
```

Eine lokale Kopie ist bewusst nicht vorgesehen — zwei Wahrheiten wären genau
das Problem, das die gemeinsame Datei löst. Wer dort die `stunden` ändert,
verschiebt damit auch die Auswertung im Lehrkräfte-Dashboard.

### 3. Optionale Einstellungen

```env
FLASK_ENV=production          # oder development
FLASK_PORT=5555
LOG_LEVEL=INFO                # DEBUG/INFO/WARN/ERROR
MODE_HEADLESS=True            # Browser beim Export unsichtbar
MODE_WAITTIME=5               # Wartezeit in Sekunden
MEBIS_IGNORED_GROUPS=IT_Lehrkraft, Verkuerzt
RECENT_SUBMISSION_DAYS=5      # Zeitfenster "Letzte Abgaben"
INACTIVE_THRESHOLD_DAYS=2     # ab wann eine Klasse als inaktiv gilt
GRADE_MAPPING={"0": "* Nicht akzeptabel", "70": "** Verbesserungsbedarf", "90": "*** Solide Umsetzung", "100": "**** Exzellent"}
```

### 4. Optionale Dateien

- `config/exclude_names.txt` — ausgeschlossene Benutzernamen, ein Name pro Zeile

## Verwendung

**WICHTIG:** Vor der ersten Verwendung müssen Daten aus Mebis exportiert werden.

### 1. Daten exportieren (erforderlich!)

**Linux/Mac:**
```bash
python scripts/export_data.py
```

**Windows:**
```cmd
scripts\export_data.cmd
```

Der Export läuft über alle nicht gesperrten Kurse aus `plan.json` und legt
eine JSON-Datei im `EXPORT_FOLDER` ab. Dauer: etwa 6–7 Minuten je Kurs bei
~50 Aktivitäten und ~65 Personen.

Zum Ausprobieren gibt es einen Testmodus mit 5 Aktivitäten je Typ:

```bash
python scripts/export_data.py --test
```

**Woher die Aktivitäten kommen** (drei Quellen, in dieser Reihenfolge):
1. Fortschrittsseite (`report/progress`) — nur Aktivitäten mit aktivierter
   Abschlussverfolgung
2. Notenbuch — ergänzt dort fehlende Elemente
3. Quiz-Index (`mod/quiz/index.php`) — kennt **alle** Quizze des Kurses

Quelle 3 ist nötig, weil Quizze ohne Abschlussverfolgung sonst unsichtbar
blieben und ihre Stunden im Soll fehlten.

**Abgabedatum-Ermittlung (Priorität):**
1. Feedback-Datum aus dem Singleview-Bewertungsbericht (wenn eingetragen)
2. „Zuletzt geändert (Abgabe)"-Datum der Bewertungsseite
3. Bewertungshistorie (Fallback für manuell eingetragene Noten)

### 2. Dashboard starten

**Linux/Mac:**
```bash
python scripts/start_dashboard.py
```

**Windows:**
```cmd
scripts\start_dashboard.bat
```

Dieser Befehl prüft die Konfiguration, validiert die Login-Credentials,
kontrolliert ob Export-Daten vorhanden sind, startet Flask und öffnet den
Browser. Erreichbar unter `http://localhost:5555` (bzw. `FLASK_PORT`).

**Tipp:** Den Export kannst du auch direkt aus dem Dashboard starten —
Button **„Aktualisieren"** oben.

### 3. Schüler-Übersichtsberichte

```bash
python scripts/generate_reports.py
python scripts/generate_reports.py --cutoff-date 2026-12-10
```

Erzeugt je Schüler ein PDF unter `data/report/{Klasse}/`, dazu Übersichten
je Pflichtaufgabe. `--cutoff-date` blendet Abgaben vor dem Stichtag aus.

### 4. Exam-Scraper & PDF-Generator

Details: [src/exam/README.md](src/exam/README.md)

```bash
# Quizzes scrapen (3 parallele Worker)
python scripts/scrape_exams.py

# Schneller mit mehr Workers
python scripts/scrape_exams.py --max-workers 5

# PDFs generieren (nur falsche Antworten)
python scripts/generate_pdfs.py --only-incorrect
```

PDFs landen in `data/LNW/`, nach Klasse und Quiz sortiert.

### Workflow

```
1. config/.env anlegen, Zugriff auf plan.json sicherstellen
   ↓
2. Daten exportieren (scripts/export_data.py)
   ↓
3. Dashboard starten (scripts/start_dashboard.py)
   ↓
4. Im Browser nutzen (http://localhost:5555)
   ↓
5. Später: "Aktualisieren"-Button im Dashboard
```

### Tests

```bash
bash tests/run_refactoring_tests.sh
```

Prüft in vier Stufen: `plan_loader` samt Abgleich mit der JS-Referenz des
Schüler-Dashboards, Testdatenerzeugung, Backend-API und die Rechenpfade des
Frontends. Für Stufe 4 wird Node benötigt.

## Features

### Datenexport über das Dashboard

1. Button **„Aktualisieren"** oben im Dashboard
2. Fortschritts-Panel erscheint am rechten Rand
3. Live-Anzeige von Prozent, verarbeiteten Aktivitäten und Restzeit
4. Nach Abschluss lädt das Dashboard die neuen Daten

Der Export läuft im Hintergrund (Headless), das Dashboard bleibt bedienbar.

### Halbjahr-Umschalter

Die Tabs wählen den auszuwertenden Kurs. „Gesamt" erscheint erst, wenn mehr
als ein Kurs Daten hat; die Gewichtung der Halbjahre ergibt sich dann von
selbst aus der Stundensumme. Der Wochen-Slider folgt dem Zeitraum des
aktiven Halbjahres.

Die Schienen starten zu unterschiedlichen Terminen — mit der Klasse ändert
sich daher auch die laufende Woche.

### Ignorierte Gruppen

```env
MEBIS_IGNORED_GROUPS=IT_Lehrkraft, Verkuerzt
```

Unabhängig davon werden Klassen ohne Eintrag in `plan.json` ohnehin nicht
ausgewertet. Die `.env`-Liste ist für Gruppen gedacht, die ein Klassenkürzel
tragen, aber trotzdem nicht erscheinen sollen.

### Ausgeschlossene Benutzer

`config/exclude_names.txt`, ein Name pro Zeile:

```
Max Mustermann
Test User
```

### Bewertungsstufen anpassen

```env
GRADE_MAPPING={"0": "* Nicht akzeptabel", "70": "** Verbesserungsbedarf", "90": "*** Solide Umsetzung", "100": "**** Exzellent"}
```

JSON mit Punktzahl als Key (String) und Bewertungstext als Value. Die
Prozentwerte der Skala stehen zusätzlich in `plan.json` (`skalen.sterne4`).

## Troubleshooting

**„Planungsdatei nicht gefunden"**
- `plan.json` liegt nicht am erwarteten Ort. Pfad per `PLAN_JSON_PATH` setzen
  oder das Schüler-Dashboard-Repo danebenlegen.

**„Export hat Schema X, erwartet wird 2"**
- Die Datei stammt aus dem Vorjahr. Altformate werden bewusst nicht gelesen —
  einen neuen Export erzeugen.

**Warnung „N Aufgabe(n) aus plan.json fehlen im Kurs"**
- Die genannten `cmid`s sind in Moodle nicht auffindbar. Entweder die Aufgabe
  ist noch nicht angelegt (dann ist alles korrekt, sie zählt als nicht
  begonnen), oder die `cmid` im Plan ist veraltet. Die Meldung nennt Stunden
  und Anteil am Soll, damit die Tragweite sichtbar ist.

**Eine Klasse fehlt im Dashboard**
- Steht sie in `klassenZuSchiene` in `plan.json`? Ohne Eintrag gibt es keine
  Schiene und damit kein Soll — die Klasse wird übersprungen.
- Steht sie in `MEBIS_IGNORED_GROUPS`?

**Ein Quiz fehlt in der Auswertung**
- Wahrscheinlich ohne aktivierte Abschlussverfolgung. Der Exporter fängt das
  über den Quiz-Index ab; falls es dennoch fehlt, prüfen ob die `cmid` im Plan
  mit der in der Kurs-URL übereinstimmt.

**„No export files found!"**
- Erst `python scripts/export_data.py` ausführen. `EXPORT_FOLDER` prüfen.

**„Login credentials not found"**
- `MEBIS_USERNAME` und `MEBIS_PASSWORD` in `config/.env` setzen.

**Dashboard zeigt veraltete Daten**
- „Aktualisieren" im Dashboard oder `python scripts/export_data.py`.

**Export-Button funktioniert nicht**
- Browser-Konsole prüfen
- `MODE_WAITTIME` auf 5–10 erhöhen
- `MODE_HEADLESS=False` setzen, um zuzusehen
- Logs in der Konsole prüfen, wo `start_dashboard.py` läuft

**ImportError beim Starten**
- Vom Projekt-Root ausführen, nicht aus `scripts/`.

**Exam-Scraper ist langsam**
- `--max-workers 5` (mehr RAM nötig), Standard ist 3, bei wenig RAM 1–2.

**Screenshots fehlen oder sind abgeschnitten**
- `MODE_HEADLESS=False` setzen und den Browser beobachten.
