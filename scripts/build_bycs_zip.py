#!/usr/bin/env python3
"""
Packt eine Browser-Seite als ZIP zum Hochladen in ByCS.

Die Dateien liegen im ZIP auf oberster Ebene, damit Moodle nach dem
Entpacken in der Aktivität „Datei" index.html direkt als Hauptdatei
anbieten kann — wie beim Schüler-Dashboard.

    python scripts/build_bycs_zip.py              # Machbarkeitstest (bycs/probe)
    python scripts/build_bycs_zip.py probe
    python scripts/build_bycs_zip.py export       # nur Export, inkl. plan.json
    python scripts/build_bycs_zip.py dashboard    # Dashboard mit Export im Browser

Ausgabe: data/bycs/bycs_<name>.zip (data/bycs/ ist gitignored)

Das Dashboard-ZIP entsteht aus den unveränderten Dateien in
src/dashboard/static/ — es gibt keine zweite Kopie des Dashboards. Dazu
kommen der Browser-Export (bycs/export/exporter.js), die Aufbereitung
(bycs/dashboard/aufbereitung.js), der Startcode (bycs/dashboard/start.js)
und drei Datendateien:

- plan.json             Kopie der geteilten Planungsdatei (für den Export)
- plan_dashboard.json   derselbe Plan, mit Python validiert (Plan.to_dict())
- einstellungen.json    Werte aus config/.env, inkl. Ausschlussliste (Namen!)

Ändert sich der Plan oder die Konfiguration, ZIP neu bauen und hochladen —
wie beim Schüler-Dashboard, dessen ZIP seine plan.json ebenfalls enthält.
"""
import json
import os
import sys
import zipfile

PROJEKT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJEKT)

# Seiten, die die Planungsdatei brauchen
MIT_PLAN = {'export'}

STATIC = os.path.join(PROJEKT, 'src', 'dashboard', 'static')
DASHBOARD_DATEIEN = ['dashboard.js', 'csv_export.js', 'js_logger.js',
                     'css/style.css', 'css/dashboard-custom.css']
BYCS_SKRIPTE = [('bycs/export/exporter.js', 'exporter.js'),
                ('bycs/dashboard/aufbereitung.js', 'aufbereitung.js'),
                ('bycs/dashboard/start.js', 'start.js')]


def plan_pfad() -> str:
    from config.config_manager import config_manager
    pfad = config_manager.get_plan_json_path()
    if not os.path.isfile(pfad):
        raise SystemExit(f"plan.json nicht gefunden: {pfad}")
    with open(pfad, encoding='utf-8') as f:
        json.load(f)  # nur gueltiges JSON einpacken
    return pfad


def dashboard_html() -> str:
    """dashboard.html für ByCS: ohne externes Skript, mit den ByCS-Skripten."""
    with open(os.path.join(STATIC, 'dashboard.html'), encoding='utf-8') as f:
        html = f.read()
    zeilen = html.split('\n')
    # Chart.js wird nicht benutzt; externe Ressourcen haben in ByCS nichts verloren
    ohne_cdn = [z for z in zeilen if 'cdn.jsdelivr.net' not in z]
    html = '\n'.join(ohne_cdn)
    anker = '<script src="csv_export.js"></script>'
    if anker not in html:
        raise SystemExit('dashboard.html: <script src="csv_export.js"> nicht gefunden')
    skripte = ''.join(f'\n    <script src="{ziel}"></script>' for _, ziel in BYCS_SKRIPTE)
    return html.replace(anker, anker + skripte)


def baue_dashboard(zf: zipfile.ZipFile) -> None:
    from src.common.plan_loader import get_plan
    from src.dashboard.bycs_daten import einstellungen_fuer_browser, plan_fuer_browser

    zf.writestr('index.html', dashboard_html())
    for datei in DASHBOARD_DATEIEN:
        zf.write(os.path.join(STATIC, datei), datei)
    for quelle, ziel in BYCS_SKRIPTE:
        zf.write(os.path.join(PROJEKT, quelle), ziel)
    zf.write(plan_pfad(), 'plan.json')
    zf.writestr('plan_dashboard.json', json.dumps(plan_fuer_browser(get_plan()), ensure_ascii=False))
    zf.writestr('einstellungen.json', json.dumps(einstellungen_fuer_browser(), ensure_ascii=False))


def baue(name: str) -> str:
    ziel_ordner = os.path.join(PROJEKT, 'data', 'bycs')
    os.makedirs(ziel_ordner, exist_ok=True)
    ziel = os.path.join(ziel_ordner, f'bycs_{name}.zip')

    if name == 'dashboard':
        with zipfile.ZipFile(ziel, 'w', zipfile.ZIP_DEFLATED) as zf:
            baue_dashboard(zf)
        return ziel

    quelle = os.path.join(PROJEKT, 'bycs', name)
    if not os.path.isfile(os.path.join(quelle, 'index.html')):
        raise SystemExit(f"Kein bycs/{name}/index.html gefunden.")
    with zipfile.ZipFile(ziel, 'w', zipfile.ZIP_DEFLATED) as zf:
        for wurzel, _, dateien in os.walk(quelle):
            for datei in sorted(dateien):
                pfad = os.path.join(wurzel, datei)
                zf.write(pfad, os.path.relpath(pfad, quelle).replace(os.sep, '/'))
        if name in MIT_PLAN:
            zf.write(plan_pfad(), 'plan.json')
    return ziel


if __name__ == '__main__':
    pfad = baue(sys.argv[1] if len(sys.argv) > 1 else 'probe')
    with zipfile.ZipFile(pfad) as zf:
        for info in zf.infolist():
            print(f"  {info.file_size:>7}  {info.filename}")
    print(f"geschrieben: {pfad}")
