# Refactoring-Plan: Lehrkräfte-Dashboard auf Kursstruktur 2026/27

Stand: 2026-09-18 · Betrifft: `mebis_statistics` (Lehrkräfte-Dashboard)
Referenz-Stammdaten: `AEuP12/BYCS_Lernplattform_Dashboard/plan.json` (schemaVersion 3)

> **Grüne Wiese.** Neues Schuljahr, neue Schüler, neuer Kurs. Es wird **nichts migriert**:
> keine Rückwärtskompatibilität des Exportformats, keine Altdaten im `EXPORT_FOLDER`,
> keine `.env`-Fallbacks. Das neue Format wird einfach gesetzt, die alten Exporte
> bleiben liegen, wo sie sind.

---

## 1. Ausgangslage

Das Lehrkräfte-Dashboard ist an drei Stellen fest auf die alte Kursstruktur verdrahtet:

| Annahme im Code | Neue Realität |
|---|---|
| **Ein** Moodle-Kurs (`MEBIS_COURSE_ID=2491549`) | **Zwei** Kurse: 2491549 (1. HJ), 2491870 (2. HJ) |
| Mitarbeitsnote **1 und 2**, wobei "2. HJ" = Prognose der 2. MA-Note | Nur **eine** Mitarbeitsnote; Halbjahre sind ein **Zeitraum-Konzept**, keine Notenstufe |
| Gruppen = `IFA12A - Team 3` (Klasse + Team) | Gruppen = nur noch Klasse (`IFA12A`), keine Teams |
| Konfiguration verteilt über ~10 `.env`-Variablen | `plan.json` als zentrale Stammdatenquelle |

### Der zentrale Denkfehler, der aufzulösen ist

Im aktuellen Code bedeutet "1. Halbjahr" / "2. Halbjahr" **nicht** einen Zeitraum,
sondern *"1. Mitarbeitsnote"* bzw. *"Prognose der 2. Mitarbeitsnote"*. Die Trennung
läuft über die **Referenzwoche** (`MITARBEITSNOTE1_REFERENCE_WEEK=4`) innerhalb
*eines* Kurses — siehe `calculateQuantitaetMA2()` in
[dashboard.js:1397](src/dashboard/static/dashboard.js#L1397), wo `soll1HJ` und `soll2HJ`
aus derselben Aufgabenliste per Wochenanteil aufgeteilt werden.

Künftig ist die Trennung **physisch**: zwei Moodle-Kurse mit je eigener Aufgabenliste.
Die gesamte Wochenanteil-Arithmetik (`soll1HJ`/`soll2HJ`/`angerechnet`/`uebertrag`)
entfällt ersatzlos. Das ist die größte Vereinfachung des Refactorings — und der Grund,
warum das keine reine Umbenennung sein kann.

---

## 2. Zielarchitektur

```
plan.json (Stammdaten, geteilt mit Schüler-Dashboard)
    │
    ├─ kurse[] → moodleCourseId, titel, anzeigen, gesperrt, aufgaben[]
    ├─ schienen{} → schulwochen[] (Woche, start, ende, stunden)
    ├─ klassenZuSchiene{} → IFA12A → Schiene1
    ├─ notenschluessel[] → Prozent → IHK-Note
    └─ skalen{} → sterne4 → Prozent
    │
    ▼
Exporter (scrape je Kurs) → output_<ts>.json { kurse: { "2491549": {...}, "2491870": {...} } }
    │
    ▼
Backend (Flask) → /api/data liefert Plan + Kursdaten
    │
    ▼
Frontend → Halbjahr-Umschalter wählt Kurs(e), nicht Notenstufe
```

**Leitentscheidung:** `plan.json` wird zur einzigen Quelle für Kurse, Aufgaben,
Schulwochen und Notenschlüssel. Die `.env` behält nur Betriebs-Konfiguration
(Zugangsdaten, Pfade, Flask, Selenium). Damit teilen sich beide Dashboards die
Stammdaten und driften nicht auseinander.

---

## 3. Arbeitspakete

### AP 1 — Stammdaten: `plan.json` als Quelle einbinden

**Neu:** `src/common/plan_loader.py`

Lädt und validiert `plan.json` analog zu `js/plan.js` des Schüler-Dashboards
(schemaVersion-Prüfung, Pflichtfelder, sprechende Fehler). Stellt bereit:

- `get_courses()` → `[{id, moodleCourseId, titel, anzeigen, gesperrt, aufgaben}]`
- `get_track_for_class(klasse)` → `"Schiene1"`
- `get_schulwochen(track)` → Wochenkalender
- `percent_to_grade(pct)` → IHK-Note über `notenschluessel`
- `get_aufgabe(cmid)` → Aufgabe inkl. `stunden`, `skala`, `lektion`

**Pfad-Konfiguration:** neue `.env`-Variable `PLAN_JSON_PATH`, default auf den
Pfad im Schüler-Dashboard-Repo. Eine lokale Kopie ist bewusst *nicht* vorgesehen —
zwei Wahrheiten wären genau das Problem, das wir beseitigen.

**Abzulösende `.env`-Variablen:**
`CLASS_TO_TRACK`, `TRACK_SCHEDULES`, `MAX_SCHOOLWEEKS`, `GRADE_MAPPING`,
`MEBIS_COURSE_ID` (→ aus `plan.json.kurse[]`).
Diese werden **ersatzlos entfernt**, nicht als Fallback belassen — ihre Werte gehören
ohnehin zum Vorjahr und wären beim Debuggen nur irreführend.

---

### AP 2 — Exporter: zwei Kurse scrapen

**Datei:** [src/export/exporter.py](src/export/exporter.py) (2097 Zeilen)

`course_id` wird derzeit durch ~12 Funktionen als Parameter gereicht
(`get_user_ids_from_group`, `get_grader_report_data`, `get_singleview_grades`,
`get_grade_history_time`, `get_singleview_feedback_dates`, `process_assignment_parallel`, …).
Die Signaturen bleiben also unverändert — sie sind bereits kurs-parametrisiert.

**Änderung nur in `main()`** ([exporter.py:1473](src/export/exporter.py#L1473)):
Schleife über `plan.kurse` (nur `anzeigen: true`, `gesperrt: false`),
pro Kurs der bestehende Ablauf, Ergebnisse unter der Kurs-ID sammeln.

**Neues Ausgabeformat** (`output_<ts>.json`):

```json
{
  "schema": 2,
  "exported_at": "2026-09-18T13:10:14",
  "kurse": {
    "2491549": { "titel": "1. Halbjahr",
                 "activities_by_category": [...], "manual_grade_items": {...} },
    "2491870": { "titel": "2. Halbjahr", "...": "..." }
  },
  "groups": [ { "name": "IFA12A", "value": "...", "users": [...] } ]
}
```

`groups` bleibt **kursübergreifend auf oberster Ebene** — dieselben Schüler in beiden
Kursen. Das vermeidet doppelte Personenlisten und Abgleichprobleme bei Umbenennungen.

**Keine Migration.** Das neue Format wird gesetzt, `load_json_data()` liest
ausschließlich `schema: 2`. Ein Export im Altformat soll mit klarer Fehlermeldung
abgelehnt werden statt stillschweigend falsch interpretiert zu werden. Die Altdateien
im `EXPORT_FOLDER` bleiben unberührt liegen.

> **Empfehlung:** neuer Export-Ordner für 2026/27 (`EXPORT_FOLDER` umstellen).
> `find_latest_file()` nimmt per `glob('output_*.json')` schlicht die neueste Datei —
> liegen alte und neue Exporte im selben Ordner, ist das nur bis zum ersten neuen
> Export unkritisch, aber die Trennung erspart Verwechslungen beim Testen.

#### Sperre des 2. Halbjahres

`plan.json` führt Kurs 2491870 als `gesperrt: true`, `anzeigen: false`,
`freischaltung: 2027-01-11`. Das ist keine Randnotiz, sondern bestimmt den
Zeitplan: **bis Januar 2027 ist nur Kurs 2491549 auswertbar.**

Daraus folgt für die Umsetzung:

- Der Exporter überspringt gesperrte Kurse (wie `ladeKursStatus()` im Schüler-Dashboard,
  [moodle.js:22](../AEuP12/BYCS_Lernplattform_Dashboard/js/moodle.js#L22)) — ein Abruf
  lieferte sonst eine Fehler- oder Anmeldeseite.
- Die Zwei-Kurs-Struktur wird **trotzdem jetzt** gebaut, nur eben vorerst mit einem
  befüllten Kurs. Das Frontend muss von Beginn an mit einem leeren zweiten Halbjahr
  umgehen können (Tab deaktiviert oder mit Hinweis „ab 11.01.2027").
- Die offenen Punkte zu Kurs 2491870 (Kategorienamen, Item-IDs, Review-Talks) lassen
  sich **erst nach Freischaltung** endgültig klären. Solange der Kurs für dich als
  Lehrkraft aber bereits sichtbar ist, genügt ein Blick in die Kursstruktur —
  siehe Abschnitt 5.

#### Pflichtaufgaben-Erkennung: `plan.json` statt Kategoriename — **entschieden**

Die Kategorie heißt weiterhin `Pflichtaufgaben`; die bestehende Prüfung
`category_name.includes('Pflichtaufgaben')` ([dashboard.js:1410](src/dashboard/static/dashboard.js#L1410))
würde also weiter funktionieren. Sie wird dennoch ersetzt:

**Eine Aufgabe ist genau dann Pflichtaufgabe, wenn ihre `cmid` in `plan.json` steht.**

Das ist nicht nur robuster gegen Umbenennungen — es ist die Voraussetzung für die
stundenbasierte Rechnung (siehe AP 4). Denn nur über die `cmid` kommt man an das
`stunden`-Feld der Aufgabe. Der Kategoriename kennt keine Stunden. Beide Entscheidungen
hängen also zusammen: ohne `cmid`-Zuordnung keine Gewichtung.

Damit gilt zugleich: **Der Plan bestimmt den Nenner, nicht Moodle.** Eine Aufgabe, die
in Moodle existiert, aber nicht im Plan steht, zählt nicht für den Fortschritt. Eine
Aufgabe, die im Plan steht, aber in Moodle (noch) fehlt, bleibt im Nenner und gilt als
nicht begonnen — genau wie im Schüler-Dashboard
([status.js:60](../AEuP12/BYCS_Lernplattform_Dashboard/js/status.js#L60)).
Das macht Soll-Werte stabil, statt sie bei jeder Kursänderung springen zu lassen.

---

### AP 3 — Team-Ebene entfernen

**Betroffen:** [group_utils.py](src/common/group_utils.py),
[dashboard.js:2057-2130](src/dashboard/static/dashboard.js#L2057),
[dashboard.html:37-58](src/dashboard/static/dashboard.html#L37),
[report_generator.py:262,597,877](src/report/report_generator.py#L262)

Das Frontend kennt zwei Navigationsebenen: `currentGrouping` (Klasse, abgeleitet aus
`name.split(' ')[0]`) und `currentGroup` (Team). Mit dem Wegfall der Teams sind beide
identisch.

**Vorgehen:** `currentGrouping` entfällt, `currentGroup` bleibt und hält künftig die
Klasse. Im HTML entfällt der Block `groupingTabs` (Zeilen 37–39); `groupTabs` bleibt.

`extract_group_prefix()` bleibt **unverändert erhalten**: Die Funktion gibt bei
Namen ohne `" - "` den Namen unverändert zurück, funktioniert also für `IFA12A`
bereits korrekt. Sie weiter zu nutzen macht das System robust, falls einzelne
Moodle-Gruppen doch noch alte Namen tragen. Gleiches gilt für das Prefix-Matching in
`getTrackForGroup()` ([dashboard.js:1186](src/dashboard/static/dashboard.js#L1186)).

> **Rückfrage:** Heißen die Moodle-Gruppen in den neuen Kursen exakt `IFA12A`,
> oder gibt es weiterhin einen Zusatz? Davon hängt ab, ob `klassenZuSchiene` aus
> `plan.json` direkt greift.
>
> **Geklärt:** Die Klassen sind IFA12A–D. IFA12E gibt es nicht mehr; `plan.json`
> ist damit vollständig.

---

### AP 4 — Mitarbeitsnote: von zwei auf eine

Das inhaltlich anspruchsvollste Paket.

**Zu entfernen** aus [dashboard.js](src/dashboard/static/dashboard.js):
- `calculateQuantitaetMA2()` (Z. 1397–1455) — die gesamte `soll1HJ`/`soll2HJ`-Arithmetik
- `calculateMitarbeitsnote2Prognose()` (Z. 1486–1570)
- Abschnitt 2 in `generateHalbjahresnotenTable()` (Z. 1675–1720), `ma2Table`
- `hj2*`-Cards in [dashboard.html:241-252](src/dashboard/static/dashboard.html#L241)
- MA2-Spalten in [csv_export.js:697,940-946](src/dashboard/static/csv_export.js#L697)

**Zu behalten und umzubenennen:**
`calculateMitarbeitsnote1()` → `calculateMitarbeitsnote()`. Die Funktion ist bereits
korrekt: Quantität und Qualität aus dem Notenbuch, Review-Talk als dritte Komponente,
tatsächliche Note hat Vorrang vor der Berechnung.

#### Quantität: stundengewichtet statt Aufgaben gezählt — **entschieden**

Das ist die folgenreichste der drei Entscheidungen. Bisher zählt der Code **Aufgaben**
(`totalPflicht++` je Aktivität), künftig summiert er **Stunden** aus `plan.json`.

Der Unterschied ist erheblich: Im 1. Halbjahr stehen 14 Aufgaben für 58,5 Stunden, die
zwischen 2,0 und 10,0 Stunden schwanken. Die „Situation Mitarbeiterverwaltung" (10 h)
wiegt damit fünfmal so viel wie ein Quiz (2 h) — beim reinen Zählen wären beide gleich.

**Formel** (übernommen aus dem Schüler-Dashboard,
[bilanz.js:96](../AEuP12/BYCS_Lernplattform_Dashboard/js/bilanz.js#L96)):

```
Ist   = Σ Stunden abgegebener Aufgaben / Σ Stunden aller Aufgaben
Soll  = Σ Stunden der Schulwochen 1..w / Σ Stunden aller Schulwochen
Delta = (Ist − Soll) × Σ Stunden gesamt     → in Unterrichtsstunden
```

Zwei Punkte, die sich aus dem Schüler-Dashboard ergeben und die ich übernehmen würde:

**1. Das Soll hängt am Wochenkalender, nicht an der Wochennummer.** `sollAnteil()`
summiert die `stunden` der Schulwochen bis Woche *w* — nicht `w / 9`. Woche 1 hat
10 Stunden, alle übrigen 14. Die lineare Näherung des jetzigen Codes
(`totalPflicht × selectedWeek / maxSchoolweeks`) ist damit schon innerhalb eines
Halbjahres leicht falsch.

**2. Bezugsgröße ist das ganze Schuljahr, auch wenn nur ein Halbjahr sichtbar ist.**
Der gesperrte Kurs bleibt im Nenner
([bilanz.js:5](../AEuP12/BYCS_Lernplattform_Dashboard/js/bilanz.js#L5): *„damit der
Nenner beim Freischalten konstant bleibt"*). Sonst springt der Fortschritt aller
Schüler am 11.01.2027 schlagartig nach unten. Für die Halbjahres-Tabs heißt das:
Die Einzelansicht eines Halbjahres begrenzt den Kalender per `begrenzeSchulwochen()`,
die Jahresbilanz nicht.

**Konsequenz für „Gesamt":** Die Frage „gleichgewichtet oder nach Stunden" stellt sich
damit nicht mehr separat — die Gewichtung 58,5 zu 35,25 fällt automatisch aus der
Summenbildung. Offener Punkt 10 ist erledigt.

**Empfehlung:** `verteileUnterrichtsstunden()`, `sollAnteil()` und `aktuelleWoche()`
nicht neu erfinden, sondern **1:1 nach Python portieren** — inklusive der Behandlung
von Blockwochen (zwischen zwei Blöcken gilt der Stand des letzten abgeschlossenen).
Diese Logik ist im Schüler-Dashboard erprobt, und zwei divergierende Implementierungen
derselben Formel wären genau die Art von Fehlerquelle, die später niemand findet.
Ein gemeinsamer Satz Testfälle für beide Seiten wäre das Ideal.

**Qualität** bleibt der **ungewichtete** Durchschnitt der Bewertungen
([bilanz.js:berechneQualitaet](../AEuP12/BYCS_Lernplattform_Dashboard/js/bilanz.js#L163)) —
eine gut gemachte kleine Aufgabe ist so viel wert wie eine gut gemachte große. Nur die
Quantität ist stundengewichtet. Das sollte in der UI benannt werden, sonst wirkt es
wie eine Inkonsistenz.

Kein Übertrag zwischen den Halbjahren mehr.

**Konfigurationsanpassung:**

```diff
- MITARBEITSNOTE1_REFERENCE_WEEK=4
- REFERENZTERMIN_MITARBEITSNOTE1={"Schiene1": "...", "Schiene3": "..."}
- PROGNOSIS_ASSIGNMENTS={"reviewTalk1":..., "reviewTalk2":..., "reviewTalk3":..., "codeReview":...}
+ PROGNOSIS_ASSIGNMENTS={"2491549": {"reviewTalk": ..., "codeReview": ...},
+                        "2491870": {"reviewTalk": ..., "codeReview": ...}}

  MANUAL_GRADE_ITEM_IDS=…   # pro Kurs neu zu ermitteln, Item-IDs sind kursspezifisch!
```

> **Rückfrage:** Die `MANUAL_GRADE_ITEM_IDS` (Quantität, Qualität, Mitarbeitsnote,
> Sonstiges, Eingereichte Aufgaben) sind Moodle-Bewertungselemente und damit **je Kurs
> verschieden**. Existieren diese manuellen Elemente in beiden neuen Kursen bereits?
> Wenn ja, brauche ich die IDs aus beiden. Ohne sie fällt die Mitarbeitsnote auf
> berechnete Werte zurück statt die eingetragenen zu zeigen.
>
> Ebenso: **"Eingereichte Aufgaben"** existierte nur, um den Übertrag vom 1. ins
> 2. Halbjahr zu berechnen. Bei getrennten Kursen wird es nicht mehr benötigt —
> bestätigen, dass es entfallen darf.

---

### AP 5 — Frontend: Halbjahr-Umschalter umdeuten

**Datei:** [dashboard.js:13](src/dashboard/static/dashboard.js#L13), `selectHalbjahr()`

Die drei Tabs bleiben sichtbar, ändern aber ihre Bedeutung:

| Tab | bisher | künftig |
|---|---|---|
| 1. Halbjahr | 1. Mitarbeitsnote | Kurs 2491549 |
| Gesamt | beide Notenstufen | beide Kurse aggregiert |
| 2. Halbjahr | Prognose 2. MA-Note | Kurs 2491870 |

`currentHalbjahr` wird zum **Kursfilter**. Alle Auswertungsfunktionen
(`calculatePflichtaufgabenProgressGesamt`, `generateOverviewTable`,
`createStructuredTables`, …) erhalten den aktiven Kurs-Scope als Parameter.

Der Default sollte `'1hj'` sein statt heute `'2hj'` — zu Schuljahresbeginn ist
das 1. Halbjahr der relevante Zeitraum. Alternativ automatisch nach heutigem Datum
gegen den Wochenkalender bestimmt; das wäre robuster und vermeidet ein weiteres
jährliches Nachziehen von Hand.

**Wochen-Slider:** `maxSchoolweeks` (bisher global 9) wird kursabhängig. Aus
`plan.json` ergibt sich der Kalender je Schiene; der Slider zeigt künftig die Wochen
des aktiven Halbjahres.

---

### AP 6 — Backend, Reports, Exams

**[backend.py](src/dashboard/backend.py)** — `_process_dashboard_data()` (Z. 479) verarbeitet
heute eine flache Struktur. Künftig Schleife über Kurse; `structured_tables` und
`recent_submissions` werden je Kurs erzeugt. `/api/data` liefert zusätzlich den
Plan-Auszug (Kurse, Wochen, Notenschlüssel), sodass das Frontend keine zweite
Quelle braucht.

**[report_generator.py](src/report/report_generator.py)** — `_get_pflichtaufgaben_items()`
und `_get_klassen_from_export()` auf das neue Format heben. Die Berichte sollten das
Halbjahr im Titel führen; ob je Halbjahr getrennte PDFs oder ein kombiniertes Dokument
gewünscht ist, ist offen.

**[src/exam/scraper.py:253](src/exam/scraper.py#L253)** — nutzt `config_manager.get_course_id()`
direkt. Auf Kursliste umstellen; Leistungsnachweise liegen vermutlich in beiden Kursen.

**[tests/test_grade_calculator.py](tests/test_grade_calculator.py)** — prüft die IHK-Noten-Umrechnung.
Erweitern um `plan_loader` (Validierung, Schienenzuordnung) und die kursbezogene
Mitarbeitsnote.

---

## 4. Reihenfolge

Jede Phase ist für sich lauffähig und testbar — kein Big-Bang-Umbau.

| Phase | Inhalt | Ergebnis |
|---|---|---|
| **1** | AP 1 (`plan_loader`), `load_json_data()` auf `schema: 2` | Plan ist lesbar, Format gesetzt |
| **2** | AP 2 (Exporter, Kursschleife, gesperrte Kurse überspringen) | Erster Export gegen Kurs 2491549 im neuen Format |
| **3** | AP 3 (Teams) + AP 4 (eine Mitarbeitsnote) | Größter Code-Rückbau; UI vereinfacht |
| **4** | AP 5 (Halbjahr = Kursfilter) + AP 6 (Backend/Reports/Exams) | Vollständig auf neuer Struktur |
| **5** | Tote `.env`-Variablen entfernen, Tests, CHANGELOG | Aufräumen |

Da nichts migriert wird, dürfen die Phasen 1 und 2 die alten Codepfade direkt
ersetzen statt sie parallel zu halten — das spart die sonst übliche Doppelspurigkeit.

**Zeitliche Zäsur:** Phasen 1–4 laufen mit nur einem befüllten Kurs. Nach Freischaltung
des 2. Halbjahres am **11.01.2027** ist ein Nachlauf nötig: Item-IDs und Review-Talk-
Aufgaben für Kurs 2491870 nachtragen, zweiten Tab aktivieren, Aggregation „Gesamt"
erstmals gegen echte Daten prüfen. Das ist der einzige Teil, der sich jetzt nicht
abschließen lässt — entsprechend sollte die Konfiguration je Kurs so angelegt sein,
dass dann nur Werte zu ergänzen und kein Code zu ändern ist.

**Empfehlung:** Refactoring-Branch statt direkt auf `main`. Der Arbeitsbaum enthält
aktuell nicht committete Änderungen in `backend.py`, `dashboard.js`, `exporter.py`,
`report_generator.py` und `csv_export.js` sowie eine unversionierte Datei `NUL` — diese
sollten vor Beginn committet oder verworfen werden, sonst vermischen sie sich mit dem Umbau.

### Umfangsabschätzung

| Bereich | Zeilen | Eingriffstiefe |
|---|---|---|
| `dashboard.js` | 5585 | hoch — Rückbau MA2, Kurs-Scope |
| `exporter.py` | 2097 | mittel — nur `main()`, Signaturen bleiben |
| `backend.py` | 1667 | mittel — Kursschleife, neues Format |
| `csv_export.js` | 1124 | mittel — Spalten je Kurs |
| `report_generator.py` | 1182 | mittel |
| `exam/*` | 4114 | gering — Kursliste statt einzelner ID |
| `plan_loader.py` | neu ~250 | — |

Netto ist mit einer **Verkleinerung** der Codebasis zu rechnen: die entfallende
MA2-Prognose-Arithmetik und die Grouping-Ebene wiegen schwerer als der neue Loader.

---

## 5. Offene Punkte (vor Implementierungsbeginn zu klären)

> **Was `MANUAL_GRADE_ITEM_IDS` bewirkt:** Es sind Moodle-Bewertungselemente ohne
> Aktivität — Spalten im Notenbuch, in die du Werte von Hand einträgst (Quantität,
> Qualität, Mitarbeitsnote, Sonstiges). Das Dashboard liest sie aus und **lässt
> deinem Eintrag den Vorrang** vor dem berechneten Wert. Sie sind also eine
> Übersteuerung, keine Voraussetzung: Fehlen sie, rechnet das Dashboard Quantität
> (stundengewichtet) und Qualität selbst und zeigt genau diese Werte.

### Jetzt zu klären (blockieren den Start)

1. **Gruppennamen** in Kurs 2491549 — exakt `IFA12A` oder mit Zusatz?
2. **`MANUAL_GRADE_ITEM_IDS` für Kurs 2491549** — Quantität, Qualität, Mitarbeitsnote,
   Sonstiges. Die alten IDs (`17751955` usw.) gehören zum Vorjahreskurs und sind
   wertlos; die neuen sind aus dem Notenbuch zu holen. Optional: ohne sie rechnet
   das Dashboard die Werte selbst (siehe unten).
3. **`PROGNOSIS_ASSIGNMENTS` für Kurs 2491549** — welche Aufgabe ist der Review-Talk,
   welche das Code-Review? Im Plan sehe ich dafür keine offensichtlichen Kandidaten.
   Ebenfalls optional.
4. **Stunden-Pflege** — `plan.json` ist die einzige Quelle der `stunden`-Werte und
   liegt im Schüler-Dashboard-Repo. Bei einer Änderung dort verschiebt sich auch die
   Lehrkräfte-Auswertung. Das ist gewollt, sollte dir aber bewusst sein.

Ein Probe-Export gegen Kurs 2491549 beantwortet die Punkte 1 und 2 von selbst.

### Später zu klären (nach Freischaltung 11.01.2027)

5. **Item-IDs und Review-Talks für Kurs 2491870** — analog zu 2 und 3.
6. **Kategorienamen in Kurs 2491870.**
7. **Reports** — je Halbjahr getrennt oder kombiniert?

### Erledigt

- **Klassen** — IFA12A–D; IFA12E gibt es nicht mehr.
- **Kategoriename** — heißt weiterhin `Pflichtaufgaben`; die Zuordnung läuft
  trotzdem über `plan.json` (siehe AP 2).
- **Gewichtung** — nach Stunden (siehe AP 4).
- **`EXPORT_FOLDER`** — neuer Ordner `Exports_2026_27`.
- **`plan.json`-Bezug** — Pfad-Referenz ins Nachbar-Repo über `PLAN_JSON_PATH`.
