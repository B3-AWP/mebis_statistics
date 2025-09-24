# Mebis Statistik Dashboard

Ein interaktives Web-Dashboard zur Visualisierung und Analyse von Mebis-Statistiken mit Gruppenfilterung und detaillierten Ansichten.

## Features

### 📊 Übersicht-Tab
- **Gruppenauswahl**: Filterung nach spezifischen Gruppen oder Anzeige aller Gruppen
- **Checklisten-Übersicht**:
  - Anzahl der 100% erfüllten Checklisten
  - Durchschnittlicher Fortschritt (Pflicht/Gesamt umschaltbar)
  - Gruppendurchschnitt
- **Pflichtaufgaben-Übersicht**:
  - Eingereichte vs. gesamte Pflichtaufgaben
  - Durchschnittsnote der Gruppe
- **Schulwochen-Slider**: Anpassung der Referenzwoche für zeitbasierte Berechnungen

### 📋 Checklisten-Tab
- **Tabellarische Ansicht** aller Personen der ausgewählten Gruppe
- **Filteroptionen**:
  - Nach Gruppe
  - Nach Fortschritt (alle, abgeschlossen, ausstehend, hoher Fortschritt)
  - Sortierung nach verschiedenen Kriterien
- **Visuelle Fortschrittsbalken** in den Tabellenzellen
- **Detail-Ansichten** für einzelne Personen

### 🎯 Pflichtaufgaben-Tab
- **Tabellarische Ansicht** aller Personen der ausgewählten Gruppe
- **Filteroptionen**:
  - Nach Gruppe
  - Nach Status (alle, erledigt, zu erledigen)
  - Nach Typ (alle, Aufgaben, Quizzes)
- **Detaillierte Statistiken**: Eingereicht, bewertet, Prozentsätze, Noten
- **Verlinkung** zu einzelnen Aufgaben

## Installation und Setup

### Voraussetzungen
- Python 3.8 oder höher
- Export-Dateien aus dem Mebis-System (JSON-Format)

### 1. Dependencies installieren
Die erforderlichen Python-Pakete werden automatisch beim ersten Start installiert:
```bash
pip install -r requirements.txt
```

Manuelle Installation:
```bash
pip install flask==2.3.3 flask-cors==4.0.0
```

### 2. Export-Daten bereitstellen
Stellen Sie sicher, dass der `export/` Ordner existiert und die neuesten JSON-Dateien enthält:
```
export/
├── output_20250922_224115.json
├── output_20250922_215951.json
└── ...
```

### 3. Dashboard starten

#### Option A: Windows Batch-Datei (empfohlen)
```bash
start_dashboard.bat
```

#### Option B: Python-Skript
```bash
python start_dashboard.py
```

#### Option C: Direkt über Backend
```bash
python dashboard_backend.py
```

Das Dashboard wird automatisch unter http://localhost:5000 verfügbar sein und der Browser öffnet sich automatisch.

## Verwendung

### Gruppenauswahl
1. Im **Übersicht-Tab** können Sie über das Dropdown-Menü eine spezifische Gruppe auswählen
2. "Alle Gruppen" zeigt aggregierte Daten aller Gruppen
3. Die Auswahl wirkt sich auf alle Statistiken aus

### Schulwochen-Anpassung
- Verwenden Sie den Slider zur Anpassung der Referenzwoche
- "Aktuelle Woche" setzt automatisch die berechnete Schulwoche
- Beeinflusst zeitbasierte Fortschrittsberechnungen

### Filter in Detailansichten
- **Checklisten-Tab**: Filtern Sie nach Fortschritt und sortieren Sie nach verschiedenen Kriterien
- **Pflichtaufgaben-Tab**: Filtern Sie nach Status und Typ der Aufgaben

## Technische Details

### Architektur
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Backend**: Python Flask mit REST API
- **Datenquelle**: JSON-Export-Dateien aus Mebis
- **Styling**: Übernommen vom Referenzprojekt mit responsivem Design

### API-Endpunkte
- `GET /api/data` - Vollständige Dashboard-Daten
- `GET /api/groups` - Liste verfügbarer Gruppen

### Datenverarbeitung
Das Backend verwendet die gleiche Logik wie `jsonAnalyse2.py`:
- Automatische Erkennung der neuesten Export-Datei
- Filterung nach `exclude_names.txt`
- Berechnung von Fortschritten und Durchschnitten
- Gruppierung nach Mebis-Gruppen

## Anpassungen

### CSS-Styling
Das Design basiert auf dem Referenzprojekt. Anpassungen können in `Referenzprojekt/style.css` vorgenommen werden.

### Konfiguration
- Ausgeschlossene Namen: `exclude_names.txt`
- Schulwochen-Einstellungen: Direkt im Dashboard oder im Code anpassbar

### Weitere Filter
Neue Filteroptionen können in `dashboard.js` hinzugefügt werden:
- Erweitern Sie die `applyChecklistFilters()` und `applyPflichtFilters()` Funktionen
- Fügen Sie entsprechende HTML-Elemente hinzu

## Fehlerbehebung

### Dashboard startet nicht
- Überprüfen Sie, ob Python korrekt installiert ist
- Stellen Sie sicher, dass der `export/` Ordner existiert und JSON-Dateien enthält
- Prüfen Sie die Konsole auf Fehlermeldungen

### Keine Daten sichtbar
- Überprüfen Sie die Browser-Konsole (F12) auf JavaScript-Fehler
- Stellen Sie sicher, dass die neueste Export-Datei korrekt formatiert ist
- Prüfen Sie die `exclude_names.txt` auf unbeabsichtigte Ausschlüsse

### Port bereits in Verwendung
Falls Port 5000 bereits belegt ist, ändern Sie die Port-Nummer in `dashboard_backend.py`:
```python
app.run(debug=False, host='0.0.0.0', port=5001)  # Anderen Port verwenden
```

## Weiterentwicklung

Das Dashboard ist modular aufgebaut und kann erweitert werden:
- Neue Tabs durch HTML/CSS/JS hinzufügen
- Zusätzliche API-Endpunkte im Backend definieren
- Erweiterte Visualisierungen mit Chart.js integrieren
- Export-Funktionen für Berichte implementieren

## Support

Bei Problemen oder Fragen:
1. Überprüfen Sie die Konsolen-Ausgaben
2. Stellen Sie sicher, dass alle Abhängigkeiten installiert sind
3. Überprüfen Sie die Dateiberechtigungen und -strukturen