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
- Datei `exclude_names.txt` im Projektverzeichnis

## Anleitung
1. Erstelle config.ini Datei mit folgenden Inhalt. Hinterlege den Mebis Username und Password
2. Starte das Python-Script init.py für Konsolenauswertung
Alternative: Starte jsonExport2.py um ein JSON Datei zu bekommen und jsonAnalyse2.py für die Auswertung

## config
Erstelle eine config.ini Datei mit folgendem Inhalt
```ini
    [login]
    username = Hello
    password = World

    [mode]
    headless = True
    waittime = 1

    [urls]
    base_url = https://lernplattform.mebis.bycs.de/report/progress/index.php
    common_params = &sifirst=&activityorder=orderincourse&activitysection=-1

    [courses]
    course_ifa12 = 1657519

    [groups]
    ifa12a = 366526
    ifa12b = 366529

    [activities]
    checklist = checklist
    assignments = assign

    [thresholds]
    green = 90
    yellow = 50
    orange = 10
    red = 0


    [General]
    Directory = export
    Filename = report.html
    TotalWeeks = 9
    ShowCommandDialog = True
    DefaultGroup = 1
    ;0 = IFA12A 1 = IFA12B
    DefaultCategories = 0
    DefaultCurrentWeek = 7

    [Analysis]
    LaggardThreshold = 50
    GenerateIndividualReports = True

    [IgnoreGroups]
    ; Gruppen die im Dashboard nicht angezeigt werden sollen
    ; Beispiel: TestGruppe = IFA12A - Test Team
    ; Entferne das Semikolon vor einer Zeile um eine Gruppe zu ignorieren:
    ; test_group = IFA12A - Team 5
    IT_Lehrkraft = IT-Lehrkraft
```

### IgnoreGroups Funktionalität

Die `[IgnoreGroups]` Sektion ermöglicht es, bestimmte Gruppen vom Dashboard auszuschließen. Gruppen die hier aufgelistet sind, werden nicht in der Dashboard-Anzeige erscheinen, aber weiterhin in den Export-Daten enthalten sein.

**Verwendung:**
- Füge Gruppen im Format `gruppenname = Anzeigename` hinzu
- Kommentiere Zeilen mit `;` aus, um sie zu deaktivieren
- Die Filterung erfolgt nur auf Dashboard-Ebene, nicht beim Datenexport