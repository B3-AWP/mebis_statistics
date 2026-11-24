#!/usr/bin/env bash
# Prueft das Kursstruktur-Refactoring 2026/27 durchgehend:
# plan_loader, Backend-API, Frontend-Rechenpfade.
set -e
cd "$(dirname "$0")/.."

FIXTURE_DIR="$(mktemp -d)"
export FIXTURE_DIR
trap 'rm -rf "$FIXTURE_DIR"' EXIT

echo "=== 1/4  plan_loader (Python, inkl. Abgleich mit js/bilanz.js) ==="
python -m unittest tests.test_plan_loader 2>&1 | tail -3
python -X utf8 -m unittest tests.test_titel_planstunden 2>&1 | tail -3
echo "--- Pruefschichten des Exports (Seiten, Abgleich, Verlauf)"
python -X utf8 -m unittest tests.test_pruefung tests.test_report_unbekannt 2>&1 | tail -3

echo
echo "=== 2/4  Testdaten erzeugen ==="
python -X utf8 tests/make_fixture.py 2>&1 | grep -v ' - INFO - \|Configuration loaded'

echo
echo "=== 3/4  Backend-API ==="
EXPORT_FOLDER="$FIXTURE_DIR" python -X utf8 -c "
import os, sys, json
sys.path.insert(0, '.')
from src.dashboard import backend
d = backend.app.test_client().get('/api/data').get_json()
json.dump(d, open(os.path.join(os.environ['FIXTURE_DIR'], 'api.json'), 'w', encoding='utf-8'), ensure_ascii=False)
assert d['schema'] == 3, d.get('schema')
assert d['pruefbericht']['luecken'], 'Pruefbericht fehlt in der API-Antwort'
nutzer = {u['name']: u['assignments'] for g in d['kurse'].values()
          for gr in g.get('groups', {}).values() for u in gr['users']}
dora, bernd = nutzer['Dora Datenluecke'], nutzer['Bernd Beflissen']
# Plan-unabhaengig: Dora = Bernds Abgaben + die 10-Stunden-Aufgabe unbekannt
stunden = next(a['stunden'] for k in d['plan']['kurse'] for a in k['aufgaben'] if a['cmid'] == '94824799')
assert dora['stunden_unbekannt'] == stunden, dora
assert dora['stunden_erledigt'] == bernd['stunden_erledigt'], (dora, bernd)
# Entwurf: Clara hat die 10-Stunden-Aufgabe nur gespeichert -> zaehlt nicht
assert nutzer['Clara Caeruleus']['stunden_erledigt'] == 0, nutzer['Clara Caeruleus']
print('  unbekannt: Dora', dora['stunden_unbekannt'], 'Std. unbekannt,', dora['stunden_erledigt'], 'Std. erledigt')
print('  Kurse:', list(d['kurse'].keys()))
" 2>&1 | grep -v ' - INFO - \|Configuration loaded\|EXCLUD\|^====\|Excluded'

echo
echo "=== 4/4  Frontend-Rechenpfade ==="
node tests/test_frontend.js "$FIXTURE_DIR/api.json" | tail -8
echo "--- Aufbereitung: Python-Backend gegen bycs/dashboard/aufbereitung.js"
python -X utf8 tests/vergleiche_aufbereitung.py "$FIXTURE_DIR/output_20261007_120000.json" 2>&1 \
    | grep -v ' - INFO - \|Configuration loaded' | tail -5
