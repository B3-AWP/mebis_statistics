# Mebis Quiz Scraper & PDF Generator

Automatisches Scraping und PDF-Generierung für Mebis Leistungsnachweise.

## Übersicht

Dieses Feature erstellt druckfähige PDFs von Mebis-Quizzes (Leistungsnachweise), die:
- Alle Fragen mit Schülerantworten enthalten
- Bewertungen und Feedback dokumentieren
- Nach Gruppen organisiert sind
- Kompakt formatiert sind (minimale Abstände für weniger Papierverbrauch)

## Architektur

### Module

1. **exam_utils.py** - Hilfsklassen
   - `QuizParser`: Konvertiert HTML zu strukturiertem JSON
   - `ImageDownloader`: Lädt Bilder mit Retry-Logik
   - `QuestionTypeDetector`: Erkennt Fragetypen

2. **exam_scraper.py** - Scraping-Engine
   - Findet alle Leistungsnachweise automatisch
   - Scrapt Quiz-Versuche pro Gruppe
   - Speichert strukturierte Daten als JSON

3. **exam_pdf_generator.py** - PDF-Erstellung
   - Generiert druckfertige PDFs mit ReportLab
   - Unterstützt alle Fragetypen
   - Kompaktes Layout (Graustufen-Druck)

### Verzeichnisstruktur

```
mebis_statistics/
├── exam_scraper.py         # CLI: Scraping
├── exam_pdf_generator.py   # CLI: PDF-Generierung
├── exam_utils.py           # Helper-Klassen
├── quiz_data/              # Gescrapte Daten (gecached)
│   └── {quiz_name}/
│       └── {group_name}/
│           ├── data.json
│           └── images/
└── LNW/                    # Fertige PDFs
    └── {quiz_name}/
        └── {quiz_name}_{group}.pdf
```

## Installation

```bash
# Abhängigkeiten installieren
pip install -r requirements.txt
```

Neue Dependencies:
- `beautifulsoup4` - HTML-Parsing
- `reportlab` - PDF-Generierung
- `lxml` - Parser-Backend

## Verwendung

### 1. Scraping: Quiz-Daten abrufen

```bash
# Alle Leistungsnachweise scrapen
python exam_scraper.py

# Nur ein spezifisches Quiz
python exam_scraper.py --quiz-id 71532121

# Nur eine spezifische Gruppe
python exam_scraper.py --group 479509

# Gecachte Daten ignorieren und neu scrapen
python exam_scraper.py --force-rescrape

# Browser im Nicht-Headless-Modus (für Debugging)
python exam_scraper.py --headless False
```

**Was passiert beim Scraping:**
1. Login zu Mebis
2. Findet alle Quizzes mit "(Leistungsnachweis)" im Namen
3. Für jedes Quiz und jede Gruppe:
   - Ruft Versuchsliste ab
   - Scrapt Review-Seiten (nur neuester Versuch pro Schüler)
   - Lädt Bilder herunter
   - Speichert strukturierte Daten in `quiz_data/`

**Beispiel-Output:**
```
Starting Mebis Quiz Scraper...
Headless: True, Waittime: 5s
Starting browser session...
Session started successfully (sesskey: 1a2b3c4d5e...)
Discovering quizzes with '(Leistungsnachweis)' in name...
Found quiz: Frontend (Leistungsnachweis) (ID: 71532121)
Found quiz: PHP Grundlagen (Leistungsnachweis) (ID: 71532124)
Discovered 2 Leistungsnachweise

Fetching groups...
Found group: IFA12C (ID: 479509)
Found group: IFA12D (ID: 479512)
Found 2 groups

============================================================
Progress: 1/4
============================================================
Processing quiz 'Frontend (Leistungsnachweis)' for group 'IFA12C'...
Fetching attempts for quiz 71532121, group 479509...
Found 15 unique student attempts
[1/15] Scraping attempt for Ann-Kathrin Rauch...
Successfully saved data for 15 students to quiz_data/Frontend (Leistungsnachweis)/IFA12C/data.json

[... weitere Kombinationen ...]

============================================================
SCRAPING COMPLETED
============================================================
Processed 2 quizzes x 2 groups = 4 combinations
```

### 2. PDF-Generierung

```bash
# Alle gescrapten Daten zu PDFs konvertieren
python exam_pdf_generator.py

# Eigenes Daten-Verzeichnis angeben
python exam_pdf_generator.py --data-dir quiz_data --output-dir LNW
```

**Was passiert bei der PDF-Generierung:**
1. Durchsucht `quiz_data/` nach `data.json` Dateien
2. Für jede Gruppe: Erstellt ein PDF mit allen Schülern
3. Speichert PDFs in `LNW/{quiz_name}/`

**Beispiel-Output:**
```
Starting PDF generation...
Loading data from quiz_data/Frontend (Leistungsnachweis)/IFA12C/data.json...
Generating PDF for student Ann-Kathrin Rauch...
Generating PDF for student Max Mustermann...
[... weitere Schüler ...]
Successfully generated group PDF: LNW/Frontend (Leistungsnachweis)/Frontend (Leistungsnachweis)_IFA12C.pdf

[... weitere Gruppen ...]

PDF generation completed
```

### 3. Workflow: Komplett-Durchlauf

```bash
# 1. Daten scrapen
python exam_scraper.py

# 2. PDFs generieren
python exam_pdf_generator.py

# Fertig! PDFs sind in LNW/ verfügbar
```

## PDF-Format

### Layout-Eigenschaften

- **Seitengröße:** A4
- **Ränder:** 1,5 cm
- **Schriftarten:** Helvetica (kompakt und lesbar)
- **Farben:** Graustufen (druckfreundlich)

### PDF-Struktur (pro Schüler)

```
═══════════════════════════════════════════════════════════
LEISTUNGSNACHWEIS: Frontend (Softwareergonomie, HTML und CSS)
═══════════════════════════════════════════════════════════
Name: Ann-Kathrin Rauch                    Gruppe: IFA12C
Begonnen: 26.09.2025, 11:22               Dauer: 19 Min 16 Sek
Punkte: 42,00 / 57,00                     Note: 73,68 / 100,00

Feedback: Du hast eine 3 erreicht...
───────────────────────────────────────────────────────────

┌─ SOFTWAREERGONOMIE ─────────────────────────────────────┐

Frage 1    ✗ FALSCH    Punkte: 0,00 von 4,00

Ordnen Sie die Begriffe der traditionellen...

[Hintergrundbild]

Ihre Antworten:
• Präsentationsschicht (Position: 73,34)
• Infrastrukturschicht (Position: 87,325)

Feedback: Die Antwort ist falsch.
[Feedback-Bild]

Kommentar: 2 richtig, aber 5 falsch

└──────────────────────────────────────────────────────────┘

[... weitere Fragen ...]
```

### Unterstützte Fragetypen

| Fragentyp | Darstellung |
|-----------|-------------|
| `ddmarker` | Hintergrundbild + Liste platzierter Marker |
| `multichoice` | Checkbox-Liste (☑/☐) mit Korrektheit-Markierung |
| `truefalse` | Wahr/Falsch-Auswahl |
| `shortanswer` | Freitext-Antwort |
| `essay` | Mehrzeiliger Textblock |
| `match` | Zuordnungstabelle |
| Andere | Hinweis auf Online-Version |

### Status-Icons

- ✓ = Richtig (dunkelgrau)
- ✗ = Falsch (mittelgrau)
- ◐ = Teilweise richtig (grau)

## Konfiguration

Die Konfiguration erfolgt über `.env` (siehe `config/.env`):

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

### data.json Schema

```json
{
  "quiz_info": {
    "quiz_id": "71532121",
    "quiz_name": "Frontend (Leistungsnachweis)",
    "group_id": "479509",
    "group_name": "IFA12C",
    "scraped_date": "2025-01-23T10:30:00"
  },
  "students": [
    {
      "user_id": "3375510",
      "user_name": "Ann-Kathrin Rauch",
      "group_id": "479509",
      "group_name": "IFA12C",
      "attempt_id": "9764734",
      "metadata": {
        "started": "26. September 2025, 11:22:53",
        "duration": "19 Minuten 16 Sekunden",
        "points": "42,00/57,00",
        "grade": "73,68 von 100,00",
        "feedback": "Du hast eine 3 erreicht..."
      },
      "sections": [
        {
          "section_name": "Softwareergonomie",
          "questions": [
            {
              "question_id": "10596283-2",
              "question_number": "1",
              "question_type": "ddmarker",
              "question_text": "Ordnen Sie die Begriffe...",
              "status": "incorrect",
              "points": "0,00 von 4,00",
              "background_image": {
                "original_url": "https://...",
                "local_path": "images/q1_bg_1.png",
                "success": true
              },
              "markers": [
                {"text": "Präsentationsschicht", "position": "73,34"}
              ],
              "feedback": {
                "text": "Die Antwort ist falsch.",
                "images": [...]
              },
              "comment": "2 richtig, aber 5 falsch"
            }
          ]
        }
      ]
    }
  ]
}
```

## Fehlerbehandlung

### Häufige Probleme

**Problem:** "No quizzes found to scrape"
- **Lösung:** Prüfe ob Quizzes mit "(Leistungsnachweis)" im Namen existieren

**Problem:** "Failed to obtain sesskey"
- **Lösung:** Prüfe Zugangsdaten in `config/.env`

**Problem:** Bilder werden nicht heruntergeladen
- **Lösung:** Prüfe Netzwerkverbindung; Bilder werden mit Platzhalter ersetzt

**Problem:** PDFs enthalten keine Fragen
- **Lösung:** Prüfe ob Scraping erfolgreich war (`quiz_data/` enthält data.json mit Fragen)

### Logs

Logs werden in der Konsole ausgegeben:
```
[INFO] exam_scraper - Starting browser session...
[INFO] exam_utils - Successfully downloaded: q1_bg_1.png
[WARNING] exam_utils - Unknown question type for classes: ['que', 'custom']
[ERROR] exam_scraper - Error scraping review page: ...
```

## Caching

- Gescrapte Daten werden in `quiz_data/` gecached
- Bei erneutem Scraping werden vorhandene Daten **übersprungen**
- Mit `--force-rescrape` können Daten neu abgerufen werden
- Vorteil: Schnellere PDF-Regenerierung ohne erneutes Scraping

## Tipps

### Effizienter Workflow

1. **Einmaliges Scraping:** Scrape alle Quizzes einmal am Ende des Semesters
   ```bash
   python exam_scraper.py
   ```

2. **PDF-Regenerierung:** Falls Layout-Änderungen nötig sind, nur PDFs neu generieren
   ```bash
   python exam_pdf_generator.py
   ```

3. **Selektives Update:** Nur ein Quiz neu scrapen
   ```bash
   python exam_scraper.py --quiz-id 71532121 --force-rescrape
   ```

### Debugging

- Verwenden Sie `--headless False` um Browser-Fenster zu sehen
- Prüfen Sie `quiz_data/{quiz}/data.json` für gescrapte Rohdaten
- Bei PDF-Problemen: Prüfen Sie ob Bilder in `images/` vorhanden sind

## Erweiterungen (zukünftig)

- [ ] Integration ins Dashboard (Button "Quiz als PDF exportieren")
- [ ] Filterung nach Datum (z.B. nur Quizzes aus diesem Semester)
- [ ] Statistik-Seite im PDF (Durchschnittsnote, Schwierigste Frage, etc.)
- [ ] Export einzelner Schüler-PDFs (statt Gruppen-PDF)
- [ ] Unterstützung für weitere Fragetypen (Lückentext, Zuordnung, etc.)

## Support

Bei Problemen oder Fragen:
1. Prüfe Logs in der Konsole
2. Validiere `quiz_data/` Struktur
3. Teste mit einem einzelnen Quiz: `python exam_scraper.py --quiz-id QUIZ_ID`
