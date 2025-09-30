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

Zusätzlich müssen folgende Ordner und Dateien angelegt werden:
- Ordner `export` im Projektverzeichnis
- Datei `config/exclude_names.txt` im config-Ordner (optional, für ausgeschlossene Benutzernamen)

## Konfiguration

1. **Erstelle die .env Datei:**
   ```bash
   cp config/.env.template config/.env
   ```

2. **Trage deine Mebis-Zugangsdaten ein:**

   Öffne `config/.env` und passe mindestens folgende Werte an:
   ```env
   # Mebis Login (ERFORDERLICH!)
   MEBIS_USERNAME=dein_mebis_username
   MEBIS_PASSWORD=dein_mebis_passwort

   # Kurs-ID (ERFORDERLICH!)
   MEBIS_COURSE_ID=deine_kurs_id

   # Ignorierte Gruppen (optional)
   MEBIS_IGNORED_GROUPS=IT_Lehrkraft,Test Team
   ```

3. **Weitere Konfigurationsoptionen:**

   Alle verfügbaren Einstellungen sind in `config/.env.template` dokumentiert:
   - Flask Environment (production/development)
   - Logging Level (DEBUG/INFO/WARN/ERROR)
   - Selenium Modi (Headless, Waittime)
   - Grade Mapping für Bewertungen

## Anleitung

1. Stelle sicher, dass die `config/.env` Datei korrekt konfiguriert ist
2. Starte das Python-Script `init.py` für Konsolenauswertung
3. Alternative: Starte `jsonExport2.py` um eine JSON Datei zu bekommen und `jsonAnalyse2.py` für die Auswertung

### Ignorierte Gruppen

Bestimmte Gruppen können vom Dashboard ausgeschlossen werden. Diese Gruppen erscheinen dann nicht in der Dashboard-Anzeige.

**Konfiguration in `.env`:**
```env
MEBIS_IGNORED_GROUPS=IT_Lehrkraft,Test Team,Demo Gruppe
```

Die Filterung erfolgt auf Dashboard-Ebene. Die Gruppen werden weiterhin in den Export-Daten erfasst.