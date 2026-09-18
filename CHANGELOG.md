# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

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
