#!/usr/bin/env python3
"""
Vergleicht die Aufbereitung eines Exports: Python-Backend gegen
bycs/dashboard/aufbereitung.js.

Beide müssen dieselbe Antwort liefern, die das Dashboard als /api/data
bekommt — sonst zeigen lokales und ByCS-Dashboard verschiedene Zahlen.
Braucht Node. Ausgegeben werden Pfade, keine Namen (lange Texte maskiert).

    python -X utf8 tests/vergleiche_aufbereitung.py <export.json>

Exit-Code 0 = gleich, 1 = Abweichungen.
"""
import json
import logging
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

TOLERANZ = 1e-9

_NODE = r"""
const fs = require('fs');
const a = require(process.argv[1]);
const [exp, plan, einst] = [2, 3, 4].map(i => JSON.parse(fs.readFileSync(process.argv[i], 'utf8')));
const erg = a.aufbereiten(exp, plan, einst, process.argv[5]);
fs.writeFileSync(process.argv[6], JSON.stringify(erg));
"""


def _zeige(wert):
    if isinstance(wert, str) and len(wert.split()) > 3:
        return f'<Text, {len(wert.split())} Wörter>'
    return repr(wert)


def vergleiche(a, b, pfad='', aus=None):
    aus = [] if aus is None else aus
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                aus.append(f"{pfad}/{k}: nur in {'Python' if k in a else 'JS'}")
            else:
                vergleiche(a[k], b[k], f'{pfad}/{k}', aus)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            aus.append(f'{pfad}: Länge Python={len(a)} JS={len(b)}')
        for i, (x, y) in enumerate(zip(a, b)):
            vergleiche(x, y, f'{pfad}[{i}]', aus)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        if abs(a - b) > TOLERANZ:
            aus.append(f'{pfad}: Python={a!r} JS={b!r}')
    elif a != b:
        aus.append(f'{pfad}: Python={_zeige(a)} JS={_zeige(b)}')
    return aus


def python_antwort(export, quelle):
    from src.dashboard import backend
    logging.disable(logging.CRITICAL)
    try:
        antwort = backend._process_dashboard_data(json.loads(json.dumps(export)), source_label=quelle)
    finally:
        logging.disable(logging.NOTSET)
    # Wie jsonify: Text-Schluessel, Sets als Listen
    antwort['ignored_groups'] = sorted(antwort['ignored_groups'])
    return json.loads(json.dumps(antwort, default=str, sort_keys=True))


def js_antwort(export, quelle):
    from src.dashboard.bycs_daten import einstellungen_fuer_browser, plan_fuer_browser
    with tempfile.TemporaryDirectory() as tmp:
        dateien = {}
        for name, inhalt in (('export', export), ('plan', plan_fuer_browser()),
                             ('einst', einstellungen_fuer_browser())):
            dateien[name] = os.path.join(tmp, f'{name}.json')
            with open(dateien[name], 'w', encoding='utf-8') as f:
                json.dump(inhalt, f, ensure_ascii=False)
        ziel = os.path.join(tmp, 'js.json')
        subprocess.run(['node', '-e', _NODE, os.path.join(REPO, 'bycs', 'dashboard', 'aufbereitung.js'),
                        dateien['export'], dateien['plan'], dateien['einst'], quelle, ziel], check=True)
        with open(ziel, encoding='utf-8') as f:
            antwort = json.load(f)
    antwort['ignored_groups'] = sorted(antwort['ignored_groups'])
    return antwort


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    pfad = sys.argv[1]
    with open(pfad, encoding='utf-8') as f:
        export = json.load(f)
    quelle = os.path.basename(pfad)
    abw = vergleiche(python_antwort(export, quelle), js_antwort(export, quelle))
    if not abw:
        print(f'Aufbereitung gleich: Python und JS liefern dieselbe Antwort ({quelle}).')
        return 0
    print(f'{len(abw)} Abweichung(en), erste 40:')
    for z in abw[:40]:
        print(' ', z)
    return 1


if __name__ == '__main__':
    sys.exit(main())
