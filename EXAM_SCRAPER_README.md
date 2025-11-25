# Mebis Quiz Scraper & PDF Generator

Automatisches Scraping und PDF-Generierung für Mebis Leistungsnachweise mit individuellen Schüler-PDFs.

## Übersicht

Dieses Tool erstellt druckfertige PDFs von Mebis-Quizzes (Leistungsnachweise), die:
- ✅ Für jeden Schüler ein eigenes PDF mit Datum im Dateinamen erstellen
- ✅ Alle Fragen mit Schülerantworten und Bewertungen enthalten
- ✅ Screenshots von Drag-and-Drop-Aufgaben mit platzierten Markern erstellen
- ✅ Optional nur fehlerhafte Fragen ausgeben (Papier sparen)
- ✅ Feedback und Kommentare farblich hervorheben (dunkelrot)
- ✅ Kopf- und Fußzeilen mit Name, Titel und Seitenzahlen
- ✅ Kompakt formatiert sind mit optimalem Layout

## Neue Features (2025)

### ✨ Individuelle PDFs mit Datum
- Jeder Schüler erhält ein eigenes PDF
- Dateiname: `YYYYMMDD_QuizName_Gruppe_Name.pdf`
- Beispiel: `20251017_Frontend_IFA12B-Team1_MaxMustermann.pdf`

### 📸 Screenshots für Drag-and-Drop
- Automatische Screenshots von ddmarker-Fragen mit allen platzierten Markern
- Eindeutige Dateinamen pro Student (keine Überschreibung)
- Fallback auf Textdarstellung falls Screenshot fehlschlägt

### 🎨 Farbliche Gestaltung
- **Dunkelgrün (#006400)**: Richtige Antworten
- **Dunkelrot (#8B0000)**: Falsche Antworten, Feedback, Kommentare
- Checkboxes: `[x]` für ausgewählt, `[ ]` für nicht ausgewählt

### 💾 Papier-Spar-Modus
- Optionaler Filter: Nur fehlerhafte/teilweise richtige Fragen ausgeben
- Intelligente Punkteauswertung (nicht status-basiert)
- Interaktiver Dialog beim Starten

### 📐 Layout-Optimierungen
- Zweispalten-Layout: Links Frage/Status, rechts Punkte (rechtsbündig)
- Kopfzeile: Name (links), Quiz-Titel (rechts)
- Fußzeile: Zentrierte Seitenzahlen "Seite x von y"
- Bilder auf 50% Originalgröße skaliert
- Mehrfache Leerzeilen auf eine reduziert

## Architektur

### Module

1. **exam_utils.py** - Hilfsklassen
   - `QuizParser`: Konvertiert HTML zu strukturiertem JSON
   - `ImageDownloader`: Lädt Bilder und erstellt Screenshots
   - `QuestionTypeDetector`: Erkennt Fragetypen

2. **exam_scraper.py** - Scraping-Engine
   - Interaktive Auswahl von Quizzes und Gruppen
   - Scrapt Quiz-Versuche pro Gruppe
   - Force-rescrape standardmäßig aktiv
   - Speichert strukturierte Daten als JSON

3. **exam_pdf_generator.py** - PDF-Erstellung
   - Generiert individuelle PDFs pro Schüler
   - Unterstützt alle Fragetypen inkl. Screenshots
   - Kompaktes Layout mit Farben

### Verzeichnisstruktur

```
mebis_statistics/
├── exam_scraper.py         # CLI: Scraping
├── exam_pdf_generator.py   # CLI: PDF-Generierung
├── exam_utils.py           # Helper-Klassen
├── quiz_data/              # Gescrapte Daten
│   └── {quiz_name}/
│       └── {group_name}/
│           ├── data.json
│           └── images/
│               ├── q1_attempt123_ddmarker_screenshot.png
│               ├── q1_attempt456_ddmarker_screenshot.png
│               └── ...
└── LNW/                    # Fertige PDFs
    └── {quiz_name}/
        ├── 20251017_QuizName_Gruppe_Student1.pdf
        ├── 20251017_QuizName_Gruppe_Student2.pdf
        └── ...
```

## Installation

```bash
# Abhängigkeiten installieren
pip install -r requirements.txt
```

Dependencies:
- `selenium` - Browser-Automation
- `beautifulsoup4` - HTML-Parsing
- `reportlab` - PDF-Generierung
- `Pillow` - Bildverarbeitung
- `lxml` - Parser-Backend

## Verwendung

### 1. Scraping: Quiz-Daten abrufen

```bash
# Interaktiver Modus (empfohlen)
python exam_scraper.py

# Alle Leistungsnachweise scrapen (ohne Bestätigung)
python exam_scraper.py

# Nur ein spezifisches Quiz
python exam_scraper.py --quiz-id 71532121

# Nur eine spezifische Gruppe
python exam_scraper.py --group 479509

# Vorhandene Daten NICHT überschreiben
python exam_scraper.py --skip-existing

# Browser sichtbar machen (für Debugging)
python exam_scraper.py --headless False
```

**Interaktiver Modus:**
```
Verfügbare Quizzes:
  1. Frontend (Leistungsnachweis) (ID: 71532121)
  2. PHP Grundlagen (Leistungsnachweis) (ID: 71532124)
  3. Alle Quizzes

Wähle Quizzes (z.B. 1,2 oder 1-2 oder 3 für alle): 1,2

Ausgewählte Quizzes (2):
  - Frontend (Leistungsnachweis)
  - PHP Grundlagen (Leistungsnachweis)

Verfügbare Gruppen:
  1. IFA12A - Team 1 (ID: 479509)
  2. IFA12A - Team 2 (ID: 479512)
  3. Alle Gruppen

Wähle Gruppen (z.B. 1,2 oder 1-2 oder 3 für alle): 3

[Scraping startet direkt ohne weitere Bestätigung]
```

**Was passiert beim Scraping:**
1. Login zu Mebis mit Anmeldedaten aus `.env`
2. Findet alle Quizzes mit "(Leistungsnachweis)" im Namen
3. Für jedes Quiz und jede Gruppe:
   - Ruft Versuchsliste ab (nur neuester Versuch pro Schüler)
   - Scrapt Review-Seiten mit allen Fragen
   - Erstellt Screenshots von ddmarker-Fragen
   - Lädt Bilder mit Session-Cookies herunter
   - Extrahiert Feedback mit Zeilenumbrüchen
   - Speichert strukturierte Daten in `quiz_data/`
4. **Standardmäßig** werden vorhandene Daten überschrieben

### 2. PDF-Generierung

```bash
# Alle gescrapten Daten zu PDFs konvertieren
python exam_pdf_generator.py

# Nur fehlerhafte Fragen ausgeben (Papier sparen)
python exam_pdf_generator.py --only-incorrect

# Eigenes Daten-Verzeichnis angeben
python exam_pdf_generator.py --data-dir quiz_data --output-dir LNW
```

**Interaktiver Modus:**
```
============================================================
PDF-GENERIERUNG - OPTIONEN
============================================================

Nur falsche/teilweise richtige Fragen ausgeben? (j/n) [n]: j
✓ Nur fehlerhafte Fragen werden ausgegeben (Papier sparen)
============================================================

Starting PDF generation...
Loading data from quiz_data/Frontend (...)/IFA12B - Team 1/data.json...
Generating PDF for Max Mustermann...
Successfully generated PDF: LNW/.../20251017_Frontend_IFA12B-Team1_MaxMustermann.pdf
[...]
Generated 15 individual PDFs in LNW/Frontend (...)
```

**Was passiert bei der PDF-Generierung:**
1. Durchsucht `quiz_data/` nach `data.json` Dateien
2. Für jeden Schüler:
   - Extrahiert Datum aus Metadaten
   - Erstellt individuelles PDF mit Datum im Dateinamen
   - Rendert alle Fragen (oder nur fehlerhafte)
   - Bindet Screenshots und Bilder ein (auf 50% skaliert)
   - Fügt Kopf-/Fußzeilen hinzu
3. Speichert PDFs in `LNW/{quiz_name}/`

### 3. Workflow: Komplett-Durchlauf

```bash
# 1. Daten scrapen (interaktiv)
python exam_scraper.py

# 2. PDFs generieren (mit Papier-Spar-Option)
python exam_pdf_generator.py

# Fertig! Individuelle PDFs sind in LNW/ verfügbar
```

## PDF-Format

### Layout-Eigenschaften

- **Seitengröße:** A4
- **Ränder:** Links/Rechts 1,5 cm, Oben 2,5 cm (für Kopfzeile), Unten 2,0 cm (für Fußzeile)
- **Schriftarten:** Helvetica (kompakt und lesbar)
- **Farben:**
  - Richtig: Dunkelgrün (#006400)
  - Falsch/Feedback/Kommentare: Dunkelrot (#8B0000)
- **Bilder:** 50% Originalgröße für optimalen Druck

### PDF-Struktur (pro Schüler)

```
┌────────────────────────────────────────────────────────┐
│ Max Mustermann          Frontend (Leistungsnachweis)   │ ← Kopfzeile
├────────────────────────────────────────────────────────┤

═══════════════════════════════════════════════════════════
LEISTUNGSNACHWEIS: Frontend (Softwareergonomie, HTML und CSS)
═══════════════════════════════════════════════════════════
Name: Max Mustermann                   Gruppe: IFA12B - Team 1
Begonnen: Freitag, 17. Okt. 2025      Dauer: 22 Minuten 16 Sek
Punkte: 47,50/57,00                   Note: 83,33 von 100,00

Feedback: Du hast eine 2 erreicht. Das ist eine
fantastische Leistung...
───────────────────────────────────────────────────────────

SOFTWAREERGONOMIE

Frage 1  ✓ richtig                    1,00 von 3,00 Punkten

Was ist Softwareergonomie?

Ihre Antwort:
Softwareergonomie befasst sich mit der Benutzerfreundlichkeit
von Software.

Frage 2  ✗ falsch                     0,00 von 4,00 Punkten

Ordnen Sie die Begriffe zu...

[Screenshot mit platzierten Markern - 50% Größe]

Feedback: Die Antwort ist teilweise richtig.
[Feedback-Bild - 50% Größe]

Kommentar: 2 richtig, aber 3 falsch positioniert.
Bitte beachten Sie die Definition im Skript.

└────────────────────────────────────────────────────────┘
│                    Seite 1 von 3                        │ ← Fußzeile
└────────────────────────────────────────────────────────┘
```

### Unterstützte Fragetypen

| Fragentyp | Darstellung |
|-----------|-------------|
| `ddmarker` / `ddmarker-readonly` | **Screenshot** mit allen platzierten Markern (kein Text) |
| `multichoice` / `truefalse` | Checkbox-Liste `[x]`/`[ ]` mit Farb-Markierung |
| `essay` / `shortanswer` | Mehrzeiliger Text mit Zeilenumbrüchen |
| `multianswer` (Lückentext) | Nummerierte Lücken mit Antworten und Feedback |
| `match` (Zuordnung) | Zuordnungstabelle mit Korrektheit |
| `description` | **Wird übersprungen** (nur Informationstext) |
| Andere | Hinweis auf Online-Version |

### Filter-Logik (Papier-Spar-Modus)

**Fragen werden ausgegeben wenn:**
- Erreichte Punkte < Maximale Punkte
- Status = "teilweise richtig"
- Status = "falsch"

**Fragen werden übersprungen wenn:**
- Erreichte Punkte >= Maximale Punkte (100% richtig)
- Status = "description" (immer)

**Beispiel:**
- Frage mit 7,00 von 7,00 Punkten → Überspringen ✓
- Frage mit 4,50 von 7,00 Punkten → Anzeigen ✓
- Frage mit Status "vollständig" aber 3,00/7,00 → Anzeigen ✓

## Konfiguration

Die Konfiguration erfolgt über `.env`:

```ini
# Mebis-Zugangsdaten
MEBIS_USERNAME=your_username
MEBIS_PASSWORD=your_password

# Kurs-ID
MEBIS_COURSE_ID=2036416

# Browser-Einstellungen
MODE_HEADLESS=True
MODE_WAITTIME=5
```

## Datenstruktur (quiz_data)

### data.json Schema (aktualisiert)

```json
{
  "quiz_info": {
    "quiz_id": "71532121",
    "quiz_name": "Frontend (Leistungsnachweis)",
    "group_id": "479509",
    "group_name": "IFA12B - Team 1",
    "scraped_date": "2025-01-23T10:30:00"
  },
  "students": [
    {
      "user_id": "3375510",
      "user_name": "Max Mustermann",
      "attempt_id": "9764734",
      "metadata": {
        "started": "Freitag, 17. Oktober 2025, 09:45",
        "duration": "22 Minuten 16 Sekunden",
        "points": "47,50/57,00",
        "grade": "83,33 von 100,00",
        "feedback": "Du hast eine 2 erreicht.\nDas ist eine fantastische Leistung..."
      },
      "sections": [
        {
          "section_name": "Softwareergonomie",
          "questions": [
            {
              "question_id": "10596283-2",
              "question_number": "1",
              "question_type": "ddmarker-readonly",
              "question_text": "Ordnen Sie die Begriffe zu...",
              "status": "vollständig",
              "points": "Erreichte Punkte 4,50 von 7,00",
              "background_image": {
                "local_path": "images/q1_attempt9764734_ddmarker_screenshot.png",
                "success": true,
                "alt": "Drag-and-Drop Screenshot mit Markern"
              },
              "markers": [
                {"text": "Präsentationsschicht", "position": "73px / 34px"},
                {"text": "Infrastrukturschicht", "position": "87px / 325px"}
              ],
              "feedback": {
                "text": "Die Antwort ist teilweise richtig.\nBitte überprüfen Sie...",
                "images": [...]
              },
              "comment": "2 richtig, aber 3 falsch.\nBitte beachten Sie die Definition im Skript.",
              "comment_html": "..."
            }
          ]
        }
      ]
    }
  ]
}
```

**Wichtige Änderungen:**
- `background_image.local_path` enthält jetzt Screenshot mit `attempt_id`
- `feedback`, `comment` mit Zeilenumbrüchen (`\n`)
- `points` im Format "Erreichte Punkte X von Y"
- `markers` nur als Fallback-Info (Screenshot ist primär)

## Fehlerbehandlung

### Häufige Probleme

**Problem:** "No quizzes found to scrape"
- **Lösung:** Prüfe ob Quizzes mit "(Leistungsnachweis)" im Namen existieren

**Problem:** "Failed to obtain sesskey"
- **Lösung:** Prüfe Zugangsdaten in `.env`

**Problem:** "Screenshot failed for ddmarker question"
- **Details:** Fehlermeldung enthält jetzt URL zur Überprüfung
- **Lösung:** Öffne URL im Browser, prüfe ob Element sichtbar ist

**Problem:** Bilder werden nicht heruntergeladen
- **Details:** "Downloaded HTML instead of image - likely authentication issue. URL: ..."
- **Lösung:** Session-Cookies werden automatisch übertragen; prüfe Netzwerkverbindung

**Problem:** PDFs zeigen vollständig richtige Fragen trotz --only-incorrect
- **Lösung:** Filter basiert auf Punkten (erreicht >= maximum), nicht auf Status

**Problem:** Keine Zeilenumbrüche in Feedback/Kommentaren
- **Lösung:** Neu scrapen - alte Daten hatten keine `\n`-Erhaltung

### Logs mit URL-Information

Fehler-Logs enthalten jetzt die Review-URL zur Überprüfung:

```
[ERROR] exam_utils - ✗ Screenshot failed for ddmarker question 18 - URL: https://lernplattform.mebis.bycs.de/mod/quiz/review.php?attempt=9764734
[ERROR] exam_utils - Downloaded HTML instead of image - likely authentication issue. URL: https://lernplattform.mebis.bycs.de/pluginfile.php/...
```

## Caching & Performance

### Scraping-Verhalten

- **Standardmäßig**: Vorhandene Daten werden **überschrieben** (force_rescrape=True)
- Mit `--skip-existing`: Vorhandene Daten überspringen
- Screenshots werden mit eindeutigen Dateinamen pro Schüler gespeichert

### PDF-Generierung

- Schnelle Regenerierung möglich (nutzt gecachte JSON-Daten)
- Keine erneute Netzwerkverbindung nötig
- Bilder werden aus `quiz_data/*/images/` geladen

## Tipps & Best Practices

### Effizienter Workflow

1. **Einmaliges Scraping am Semesterende**
   ```bash
   python exam_scraper.py
   # Interaktiv: Wähle alle Quizzes und alle Gruppen
   ```

2. **PDF mit verschiedenen Optionen testen**
   ```bash
   # Vollständige PDFs
   python exam_pdf_generator.py

   # Nur Fehler (für Nachbesprechungen)
   python exam_pdf_generator.py --only-incorrect
   ```

3. **Selektives Update bei Änderungen**
   ```bash
   python exam_scraper.py --quiz-id 71532121
   ```

### Papier sparen

**Option 1: Nur fehlerhafte Fragen**
```bash
python exam_pdf_generator.py --only-incorrect
```
Spart ca. 30-60% Papier (je nach Leistung)

**Option 2: Beidseitiger Druck**
- PDFs sind für beidseitigen Druck optimiert
- Spart zusätzlich 50% Papier

**Option 3: Mehrere Seiten pro Blatt**
- PDF-Viewer: 2 Seiten pro Blatt drucken
- Spart weitere 50% Papier
- Noch gut lesbar dank kompaktem Layout

### Debugging

**Browser sichtbar machen:**
```bash
python exam_scraper.py --headless False
```

**Einzelne Komponenten prüfen:**
1. JSON-Daten: `quiz_data/{quiz}/data.json`
2. Screenshots: `quiz_data/{quiz}/images/q*_attempt*_ddmarker_screenshot.png`
3. Scraping-Logs: URL-Informationen bei Fehlern
4. PDF-Rendering: Prüfe Bilder und Zeilenumbrüche

**Typische Debugging-Schritte:**
1. Öffne `data.json` → Sind Fragen vorhanden?
2. Prüfe `images/` → Sind Screenshots erstellt?
3. Öffne URL aus Error-Log → Ist Element sichtbar?
4. Teste PDF-Generierung isoliert für ein Quiz

## Technische Details

### Screenshot-Mechanismus

1. Selenium findet `div.droparea` Element
2. Scrollt Element ins Sichtfeld
3. Wartet 0,5s für JS-Rendering
4. Erstellt Screenshot des Elements (nicht ganzer Seite)
5. Speichert als `q{N}_attempt{ID}_ddmarker_screenshot.png`

### Bildverarbeitung

- PIL/Pillow für Größenberechnung
- Konvertierung: Pixel (96 DPI) → PDF Points (72 DPI)
- Skalierung: 50% Originalgröße
- Aspect Ratio wird erhalten

### Zeilenumbruch-Verarbeitung

**Beim Scraping:**
```python
# BeautifulSoup mit separator='\n'
text = element.get_text(separator='\n', strip=True)
```

**Im PDF:**
```python
# Normalisierung: \n\n\n → \n\n (max 1 Leerzeile)
text = re.sub(r'\n{3,}', '\n\n', text)
# Rendering: \n → <br/>
text = text.replace('\n', '<br/>')
```

### Dateinamen-Generierung

```python
# Parse Datum: "Freitag, 17. Oktober 2025, 09:45"
date_prefix = "20251017_"  # YYYYMMDD

# Bereinige Namen (nur alphanumerisch, -, _)
safe_name = "Frontend_IFA12B-Team1_MaxMustermann"

# Kombiniere
filename = f"{date_prefix}{safe_name}.pdf"
# → 20251017_Frontend_IFA12B-Team1_MaxMustermann.pdf
```

## Changelog

### v2.0 (Januar 2025)
- ✨ Individuelle PDFs pro Schüler mit Datum im Dateinamen
- 📸 Screenshots für ddmarker-Fragen mit eindeutigen Dateinamen
- 🎨 Farbliche Gestaltung (dunkelgrün/dunkelrot)
- 💾 Papier-Spar-Modus (nur fehlerhafte Fragen)
- 📐 Header/Footer mit Seitenzahlen
- 🔄 Zeilenumbrüche in Feedback/Kommentaren
- 📏 Bilder auf 50% Originalgröße skaliert
- ⚙️ Force-rescrape standardmäßig aktiv
- 🔍 URL in Fehler-Logs
- 🚫 Description-Fragen werden übersprungen
- ✅ Interaktive Auswahl ohne Bestätigung

### v1.0 (Ursprung)
- Grundlegendes Scraping und PDF-Generierung
- Unterstützung für Basis-Fragetypen
- Gruppen-PDFs

## Support

Bei Problemen:
1. Prüfe Logs (mit URL-Informationen)
2. Validiere `quiz_data/` Struktur
3. Teste mit einzelnem Quiz: `python exam_scraper.py --quiz-id QUIZ_ID`
4. Prüfe Screenshots in `images/` Ordner
5. Teste PDF-Generierung: `python exam_pdf_generator.py --data-dir quiz_data`

## Lizenz

Internes Tool für Schulgebrauch.
