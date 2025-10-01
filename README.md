# Dokumentation für die Mebis Statistik

## Inhaltsverzeichnis
- [Dokumentation für die Mebis Statistik](#dokumentation-für-die-mebis-statistik)
  - [Inhaltsverzeichnis](#inhaltsverzeichnis)
  - [Idee](#idee)
  - [Voraussetzungen](#voraussetzungen)
  - [Anleitung](#anleitung)
  - [config](#config)

## Idee
Das Skript ermöglicht es den Status von Checklisten und Aufgaben eines Mebiskurses in der Konsole anzuzeigen.

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

## Konfiguration

Die Anwendung nutzt **Environment Variables** für die Konfiguration. Diese können auf zwei Wegen bereitgestellt werden:

1. **`.env` Datei** (empfohlen für lokale Entwicklung)
2. **System-Umgebungsvariablen** (empfohlen für Server/Produktion)

### 1. Erstelle die .env Datei

```bash
cp config/.env.template config/.env
```

Für Windows:
```cmd
copy config\.env.template config\.env
```

**Alternative: System-Umgebungsvariablen**

Statt einer `.env` Datei können die Werte auch als System-Umgebungsvariablen gesetzt werden. Dies ist besonders für Server-Deployments oder CI/CD-Pipelines nützlich.

### 2. Pflichtfelder konfigurieren

Öffne `config/.env` und passe folgende **ERFORDERLICHE** Werte an:

```env
# Mebis Login-Daten
MEBIS_USERNAME=dein_mebis_username
MEBIS_PASSWORD=dein_mebis_passwort

# Kurs-ID (findest du in der Mebis-Kurs-URL)
MEBIS_COURSE_ID=deine_kurs_id

# Export-Ordner für JSON-Dateien
EXPORT_FOLDER=export
```

**Hinweis zum Export-Ordner:**
- Kann ein relativer Pfad sein (z.B. `export`)
- Kann ein absoluter Pfad sein (z.B. `G:\Meine Ablage\Exports`)
- Der Ordner muss existieren, bevor du exportData.py ausführst

### 3. Optionale Konfigurationen

Alle verfügbaren Einstellungen sind in `config/.env.template` ausführlich dokumentiert:

- **Flask Environment** - `FLASK_ENV=production` oder `development`
- **Logging Level** - `LOG_LEVEL=INFO` (DEBUG/INFO/WARN/ERROR)
- **Selenium Modi** - `MODE_HEADLESS=True`, `MODE_WAITTIME=1`
- **Export-Ordner** - `EXPORT_FOLDER=export` (beliebiger Pfad)
- **Ignorierte Gruppen** - `MEBIS_IGNORED_GROUPS=IT_Lehrkraft,Test Team`
- **Grade Mapping** - JSON-Format für Bewertungsstufen
- **Server-Einstellungen** - `FLASK_HOST`, `FLASK_PORT`

### 4. Optionale Dateien

- `config/exclude_names.txt` - Liste mit ausgeschlossenen Benutzernamen (ein Name pro Zeile)

## Verwendung

**WICHTIG:** Vor der ersten Verwendung müssen Daten aus Mebis exportiert werden!

### 1. Daten exportieren (erforderlich!)

**Linux/Mac:**
```bash
python exportData.py
```

**Windows:**
```cmd
exportData.cmd
```

Dies lädt alle Daten aus Mebis und speichert sie als JSON-Datei im konfigurierten `EXPORT_FOLDER`.

⚠️ **Ohne diesen Schritt kann das Dashboard nicht gestartet werden!**

### 2. Dashboard starten

**Linux/Mac:**
```bash
python start_dashboard.py
```

**Windows:**
```cmd
start_dashboard.cmd
```

Dieser Befehl:
- Prüft die Konfiguration (`.env` Datei)
- Validiert Login-Credentials
- Prüft ob Export-Daten vorhanden sind
- Startet das Flask-Dashboard
- Öffnet automatisch den Browser

Das Dashboard ist dann erreichbar unter: `http://localhost:5000`

**Tipp:** Du kannst den Datenexport auch direkt aus dem Dashboard starten! Klicke auf den **"Aktualisieren"**-Button oben im Dashboard. Der Export läuft dann im Hintergrund und zeigt den Fortschritt an.

### Workflow

```
1. Konfiguration erstellen (config/.env)
   ↓
2. Daten exportieren (exportData.py / exportData.cmd)
   ↓
3. Dashboard starten (start_dashboard.py / start_dashboard.cmd)
   ↓
4. Dashboard im Browser nutzen (http://localhost:5000)
   ↓
5. (Optional) Daten aktualisieren über "Aktualisieren"-Button im Dashboard
```

**Hinweis:** Du musst Schritt 2 nur beim ersten Mal manuell ausführen. Danach kannst du Daten bequem über den "Aktualisieren"-Button im Dashboard aktualisieren.

## Features

### Datenexport über Dashboard

Der Export kann direkt aus dem Dashboard heraus gestartet werden:

1. Klicke auf den **"Aktualisieren"**-Button oben im Dashboard
2. Ein Fortschritts-Panel erscheint am rechten Bildschirmrand
3. Der Export zeigt live an:
   - Fortschritt in Prozent
   - Anzahl verarbeiteter Assignments, Checklists und Quizzes
   - Geschätzte Restzeit
4. Nach Abschluss wird das Dashboard automatisch mit den neuen Daten aktualisiert

**Vorteile:**
- Kein manuelles Ausführen von exportData.py nötig
- Live-Fortschrittsanzeige
- Export läuft im Hintergrund (Headless-Mode)
- Dashboard bleibt bedienbar während Export läuft

### Ignorierte Gruppen

Bestimmte Gruppen können vom Dashboard ausgeschlossen werden. Diese erscheinen dann nicht in der Dashboard-Anzeige.

**Konfiguration in `config/.env`:**
```env
MEBIS_IGNORED_GROUPS=IT_Lehrkraft,Test Team,Demo Gruppe
```

Die Filterung erfolgt nur auf Dashboard-Ebene. Die Gruppen werden weiterhin in den Export-Daten erfasst.

### Ausgeschlossene Benutzer

Einzelne Benutzer können von der Statistik ausgeschlossen werden.

**Datei:** `config/exclude_names.txt`
```
Max Mustermann
Test User
Demo Account
```

Ein Name pro Zeile. Diese Benutzer erscheinen nicht im Dashboard.

### Bewertungsstufen anpassen

Das Grade Mapping kann in der `.env` Datei angepasst werden:

```env
GRADE_MAPPING={"0": "* Nicht akzeptabel", "70": "** Verbesserungsbedarf", "100": "*** Solide Umsetzung", "130": "**** Exzellent"}
```

Format: JSON mit Punktzahl als Key (String) und Bewertungstext als Value.

## Troubleshooting

**Problem: "No export files found!"**
- Lösung: Führe zuerst `python exportData.py` aus um Daten zu exportieren
- Prüfe ob der `EXPORT_FOLDER` Pfad in `.env` korrekt ist

**Problem: "Login credentials not found"**
- Lösung: Prüfe ob `MEBIS_USERNAME` und `MEBIS_PASSWORD` in `config/.env` gesetzt sind

**Problem: "Export folder not found"**
- Lösung: Erstelle den Ordner oder passe `EXPORT_FOLDER` in `.env` an

**Problem: Dashboard zeigt veraltete Daten**
- Lösung: Klicke auf den "Aktualisieren"-Button im Dashboard oder führe `python exportData.py` manuell aus

**Problem: Export-Button im Dashboard funktioniert nicht**
- Lösung 1: Prüfe die Browser-Konsole auf Fehlermeldungen
- Lösung 2: Erhöhe `MODE_WAITTIME` in `.env` auf 5 oder 10 Sekunden
- Lösung 3: Setze `MODE_HEADLESS=False` in `.env` um zu sehen, was passiert
- Lösung 4: Prüfe die Logs in der Konsole wo `start_dashboard.py` läuft