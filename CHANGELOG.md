# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

## [Unreleased] - 2026-11-17 — Prüfbericht statt Dateigröße

### ✏️ Dashboard: „unvollständig (mindestens)" statt „mind." (2026-11-18)

Die Quantität einer Person mit unbekanntem Stand hieß bisher knapp
„mind. 45 %" — die Abkürzung erklärte nicht, *warum* der Wert eine
Untergrenze ist. Jetzt steht dort „unvollständig (mindestens) 45 %".
Rechnung, Marke „vorl." und Tooltip bleiben unverändert.

### 🐛 Export: Namensfilter aus Moodle wird zurückgesetzt (2026-11-18)

Die Buchstabenleiste („Vorname/Nachname: A B C …") speichert Moodle im
Konto. War dort z.B. auf der Bewertungsseite „B" gewählt, las der Export nur
diese Personen — alle übrigen fehlten in der Tabelle, galten im Abgleich als
unbekannt, und das Dashboard zeigte „mind." und „vorl.". Jetzt setzt jeder
Abruf einer Personentabelle den Filter leer (`tifirst`, `tilast`, `sifirst`,
`silast`; `pruefung.ohne_namensfilter`): zentral in `lade_alle_seiten` bzw.
`ladeAlleSeiten`, dazu Fortschrittsbericht und Singleview. Als
Sicherheitsnetz meldet `pruefe_namensfilter` eine Seite mit trotzdem
ausgewähltem Buchstaben als unvollständig („Namensfilter aktiv (B)"). Python
und Browser-Export gleich; abgesichert in `tests/test_pruefung.py`.

### 🐛 Dashboard: „bewertbar" öffnet die richtige Person

Der Link „bewertbar" führte in Moodles Korrekturansicht ohne `userid` —
Moodle zeigte dann die erste Person der Gruppe statt der, deren Zelle
angeklickt wurde. `bewertungsUrl()` hängt jetzt die Moodle-ID der Person an
(`…&action=grader&userid=…`); die ID steht bereits je Status im Export.
Die (ausgeblendeten) Leistungsnachweis-Tabellen nutzen dieselbe Funktion
statt eines eigenen Links auf die Aufgaben-Startseite. Abgesichert in
`tests/test_frontend.js` („Bewertungslink je Person").

### 🔗 Dashboard: Links öffnen grundsätzlich im neuen Tab

`dashboard.html` setzt `<base target="_blank">`. Die vorhandenen Links
(Aufgaben, „bewertbar", Checklisten, „Bewertung überschreiben") hatten das
schon einzeln; neu gilt es zentral auch für jeden künftigen Link ohne eigenes
`target`. Der CSV-Download setzt ausdrücklich `target="_self"`, damit kein
leerer Tab aufgeht.

### 🛡️ Export: unbekannt statt still „nicht abgegeben"

Fiel eine Bewertungsseite aus (Zeitüberschreitung, fehlende Spalte, Fehler im
Thread), lieferte der Export eine leere Liste — die ganze Klasse stand bei
dieser Aufgabe als „nicht abgegeben" da. Die Validierung schlug dabei nie an,
weil das Status-Wörterbuch den Schlüssel trotzdem enthielt. Jetzt wird die
Seite bis zu dreimal versucht; bleibt sie unlesbar, ist der Status
**unbekannt** (`"unbekannt": true`, `"grund": …`).

Dasselbe gilt für Personen, die laut Gruppe zur Klasse gehören, aber in einer
sonst vollständig gelesenen Bewertungstabelle oder in der Bewerterübersicht
fehlen, und für Pflicht-Tests ohne Spalte in der Bewerterübersicht.

### 🛡️ Export: aufgeteilte Seiten werden nachgeladen

Bewerterübersicht, Bewertungsseite, Testbericht und Fortschrittsbericht
(Gruppenmitglieder) teilen ihre Tabellen je nach den im Moodle-Konto
gespeicherten Einstellungen auf. Der Export las bisher nur die erste Seite;
Personen jenseits davon fehlten in jedem Lauf gleich — auch für den
Größenvergleich unsichtbar. Neu: `lade_alle_seiten()` folgt der Seitenleiste
(`page=`/`start=`), übernimmt aber nur die Nummer, nie den Link, damit kein
Filter (Buchstabenleiste) in der Sitzung hängen bleibt.

### 🛡️ Export: Prüfbericht ersetzt den Größenvergleich

Der Vergleich der Dateigröße mit dem Vorlauf (und das automatische Verwerfen
einer >1 % kleineren Datei) entfällt. An seine Stelle tritt ein Vergleich der
Zählwerte je Aufgabe und Klasse (abgegeben, bewertet) — ein Rückgang ist eine
Warnung mit Ort („Quiz HTML, IFA12A: abgegeben 23 → 0"), kein Abbruch. Lücken,
Rückgänge, fehlende Kurse und Hinweise stehen im Export unter `pruefbericht`,
am Ende des Logs und im Dashboard über der Tabelle.

### 🐛 Export: Abgaben späterer Kurse gingen verloren

`main()` übernahm die Gruppen samt Personendaten nur vom ersten Kurs; die
Abgaben aller weiteren Kurse wurden verworfen. Solange das 2. Halbjahr gesperrt
war, fiel das nicht auf — ab dessen Freischaltung hätte dort jede Person 0 %
gehabt. `fuehre_gruppen_zusammen()` legt die Aktivitäten je Person über alle
Kurse zusammen.

### 📊 Dashboard, CSV, Bericht: vorläufige Noten

- Übersicht: Quantität als Untergrenze („mind. 45 %"), Note und
  Mitarbeitsnote mit der Marke **vorl.**, Tooltip nennt die betroffenen
  Aufgaben. Im Klassenvergleich trägt die Klasse die Marke, sobald eine
  Person betroffen ist.
- Aufgabentabellen: **?** statt ❌, Grund im Tooltip.
- CSV: neue Spalte „Vorläufig", Aufgabenzellen „unbekannt".
- Schülerbericht (PDF): „Stand unbekannt" statt „nicht abgegeben"; der
  Datumsfilter blendet unbekannte Einträge nicht aus.

### ⚠️ Exportformat: Schema 3

`EXPORT_SCHEMA_VERSION` 2 → 3 in Exporter, Backend und Bericht. Schema-2-Exporte
werden abgelehnt — sie hätten jede Lücke als „nicht abgegeben" geführt.
**Nach dem Update einen neuen Export erzeugen.**

### 🧭 ByCS: Machbarkeitstest als ZIP

Neu unter `bycs/probe/`: eine Seite, die — als Aktivität „Datei" in ByCS
hochgeladen — dieselben Moodle-Seiten abruft wie der Export und meldet, ob sie
lesbar sind, ob die Tabellen da sind und ob Moodle sie aufteilt. Nur
Zählwerte, keine Namen. Gebaut mit `python scripts/build_bycs_zip.py` nach
`data/bycs/` (neu in `.gitignore`). Vorstufe für einen Export direkt im
Browser ohne Python und Selenium.

### 🧭 ByCS: Machbarkeitstest bestanden — Lücke bestätigt

Der Test in ByCS (Kurs 2491549) zeigt: Alle Seiten sind aus einer
hochgeladenen Seite lesbar. Er bestätigt zugleich die Lücke im bisherigen
Export: Der Fortschrittsbericht teilt mit `page=` nach 25 Personen auf. Im
Export vom 17.11.2026 hatten alle vier Klassen **genau 25** Personen (Summe
104), die Bewerterübersicht kennt 115 — rund 11 Schüler:innen fehlten im
Dashboard ganz. Der neue Export lädt die Folgeseiten nach.

### 🚀 Export im Browser (`bycs/export/`)

Erzeugt dieselbe Exportdatei (Schema 3) wie `scripts/export_data.py`, in der
Moodle-Sitzung der angemeldeten Lehrkraft: Eins-zu-eins-Übertragung von
`export_course`/`main` samt Prüfschichten nach JavaScript (`fetch` +
`DOMParser`, 4 parallele Abrufe, 3 Versuche je Seite). Die Datei wird
heruntergeladen und im bestehenden Dashboard über „Datei laden" geöffnet.
ZIP: `python scripts/build_bycs_zip.py export` (enthält eine Kopie der
`plan.json`). Für den Parallelbetrieb vergleicht
`tests/vergleiche_exporte.py` zwei Exporte Feld für Feld.

### 🐛 Bewerterübersicht im Bearbeitungsmodus

Der erste Parallelvergleich (Python 12:48 gegen Browser 21:20) fand 2912
abweichende Testbewertungen — alle mit derselben Ursache: Ist in Moodle der
Bearbeitungsmodus an, trägt jede Zelle der Bewerterübersicht ein Eingabefeld
und eine versteckte Beschriftung „Name, Aktivität, Bewertung". Leere
Testzellen wurden so als bewertet gelesen. Beide Exporter entfernen jetzt
versteckte Hilfstexte, lesen Eingabefelder über ihren Wert und werten eine
leere Zelle als „-"; der Browser-Export vermerkt den Bearbeitungsmodus im
Prüfbericht. Abgesehen davon waren die beiden Exporte Feld für Feld gleich
(übrige Abweichungen: echte neue Abgaben zwischen den Läufen).
`tests/vergleiche_exporte.py` maskiert jetzt lange Texte, damit kein Name in
der Ausgabe landet.

### 🚀 Dashboard in ByCS (`bycs/dashboard/`)

Das komplette Dashboard läuft als ZIP in ByCS: Beim Öffnen liest es Moodle in
der Sitzung der Lehrkraft und zeigt das Ergebnis sofort an.
`aufbereitung.js` überträgt `_process_dashboard_data` samt Hilfsfunktionen
eins zu eins nach JavaScript — einschließlich Pythons `round()` (Gleichstand
zur geraden Ziffer auf dem exakten Binärwert) und `sum()` (Neumaier-Summation
seit Python 3.12; ohne sie kippte ein Klassenschnitt von 66,59 auf 66,58).
`tests/vergleiche_aufbereitung.py` vergleicht Python und JS; am echten Export
vom 17.11.2026 und an den Testdaten identisch. `dashboard.js` bleibt
unverändert und wird beim Bauen aus `src/dashboard/static/` übernommen; der
Startcode `start.js` ersetzt nur die drei Serveraufrufe.

### 🗑️ Exam-Teil entfernt

Quiz-Versuche scrapen und individuelle Korrektur-PDFs erzeugen ist in einem
anderen Projekt umgesetzt. Entfernt: `src/exam/` (Scraper, PDF-Generator,
Hilfsfunktionen, README), `scripts/scrape_exams.py`, `scripts/generate_pdfs.py`
samt `.bat`, dazu `config_manager.get_course_id()` (nur noch dort genutzt)
und die tote Pfadangabe `quiz_data` im Berichtsgenerator. Der
Schüler-Übersichtsbericht (`generate_reports.py`) hing nicht am Exam-Teil.
Lokale Daten in `data/quiz_data/` und `data/LNW/` bleiben unberührt und
weiterhin gitignored.

### ⚡ Export: ein Abruf je Aufgabe weniger, Browser-Export paralleler

- **Gruppenabfrage entfällt** (Python `get_assignment_groups`, JS
  `aufgabenGruppen`). Für jede Aufgabe wurde zusätzlich die Aufgabenseite
  geöffnet, um das Gruppen-Auswahlfeld zu lesen. Ergebnis in allen Exporten
  vom 17.11.2026: 29 × „all"; gelesen hat das Feld außer dem Abgleich
  niemand. Das Auswahlfeld zeigt zudem die gerade gewählte Gruppe der
  Lehrkraft, keine Einschränkung der Aufgabe, und die Bewertungsseite wird
  ohnehin mit `group=0` gelesen. Das Feld `groups` bleibt im Export („all"),
  das Format ändert sich nicht. Spart rund 29 von ~157 Seitenabrufen je Kurs;
  im Python-Export (Selenium rendert jede Seite) am deutlichsten.
- **Browser-Export: 6 statt 4 gleichzeitige Abrufe.** Der Python-Export
  bleibt bei 2 Chrome-Instanzen — jede weitere ist ein eigener Browser mit
  eigener Anmeldung.

### 🔄 ByCS-Dashboard: einzelne Pflichtaufgabe nachladen

Im Reiter *Pflichtaufgaben* steht über jeder Aufgabe ein ⟳-Knopf. Er liest
nur diese Aufgabe neu aus Moodle, trägt sie in den Export ein und rechnet das
Dashboard neu — Klasse, Halbjahr und Reiter bleiben. Dafür ist
`exportiereKurs` in `bycs/export/exporter.js` in Bausteine zerlegt
(`liesAufgabe`, `liesTestzeiten`, `liesBewerteruebersichtKomplett`,
`setzeStatus`); Gesamtexport und `aktualisiereAktivitaet` nutzen dieselben,
der Gesamtexport liefert unverändert dasselbe Ergebnis. `dashboard.js` zeigt
den Knopf nur, wenn `window.pflichtSync` existiert — also nur in ByCS.
Funktioniert auch nach „Datei laden".

### 🙈 Dashboard: Tab „Leistungsnachweise" ausgeblendet

Der Tab erkennt Leistungsnachweise am Namen der Notenbuch-Kategorie
(„Leistungsnachweise" oder „📊"). Der Kurs 2026/27 hat keine solche Kategorie,
der Tab war leer. Der Schalter `SHOW_LEISTUNGSNACHWEISE` oben in
`dashboard.js` steht auf `false`; mit `true` ist der Tab wieder da.
`showTab('exam')` leitet auf die Übersicht um. Code, CSV-Spalten und
PDF-Bericht bleiben unverändert.

### 📐 Dashboard nutzt den ganzen Bildschirm

- Die Seite war auf 1280 px Breite begrenzt (`--max-width`); jetzt keine
  Obergrenze mehr — breite Klassentabellen nutzen große Bildschirme aus.
- Tabellenkästen scrollten ab 70 % der Fensterhöhe; jetzt erst ab
  `100vh − 120px`. Der Kasten bleibt, damit der Tabellenkopf beim Scrollen
  stehen bleibt.
- ByCS: Zeigt Moodle das Dashboard eingebettet oder im Pop-up, erscheint
  oben „Im ganzen Fenster öffnen". Empfohlene Darstellung der Aktivität:
  „Öffnen" oder „Im neuen Fenster".

### 🐛 Dashboard: „Stand" der Datei wurde nie angezeigt

`applyDashboardData` las `last_updated` und `environment` aus den Kursdaten
statt aus der Gesamtantwort — seit der Umstellung auf mehrere Kurse blieb die
Anzeige „Stand" in der Navigation leer. Behoben in `dashboard.js`, gilt lokal
wie in ByCS.

### 🧪 Tests

- `tests/test_pruefung.py`: Seitenleisten, Nachladen (mit Browser- und
  Sitzungsattrappen), Abgleich in `export_course` an einem simulierten Kurs,
  Verlaufsvergleich, Zusammenführen der Kurse.
- `tests/test_report_unbekannt.py`: Schülerbericht.
- Testdaten um „Dora" mit unbekannter 10-Stunden-Aufgabe ergänzt; Frontend-
  und API-Stufe prüfen Untergrenze, Marke und Prüfbericht.

## [Unreleased] - 2026-11-17 — Tabellen in einem Rutsch lesen

### 🙈 Dashboard: „Letzte Abgaben je Gruppe" ausgeblendet

Die Sektion auf der Übersicht erscheint nicht mehr. Der Schalter
`SHOW_RECENT_SUBMISSIONS` oben in `dashboard.js` steht auf `false`; mit
`true` ist sie wieder da. Rendering-Code, Sortierung, Pflicht-Filter und
die Backend-Aggregation (`build_recent_submissions`) bleiben unverändert.

### ⚡ Export: Batch-Auslesung statt zeilenweisem Selenium

Ein Lauf über einen Kurs (29 Assignments, 28 Quizze, 104 Personen) dauerte
12,7 min, davon 6,9 min Assignments und 4,0 min Quizze. Ursache war nicht
das Laden der Seiten, sondern das Auslesen: jede Tabellenzelle kostete
eigene WebDriver-Roundtrips (`find_element`, `.text`, `get_attribute`) —
rund 10 je Schüler auf der Bewertungsseite, weitere ~5 je Schüler auf der
Singleview, die für jedes Assignment *und* jedes Quiz geladen wird.

Vier Funktionen lesen ihre Tabelle jetzt mit einem einzigen
`execute_script`, nach dem Muster, das `get_grader_report_data()` schon
nutzte:

- `get_assignment_status()` — Bewertungsseite
- `get_quiz_submission_times()` — Quiz-Report
- `get_singleview_feedback_dates()` — Singleview-Feedback
- `get_all_activity_categories()` — Kategorienbaum

Die Elementauswahl ist 1:1 übernommen, Defaults und Datums-Parsing bleiben
in Python. Der Helfer `_JS_TEXT` liest Text wie Seleniums `.text`
(gerendert, geschützte Leerzeichen normalisiert, getrimmt). Gegen
Test-Seiten mit Sonderfällen (Mehrfachversuche, fehlende Zellen, versteckte
Dropdowns, Feedback als textarea/input/HTML) liefern alte und neue Variante
identische Ergebnisse; das Auslesen einer Seite mit ~120 Zeilen sinkt
dabei von 5–9 s auf unter 0,1 s.

Außerdem wartet der Quiz-Report nicht mehr auf `#attempts`: Bei Quizzen
ohne Versuche gibt es die Tabelle nicht, und jedes solche Quiz kostete die
volle `MODE_WAITTIME`.

Gemessen am selben Kurs:

| Phase | vorher | nachher |
|---|---|---|
| Assignments | 6,9 min | 1,7 min |
| Quiz Submission Times | 4,0 min | 43 s |
| Kategorien laden | 7,7 s | 1,1 s |
| **Gesamt** (ohne Login) | 11,4 min | 2,8 min |

Der Export ist inhaltlich identisch zum vorherigen (reihenfolgeunabhängiger
Vergleich beider JSON-Dateien: 0 Abweichungen).

## [Unreleased] - 2026-11-17 — Feedbacktext ist kein Datumsfehler

### 🔧 Export: Singleview-Feedback flutet das Log nicht mehr

Das Feedback-Feld der Singleview dient als Override für das Abgabedatum
(siehe 2026-03-16). Steht dort echtes Feedback — meist als HTML aus dem
Editor —, schrieb der Export für jeden Schüler eine Warnung
„Kein Datumsformat erkannt“ samt komplettem HTML-Block ins Log.

- Neue Funktion **`feedback_als_datum()`** in `exporter.py`: entfernt
  HTML-Tags und wertet das Feld nur dann als Datum, wenn es **ausschließlich**
  ein Datum enthält (`09.01.2026`, `09.01.2026 14:30`,
  `24. September 2025 08:12`, `Dienstag, 23. September 2025, 07:46`).
  Feedbacktext wird stillschweigend übersprungen; ein Datum mitten im Text
  („Abgabe bis 09.01.2026 …“) zählt bewusst nicht.
- Ein vom Editor eingepacktes Datum (`<p>09.01.2026</p>`) wird jetzt
  ebenfalls erkannt.
- Die Singleview-Zusammenfassung nennt die Zahl übersprungener
  Feedback-Texte.
- Warnungen aus `parse_german_datetime()` kürzen den Wert auf 80 Zeichen.

## [Unreleased] - 2026-09-22 — Planstunden im Titel, Sprung in die Bewertung

### 🚀 Stundenraster: Soll wächst tagesgenau statt sprunghaft

Bisher zählte eine Blockwoche komplett, sobald sie begonnen hatte. Am
Montagmorgen schuldete ein Schüler damit bereits alle 14 Stunden der
Woche — bei IFA12D rund **9 Unterrichtsstunden künstliches Minus** genau
in der Woche, in der man mit der Klasse über den Stand spricht. Nach dem
Block stimmte es wieder; der Fehler traf also immer den Moment des
Hinsehens.

Neu verteilt ein **Stundenraster** die Wochenstunden auf Mo–Fr. Während
einer laufenden Blockwoche zählt nur der bereits gehaltene Anteil:

```
IFA12D, Blockwoche 2 (122 Std gesamt, Raster 2/3/2/5/2)
  Mo  vorher 19,7 %  →  jetzt  9,8 %
  Di  vorher 19,7 %  →  jetzt 12,3 %
  Do  vorher 19,7 %  →  jetzt 18,0 %
  Fr  vorher 19,7 %  →  jetzt 19,7 %
```

- **`plan.json` bekommt zwei neue Blöcke** (`stundenraster`,
  `klassenZuRaster`) und steigt auf **`schemaVersion` 4**. Mehrere Klassen
  können sich ein Raster teilen — IFA12A/B und IFA12C/D haben je eines,
  über beide Schienen hinweg.
- **Das Raster gibt nur die Form der Verteilung, die Wochensumme aus der
  Schiene die Höhe.** Gerechnet wird anteilig, damit die verkürzte erste
  Blockwoche (10 statt 14 Stunden) nicht mehr ausweist als sie hat. Tage
  außerhalb `start`–`ende` zählen nicht — so fällt der fehlende Montag der
  Schiene 3 in Woche 1 von selbst heraus.
- **Optional und abwärtskompatibel:** ohne Rastereintrag zählt die
  angebrochene Woche wie bisher ganz. Alle Wochen sind dann rechnerisch
  bitgleich zum alten Verhalten.
- `soll_anteil()` in [plan_loader.py](src/common/plan_loader.py) nimmt
  Raster und Stichtag als optionale Parameter; Gegenstücke in
  [dashboard.js](src/dashboard/static/dashboard.js) und in `js/bilanz.js`
  des Schüler-Dashboards wurden mitgezogen. Neu:
  `Plan.get_raster_for_class()`, das den Gruppennamen in jeder Form
  entgegennimmt wie `get_track_for_class()`.

### 🚀 Wochentag-Auswahl neben dem Wochen-Slider

Damit der Stichtag nicht geraten werden muss, steht neben dem
Schulwochen-Slider eine Radiogruppe **Mo Di Mi Do Fr**. Vorausgewählt ist
der aktuelle Wochentag, sofern heute in der gezeigten Blockwoche liegt —
sonst Freitag, womit die Woche komplett zählt.

- **Beim Wochenwechsel bleibt der Tag stehen**; nur die Ausgrauung richtet
  sich nach der neuen Woche.
- **Tage außerhalb der Blockwoche sind deaktiviert** statt stumm falsch zu
  rechnen. In Woche 1 der Schiene 3 (Di-Start) ist „Mo" ausgegraut; fällt
  der gewählte Tag weg, rückt die Auswahl auf den letzten verfügbaren.
- „Aktuelle Woche" setzt Woche **und** Tag auf heute zurück.
- Der Stichtag wird aus Woche und Tag abgeleitet (`getStichtagForWeek()`),
  nicht mehr aus `new Date()`. Vorher ließ sich nicht unterscheiden, ob
  der Slider bewusst verstellt oder nur vorbelegt war.



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

### 🚀 Stand der geladenen Datei neben „Datei laden"

Wie aktuell die angezeigten Zahlen sind, war bisher nicht abzulesen: die
Datei-Info saß am linken Rand der Toolbar, weit weg von den Knöpfen, und
war ungestylt. Sie steht jetzt **direkt links neben „Datei laden"**, wo
die Frage aufkommt.

- Anzeige als `Stand 22.09.2026, 07:30` — die Sekunden aus dem
  Dateinamen entfallen, in einer Toolbar zählen Tag und Uhrzeit. Der
  vollständige Dateiname steht im Tooltip.
- Der Hinweis auf veraltete Daten (ab zwei Tagen) sitzt in derselben
  Zeile und ist vom gelben Signalkasten auf Text in `--warning-color`
  umgestellt — das Layout ist flach, ohne Farbflächen.
- Ein- und Ausblenden läuft über das `hidden`-Attribut statt über
  `style.display`, sodass die Darstellung ganz in der CSS bleibt.
  Die Regeln für `.file-info-*` standen doppelt in
  [style.css](src/dashboard/static/css/style.css) und
  [dashboard-custom.css](src/dashboard/static/css/dashboard-custom.css);
  maßgeblich ist jetzt nur noch die zuletzt geladene
  `dashboard-custom.css`.

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
