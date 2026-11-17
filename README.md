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

### Innerhalb einer Blockwoche zählt nur, was schon gehalten wurde

Steht in `plan.json` ein **Stundenraster** für die Klasse, wächst das Soll
während einer laufenden Blockwoche tagesgenau, statt am Montag auf die volle
Woche zu springen:

```json
"stundenraster": {
  "RasterAB": { "mo": 2, "di": 5, "mi": 2, "do": 3, "fr": 2 },
  "RasterCD": { "mo": 2, "di": 3, "mi": 2, "do": 5, "fr": 2 }
},
"klassenZuRaster": {
  "IFA12A": "RasterAB", "IFA12B": "RasterAB",
  "IFA12C": "RasterCD", "IFA12D": "RasterCD"
}
```

Mehrere Klassen dürfen sich ein Raster teilen, auch über Schienen hinweg —
die Termine stehen in der Schiene, das Raster sagt nur, wie sich die
Wochenstunden auf Mo–Fr verteilen.

Das **Raster gibt die Form, die Wochensumme der Schiene die Höhe**:
gerechnet wird anteilig, damit die verkürzte erste Blockwoche (10 statt 14
Stunden) nicht mehr ausweist als sie hat. Tage außerhalb `start`–`ende`
zählen nicht mit.

Das Raster ist **optional**: ohne Eintrag zählt die angebrochene Woche wie
bisher ganz.

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
│   │   └── exporter.py
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
RECENT_SUBMISSION_DAYS=5      # Zeitfenster "Letzte Abgaben" (Sektion derzeit ausgeblendet)
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
eine JSON-Datei im `EXPORT_FOLDER` ab. Dauer: etwa 3 Minuten je Kurs bei
~57 Aktivitäten und ~115 Personen. Am Ende jedes Laufs steht eine
Phasenübersicht, die zeigt, wo die Zeit geblieben ist.

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
1. Feedback-Datum aus dem Singleview-Bewertungsbericht — nur wenn das
   Feedback-Feld **ausschließlich** ein Datum enthält (z.B. `09.01.2026`
   oder `09.01.2026 14:30`); normaler Feedbacktext wird übersprungen
2. „Zuletzt geändert (Abgabe)"-Datum der Bewertungsseite
3. Bewertungshistorie (Fallback für manuell eingetragene Noten)

#### Wie der Export seine Vollständigkeit prüft

Früher verglich der Export die Dateigröße mit dem Vorlauf und verwarf eine
kleinere Datei. Das sagte nicht, *wo* etwas fehlt, und konnte einen Ausfall
verdecken, wenn anderswo genug Abgaben dazukamen. Heute prüft er auf drei
Ebenen ([src/export/pruefung.py](src/export/pruefung.py)):

| Ebene | Prüft | Folge bei Befund |
|---|---|---|
| **Seite** | keine Anmeldeseite, erwartete Tabelle vorhanden, aufgeteilte Seiten vollständig nachgeladen | Status der Aufgabe **unbekannt** |
| **Abgleich** | Wer laut Gruppe zur Klasse gehört, muss in jeder Bewertungstabelle und in der Bewerterübersicht stehen | Status dieser Person **unbekannt** |
| **Verlauf** | Abgegeben/bewertet je Aufgabe und Klasse gegenüber dem letzten `output_*.json` | Warnung im Prüfbericht |

**Aufgeteilte Seiten.** Bewerterübersicht, Bewertungsseite, Testbericht und
Fortschrittsbericht zeigen je nach den im Moodle-Konto gespeicherten
Einstellungen nur einen Teil der Personen pro Seite. Der Export folgt der
Seitenleiste (`page=` bzw. `start=`) und lädt alle Teilseiten. Er übernimmt
dabei nur die Seitennummer, nie den Link: Filterlinks wie die Buchstabenleiste
speichert Moodle in der Sitzung, und ein versehentlich gesetzter Filter würde
alle folgenden Abrufe verfälschen.

**Unbekannt ist nicht „nicht abgegeben".** Lässt sich eine Seite auch nach drei
Versuchen nicht lesen, steht im Export `"unbekannt": true` samt Grund. Im
Dashboard erscheint die Zelle als **?**, die Quantität als Untergrenze
(„mind. 45 %") und die Mitarbeitsnote mit der Marke **vorl.** — der wahre Wert
kann nur höher liegen. In der CSV steht dazu die Spalte „Vorläufig", im
Schülerbericht „Stand unbekannt".

**Was den Lauf abbricht.** Nur, was eine ganze Klasse unsichtbar machen würde:
Mitglieder einer Plan-Klasse nicht ladbar, keine Gruppen, keine Aktivitäten
oder keine einzige lesbare Bewertungsseite. Der Kurs fehlt dann im Export und
der Prüfbericht nennt ihn.

**Prüfbericht.** Am Ende jedes Laufs steht im Log ein Abschnitt
„PRÜFBERICHT"; derselbe Inhalt liegt im Export unter `pruefbericht` und
erscheint im Dashboard über der Tabelle — grün, wenn jeder Status bekannt ist,
sonst aufklappbar mit allen Lücken und Rückgängen. Ein Rückgang (z.B.
„Quiz HTML, IFA12A: abgegeben 23 → 0") verwirft den Export nicht mehr:
Abmeldungen oder zurückgesetzte Abgaben senken Zahlen zu Recht.

#### Machbarkeitstest: Export im Browser direkt in ByCS

Langfristig soll der Export ohne Python und Selenium auskommen: als ZIP, das
wie das Schüler-Dashboard als Aktivität „Datei" im Kurs liegt und die
Moodle-Seiten in der Sitzung der angemeldeten Lehrkraft liest. Ob ByCS die
dafür nötigen Lehrkräfte-Seiten an eine hochgeladene Seite ausliefert, prüft
der Machbarkeitstest in [bycs/probe/](bycs/probe/):

```bash
python scripts/build_bycs_zip.py        # -> data/bycs/bycs_probe.zip
```

1. In einem Kurs eine Aktivität **Datei** anlegen, das ZIP hochladen, im
   Dateimanager **entpacken** und `index.html` als Hauptdatei setzen.
2. Die Aktivität **für Lernende verbergen**. Das ist Ordnung, kein Schutz —
   die Daten schützt Moodle über die Rechte; eine Lernende bekäme die
   Lehrkräfte-Seiten gar nicht ausgeliefert.
3. Öffnen, Kurs-ID eintragen, **Test starten**.

Geprüft werden Fortschrittsbericht (je Gruppe), Bewerterübersicht,
Bewertungsseite, Testbericht, Notenkategorien und die Moodle-5-Kursübersicht —
jeweils, ob sie lesbar sind, ob die erwartete Tabelle da ist und ob Moodle sie
aufteilt. Angezeigt werden **nur Zählwerte**, keine Namen und keine
Personen-IDs; gespeichert oder gesendet wird nichts. „Ergebnis als Text
kopieren" liefert eine Zusammenfassung zum Weitergeben.

#### Dashboard in ByCS

Das komplette Lehrkräfte-Dashboard läuft auch direkt in ByCS — ohne Python,
ohne Flask, ohne Zugangsdaten:

```bash
python scripts/build_bycs_zip.py dashboard   # -> data/bycs/bycs_dashboard.zip
```

Hochladen als Aktivität „Datei" (entpacken, `index.html` als Hauptdatei,
**für Lernende verbergen**). Beim Öffnen liest es Moodle in der Sitzung der
angemeldeten Lehrkraft (etwa 1–2 Minuten, Fortschritt unten rechts) und zeigt
das Ergebnis sofort an — dieselbe Oberfläche wie lokal.

- **Aktualisieren** liest Moodle erneut, **Datei laden** öffnet eine
  gespeicherte Exportdatei, **Export speichern** lädt die zuletzt gelesene
  Datei herunter (z.B. für `generate_reports.py`).
- **Einzelne Aufgabe nachladen**: Im Reiter *Pflichtaufgaben* steht über
  jeder Aufgabe ein ⟳-Knopf. Er liest nur diese Aufgabe neu (Bewertungsseite,
  Feedback-Datum) — wenige Sekunden statt eines ganzen Exports — und rechnet
  das Dashboard neu. Bei einem Test wird die ganze Bewerterübersicht gelesen,
  weil dort der Teststatus steht. Es gelten dieselben Prüfregeln wie beim
  Gesamtexport; die Lücken dieser Aufgabe im Prüfbericht werden ersetzt.
  Lokal (Flask) gibt es den Knopf nicht — dort fehlt die Moodle-Sitzung im
  Browser.
- Nichts wird gespeichert: Die Daten leben nur im Speicher der Seite.
- Das ZIP entsteht aus den unveränderten Dateien in `src/dashboard/static/`.
  Was lokal der Flask-Server rechnet, übernimmt
  [bycs/dashboard/aufbereitung.js](bycs/dashboard/aufbereitung.js); Plan und
  Einstellungen legt das Build-Skript mit Python geprüft bei
  (`plan_dashboard.json`, `einstellungen.json` aus `config/.env`).
- `einstellungen.json` enthält die Ausschlussliste, also Namen — ein Grund
  mehr, die Aktivität zu verbergen.
- Ändern sich `plan.json` oder `config/.env`, das ZIP neu bauen und hochladen.
- **Bearbeitungsmodus aus**: Ist er in Moodle eingeschaltet, liest der Export
  die Noten aus den Eingabefeldern und vermerkt das im Prüfbericht.
- **Darstellung „Öffnen" oder „Im neuen Fenster"** wählen (Einstellungen der
  Aktivität → Darstellung). „Einbetten" zeigt das Dashboard in einem Rahmen
  mit fester Höhe, „Im Pop-up" in einem kleinen Fenster (Standard 620 × 450).
  In beiden Fällen bietet das Dashboard oben „Im ganzen Fenster öffnen" an —
  das liest Moodle allerdings neu ein.

Dass ByCS- und lokales Dashboard dieselben Zahlen zeigen, prüft
`tests/vergleiche_aufbereitung.py` (Stufe 4 der Testsuite, braucht Node):

```bash
python -X utf8 tests/vergleiche_aufbereitung.py <export>.json
```

#### Export im Browser (ohne Python)

Der Machbarkeitstest war erfolgreich (17.11.2026): Alle Seiten sind aus einer
hochgeladenen Seite lesbar. [bycs/export/](bycs/export/) erzeugt deshalb
dieselbe Exportdatei wie `scripts/export_data.py`, direkt im Browser der
angemeldeten Lehrkraft — ohne Python, Selenium oder Zugangsdaten in der `.env`.

```bash
python scripts/build_bycs_zip.py export   # -> data/bycs/bycs_export.zip (inkl. plan.json)
```

Hochladen wie den Machbarkeitstest (Aktivität „Datei", entpacken, `index.html`
als Hauptdatei, für Lernende verbergen). Die Seite liest die `plan.json`
neben sich, bietet die nicht gesperrten Kurse an, zeigt am Ende den
Prüfbericht und lädt die Datei `output_<Zeitstempel>.json` herunter. Diese im
Dashboard über **„Datei laden"** öffnen oder in den `EXPORT_FOLDER` legen.

- Dieselben Regeln wie der Python-Export: aufgeteilte Seiten nachladen,
  „unbekannt" statt „nicht abgegeben", Abgleich gegen die Gruppenmitglieder.
- Der Verlaufsvergleich nutzt nur Zählwerte (keine Namen), die im Browser
  gespeichert werden — er greift ab dem zweiten Lauf im selben Browser.
- Die `plan.json` im ZIP ist eine Kopie. Ändert sich der Plan, ZIP neu bauen
  und hochladen — wie beim Schüler-Dashboard.

**Parallelbetrieb.** Bis der Browser-Export den Python-Export ersetzt, beide
direkt nacheinander laufen lassen und vergleichen:

```bash
python -X utf8 tests/vergleiche_exporte.py <python-export>.json <browser-export>.json
```

Das Werkzeug vergleicht Kurse, Aktivitäten, Gruppenmitglieder und je Person
und Aktivität Status, Bewertung, Abgabezeit und „unbekannt". Es gibt nur IDs
aus, keine Namen. Leerraum-Unterschiede (Selenium `.text` gegenüber
`textContent`) zählen nicht.

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

### Aufbau der Oberfläche

Das Dashboard ist auf wenige Zeilen verdichtet:

1. **Toolbar** — Klassenauswahl, Ansicht (Übersicht, Pflichtaufgaben,
   Leistungsnachweise) und rechts „Datei laden" / „Aktualisieren".
   Links neben „Datei laden" steht der **Stand der geladenen Datei**
   (Datum und Uhrzeit des Exports, z. B. `22.09.2026, 07:30`); der
   vollständige Dateiname erscheint als Tooltip. Ist der Export älter
   als einen Tag, folgt daneben der Hinweis „N Tage alt".
2. **Steuerleiste** — Schulwochen-Slider, Wochentag (Mo–Fr), „Aktuelle
   Woche", „CSV Export" und der Halbjahr-Umschalter. Der Wochentag teilt
   die gewählte Blockwoche tagesgenau; vorausgewählt ist der heutige Tag,
   außerhalb eines Blocks Freitag. Tage außerhalb der Blockwoche sind
   ausgegraut — in Woche 1 der Schiene 3 beginnt der Unterricht erst am
   Dienstag. Beim Wochenwechsel bleibt der Tag stehen, „Aktuelle Woche"
   setzt beides auf heute zurück.
3. **Kennzahlenleiste** — Ø Pflichtaufgaben, Durchschnittsnote, Ø Note
   Pflichtaufgaben, Quantität, Delta, Qualität und Mitarbeitsnote in
   einer geteilten Zeile.
4. Darunter die Detailtabelle der gewählten Klasse — welche das ist,
   bestimmt der Halbjahr-Umschalter. Die frühere Sektion **Letzte Abgaben
   je Gruppe** ist ausgeblendet; `SHOW_RECENT_SUBMISSIONS = true` in
   `dashboard.js` blendet sie wieder ein.

### Pflichtaufgaben-Tabelle

Die Übersicht ist eine Matrix: **je Zeile eine Person, je Spalte eine
Pflichtaufgabe**, sortiert nach Aufgabennummer. Die Zeilen stehen
standardmäßig nach Vorname sortiert; ein Klick auf eine Spaltenüberschrift
sortiert um.

Die Aufgabenspalten sind bewusst schmal — bei 15 bis 20 Aufgaben wäre die
Tabelle sonst unlesbar breit. Deshalb:

- Das Präfix **„Pflicht: " wird ausgeblendet**; es steht in jeder Spalte
  und trägt nichts bei.
- Der Titel bricht über **bis zu drei Zeilen** um und wird danach
  abgeschnitten.
- Der **vollständige Titel** samt Typ und Kategorie erscheint **beim
  Überfahren mit der Maus**.

Ganz rechts steht je Person die Durchschnittsnote aus ihren bewerteten
Pflichtaufgaben. Die Personenspalte bleibt beim seitlichen Scrollen stehen.

Die Filter (Status, Typ, Abgabezeitraum) blenden **Aufgabenspalten** aus;
die Klassenliste in den Zeilen bleibt dabei vollständig.

### Datenexport über das Dashboard

1. Button **„Aktualisieren"** oben im Dashboard
2. Fortschritts-Panel erscheint am rechten Rand
3. Live-Anzeige von Prozent, verarbeiteten Aktivitäten und Restzeit
4. Nach Abschluss lädt das Dashboard die neuen Daten

Der Export läuft im Hintergrund (Headless), das Dashboard bleibt bedienbar.

### Halbjahr-Umschalter

Der Umschalter in der Steuerleiste wählt den auszuwertenden Kurs:

| Auswahl | Datengrundlage |
|---|---|
| **Gesamt** | alle Kurse zusammen |
| **1. Halbjahr** | nur der erste Kurs |
| **2. Halbjahr** | nur der zweite Kurs |

Die **Darstellung ist in allen drei Stellungen gleich** — dieselbe Tabelle,
dieselben Spalten, nur andere Zahlen:

| Spalte | Bedeutung |
|---|---|
| Quantität Pflicht (%) | erreichte Stunden am Soll der gewählten Woche |
| Delta (Std.) | Vorsprung bzw. Rückstand in Unterrichtsstunden |
| Note | aus der Quantität (92/81/67/50/30 %) |
| Qualität (%) | Durchschnitt der Bewertungen |
| Eingereichte Aufgaben | Anzahl |
| Note Pflichtaufgaben | Durchschnitt der bewerteten Pflichtaufgaben |
| Mitarbeitsnote | (Quantität + Qualität) / 2 |

Über 100 % in der Quantität heißt: dem Plan voraus. Für die Mitarbeitsnote
wird sie bei 100 % gekappt, damit ein Vorsprung keine schwache Qualität
ausgleicht.

„Gesamt" steht an erster Stelle und ist immer wählbar — hat erst ein Kurs
Daten, zeigt es eben nur dessen Zahlen. Sobald beide Halbjahre Daten haben,
ergibt sich ihre Gewichtung von selbst aus der Stundensumme.

In der Ansicht **„Alle Klassen"** steht unabhängig davon der
Klassenvergleich. Der Wochen-Slider folgt dem Zeitraum des aktiven
Halbjahres.

Die Schienen starten zu unterschiedlichen Terminen — mit der Klasse ändert
sich daher auch die laufende Woche.

### Zeitangabe im Aufgabentitel

In Moodle steht im Namen einer Aktivität die reine Bearbeitungszeit
(„Quiz HTML Grundlagen (20 Min)"). Das ist **nicht** die Zeit, mit der das
Dashboard rechnet — maßgeblich sind die `stunden` aus `plan.json`.

Das Dashboard ersetzt die Angabe deshalb bei der Anzeige:

```
Moodle:     Pflicht: Quiz HTML Grundlagen (20 Min)
Dashboard:  Pflicht: Quiz HTML Grundlagen (3 Std.)
```

Aktivitäten ohne Eintrag in `plan.json` behalten ihren Moodle-Titel — für
sie gibt es keine Planstunden. Steht die Zeit in einer Klammer mit weiterem
Text, bleibt nur die Zeit weg: „(Lernzielkontrolle, ~25 Min)" wird zu
„(Lernzielkontrolle) (8 Std.)".

### Direkt zur Bewertung springen

Ist eine Aufgabe abgegeben, aber noch nicht bewertet, steht in der Tabelle
**„bewertbar"**. Der Link führt direkt in Moodles Korrekturansicht der
gewählten Klasse (`…/mod/assign/view.php?id=…&group=…&action=grader`).

Welche Abgaben dort gelistet werden, steuert Moodle über die persönliche
Einstellung *„Bewertung erforderlich"* — die lässt sich nicht über die URL
setzen. Einmal im Grader eingestellt, merkt Moodle sie sich für die
folgenden Aufrufe.

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

**„Export hat Schema X, erwartet wird 3"**
- Die Datei stammt aus einer älteren Version. Schema 2 kannte keinen
  unbekannten Status und hat jede Lücke als „nicht abgegeben" exportiert.
  Altformate werden bewusst nicht gelesen — einen neuen Export erzeugen.

**Zellen mit „?" und die Marke „vorl."**
- Der Export konnte den Stand dieser Aufgaben nicht lesen (Seite fehlte,
  Person nicht in der Tabelle). Der Prüfbericht über der Tabelle nennt
  Aufgabe und Grund. Meist genügt ein neuer Export; bleibt dieselbe Lücke,
  lohnt ein Blick auf die genannte Moodle-Seite.

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
