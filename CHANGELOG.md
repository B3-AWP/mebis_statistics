# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

## [Unreleased] - 2026-09-22 — Planstunden im Titel, Sprung in die Bewertung

### 🚀 Aufgabentitel nennen die Planstunden

Moodle führt im Namen einer Aktivität die reine Bearbeitungszeit
(„Quiz HTML Grundlagen (20 Min)"). Gerechnet wird aber mit den `stunden`
aus `plan.json` — zwei verschiedene Zahlen nebeneinander waren
verwirrend. Das Backend schreibt die Titel beim Laden deshalb einmal
zentral um:

```
Moodle:     Pflicht: Quiz HTML Grundlagen (20 Min)
Dashboard:  Pflicht: Quiz HTML Grundlagen (3 Std.)
```

- Neue Funktionen `titel_mit_planstunden()` und
  `_titel_auf_planstunden_umstellen()` in
  [backend.py](src/dashboard/backend.py). Die Umstellung passiert **einmal
  auf `activities_by_category`**, bevor Details und strukturierte Tabellen
  daraus gebaut werden — der Pflichtaufgaben-Tab liest die Kategorien
  direkt, deshalb reichte ein Umschreiben in `get_assignment_details()`
  nicht.
- Erkannt werden `(20 Min)`, `(10 Min.)`, `(ca. 45 Minuten)`, `(~25 Min)`,
  `(2-3 Std)`. Steht die Zeit in einer Klammer mit weiterem Text, fällt
  nur sie weg: „(Lernzielkontrolle, ~25 Min)" → „(Lernzielkontrolle)".
- **Aktivitäten ohne Plan-Eintrag bleiben unverändert** — für sie gibt es
  keine Planstunden (Übungen, SD-Übungen behalten ihre Moodle-Zeit).
- Halbe Stunden deutsch geschrieben: `2.5` → „2,5 Std.".
- Die Umschreibung ist idempotent, ein zweiter Durchlauf hängt nichts an.

### 🚀 „bewertbar" springt in die Korrekturansicht

Der Link öffnet jetzt direkt Moodles Grader statt der Aufgaben-Startseite:

```
vorher:  …/mod/assign/view.php?id=91837888&group=625177
jetzt:   …/mod/assign/view.php?id=91837888&group=625177&action=grader
```

- Neue Hilfsfunktion `bewertungsUrl()` in
  [dashboard.js](src/dashboard/static/dashboard.js); sie ersetzt vier
  Stellen, die den Link zuvor je eigen zusammengebaut haben.
- Der Filter *„Bewertung erforderlich"* ist eine Moodle-Nutzereinstellung
  (`assign_filter`), die per POST auf `/api/rest/v2/user/current/preferences`
  gesetzt wird — **nicht über die URL steuerbar**. Moodle merkt sie sich
  aber je Nutzer, sodass sie nach einmaligem Setzen im Grader erhalten
  bleibt.

### 🔧 Technische Änderungen

- `Dashboard Redesign/` entfernt — war nur Ansichtsmaterial für das
  Frontend-Redesign und wird nicht mehr gebraucht. Der Verweis darauf in
  CLAUDE.md ist ebenfalls raus.
- Neue Testdatei
  [tests/test_titel_planstunden.py](tests/test_titel_planstunden.py)
  (12 Tests, in Stufe 1 von `run_refactoring_tests.sh` eingehängt).

---

## [Unreleased] - 2026-09-20 — Frontend-Redesign (kompaktes Layout)

Visuelle Überarbeitung des Dashboards nach dem Entwurf in
`Dashboard Redesign/Main.dc.html`, dazu eine Verhaltensänderung am
Halbjahr-Umschalter. **Keine Rechenregel und keine Datenstruktur
geändert** — die Zahlen entstehen unverändert.

### 🎨 Layout

- **Zwei Navigationszeilen zu einer Toolbar zusammengefasst.** Klasse,
  Ansicht und die Aktionen „Datei laden"/„Aktualisieren" stehen jetzt in
  einer Zeile, getrennt durch senkrechte Striche.
- **Halbjahr-Umschalter nach oben in die Steuerleiste**, neben Schulwoche,
  „Aktuelle Woche" und „CSV Export". Die eigene Karte darüber entfällt;
  der Hinweis bei gesperrtem Halbjahr (`#halbjahrHinweis`) bleibt als
  Zeile darunter erhalten.
- **Kennzahlen als eine geteilte Zeile** statt sieben Kacheln: Label
  klein über der Zahl, Spalten durch feine Striche getrennt. Spart etwa
  eine Bildschirmhöhe.
- Klassen- und Halbjahr-Auswahl sind **Segmented Controls** (Knöpfe in
  einer grauen Rille, aktiver Knopf flächig gefärbt).

### 📋 Pflichtaufgaben-Tabelle

- **Achsen getauscht**: Zeilen sind jetzt **Personen**, Spalten die
  **Aufgaben** (vorher umgekehrt). Bei 25 Personen und 16 Aufgaben liest
  sich die Klasse damit von oben nach unten statt von links nach rechts.
- Das Präfix **„Pflicht: " wird in den Spaltenköpfen ausgeblendet**; der
  Titel bricht über bis zu drei Zeilen um und wird danach abgeschnitten.
  Der **vollständige Titel** samt Typ und Kategorie steht im **Tooltip**.
- Die **Durchschnittsnote** wandert von der Kopfzeile in eine **Spalte am
  Zeilenende** — je Person eine Note, wie zuvor aus den bewerteten
  Aufgaben gemittelt (Rechenweg unverändert).
- Die Filter (Status, Typ, Abgabezeitraum) blenden jetzt
  **Aufgabenspalten** statt Zeilen aus; die Klassenliste bleibt vollständig.
- Ein Klick auf einen Aufgabentitel öffnet Moodle und sortiert nicht mehr
  zusätzlich die Tabelle.

### 🔤 Sortierung

- **Tabellen sortieren Personen standardmäßig nach Vorname.** Moodle
  liefert „Vorname Nachname"; verglichen wird von links, bei gleichem
  Vornamen entscheidet der Nachname. Betrifft Mitarbeitsnoten-,
  Fortschritts-, Leistungsnachweis- und Pflichtaufgaben-Tabelle.

### 🎨 Stil

- **Flache Palette**: weiße Karten mit 1px-Rahmen auf grauem Grund,
  keine Farbverläufe, keine Schlagschatten, kein Hover-Anheben. Akzent
  ist `#2563EB`, die Klassenauswahl `#7C3AED`.
- **Tabellen** mit hellem, kleinem Kopf statt dunkelblauem Band; Zeilen
  nur durch feine Linien getrennt (Zebra-Streifen entfallen).
- **Zahlen in Mono** (`--font-mono`, `tabular-nums`), damit Kommastellen
  in Flucht stehen; Kopfzellen der Zahlenspalten rechtsbündig wie ihre
  Werte.
- **Systemschriften statt IBM Plex** aus dem Entwurf — das Dashboard
  läuft lokal und soll ohne CDN identisch aussehen.
- Statustönung in „Letzte Abgaben" durch einen **Farbstrich am linken
  Rand** ersetzt; die Aussage trägt ohnehin das Badge in der Statusspalte.
- Die Tabs Pflichtaufgaben, Leistungsnachweise und Checklisten erben
  Typografie, Buttons, Filterleisten und Tabellenstil aus demselben
  Token-Satz.

### 🚀 Eine einheitliche Tabelle je Umschalter-Stellung

Der Halbjahr-Umschalter wechselt nur noch den **Datensatz**, nicht die
Darstellung. „Gesamt", „1. Halbjahr" und „2. Halbjahr" zeigen dieselbe
Tabelle mit denselben Spalten:

| Spalte | Bedeutung |
|---|---|
| Quantität Pflicht (%) | Erreichte Stunden am Soll der gewählten Woche — über 100 % heißt: dem Plan voraus |
| Delta (Std.) | Vorsprung bzw. Rückstand in Unterrichtsstunden |
| Note | Aus der Quantität, Schwellen 92/81/67/50/30 % |
| Qualität (%) | Ungewichteter Durchschnitt der Bewertungen |
| Eingereichte Aufgaben | Anzahl, Balken nach `percent_submitted` |
| Note Pflichtaufgaben | Durchschnitt der bewerteten Pflichtaufgaben, mit N |
| Mitarbeitsnote | (Quantität + Qualität) / 2 |

- **„Gesamt" steht dauerhaft an erster Stelle** und fasst alle Kurse
  zusammen — auch wenn erst ein Kurs Daten hat. Bisher erschien der Knopf
  nur bei mehr als einem Kurs und stand zwischen den Halbjahren.
- Die zweite Tabelle („Mitarbeitsnote") **entfällt**; ihre Spalten Delta,
  Qualität und Mitarbeitsnote sind in die eine Tabelle gewandert.
  `generateHalbjahresnotenTable()` ist damit entfallen.
- **Für die Mitarbeitsnote wird die Quantität bei 100 % gekappt.** Ein
  Vorsprung soll eine schwache Qualität nicht rechnerisch ausgleichen —
  in der eigenen Spalte steht weiterhin der ungekappte Wert.
- Über der Tabelle steht die Bezugszeile „{Zeitraum} (Woche w von n,
  Soll x %, Schiene: …)".
- **Unverändert:** In der Ansicht „Alle Klassen" steht weiterhin der
  Klassenvergleich, in jeder Umschalter-Stellung.

### 🔧 Technische Änderungen

- Design-Tokens in `:root` von [style.css](src/dashboard/static/css/style.css):
  `--accent`, `--class-accent`, `--surface*`, `--line*`, `--text-*`,
  `--font-mono`. Bestehende Variablen wie `--primary-color` zeigen auf die
  neuen Werte, damit nicht umgestellte Stellen mitziehen.
- Alle IDs und Klassennamen unverändert — `dashboard.js` und
  `csv_export.js` arbeiten ohne Anpassung weiter.
- Kaputte Selektorenkette in `dashboard-custom.css` repariert (fehlende
  Kommas bei der Spaltenausrichtung von `#recentSubmissionsDataTable`).
- [tests/test_frontend.js](tests/test_frontend.js) prüft, dass jede
  Umschalter-Stellung dieselbe Tabelle mit allen sieben Spalten erzeugt
  und dass „Gesamt" vor dem 1. Halbjahr steht. Die alte Zusicherung
  „kein Gesamt bei nur einem Kurs" ist entfallen.
- Doppelte Titelvergabe beseitigt: `selectHalbjahr()` setzte den Titel
  der Einzelklassen-Ansicht abweichend von `generateGroupProgressTable()`
  und behielt bei einem gesperrten Kurs den alten Text.

---

## [Unreleased] - 2026-09-18 — Kursstruktur 2026/27

Umfassendes Refactoring auf die neue Kursstruktur. Details und offene
Punkte: [REFACTORING_PLAN.md](REFACTORING_PLAN.md).

### 💥 Breaking Changes

- **Exportformat `schema: 2`.** Ein Export enthält mehrere Kurse unter
  `kurse`, die Gruppen stehen kursübergreifend auf oberster Ebene.
  Altformate werden **abgelehnt**, nicht migriert — neues Schuljahr,
  neue Schüler, neuer Kurs.
- **`plan.json` ist Pflicht.** Ohne die Planungsdatei startet weder
  Export noch Dashboard.
- **Entfallene `.env`-Variablen:** `MEBIS_COURSE_ID`, `CLASS_TO_TRACK`,
  `TRACK_SCHEDULES`, `MAX_SCHOOLWEEKS`, `MITARBEITSNOTE1_REFERENCE_WEEK`.
  Sie stehen jetzt in `plan.json`.
- **`MANUAL_GRADE_ITEM_IDS` entfällt.** Manuelle Notenbuch-Spalten
  (Quantität, Qualität, Mitarbeitsnote, Sonstiges, Eingereichte Aufgaben)
  gibt es nicht mehr. Die Werte werden ausschließlich berechnet; der
  Export scrapet sie nicht mehr, was ihn zusätzlich beschleunigt.
- **`PROGNOSIS_ASSIGNMENTS` entfällt.** Review-Talk und Code-Review gibt es
  im neuen Kurs nicht. Die Mitarbeitsnote besteht aus Quantität und
  Qualität — beide berechnet. Damit braucht die `.env` überhaupt keine
  kursspezifischen IDs mehr.

### 🚀 Neue Struktur

#### Halbjahre sind Kurse, keine Notenstufen
Bisher bedeutete „1./2. Halbjahr" *1. Mitarbeitsnote* bzw. *Prognose der
2.*; getrennt wurde über die Referenzwoche innerhalb **eines** Kurses.
Jetzt sind es zwei Moodle-Kurse (2491549, 2491870) mit je eigener
Aufgabenliste. Die gesamte `soll1HJ`/`soll2HJ`-Arithmetik samt Übertrag
entfällt ersatzlos.

Das 2. Halbjahr ist bis **11.01.2027** gesperrt: Der Exporter überspringt
es, das Dashboard zeigt den Tab deaktiviert mit Freischaltdatum.

#### Quantität ist stundengewichtet
```
Ist   = Σ Stunden abgegebener Aufgaben / Σ Stunden aller Aufgaben
Soll  = Σ Stunden der Blockwochen 1..w / Σ Stunden aller Wochen
Delta = (Ist − Soll) × Σ Stunden gesamt        → in Unterrichtsstunden
```
Eine 10-Stunden-Aufgabe wiegt fünfmal so viel wie ein 2-Stunden-Quiz.
Das Soll folgt dem Wochenkalender (Woche 1 hat 10 Stunden, die übrigen
14) statt einer linearen Näherung. **Qualität bleibt ungewichtet** — eine
gut gemachte kleine Aufgabe ist so viel wert wie eine gut gemachte große.

Die Formeln sind aus `js/bilanz.js` des Schüler-Dashboards portiert und
gegen dieselbe `plan.json` auf identische Werte geprüft.

#### Eine Mitarbeitsnote statt zwei
`calculateMitarbeitsnote()` ersetzt `calculateMitarbeitsnote1()` und
`calculateMitarbeitsnote2Prognose()`. Neu ist die Delta-Spalte in
Unterrichtsstunden.

#### Keine Team-Ebene
Gruppen sind jetzt Klassen (`IFA12A` statt `IFA12A - Team 3`). Die
Gruppierungs-Navigation und `currentGrouping` entfallen.

#### Pflichtaufgaben über `plan.json`
Eine Aufgabe ist genau dann Pflichtaufgabe, wenn ihre `cmid` im Plan
steht — nicht mehr über den Kategorienamen. Nur so kommt man an das
`stunden`-Feld. Damit bestimmt der Plan den Nenner: Eine Aufgabe, die in
Moodle fehlt, bleibt darin und gilt als nicht begonnen.

### 🔧 Änderungen im Detail

- **Neu:** `src/common/plan_loader.py` — lädt und validiert `plan.json`,
  portiert die Rechenfunktionen aus `js/bilanz.js`
- **Neu:** `tests/test_plan_loader.py` — 27 Tests, davon 7 gegen die
  echte `plan.json` mit den Sollwerten der JS-Implementierung
- **Neu:** `.env`-Variable `PLAN_JSON_PATH` (Default: Nachbar-Repo)
- `exporter.py`: `export_course()` je Kurs, `main()` iteriert; ein
  Validierungsfehler überspringt nur den betroffenen Kurs
- `backend.py`: Kursschleife, Plan in `/api/data`, stundengewichtete
  Kennzahlen je Person
- `dashboard.js`: Kurs-Scope-Ebene, Wochen-Slider folgt dem Halbjahr
- `report_generator.py`: flache Sicht über alle Kurse
- `exam/scraper.py`: Kurs aus `plan.json` statt `MEBIS_COURSE_ID`
- `group_utils.py`: Klassenkürzel per Muster statt als Präfix
- `exporter.py`: Quiz-Index als dritte Aktivitätsquelle

### 🐛 Bugfixes

#### „Aktuelle Woche“ folgt wieder dem Blockwochen-Kalender
Der Button im Wochen-Slider rechnete die Schulwoche als
`ceil((heute − 1. September) / 7 Tage)` — eine Kalendernäherung, die den
Blockwochen-Kalender ignorierte. Am 20.09.2026 ergab das Woche 3, obwohl
auf Schiene 3 gerade Woche 1 lief und auf Schiene 1 noch gar kein Block
begonnen hatte. Da Blöcke weit auseinanderliegen, war der Wert praktisch
immer falsch.

Die Schaltfläche nutzt jetzt `getCurrentReferenceWeekForTrack()` —
dieselbe Funktion, mit der `updateWeekSlider()` den Slider beim Laden
stellt — samt derselben Klammerung auf das angezeigte Halbjahr. Damit
führt der Button zurück auf genau den Zustand, den das Dashboard beim
Öffnen zeigt, und rechnet schienengenau.

### ✅ Im Betrieb erprobt

Erster Vollexport am 18.09.2026 gegen Kurs 2491549: 6:41 Minuten,
53 Aktivitäten, 65 Personen, alle 14 Plan-Aufgaben gefunden.

Die Klassen sind IFA12A–D; IFA12E gibt es nicht mehr. IFA12C war beim
ersten Export noch nicht eingeschrieben — sie erscheint automatisch,
sobald sie im Kurs auftaucht, ohne Konfigurationsänderung.

### 🔍 Was der erste Export zutage förderte

Drei Punkte, die erst der Kontakt mit dem echten Kurs zeigte:

**Gruppennamen im Format `K - IFA12A (6072)`.** Die frühere Präfix-Regel
hätte `"K"` für jede Klasse geliefert — keine Schienenzuordnung, kein
Soll, und zwar ohne Fehlermeldung. `extract_group_prefix()` zieht das
Kürzel jetzt per Muster aus dem Namen.

**Fremde Klassen im Kurs** (IF10B, IF10C, IF11A, IF11C, IF11J, eine
Testgruppe). Klassen ohne Eintrag in `plan.json` werden übersprungen.

**Vier Quizze fehlten im Export.** Die Fortschrittsseite listet nur
Aktivitäten mit aktivierter Abschlussverfolgung (21 Quizze), der
Quiz-Index kennt 25. Betroffen war unter anderem `Pflicht: OOP - SOLID`
— 8 der 58,5 Plan-Stunden, also 13,7 % des Halbjahres-Solls.
`get_activity_urls()` liest seither `mod/quiz/index.php` als dritte
Quelle; `_warne_bei_planabweichung()` meldet fehlende Plan-Aufgaben beim
Laden mit Stundenzahl und Anteil am Soll.

## [Unreleased] - 2026-03-16 (2)

### 🚀 Neue Features

#### Dashboard: Spalte „Eingereichte Aufgaben" in der 1. Halbjahresnoten-Tabelle
- Neue Spalte im 1.-HJ-Abschnitt der Halbjahresnotentabelle
- Zeigt den gecachten Notenbuch-Wert des manuellen Grade-Items `17762677:Eingereichte Aufgaben`
- Spalte wird nur eingeblendet, wenn mindestens ein Schüler einen eingetragenen Wert hat

#### Dashboard: Überarbeitete Quantität-Berechnung für die 2. HJ Prognose
- **Bisher**: Checklisten-basierte Formel (abhängig von Checklist-Rohdaten und `quantitaet1Pct` der 1. MA)
- **Neu**: Pflichtaufgaben-basierte 7-Schritt-Formel; kein Zugriff auf Checklisten mehr nötig

**Formel (7 Schritte):**

| # | Was | Formel |
|---|-----|--------|
| 1 | Gesamtzahl Pflicht | `totalPflicht` = Anzahl Items in Pflichtaufgaben-Kategorie |
| 2 | Soll pro HJ | `soll1HJ = ROUND(totalPflicht × B7 / weeks)`, `soll2HJ = totalPflicht - soll1HJ` |
| 3 | Eingereichte aus MA1 | `eingereicht1HJ` aus `17762677:Eingereichte Aufgaben` (Notenbuch), Fallback: `soll1HJ` |
| 4 | Anrechnung 1. HJ | `angerechnet = MIN(eingereicht1HJ, soll1HJ)` |
| 5 | Abgeschlossen im 2. HJ | `completed2HJ = MAX(0, completedGesamt - angerechnet)` |
| 6 | Zeitproportionaler Nenner | `ROUND(soll2HJ × (C7 - B7) / (weeks - B7))` |
| 7 | Quantität | `(completed2HJ / Nenner) × 100` |

**Schlüsselvariablen:**
- `B7` = `mitarbeitsnote1_reference_week` (Woche der 1. Mitarbeitsnote)
- `C7` = aktuelle Referenzwoche (Slider)
- `weeks` = `maxSchoolweeks` (Semesterlänge)
- Übertrag aus 1. HJ (wenn `eingereicht1HJ > soll1HJ`) wirkt nur auf den Zähler, nicht den Nenner

### 🔧 Technische Änderungen

#### src/dashboard/static/dashboard.js
- `calculateQuantitaetMA2(user, groupName, currentWeek)`: Signatur vereinfacht (kein `quantitaet1Pct` mehr); komplette Neuimplementierung mit Pflichtaufgaben-Iteration statt Checklist-Rohdaten
- `calculateMitarbeitsnote2Prognose()`: Entfernt `quantitaetId`-, `actualQuantitaet1`-, `ma1`- und `quantitaet1Pct`-Berechnung; vereinfachter Aufruf von `calculateQuantitaetMA2`
- `generateHalbjahresnotenTable()`: Neue Variablen `eingereichtId` und `hasEingereicht`; Spalte „Eingereichte Aufgaben" in Tabellenkopf und Zeilen des 1.-HJ-Abschnitts; `colCount` um Eingereicht-Spalte erweitert

---

## [Unreleased] - 2026-03-16

### 🚀 Neue Features

#### Abgabedatum-Ermittlung via Singleview-Feedback (exporter.py)
- **Neue Funktion `get_singleview_feedback_dates()`**: Liest Feedback-Datumsangaben aus der Moodle-Singleview (`/grade/report/singleview/index.php?itemid={grade_item_id}`) für jedes Assignment
- **Priorität über Grading-Page-Datum**: Das Feedback-Datum hat Vorrang vor dem bisherigen `Zuletzt geändert (Abgabe)`-Datum der Bewertungsseite
- **Dreistufige Priorität**:
  1. Singleview-Feedback-Datum (Spalte c4 der Tabelle `#singleview-grades`)
  2. Grading-Page-Datum (`Zuletzt geändert (Abgabe)`)
  3. Bewertungshistorie als letzter Fallback (für manuell eingetragene Bewertungen)
- **Robuste Textextraktion**: Versucht sichtbaren Text, dann `<textarea>`-Wert, dann `<input>`-Wert
- **Logging**: Anzahl extrahierter Feedback-Daten wird geloggt für Nachvollziehbarkeit

#### Erweitertes Datumsformat-Parsing (exporter.py)
- **Neues Format `DD.MM.YYYY`**: `parse_german_datetime()` unterstützt jetzt das numerische Kurzformat (z.B. `09.01.2026`) zusätzlich zu den bisherigen deutschen Langformaten
- **Neues Format `DD.MM.YYYY HH:MM`**: Auch numerisches Format mit Uhrzeit wird erkannt

#### Singleview-Feedback-Fallback auch für Quizzes (exporter.py)
- `process_quiz_parallel()`: Wenn `get_quiz_submission_times()` für einen User kein Datum liefert, wird das Singleview-Feedback-Datum als Fallback verwendet
- **Keine Überschreibung**: Vorhandene Quiz-Abgabezeitpunkte bleiben erhalten; Singleview ergänzt nur fehlende Einträge

### 🔧 Technische Änderungen

#### src/export/exporter.py
- Neue Funktion `get_singleview_feedback_dates(driver, course_id, grade_item_id, waittime)`
- `process_assignment_parallel()`: Singleview-Schritt wird vor dem History-Fallback ausgeführt; `grade_item_id` wird früher im Funktionsablauf gesetzt
- `process_quiz_parallel()`: Singleview-Feedback als Fallback für fehlende submission_times ergänzt
- `parse_german_datetime()`: Zwei neue Formate `%d.%m.%Y %H:%M` und `%d.%m.%Y` ergänzt

---

## [Unreleased] - 2025-11-27

### 🚀 Neue Features

#### Paralleles Scraping
- **Multi-Threading Support**: Exam-Scraper nutzt jetzt ThreadPoolExecutor für parallele Verarbeitung
- **3x schnellere Performance**: Standard-Konfiguration mit 3 parallelen Workers
- **Konfigurierbar**: `--max-workers` Parameter zum Anpassen der Anzahl (1-5 empfohlen)
- **Isolation**: Jeder Worker nutzt eigene WebDriver-Instanz
- **Zeitanzeige**: Gesamtdauer wird am Ende des Scrapings angezeigt

#### Verbesserte Screenshots
- **Multianswer-Screenshots**: Automatische Screenshots für alle Lückentext-Fragen (multianswer/cloze)
- **Viewport-Optimierung**: JavaScript-basierte Prüfung ob Element vollständig sichtbar
- **Intelligentes Scrolling**: Scrollt zum Element mit optimalem Abstand (block: start, dann -100px)
- **Längere Timeouts**: 5 Sekunden für komplexe Fragen statt 2 Sekunden
- **Fallback-Strategie**: Versucht erst `div.formulation`, dann gesamtes Question-Element
- **Rendering-Wartezeit**: 0.5s Wartezeit für vollständiges Rendering vor Screenshot

#### Intelligente PDF-Filterung
- **Teilantwort-Filterung bei Multianswer**: Bei "nur falsche Fragen" werden auch richtige Lücken ausgeblendet
- **Teilantwort-Filterung bei Sub-Questions**: Fehlerhafte Checkbox-Fragen werden intelligent gefiltert
- **Beispiel**: Frage mit 4 Lücken, 2 falsch → Zeigt nur die 2 falschen Lücken im PDF
- **Papier-Ersparnis**: Deutlich kompaktere PDFs im Filtermodus

#### Verbesserte Kommentar-Darstellung
- **HTML-Parsing**: Nutzt `comment_html` für strukturierte Kommentare
- **Listen-Formatierung**: `<li>`-Elemente werden als Bullet-Points (•) dargestellt
- **Leerzeichen statt Zeilenumbrüche**: Zwischen inline-HTML-Elementen werden Leerzeichen eingefügt
- **HTML-Entity-Dekodierung**: `html.unescape()` konvertiert `&lt;` zu `<` und `&gt;` zu `>`
- **Lesbarkeit**: Viel übersichtlichere Darstellung von Lehrer-Kommentaren

#### Gruppen-basierte Datenorganisation
- **Strukturänderung**: Ordnerstruktur geändert von `quiz_data/{quiz_name}/{prefix}/` zu `quiz_data/{prefix}/{quiz_name}/`
- **Vorteil**: Alle Quizzes einer Gruppe sind jetzt in einem Ordner
- **Mehrere Teams pro Präfix**: Alle Teams eines Präfixes in einem Ordner
- **Eindeutige Dateinamen**: `data_{group_id}.json` verhindert Überschreibungen
- **PDF-Organisation**: PDFs folgen der neuen Struktur: `LNW/{prefix}/{quiz_name}/`

#### Datumsfilter für Exam-Scraping
- **Interaktiver Dialog**: Fragt nach Startdatum beim Scraping (Format: TT.MM.YYYY)
- **CLI-Parameter**: `--since-date 28.01.2025` für nicht-interaktive Verwendung
- **Leere Eingabe**: Alle Versuche werden gescrapt (Standard-Verhalten)
- **Performance**: Filtert vor dem Scraping → weniger Review-Seiten müssen geladen werden
- **Filterung**: Nutzt `metadata.started` Feld zum Vergleich
- **Beispiel**: `python scripts/scrape_exams.py --since-date 01.11.2025` scrapt nur Versuche seit November 2025

### 🐛 Bugfixes

#### Login-Fehler in Worker-Threads
- **Problem**: Worker-Threads riefen `login()` mit falschen Parametern auf
- **Fix**: Korrekte Parameter-Reihenfolge und Navigation zur URL vor Login
- **Fehler**: `ValueError: could not convert string to float: '$4ndr@'`
- **Gelöst**: Login-Funktion erwartet `(driver, username, password, waittime)` ohne URL

#### Abgeschnittene Screenshots
- **Problem**: Screenshots wurden teilweise abgeschnitten
- **Fix**: Viewport-Prüfung stellt sicher, dass Element vollständig sichtbar ist
- **Verbesserung**: Scroll-Anpassung mit -100px Offset für bessere Sichtbarkeit

#### Identische Screenshots bei Multianswer
- **Problem**: Alle Multianswer-Screenshots waren identisch
- **Ursache**: Generischer Selektor `div.formulation` fand immer erstes Element
- **Fix**: Eindeutiger Selektor `#question-{question_id} div.formulation`

#### Fehlende Zeilenumbrüche in PDFs
- **Problem**: `\n` Zeichen in `question_text`, `comment` und anderen Textfeldern wurden nicht als Zeilenumbrüche gerendert
- **Betroffene Felder**: question_text, sub-question text, choice text, match text, blank answers, description content
- **Fix**: Alle Textfelder verwenden jetzt `_normalize_linebreaks()` + `_escape_html()` + `.replace('\n', '<br/>')`
- **Ergebnis**: Mehrzeilige Texte werden korrekt mit Zeilenumbrüchen dargestellt

### 📝 Dokumentation

- **README.md**: Aktualisiert mit neuen Features und Troubleshooting
- **src/exam/README.md**: Erweitert mit detaillierter Feature-Dokumentation
- **Verwendungsbeispiele**: Neue CLI-Beispiele mit `--max-workers` Parameter
- **Troubleshooting**: Neue Einträge für Performance und Screenshots

### ⚡ Performance

- **Scraping**: ~3x schneller durch parallele Verarbeitung (3 Worker)
- **Screenshot-Timeout**: Reduziert von 5s auf 2s (Standard), 5s für Multianswer
- **Scroll-Wartezeit**: Optimiert auf 0.1s (von 0.3s)

### 🔧 Technische Änderungen

#### src/exam/scraper.py
- Neue Imports: `ThreadPoolExecutor`, `as_completed`, `Lock`, `Optional` (typing)
- Neue statische Methode: `_scrape_attempt_worker()` für parallele Verarbeitung
- Neue Funktion: `parse_user_date()` für Datumsverarbeitung (TT.MM.YYYY → datetime)
- Erweiterte `scrape_quiz_for_group()`: Nutzt ThreadPoolExecutor
- Erweiterte `get_attempts_for_group()`: Neuer Parameter `since_date` für Datumsfilterung
- Geänderte Ordnerstruktur: `quiz_data/{prefix}/{quiz_name}/` statt `{quiz_name}/{prefix}/`
- Neuer Parameter `max_workers` in `run()` Methode
- CLI-Argument: `--max-workers` (Standard: 3)
- CLI-Argument: `--since-date` (Format: TT.MM.YYYY)
- Interaktiver Datumsfilter-Dialog bei interaktivem Modus
- Zeitanzeige am Ende mit `time.time()` Messung

#### src/exam/utils.py
- Verbesserte `take_element_screenshot()`:
  - Viewport-Prüfung mit JavaScript
  - Intelligentes Scrolling (block: start, -100px offset)
  - Längere Rendering-Wartezeit (0.5s)
- Erweiterte `parse_multianswer_question()`:
  - Screenshot-Erstellung für alle Multianswer-Fragen
  - Eindeutige Selektoren mit Question-ID
  - Fallback-Strategie

#### src/exam/pdf_generator.py
- Angepasste Pfad-Parsing-Logik für neue Ordnerstruktur `{prefix}/{quiz_name}/`
- Neue Methode: `_extract_comment_from_html()` für HTML-Parsing
- Verbesserte `_escape_html()`: HTML-Entity-Dekodierung mit `html.unescape()`
- **Zeilenumbruch-Fix in allen Render-Methoden**:
  - `_render_question()`: question_text mit Zeilenumbrüchen
  - `_render_multianswer()`: sub_q_text, blank answers, correct answers mit Zeilenumbrüchen
  - `_render_multichoice()`: choice text mit Zeilenumbrüchen
  - `_render_match()`: question_text und selected mit Zeilenumbrüchen
  - `_render_description()`: content mit Zeilenumbrüchen
- Erweiterte `_render_multianswer()`:
  - Filterung richtiger Blanks bei `only_incorrect`
  - Filterung richtiger Sub-Questions
  - Nutzung von `comment_html` statt `comment`

### 📦 Abhängigkeiten

Keine neuen Abhängigkeiten erforderlich. Alle Features nutzen Python Standard Library:
- `concurrent.futures` (bereits in Python 3.2+)
- `threading` (Standard Library)
- `html` (Standard Library)

---

## [Previous Versions]

Ältere Versionen vor November 2025 sind nicht in diesem Changelog dokumentiert.
