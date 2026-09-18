"""
Erzeugt einen synthetischen Export im Schema 2 aus der echten plan.json.

Drei Schueler mit unterschiedlichem Abgabeverhalten, damit die
stundengewichtete Rechnung sichtbar wird:
  - Anna:  nur die grosse 10-Stunden-Aufgabe        -> wenige Aufgaben, viele Stunden
  - Bernd: vier kleine Quizze (2+2.5+2.5+2 = 9 h)   -> viele Aufgaben, wenig Stunden
  - Clara: nichts
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.common.plan_loader import get_plan  # noqa: E402

plan = get_plan()
kurs = plan.get_kurs('halbjahr-1')
aufgaben = kurs['aufgaben']

# Anna: die 10-Stunden-Aufgabe (94824799)
anna_cmids = {'94824799'}
# Bernd: die vier kleinsten Quizze
quizze = sorted([a for a in aufgaben if a['typ'] == 'quiz'], key=lambda a: a['stunden'])[:4]
bernd_cmids = {a['cmid'] for a in quizze}

print('Anna  :', sorted(anna_cmids), '=', sum(plan.get_stunden(c) for c in anna_cmids), 'h')
print('Bernd :', sorted(bernd_cmids), '=', sum(plan.get_stunden(c) for c in bernd_cmids), 'h')


def build_user(uid, name, done_cmids):
    assignments, quizzes = [], []
    for a in aufgaben:
        done = a['cmid'] in done_cmids
        status = {
            "user_id": uid,
            "status": "Zur Bewertung abgegeben" if done else "Nicht eingereicht",
            "status2": "Bewertet" if done else "Nicht bewertet",
            "submission": "Keine Abgabe",
            "submission_time": "2026-10-07T10:00:00" if done else None,
            "grade_options": [],
            "grade": "*** Solide Umsetzung" if done else "-",
        }
        entry = {"id": a['cmid'], "status": status,
                 "category_id": "cg1", "category_name": "🎯Pflichtaufgaben"}
        (assignments if a['typ'] == 'assign' else quizzes).append(entry)
    return {"id": uid, "name": name,
            "activities": {"assignments": assignments, "quizzes": quizzes,
                           "checklists": [], "feedbacks": [], "manual_grades": []}}


categories = [{
    "id": "cg1",
    "category_name": "🎯Pflichtaufgaben",
    "assignments": [{"id": a['cmid'], "title": a['titel'], "url": "#"}
                    for a in aufgaben if a['typ'] == 'assign'],
    "quizzes": [{"id": a['cmid'], "title": a['titel'], "url": "#"}
                for a in aufgaben if a['typ'] == 'quiz'],
    "checklists": [], "feedbacks": [],
}]

export = {
    "schema": 2,
    "exported_at": "2026-10-07T12:00:00",
    "schuljahr": plan.schuljahr,
    "kurse": {
        kurs['moodle_course_id']: {
            "titel": kurs['titel'],
            "course_id": kurs['moodle_course_id'],
            "activities_by_category": categories,
            "activityincludes": [], "activitysections": [],
            "manual_grade_items": {},
        }
    },
    "groups": [{
        "name": "IFA12A", "value": "1001",
        "users": [
            build_user("1", "Anna Abgabe", anna_cmids),
            build_user("2", "Bernd Beflissen", bernd_cmids),
            build_user("3", "Clara Caeruleus", set()),
        ],
    }],
}

out_dir = os.environ.get('FIXTURE_DIR') or tempfile.mkdtemp(prefix='mebis_fixture_')
fixture_dir = out_dir
os.makedirs(fixture_dir, exist_ok=True)
path = os.path.join(fixture_dir, 'output_20261007_120000.json')
with open(path, 'w', encoding='utf-8') as f:
    json.dump(export, f, ensure_ascii=False)
print('geschrieben:', path)
