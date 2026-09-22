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
assert d['schema'] == 2, d.get('schema')
print('  Kurse:', list(d['kurse'].keys()))
" 2>&1 | grep -v ' - INFO - \|Configuration loaded\|EXCLUD\|^====\|Excluded'

echo
echo "=== 4/4  Frontend-Rechenpfade ==="
node tests/test_frontend.js "$FIXTURE_DIR/api.json" | tail -8
