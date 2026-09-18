#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mebis Statistik Dashboard - Backend
Version mit professionellem Logging und Environment Variables Support
"""

import os
import sys

# Add project root to path for imports
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Change working directory to project root for relative paths to work
os.chdir(_project_root)

import json
import glob
import math
import subprocess
import threading
import time as time_module
from flask import Flask, jsonify, send_from_directory, request, send_file
import tempfile
import zipfile
from flask_cors import CORS

# Sichere Konfiguration und Logging
from config.config_manager import config_manager
from config.logger_config import get_logger, backend_logger, api_logger, data_logger

# Stammdaten (Kurse, Aufgaben, Stunden, Schulwochen)
from src.common import plan_loader
from src.common.plan_loader import PlanFehler, get_plan

# PDF Generator
from src.export.pdf_multi import ReviewPDFGeneratorMulti

# Erwartete Version des Exportformats (siehe exporter.EXPORT_SCHEMA_VERSION)
EXPORT_SCHEMA_VERSION = 2

# Flask App Setup mit sicherer Konfiguration
# Use absolute path for static folder
_static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask(__name__, static_folder=_static_folder)
# CORS mit expliziten Optionen für POST-Anfragen
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"]}}, supports_credentials=True)

# Flask Konfiguration aus Environment Variables
flask_config = config_manager.get_flask_config()
app.config.update({
    'DEBUG': flask_config['debug'],
    'SECRET_KEY': flask_config['secret_key'],
    'ENV': flask_config['env']
})

def find_latest_file(directory=None):
    """
    Findet die neueste JSON-Datei im Export-Ordner

    Args:
        directory: Verzeichnis zum Durchsuchen (None = aus Konfiguration)

    Returns:
        str: Pfad zur neuesten Datei oder None
    """
    logger = data_logger

    # Hole Export-Ordner aus Konfiguration wenn nicht angegeben
    if directory is None:
        directory = config_manager.get_export_folder()

    # Make directory absolute if it's relative
    if not os.path.isabs(directory):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        directory = os.path.join(project_root, directory)

    try:
        pattern = os.path.join(directory, 'output_*.json')
        files = glob.glob(pattern)

        logger.info(f"Searching for JSON files in '{directory}' with pattern '{pattern}'")

        if not files:
            logger.warning(f"No JSON files found in directory '{directory}'")
            return None

        latest_file = max(files, key=os.path.getctime)
        logger.info(f"Latest file found: {os.path.basename(latest_file)}")
        return latest_file

    except Exception as e:
        logger.error(f"Error finding latest file: {e}")
        return None

def load_json_data(file_path):
    """
    Lädt JSON-Daten aus einer Datei mit Fehlerbehandlung

    Args:
        file_path: Pfad zur JSON-Datei

    Returns:
        dict: Geladene Daten oder None bei Fehler
    """
    logger = data_logger

    if not file_path:
        logger.error("No file path provided")
        return None

    if not os.path.exists(file_path):
        logger.error(f"File does not exist: {file_path}")
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)

        if not isinstance(data, dict):
            logger.error("Loaded JSON is not a dictionary")
            return None

        # Schuljahr 2026/27: Ein Export enthält mehrere Kurse unter "kurse".
        # Altformate werden bewusst abgelehnt statt stillschweigend falsch
        # interpretiert — sie stammen aus dem Vorjahr mit anderer Kursstruktur.
        schema = data.get('schema')
        if schema != EXPORT_SCHEMA_VERSION:
            logger.error(
                f"Export '{os.path.basename(file_path)}' hat Schema {schema!r}, "
                f"erwartet wird {EXPORT_SCHEMA_VERSION}. "
                f"Altformate aus dem Vorjahr werden nicht mehr gelesen — "
                f"bitte einen neuen Export erzeugen."
            )
            return None

        logger.info(f"JSON file loaded successfully. Keys: {list(data.keys())}")
        return data

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format in {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading JSON data from {file_path}: {e}")
        return None

def load_excluded_names(file_path='config/exclude_names.txt'):
    """
    Lädt die Liste der ausgeschlossenen Namen

    Args:
        file_path: Pfad zur Datei mit ausgeschlossenen Namen

    Returns:
        set: Set mit ausgeschlossenen Namen
    """
    logger = data_logger

    try:
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Attempting to load excluded names from: {file_path}")
        logger.info(f"File exists: {os.path.exists(file_path)}")

        if not os.path.exists(file_path):
            logger.warning(f"File not found at {file_path}")
            # List directory contents for debugging
            config_dir = 'config'
            if os.path.exists(config_dir):
                logger.info(f"Contents of {config_dir}: {os.listdir(config_dir)}")
            return set()

        # Try multiple encodings
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        excluded_names = set()

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as file:
                    # Read and clean names: strip whitespace and line endings
                    excluded_names = {
                        line.strip().rstrip('\r\n').strip()
                        for line in file.readlines()
                        if line.strip()
                    }
                logger.info(f"Successfully loaded {len(excluded_names)} excluded names from {file_path} using {encoding} encoding")
                logger.info(f"Excluded names: {sorted(list(excluded_names))}")
                return excluded_names
            except (UnicodeDecodeError, UnicodeError):
                logger.debug(f"Failed to decode with {encoding}, trying next encoding")
                continue

        logger.warning(f"Could not decode {file_path} with any known encoding")
        return set()

    except FileNotFoundError:
        logger.warning(f"No excluded names file found at {file_path}")
        return set()
    except Exception as e:
        logger.error(f"Error loading excluded names from {file_path}: {e}", exc_info=True)
        return set()

def load_ignored_groups():
    """
    Lädt die Liste der ignorierten Gruppen aus sicherer Konfiguration

    Returns:
        set: Set mit ignorierten Gruppennamen
    """
    logger = data_logger

    try:
        ignored_groups = config_manager.get_ignored_groups()
        logger.info(f"Loaded {len(ignored_groups)} ignored groups from configuration")
        return ignored_groups

    except Exception as e:
        logger.error(f"Error loading ignored groups: {e}")
        return set()

def get_assignment_details(assignments_by_category):
    """
    Erstellt ein Dictionary mit Assignment-Details

    Args:
        assignments_by_category: Liste der Kategorien mit Assignments

    Returns:
        dict: Dictionary mit Assignment-Details, indexiert nach ID
    """
    logger = data_logger
    assignment_details = {}
    total_assignments = 0

    try:
        for category in assignments_by_category:
            category_name = category.get('category_name', 'Unknown')

            # Assignments hinzufügen
            for assignment in category.get('assignments', []):
                assignment_details[assignment['id']] = {
                    'title': assignment['title'],
                    'url': assignment['url'],
                    'category_name': category_name,
                    'type': 'assignment'
                }
                total_assignments += 1

            # Quizzes hinzufügen
            for quiz in category.get('quizzes', []):
                assignment_details[quiz['id']] = {
                    'title': quiz['title'],
                    'url': quiz['url'],
                    'category_name': category_name,
                    'type': 'quiz'
                }
                total_assignments += 1

            # Checklists hinzufügen
            for checklist in category.get('checklists', []):
                assignment_details[checklist['id']] = {
                    'title': checklist['title'],
                    'url': checklist['url'],
                    'category_name': category_name,
                    'type': 'checklist'
                }
                total_assignments += 1

            # Feedbacks hinzufügen
            for feedback in category.get('feedbacks', []):
                assignment_details[feedback['id']] = {
                    'title': feedback['title'],
                    'url': feedback['url'],
                    'category_name': category_name,
                    'type': 'feedback'
                }
                total_assignments += 1

        logger.info(f"Created assignment details for {total_assignments} activities")
        return assignment_details

    except Exception as e:
        logger.error(f"Error creating assignment details: {e}")
        return {}

# Hilfsfunktionen für Notenberechnungen
def convert_grade_to_ihk(grade_str):
    """
    Konvertiert verschiedene Notenformate zu IHK-Note (1-6)

    Args:
        grade_str: Note als String in verschiedenen Formaten

    Returns:
        float: IHK-Note oder None wenn nicht konvertierbar
    """
    if not grade_str or grade_str in ['-', 'Nicht bewertet', 'Keine Bewertung']:
        return None

    grade_str = str(grade_str).strip()

    # Sterne-basierte Noten (4-Punkt-System zu IHK)
    star_mapping = {
        "**** Exzellent": 1.0,           # Sehr gut
        "*** Solide Umsetzung": 2.5,     # Gut-Befriedigend
        "** Verbesserungsbedarf": 4.0,   # Ausreichend
        "* Nicht akzeptabel": 5.5        # Mangelhaft
    }

    if grade_str in star_mapping:
        return star_mapping[grade_str]

    # Prozent-Noten (z.B. "54 %" oder "54%")
    if '%' in grade_str:
        try:
            percentage = float(grade_str.replace('%', '').replace(' ', ''))
            return points_to_ihk_grade(percentage)
        except (ValueError, TypeError):
            pass

    # Punkte-basierte Noten (z.B. "80 / 100")
    if '/' in grade_str:
        try:
            parts = grade_str.split('/')
            points = float(parts[0].strip())
            max_points = float(parts[1].strip())
            percentage = (points / max_points) * 100

            # Konvertiere Prozent zu IHK-Note
            return points_to_ihk_grade(percentage)
        except (ValueError, IndexError, ZeroDivisionError):
            backend_logger.warning(f"Could not parse grade format: {grade_str}")

    # Numerische Noten (1-6)
    try:
        if isinstance(grade_str, str):
            grade_num = float(grade_str.replace(',', '.'))
        else:
            grade_num = float(grade_str)

        # Nur Noten zwischen 1 und 6 sind gültig
        if 1 <= grade_num <= 6:
            return grade_num
    except (ValueError, TypeError):
        backend_logger.warning(f"Could not convert grade to number: {grade_str}")

    return None

def points_to_ihk_grade(points):
    """Konvertiert Punkte (0-100) zu IHK-Note (1-6)"""
    if points >= 92:
        return 1.0  # Sehr gut
    elif points >= 81:
        return 2.0  # Gut
    elif points >= 67:
        return 3.0  # Befriedigend
    elif points >= 50:
        return 4.0  # Ausreichend
    elif points >= 30:
        return 5.0  # Mangelhaft
    else:
        return 6.0  # Ungenügend

def calculate_ihk_grade_average(grades):
    """
    Berechnet IHK-konformen Notendurchschnitt

    Args:
        grades: Liste von Noten in verschiedenen Formaten

    Returns:
        float: Durchschnittsnote oder None
    """
    if not grades:
        return None

    # Konvertiere alle Noten zu IHK-Format
    valid_grades = []
    for grade in grades:
        ihk_grade = convert_grade_to_ihk(grade)
        if ihk_grade is not None:
            valid_grades.append(ihk_grade)

    if not valid_grades:
        return None

    # IHK-konforme Durchschnittsberechnung:
    # Arithmetisches Mittel der Noten, gerundet auf 0.1
    average = sum(valid_grades) / len(valid_grades)
    return round(average, 1)

def round_grade(grade_str):
    """
    Rundet eine Note auf ganze Zahlen: bis 0.5 ab, ab 0.5 auf

    Args:
        grade_str: Note als String

    Returns:
        str: Gerundete Note oder ursprünglicher Wert
    """
    if not grade_str or grade_str in ['-', 'Nicht bewertet', 'Keine Bewertung']:
        return grade_str

    try:
        # Versuche, eine Zahl aus dem Grade-String zu extrahieren
        import re
        grade_match = re.search(r'(\d+[.,]\d+|\d+)', grade_str)
        if grade_match:
            grade_text = grade_match.group(1).replace(',', '.')
            grade_float = float(grade_text)

            # Runde auf ganze Zahlen: bis 0.5 ab, ab 0.5 auf
            rounded_grade = math.floor(grade_float + 0.5)
            return str(int(rounded_grade))
    except Exception as e:
        backend_logger.debug(f"Could not round grade {grade_str}: {e}")

    return grade_str

def find_user_checklist_progress(user, checklist_id):
    """Findet den Fortschritt einer spezifischen Checkliste für einen Benutzer"""
    for checklist in user.get('checklists', {}).get('individual_checklists', []):
        if checklist['id'] == checklist_id:
            return {
                'required_progress': checklist['required_progress'],
                'all_progress': checklist['all_progress'],
                'url': checklist['url']
            }

    return {
        'required_progress': '0%',
        'all_progress': '0%',
        'url': '#'
    }

def find_user_assignment_status(user, assignment_id):
    """Findet den Status einer spezifischen Aufgabe für einen Benutzer"""
    logger = backend_logger
    logger.debug(f"Searching assignment {assignment_id} for user {user.get('name', 'Unknown')}")

    # Suche in den User-Aktivitäten (assignments und quizzes)
    activities = user.get('activities', {})
    logger.debug(f"User has {len(activities.get('assignments', []))} assignments and {len(activities.get('quizzes', []))} quizzes")

    # Suche in assignments
    for assignment in activities.get('assignments', []):
        if assignment.get('id') == assignment_id:
            status_info = assignment.get('status', {})
            raw_grade = status_info.get('grade', '-')
            rounded_grade = round_grade(raw_grade)
            result = {
                'status': status_info.get('status', 'Nicht eingereicht'),
                'status2': status_info.get('status2', ''),
                'grade': rounded_grade,
                'submission_time': status_info.get('submission_time', None)
            }
            logger.debug(f"MATCH! {user.get('name')} - Assignment {assignment_id}: {result}")
            return result

    # Suche in quizzes
    for quiz in activities.get('quizzes', []):
        if quiz.get('id') == assignment_id:
            status_info = quiz.get('status', {})
            raw_grade = status_info.get('grade', '-')
            rounded_grade = round_grade(raw_grade)
            result = {
                'status': status_info.get('status', 'Nicht eingereicht'),
                'status2': status_info.get('status2', ''),
                'grade': rounded_grade,
                'submission_time': status_info.get('submission_time', None)
            }
            logger.debug(f"QUIZ MATCH! {user.get('name')} - Quiz {assignment_id}: {result}")
            return result

    # Wenn nicht gefunden
    result = {
        'status': 'Nicht eingereicht',
        'status2': '',
        'grade': '-',
        'submission_time': None
    }
    logger.debug(f"NOT FOUND! {user.get('name')} - Assignment {assignment_id}: {result}")
    return result

# API Endpoints
@app.route('/')
def index():
    """Serviert die Dashboard HTML-Datei"""
    return send_from_directory(app.static_folder, 'dashboard.html')

@app.route('/<path:filename>')
def static_files(filename):
    """Serviert statische Dateien"""
    return send_from_directory(app.static_folder, filename)

def _process_dashboard_data(data, source_label=None):
    """
    Verarbeitet einen Export mit mehreren Kursen.

    Jeder Kurs wird einzeln ausgewertet (_process_course_data); die Gruppen
    liegen kursübergreifend auf oberster Ebene und werden in jeden Kurs
    hineingereicht.

    Args:
        data: Geladenes JSON-Dict (Schema 2)
        source_label: Anzeigename der Quelle (Dateipfad oder Dateiname)

    Returns:
        dict: Response-Dict für jsonify
    """
    logger = data_logger

    try:
        plan = get_plan()
    except PlanFehler as e:
        logger.error(f"Planungsdatei nicht ladbar: {e}")
        raise

    raw_groups = data.get('groups', [])
    kurse_raw = data.get('kurse', {})

    kurse_response = {}
    for course_id, course_data in kurse_raw.items():
        kurs = plan.get_kurs_by_moodle_id(course_id)
        if not kurs:
            logger.warning(
                f"Kurs {course_id} steht nicht in plan.json — wird übersprungen. "
                f"Bekannte Kurse: {[k['moodle_course_id'] for k in plan.kurse]}"
            )
            continue

        logger.info(f"Verarbeite Kurs {course_id} ({kurs['titel']})")
        # Die Gruppen stehen nur einmal ganz oben; der Kursauswertung
        # reichen wir sie als 'groups' hinein.
        merged = dict(course_data)
        merged['groups'] = raw_groups

        kurs_response = _process_course_data(
            merged, plan=plan, kurs=kurs, source_label=source_label
        )
        kurs_response['titel'] = kurs['titel']
        kurs_response['kurs_id'] = kurs['id']
        kurs_response['gesperrt'] = kurs['gesperrt']
        kurse_response[str(course_id)] = kurs_response

    # Kurse, die im Plan stehen, aber (noch) nicht exportiert wurden —
    # typischerweise das gesperrte 2. Halbjahr. Sie erscheinen als leere
    # Huelle, damit das Frontend den Tab anzeigen und begruenden kann.
    for kurs in plan.get_kurse():
        cid = kurs['moodle_course_id']
        if cid in kurse_response:
            continue
        kurse_response[cid] = {
            'titel': kurs['titel'],
            'kurs_id': kurs['id'],
            'gesperrt': kurs['gesperrt'],
            'freischaltung': kurs['freischaltung'].isoformat() if kurs['freischaltung'] else None,
            'verfuegbar': False,
            'groups': {},
            'overall_stats': {},
            'activities_by_category': [],
            'categories': [],
            'structured_tables': {},
            'assignment_details': {},
            'recent_submissions': [],
        }

    environment_settings = {
        'flask_env': os.getenv('FLASK_ENV', 'production'),
        'log_level': os.getenv('LOG_LEVEL', 'INFO'),
        'flask_debug': os.getenv('FLASK_DEBUG', 'False'),
    }

    return {
        'schema': EXPORT_SCHEMA_VERSION,
        'exported_at': data.get('exported_at'),
        'schuljahr': data.get('schuljahr') or plan.schuljahr,
        'plan': plan.to_dict(),
        'kurse': kurse_response,
        'ignored_groups': list(load_ignored_groups()),
        'last_updated': source_label,
        'environment': environment_settings,
        'manual_grade_item_ids': config_manager.get_manual_grade_item_ids(),
        'recent_submission_days': config_manager.get_recent_submission_days(),
    }


def _process_course_data(data, plan, kurs, source_label=None):
    """
    Verarbeitet die Rohdaten eines einzelnen Kurses.

    Args:
        data: Kursdaten inkl. hineingereichter 'groups'
        plan: geladener Plan (Stammdaten)
        kurs: Kurseintrag aus plan.json
        source_label: Anzeigename der Quelle

    Returns:
        dict: Auswertung dieses Kurses
    """
    import datetime, re as _re

    logger = data_logger

    excluded_names = load_excluded_names()
    ignored_groups = load_ignored_groups()

    logger.info("=" * 80)
    logger.info(f"EXCLUDED NAMES: {len(excluded_names)} names loaded")
    logger.info(f"Excluded names list: {sorted(list(excluded_names))}")
    logger.info("=" * 80)

    try:
        grade_mapping = config_manager.get_grade_mapping()
    except Exception as e:
        logger.error(f"Error loading grade_mapping: {e}")
        grade_mapping = {}

    assignment_details = get_assignment_details(data.get('activities_by_category', []))

    # Wochenkalender: die Klassen dieses Exports können auf mehreren Schienen
    # liegen. Für die kursweite Vorberechnung nehmen wir die erste Schiene;
    # die schienengenaue Rechnung passiert pro Gruppe im Frontend.
    erste_schiene = next(iter(plan.schienen), None)
    schulwochen = plan.get_schulwochen(erste_schiene) if erste_schiene else []
    total_weeks = len(schulwochen) or 1
    current_week = plan_loader.aktuelle_woche(schulwochen) if schulwochen else 0

    groups_data = {}
    for group in data.get('groups', []):
        group_name = group.get('name', 'Unknown')
        if group_name in ignored_groups:
            continue

        all_users_in_group = [user.get('name') for user in group.get('users', [])]
        logger.info(f"Group '{group_name}' has {len(all_users_in_group)} users before filtering")

        group_users = []
        excluded_count = 0
        for user in group.get('users', []):
            user_name = user.get('name', '')
            if user_name in excluded_names:
                logger.info(f"  ✗ Excluding user '{user_name}' from group '{group_name}'")
                excluded_count += 1
            else:
                group_users.append(user)

        if excluded_count > 0:
            logger.info(f"Group '{group_name}': Excluded {excluded_count} users, {len(group_users)} remaining")

        if group_users:
            groups_data[group_name] = {
                'name': group_name,
                'value': group.get('value'),
                'users': []
            }
            for user in group_users:
                try:
                    user['group'] = group_name
                    user_progress = calculate_user_progress(
                        user, assignment_details, data.get('activities_by_category', []),
                        current_week, total_weeks, plan=plan, kurs=kurs
                    )
                    groups_data[group_name]['users'].append(user_progress)
                except Exception as e:
                    logger.warning(f"Error processing user {user.get('name', 'Unknown')}: {e}")
                    groups_data[group_name]['users'].append(create_fallback_user(user, group_name))

    for group_name, group_data in groups_data.items():
        group_data.update(calculate_group_averages(group_data['users']))

    all_users = []
    for group_data in groups_data.values():
        all_users.extend(group_data['users'])
    overall_stats = calculate_group_averages(all_users)

    structured_data = create_structured_tables(groups_data, data.get('activities_by_category', []))

    pflichtaufgaben_category = None
    other_categories = []
    for category in data.get('activities_by_category', []):
        if 'Pflichtaufgaben' in category.get('category_name', ''):
            pflichtaufgaben_category = category
        else:
            other_categories.append(category)
    activities_ordered = ([pflichtaufgaben_category] + other_categories) if pflichtaufgaben_category else data.get('activities_by_category', [])

    def add_user_status_to_activities(activities, data, groups_data, excluded_names):
        for category in activities:
            for assignment in category.get('assignments', []):
                assignment['user_status'] = []
                assignment_id = assignment.get('id')
                for group in data.get('groups', []):
                    gname = group.get('name', '')
                    if gname in ignored_groups:
                        continue
                    for user in group.get('users', []):
                        if user.get('name') in excluded_names:
                            continue
                        status = find_user_assignment_status(user, assignment_id)
                        assignment['user_status'].append({
                            'user_name': user.get('name', ''),
                            'user_id': user.get('id', ''),
                            'status': status.get('status', 'Nicht eingereicht'),
                            'grade': status.get('grade', '-'),
                            'submission_time': status.get('submission_time', None)
                        })
            for quiz in category.get('quizzes', []):
                quiz['user_status'] = []
                quiz_id = quiz.get('id')
                for group in data.get('groups', []):
                    gname = group.get('name', '')
                    if gname in ignored_groups:
                        continue
                    for user in group.get('users', []):
                        if user.get('name') in excluded_names:
                            continue
                        status = find_user_assignment_status(user, quiz_id)
                        quiz['user_status'].append({
                            'user_name': user.get('name', ''),
                            'user_id': user.get('id', ''),
                            'status': status.get('status', 'Nicht eingereicht'),
                            'grade': status.get('grade', '-'),
                            'submission_time': status.get('submission_time', None)
                        })
        return activities

    activities_with_status = add_user_status_to_activities(activities_ordered, data, groups_data, excluded_names)

    flask_config = config_manager.get_flask_config()
    environment_settings = {'mode': flask_config['env'], 'debug': flask_config['debug']}

    export_date = None
    if source_label:
        _m = _re.search(r'(\d{8})_\d{6}', os.path.basename(source_label))
        if _m:
            try:
                ds = _m.group(1)
                export_date = datetime.date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
            except ValueError:
                pass
    if export_date is None:
        export_date = datetime.date.today()

    # Schienen und Wochenkalender kommen aus plan.json; aus der .env
    # stammen nur noch die kursspezifischen Aufgaben-IDs.
    mitarbeitsnote_cfg = config_manager.get_mitarbeitsnote_config() or {}
    mitarbeitsnote_cfg['class_to_track'] = dict(plan.klassen_zu_schiene)
    mitarbeitsnote_cfg['track_schedules'] = {
        name: [
            {
                'week': w['woche'],
                'start': w['start'].isoformat() if w['start'] else None,
                'end': w['ende'].isoformat() if w['ende'] else None,
            }
            for w in schiene['schulwochen']
        ]
        for name, schiene in plan.schienen.items()
    }
    manual_grade_ids = config_manager.get_manual_grade_item_ids()
    recent_days = config_manager.get_recent_submission_days()
    inactive_threshold = config_manager.get_inactive_threshold_days()
    recent_submissions = build_recent_submissions(
        groups_data=groups_data,
        raw_groups=data.get('groups', []),
        manual_grade_item_ids=manual_grade_ids,
        mitarbeitsnote_config=mitarbeitsnote_cfg,
        recent_submission_days=recent_days,
        assignment_details=assignment_details,
        reference_date=export_date,
        categories=activities_with_status,
        inactive_threshold_days=inactive_threshold,
    )

    response_data = {
        'verfuegbar': True,
        'course_id': kurs['moodle_course_id'],
        'groups': groups_data,
        'overall_stats': overall_stats,
        'assignment_details': assignment_details,
        'categories': activities_with_status,
        'activities_by_category': activities_with_status,
        'structured_tables': structured_data,
        'grade_mapping': grade_mapping,
        'mitarbeitsnote_config': mitarbeitsnote_cfg,
        'manual_grade_item_ids': manual_grade_ids,
        'manual_grade_items': data.get('manual_grade_items', {}),
        'recent_submissions': recent_submissions,
        'stunden_geplant': kurs['stundenGeplant'],
    }

    logger.info(
        f"Kurs {kurs['moodle_course_id']} verarbeitet: {len(groups_data)} Gruppen"
    )
    return response_data


@app.route('/api/data')
def get_data():
    """
    API-Endpoint für Dashboard-Daten mit professionellem Error-Handling
    """
    logger = api_logger
    logger.info("API endpoint /api/data called")

    try:
        latest_file = find_latest_file()
        if not latest_file:
            logger.error("No export file found")
            return jsonify({'error': 'Keine Export-Datei gefunden'}), 404

        data = load_json_data(latest_file)
        if not data:
            logger.error("Failed to load JSON data")
            return jsonify({'error': 'Fehler beim Laden der Daten'}), 500

        response_data = _process_dashboard_data(data, source_label=latest_file)

        import json
        json_test = json.dumps(response_data, default=str, ensure_ascii=False)
        logger.debug(f"JSON serialization successful, size: {len(json_test)} characters")

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Unexpected error in get_data: {e}", exc_info=True)
        return jsonify({'error': 'Unerwarteter Server-Fehler'}), 500


@app.route('/api/load-file', methods=['POST'])
def load_file():
    """
    API-Endpoint zum manuellen Laden einer JSON-Exportdatei (Upload vom Browser)
    """
    logger = api_logger
    logger.info("API endpoint /api/load-file called")

    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Keine Datei übermittelt'}), 400

        uploaded = request.files['file']
        if not uploaded.filename:
            return jsonify({'error': 'Kein Dateiname'}), 400
        if not uploaded.filename.lower().endswith('.json'):
            return jsonify({'error': 'Nur JSON-Dateien erlaubt'}), 400

        try:
            data = json.load(uploaded.stream)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in uploaded file: {e}")
            return jsonify({'error': f'Ungültiges JSON-Format: {e}'}), 400

        response_data = _process_dashboard_data(data, source_label=uploaded.filename)
        json.dumps(response_data, default=str, ensure_ascii=False)  # Serialization check
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Unexpected error in load_file: {e}", exc_info=True)
        return jsonify({'error': 'Unerwarteter Server-Fehler'}), 500

def create_fallback_user(user, group_name):
    """Erstellt einen Fallback-Benutzer bei Verarbeitungsfehlern"""
    return {
        "name": user.get('name', 'Unknown'),
        "group": group_name,
        "assignments": {
            "reviewed_count": 0,
            "submitted_count": 0,
            "grades": {},
            "percent_submitted": 0,
            "percent_submitted_timed": 0,
            "average_grade": None
        },
        "checklists": {
            "required_100_count": 0,
            "avg_required_progress": 0,
            "avg_all_progress": 0,
            "avg_required_progress_timed": 0,
            "avg_all_progress_timed": 0,
            "individual_checklists": []
        }
    }

def calculate_user_progress(user, assignment_details, categories, current_week, total_weeks,
                            plan=None, kurs=None):
    """
    Berechnet den Fortschritt eines Benutzers.

    Args:
        plan: geladener Plan; bestimmt über die cmid, was Pflichtaufgabe ist,
              und liefert die Stundengewichte. Ohne Plan fällt die Erkennung
              auf den Kategorienamen zurück (nur für Alt-Aufrufer).
        kurs: Kurseintrag; begrenzt die Pflichtaufgaben auf diesen Kurs.
    """
    user_data = {
        "name": user['name'],
        "group": user.get('group', 'Unbekannt'),
        "assignments": {
            "reviewed_count": 0,
            "submitted_count": 0,
            "grades": {},
            "percent_submitted": 0,
            "percent_submitted_timed": 0,
            "average_grade": None
        },
        "checklists": {
            "required_100_count": 0,
            "avg_required_progress": 0,
            "avg_all_progress": 0,
            "avg_required_progress_timed": 0,
            "avg_all_progress_timed": 0,
            "individual_checklists": []
        },
        "manual_grades": user.get('activities', {}).get('manual_grades', [])
    }

    # Pflichtaufgaben bestimmt der Plan über die cmid, nicht der Kategoriename.
    # Nur so kommt man an das stunden-Feld, das die Gewichtung trägt.
    user_assignments = user['activities'].get('assignments', [])
    user_quizzes = user['activities'].get('quizzes', [])
    user_checklists = user['activities'].get('checklists', [])
    user_feedbacks = user['activities'].get('feedbacks', [])

    if plan is not None:
        plan_cmids = {a['cmid'] for a in (kurs['aufgaben'] if kurs else plan.get_alle_aufgaben())}

        def _ist_pflicht(act):
            return str(act.get('id', '')).strip() in plan_cmids

        pflicht_assignments = [a for a in user_assignments if _ist_pflicht(a)]
        pflicht_quizzes = [q for q in user_quizzes if _ist_pflicht(q)]
        pflicht_checklists = [c for c in user_checklists if _ist_pflicht(c)]
        pflicht_feedbacks = [f for f in user_feedbacks if _ist_pflicht(f)]

        # Nenner = alle im Plan vorgesehenen Aufgaben. Eine Aufgabe, die in
        # Moodle (noch) fehlt, bleibt darin und gilt als nicht begonnen.
        total_pflicht_activities = len(plan_cmids)
    else:
        pflicht_categories = [c for c in categories
                              if 'Pflichtaufgaben' in c.get('category_name', '')]
        if not pflicht_categories:
            return user_data

        pflicht_category = pflicht_categories[0]
        pflicht_category_id = pflicht_category['id']

        pflicht_assignments = [a for a in user_assignments if a.get('category_id') == pflicht_category_id]
        pflicht_quizzes = [q for q in user_quizzes if q.get('category_id') == pflicht_category_id]
        pflicht_checklists = [c for c in user_checklists if c.get('category_id') == pflicht_category_id]
        pflicht_feedbacks = [f for f in user_feedbacks if f.get('category_id') == pflicht_category_id]

        total_pflicht_activities = (
            len(pflicht_category.get('assignments', [])) +
            len(pflicht_category.get('quizzes', [])) +
            len(pflicht_category.get('checklists', [])) +
            len(pflicht_category.get('feedbacks', []))
        )

    # Alle Pflichtaktivitäten kombinieren
    all_pflicht_activities = pflicht_assignments + pflicht_quizzes + pflicht_checklists + pflicht_feedbacks

    # Bewertete und eingereichte Aktivitäten aus allen Pflichtaktivitäten
    reviewed_activities = [a for a in all_pflicht_activities if a.get('status', {}).get('status2') == "Bewertet"]
    submitted_activities = [a for a in all_pflicht_activities if a.get('status', {}).get('status') == "Zur Bewertung abgegeben"]

    reviewed_count = len(reviewed_activities)
    submitted_count = len(submitted_activities)

    user_data['assignments']['reviewed_count'] = reviewed_count
    user_data['assignments']['submitted_count'] = submitted_count
    user_data['assignments']['grades'] = {"Pflichtaufgaben": []}

    # Noten sammeln und Durchschnitt berechnen
    grades = []
    for activity in submitted_activities:
        activity_id = activity['id']
        details = assignment_details.get(activity_id, {})
        title = details.get('title', 'N/A')
        url = details.get('url', '#')
        grade_str = activity.get('status', {}).get('grade', 'Nicht bewertet')

        # Runde die Note für die Anzeige
        rounded_grade = round_grade(grade_str)

        user_data['assignments']['grades']["Pflichtaufgaben"].append({
            'title': title,
            'grade': rounded_grade,
            'url': url,
            'type': details.get('type', 'unknown')
        })

        # Konvertiere Note zu IHK-Format (unterstützt verschiedene Notenformate)
        ihk_grade = convert_grade_to_ihk(grade_str)
        if ihk_grade is not None:
            grades.append(ihk_grade)

    # IHK-konforme Durchschnittsnote berechnen
    if grades:
        user_data['assignments']['average_grade'] = calculate_ihk_grade_average(grades)

    # Prozentberechnung basierend auf Gesamtanzahl der Pflichtaufgaben
    user_data['assignments']['percent_submitted'] = round((submitted_count / total_pflicht_activities) * 100, 2) if total_pflicht_activities > 0 else 0

    # Referenzwoche-basierte Berechnung
    expected_pflicht_for_week = math.ceil((total_pflicht_activities / total_weeks) * current_week)
    user_data['assignments']['percent_submitted_timed'] = round((submitted_count / expected_pflicht_for_week) * 100, 2) if expected_pflicht_for_week > 0 else 0

    # --- Stundengewichteter Fortschritt (Quantität) ---
    # Eine 10-Stunden-Aufgabe wiegt fünfmal so viel wie ein 2-Stunden-Quiz.
    # Gezählte Aufgaben (oben) bleiben als Nebenangabe erhalten.
    if plan is not None:
        geplante = kurs['aufgaben'] if kurs else plan.get_alle_aufgaben()
        stunden_gesamt = sum(a['stunden'] for a in geplante)

        # "Abgegeben" zählt unabhängig von der Bewertung — wie im Schüler-Dashboard.
        erledigte_ids = set()
        for activity in all_pflicht_activities:
            status = activity.get('status', {}) or {}
            hat_abgabe = bool(status.get('submission_time'))
            hat_note = status.get('grade') not in (None, '', '-', 'Nicht bewertet',
                                                   'Nicht eingereicht', 'Keine Bewertung')
            if hat_abgabe or hat_note or status.get('status2') == 'Bewertet':
                erledigte_ids.add(str(activity.get('id', '')).strip())

        stunden_erledigt = sum(a['stunden'] for a in geplante if a['cmid'] in erledigte_ids)

        user_data['assignments']['stunden_gesamt'] = round(stunden_gesamt, 2)
        user_data['assignments']['stunden_erledigt'] = round(stunden_erledigt, 2)
        user_data['assignments']['percent_stunden'] = (
            round((stunden_erledigt / stunden_gesamt) * 100, 2) if stunden_gesamt > 0 else 0
        )
        user_data['assignments']['aufgaben_erledigt'] = len(erledigte_ids)
        user_data['assignments']['aufgaben_gesamt'] = len(geplante)

    # Checklisten verarbeiten - nur Pflicht-Checklisten (is_mandatory: true)
    checklists = user['activities'].get('checklists', [])
    mandatory_checklists = [c for c in checklists if c.get('is_mandatory', True)]  # Default: true für Abwärtskompatibilität
    total_mandatory_checklists = len(mandatory_checklists)

    # Nur Pflicht-Checklisten mit 100% zählen
    required_100 = [c for c in mandatory_checklists if c['progress']['required_progress'] == "100%"]
    user_data['checklists']['required_100_count'] = len(required_100)

    # Individuelle Checklisten-Details sammeln (alle, nicht nur Pflicht)
    for checklist in checklists:
        checklist_detail = {
            'id': checklist['id'],
            'title': checklist.get('title', 'Unbekannt'),
            'url': checklist.get('url', '#'),
            'required_progress': checklist['progress']['required_progress'],
            'all_progress': checklist['progress']['all_progress'],
            'is_mandatory': checklist.get('is_mandatory', True)
        }
        user_data['checklists']['individual_checklists'].append(checklist_detail)

    # Durchschnitte nur für Pflicht-Checklisten berechnen
    if total_mandatory_checklists > 0:
        user_data['checklists']['avg_required_progress'] = round(
            sum(float(c['progress']['required_progress'].strip('%')) for c in mandatory_checklists if c['progress']['required_progress']) / total_mandatory_checklists, 2)
        user_data['checklists']['avg_all_progress'] = round(
            sum(float(c['progress']['all_progress'].strip('%')) for c in mandatory_checklists if c['progress']['all_progress']) / total_mandatory_checklists, 2)
    else:
        user_data['checklists']['avg_required_progress'] = 0
        user_data['checklists']['avg_all_progress'] = 0

    # Zeitbasierte Fortschrittsprognose
    if current_week > 0:
        user_data['checklists']['avg_required_progress_timed'] = round((user_data['checklists']['avg_required_progress'] / current_week) * total_weeks, 2)
        user_data['checklists']['avg_all_progress_timed'] = round((user_data['checklists']['avg_all_progress'] / current_week) * total_weeks, 2)
    else:
        user_data['checklists']['avg_required_progress_timed'] = 0
        user_data['checklists']['avg_all_progress_timed'] = 0

    return user_data

def calculate_group_averages(users_data):
    """Berechnet die Gruppendurchschnitte"""
    if not users_data:
        return {
            "assignments": {
                "avg_percent_submitted": 0,
                "avg_percent_submitted_timed": 0,
                "avg_grade": None
            },
            "checklists": {
                "total_required_100": 0,
                "avg_required_progress": 0,
                "avg_all_progress": 0,
                "avg_required_progress_timed": 0,
                "avg_all_progress_timed": 0
            }
        }

    total_users = len(users_data)

    group_data = {
        "assignments": {
            "avg_percent_submitted": round(sum(user['assignments']['percent_submitted'] for user in users_data) / total_users, 2),
            "avg_percent_submitted_timed": round(sum(user['assignments']['percent_submitted_timed'] for user in users_data) / total_users, 2),
            "avg_grade": None
        },
        "checklists": {
            "total_required_100": sum(user['checklists']['required_100_count'] for user in users_data),
            "avg_required_progress": round(sum(user['checklists']['avg_required_progress'] for user in users_data) / total_users, 2),
            "avg_all_progress": round(sum(user['checklists']['avg_all_progress'] for user in users_data) / total_users, 2),
            "avg_required_progress_timed": 0,  # Wird unten berechnet
            "avg_all_progress_timed": 0        # Wird unten berechnet
        }
    }

    # IHK-konforme Durchschnittsnote berechnen
    grades = [user['assignments']['average_grade'] for user in users_data if user['assignments']['average_grade'] is not None]
    if grades:
        group_data['assignments']['avg_grade'] = calculate_ihk_grade_average(grades)

    # Die wochenbasierten Durchschnitte werden vom Frontend berechnet
    # Setze sie auf die gleichen Werte wie die normalen Durchschnitte
    # Das Frontend wird sie entsprechend der gewählten Woche anpassen
    group_data['checklists']['avg_required_progress_timed'] = group_data['checklists']['avg_required_progress']
    group_data['checklists']['avg_all_progress_timed'] = group_data['checklists']['avg_all_progress']

    return group_data

def count_school_days_since(submission_time_str, track_schedules, today=None):
    """
    Zählt vergangene Schularbeitstage seit submission_time_str anhand der TRACK_SCHEDULES.

    Args:
        submission_time_str: ISO-Datumsstring der Abgabe (z.B. "2025-12-10T14:30:00")
        track_schedules: Liste von {"week": N, "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
        today: Referenzdatum (datetime.date), Standard: heute

    Returns:
        int: Anzahl vergangener Schularbeitstage seit der Abgabe
    """
    import datetime
    if today is None:
        today = datetime.date.today()

    if not submission_time_str:
        return None

    try:
        sub_date = datetime.date.fromisoformat(submission_time_str[:10])
    except (ValueError, TypeError):
        return None

    school_days = 0
    for week in track_schedules:
        try:
            week_start = datetime.date.fromisoformat(week['start'])
            week_end = datetime.date.fromisoformat(week['end'])
        except (KeyError, ValueError):
            continue

        # Schulwoche muss ganz oder teilweise nach der Abgabe und bis heute liegen
        if week_end <= sub_date:
            continue
        if week_start > today:
            break

        # Zähle Tage in [max(week_start, sub_date+1), min(week_end, today)]
        count_from = max(week_start, sub_date + datetime.timedelta(days=1))
        count_to = min(week_end, today)

        if count_from > count_to:
            continue

        # Nur Werktage (Mo-Fr) zählen – Schulwochen sind Mon-Fr, aber sicherheitshalber prüfen
        current = count_from
        while current <= count_to:
            if current.weekday() < 5:  # 0=Mo, 4=Fr
                school_days += 1
            current += datetime.timedelta(days=1)

    return school_days


def build_recent_submissions(groups_data, raw_groups, manual_grade_item_ids,
                              mitarbeitsnote_config, recent_submission_days,
                              assignment_details=None, reference_date=None,
                              categories=None, inactive_threshold_days=14):
    """
    Aggregiert Abgaben je Gruppe für die "Letzte Abgaben"-Ansicht.

    Alle Zeitberechnungen erfolgen relativ zu reference_date (= Export-Datum),
    nicht zum aktuellen Datum.

    Args:
        groups_data:              Dict der verarbeiteten Gruppen.
        raw_groups:               Rohdaten-Gruppen aus dem Export-JSON.
        manual_grade_item_ids:    Mapping item_id -> Titel für manuelle Bewertungen.
        mitarbeitsnote_config:    Konfiguration mit class_to_track und track_schedules.
        recent_submission_days:   Zeitfenster in Kalendertagen für angezeigte Abgaben
                                  (RECENT_SUBMISSION_DAYS).
        assignment_details:       Dict mit Titelinformationen je Aktivitäts-ID.
        reference_date:           Referenzdatum (= Export-Datum) für alle Berechnungen.
        categories:               Aktivitätskategorien; wird genutzt um Pflichtaufgaben
                                  zu identifizieren.
        inactive_threshold_days:  Ab wie vielen Schultagen ohne Abgabe eine Gruppe als
                                  inaktiv gilt (INACTIVE_THRESHOLD_DAYS).

    Liefert pro Gruppe:
        recent_submissions:       Abgaben innerhalb der letzten recent_submission_days
                                  Kalendertage; jede Abgabe enthält school_days_ago
                                  (Schultage Mo-Fr, Ferien ausgeblendet) und
                                  calendar_days_ago (einfache Kalenderdifferenz).
        last_submission_*:        Letzte bekannte Abgabe (ggf. älter als Schwelle).
        school_days_since:        Schultage (Mo-Fr innerhalb der Schulwochen) seit der
                                  letzten bekannten Abgabe.
        calendar_days_since:      Kalendertage seit der letzten bekannten Abgabe.
        inactive:                 True wenn school_days_since > inactive_threshold_days.
        no_submissions:           True wenn die Gruppe überhaupt keine Abgaben hat.
    """
    import datetime

    class_to_track = (mitarbeitsnote_config or {}).get('class_to_track') or {}
    track_schedules_map = (mitarbeitsnote_config or {}).get('track_schedules') or {}
    ref_date = reference_date or datetime.date.today()
    details = assignment_details or {}

    raw_group_by_name = {g.get('name'): g for g in raw_groups}

    # Pflicht-Kategorie-ID ermitteln
    pflicht_cat_id = None
    if categories:
        for cat in categories:
            if 'Pflichtaufgaben' in cat.get('category_name', ''):
                pflicht_cat_id = cat.get('id')
                break

    def _school_days(submission_time_str, track_schedules):
        """Schularbeitstage (Mo–Fr) seit Abgabe innerhalb der Schulwochen, relativ zu ref_date."""
        if track_schedules:
            return count_school_days_since(submission_time_str, track_schedules, ref_date)
        return None  # Kein Fallback auf Schultage ohne Schedule

    def _calendar_days(submission_time_str):
        """Kalendertage seit Abgabe (einfache Differenz, unabhängig vom Schulplan)."""
        try:
            sub_date = datetime.date.fromisoformat(submission_time_str[:10])
            return (ref_date - sub_date).days
        except (ValueError, TypeError):
            return None

    def _title_for(act_id, act_obj):
        """Titel via assignment_details nachschlagen; Fallback auf Objekt-Feld."""
        t = details.get(str(act_id), {}).get('title')
        if t:
            return t
        return act_obj.get('title') or '?'

    result = {}

    for group_name in groups_data:
        # Zuerst exakten Namen probieren, dann Klassen-Prefix ("IFA12A - Team 1" → "IFA12A")
        track_name = class_to_track.get(group_name) or class_to_track.get(group_name.split(' ')[0])
        track_schedules = track_schedules_map.get(track_name, []) if track_name else []

        # Alle Abgaben dieser Gruppe sammeln
        all_submissions = []
        raw_group = raw_group_by_name.get(group_name, {})

        # Nutzer-Whitelist aus gefilterten groups_data (excluded_names bereits entfernt)
        valid_user_names = {u['name'] for u in groups_data.get(group_name, {}).get('users', [])}

        for user in raw_group.get('users', []):
            if valid_user_names and user.get('name') not in valid_user_names:
                continue
            activities = user.get('activities', {})

            for act in activities.get('assignments', []):
                status_obj = act.get('status', {})
                st = status_obj.get('submission_time')
                status_val = status_obj.get('status', 'Nicht eingereicht')
                if st and status_val != 'Nicht eingereicht':
                    act_id = act.get('id', '')
                    cat_id = act.get('category_id')
                    act_details = details.get(str(act_id), {})
                    grade_val = (status_obj.get('grade') or status_obj.get('rating') or status_obj.get('score') or '-')
                    all_submissions.append({
                        'time': st,
                        'title': _title_for(act_id, act),
                        '_key': str(act_id) if act_id else None,
                        '_status': status_val,
                        'is_pflicht': (pflicht_cat_id is not None and cat_id == pflicht_cat_id),
                        '_grade': grade_val,
                        'category_name': act_details.get('category_name', ''),
                        'url': act_details.get('url'),
                        'activity_type': 'assignment',
                    })

            for act in activities.get('quizzes', []):
                status_obj = act.get('status', {})
                st = status_obj.get('submission_time')
                status_val = status_obj.get('status', 'Nicht eingereicht')
                if st and status_val != 'Nicht eingereicht':
                    act_id = act.get('id', '')
                    cat_id = act.get('category_id')
                    act_details = details.get(str(act_id), {})
                    all_submissions.append({
                        'time': st,
                        'title': _title_for(act_id, act),
                        '_key': str(act_id) if act_id else None,
                        '_status': status_val,
                        'is_pflicht': (pflicht_cat_id is not None and cat_id == pflicht_cat_id),
                        '_grade': status_obj.get('grade', '-'),
                        'category_name': act_details.get('category_name', ''),
                        'url': act_details.get('url'),
                        'activity_type': 'quiz',
                    })

            for mg in activities.get('manual_grades', []):
                st = mg.get('submission_time')
                if st:
                    item_id = str(mg.get('item_id', ''))
                    title = manual_grade_item_ids.get(item_id, mg.get('title', 'Manuelle Bewertung'))
                    all_submissions.append({
                        'time': st,
                        'title': title,
                        '_key': f'mg_{item_id}' if item_id else None,
                        '_status': '',
                        'is_pflicht': False,
                        '_grade': mg.get('grade', '-'),
                        'category_name': 'Manuelle Bewertung',
                        'url': None,
                        'activity_type': 'manual',
                    })

        # Nach Zeit absteigend sortieren
        all_submissions.sort(key=lambda x: x['time'], reverse=True)

        # Deduplizieren: pro Aktivität neueste Abgabe behalten, Noten aller Schüler sammeln
        grades_by_key = {}
        statuses_by_key = {}
        first_by_key = {}
        key_order = []
        for sub in all_submissions:
            key = sub.get('_key') or sub['title']
            if key not in first_by_key:
                first_by_key[key] = sub
                key_order.append(key)
                grades_by_key[key] = []
                statuses_by_key[key] = []
            g = sub.get('_grade', '-')
            if g and g not in ('-', 'Nicht bewertet', 'Keine Bewertung', 'Nicht benotet'):
                grades_by_key[key].append(g)
            s = sub.get('_status', '')
            if s:
                statuses_by_key[key].append(s)

        deduped = []
        for key in key_order:
            sub = first_by_key[key]
            grades = grades_by_key[key]
            if not grades:
                grade_display = None
            elif len(set(grades)) == 1:
                grade_display = grades[0]
            else:
                numeric = [n for n in (convert_grade_to_ihk(g) for g in grades) if n is not None]
                if numeric:
                    grade_display = f'∅ {round(sum(numeric) / len(numeric), 1)}'
                else:
                    grade_display = grades[0]
            entry = {k: v for k, v in sub.items() if not k.startswith('_')}
            entry['grade_display'] = grade_display
            entry['is_bewertbar'] = 'Zur Bewertung abgegeben' in statuses_by_key.get(key, [])
            deduped.append(entry)
        all_submissions = deduped

        no_submissions = not all_submissions

        # Letzte bekannte Abgabe
        last = all_submissions[0] if all_submissions else None
        school_days_since = _school_days(last['time'], track_schedules) if last else None
        calendar_days_since = _calendar_days(last['time']) if last else None

        # Schwellenwert-Prüfung: Kalendertage (RECENT_SUBMISSION_DAYS)
        def _within_threshold(sub_time):
            cd = _calendar_days(sub_time)
            return cd is not None and cd <= recent_submission_days

        # Abgaben innerhalb des Zeitfensters
        recent_submissions = []
        for sub in all_submissions:
            sd = _school_days(sub['time'], track_schedules)
            cd = _calendar_days(sub['time'])
            if _within_threshold(sub['time']):
                recent_submissions.append({
                    **sub,
                    'school_days_ago': sd,
                    'calendar_days_ago': cd,
                })
            else:
                break  # Liste ist absteigend – ältere passen nie mehr

        # Inaktiv: keine Abgabe innerhalb von INACTIVE_THRESHOLD_DAYS Schultagen
        inactive = no_submissions or (school_days_since is None) or (school_days_since > inactive_threshold_days)

        result[group_name] = {
            'recent_submissions': recent_submissions,
            'group_id': raw_group.get('value'),
            'last_submission_time': last['time'] if last else None,
            'last_submission_title': last['title'] if last else None,
            'last_submission_grade': last.get('grade_display') if last else None,
            'last_submission_category': last.get('category_name') if last else None,
            'last_submission_url': last.get('url') if last else None,
            'last_submission_type': last.get('activity_type') if last else None,
            'last_submission_bewertbar': last.get('is_bewertbar', False) if last else False,
            'last_submission_is_pflicht': last.get('is_pflicht', False) if last else False,
            'school_days_since': school_days_since,
            'calendar_days_since': calendar_days_since,
            'inactive': inactive,
            'no_submissions': no_submissions,
        }

    return result


def create_structured_tables(groups_data, categories):
    """Erstellt strukturierte Daten für die Tabellen-Ansichten"""

    # Alle Checklisten aus den Kategorien sammeln
    all_checklists = []
    pflicht_assignments = []
    zentrale_assignments = []

    for category in categories:
        # Checklisten sammeln
        for checklist in category.get('checklists', []):
            all_checklists.append({
                'id': checklist['id'],
                'title': checklist['title'],
                'url': checklist.get('url', '#'),
                'category_name': category['category_name'],
                'is_mandatory': checklist.get('is_mandatory', False)
            })

        # Pflichtaufgaben sammeln (nur aus Pflichtaufgaben-Kategorie)
        if category['category_name'] == "🎯Pflichtaufgaben":
            for assignment in category.get('assignments', []):
                pflicht_assignments.append({
                    'id': assignment['id'],
                    'title': assignment['title'],
                    'url': assignment.get('url', '#'),
                    'type': 'assignment'
                })
            for quiz in category.get('quizzes', []):
                pflicht_assignments.append({
                    'id': quiz['id'],
                    'title': quiz['title'],
                    'url': quiz.get('url', '#'),
                    'type': 'quiz'
                })

        # Zentrale Leistungsnachweise sammeln (alle Kategorien mit "Zentrale Leistungsnachweise" im Namen)
        if category['category_name'] and ('Zentrale Leistungsnachweise' in category['category_name'] or 'chart' in category['category_name'].lower()):
            try:
                backend_logger.info(f"Found Zentrale Leistungsnachweise category with {len(category.get('assignments', []))} assignments and {len(category.get('quizzes', []))} quizzes")
            except Exception:
                backend_logger.info("Found Zentrale Leistungsnachweise category")
            for assignment in category.get('assignments', []):
                zentrale_assignments.append({
                    'id': assignment['id'],
                    'title': assignment['title'],
                    'url': assignment.get('url', '#'),
                    'type': 'assignment'
                })
            for quiz in category.get('quizzes', []):
                zentrale_assignments.append({
                    'id': quiz['id'],
                    'title': quiz['title'],
                    'url': quiz.get('url', '#'),
                    'type': 'quiz'
                })

    backend_logger.info(f"Total Zentrale Leistungsnachweise found: {len(zentrale_assignments)}")

    # Sortiere Pflichtaufgaben alphabetisch nach Titel
    pflicht_assignments.sort(key=lambda x: x['title'])

    # Sortiere Zentrale Leistungsnachweise alphabetisch nach Titel
    zentrale_assignments.sort(key=lambda x: x['title'])

    # Strukturierte Tabellen für jede Gruppe erstellen
    structured_tables = {}

    for group_name, group_data in groups_data.items():
        users = group_data['users']

        # Checklisten-Tabelle: Zeilen = Checklisten, Spalten = Benutzer
        checklist_table = {
            'headers': ['Checkliste'] + [user['name'] for user in users],
            'rows': []
        }

        for checklist in all_checklists:
            row = {
                'checklist_id': checklist['id'],
                'checklist_title': checklist['title'],
                'checklist_url': checklist['url'],
                'checklist_category': checklist['category_name'],
                'is_mandatory': checklist.get('is_mandatory', False),
                'user_progress': []
            }

            for user in users:
                # Finde den Fortschritt dieser Checkliste für diesen Benutzer
                progress = find_user_checklist_progress(user, checklist['id'])
                row['user_progress'].append(progress)

            checklist_table['rows'].append(row)

        # Pflichtaufgaben-Tabelle: Zeilen = Aufgaben, Spalten = Benutzer
        pflicht_table = {
            'headers': ['Aufgabe'] + [user['name'] for user in users],
            'rows': []
        }

        for assignment in pflicht_assignments:
            row = {
                'assignment_id': assignment['id'],
                'assignment_title': assignment['title'],
                'assignment_url': assignment['url'],
                'assignment_type': assignment['type'],
                'user_status': []
            }

            for user in users:
                # Finde den Status dieser Aufgabe für diesen Benutzer
                status = find_user_assignment_status(user, assignment['id'])
                # Füge user_name hinzu für Frontend-Kompatibilität
                status['user_name'] = user.get('name', 'Unknown')
                row['user_status'].append(status)

            pflicht_table['rows'].append(row)

        # Zentrale Leistungsnachweise-Tabelle: Zeilen = Aufgaben, Spalten = Benutzer
        zentrale_table = {
            'headers': ['Aufgabe'] + [user['name'] for user in users],
            'rows': []
        }

        for assignment in zentrale_assignments:
            row = {
                'assignment_id': assignment['id'],
                'assignment_title': assignment['title'],
                'assignment_url': assignment['url'],
                'assignment_type': assignment['type'],
                'user_status': []
            }

            for user in users:
                # Finde den Status dieser Aufgabe für diesen Benutzer
                status = find_user_assignment_status(user, assignment['id'])
                # Füge user_name hinzu für Frontend-Kompatibilität
                status['user_name'] = user.get('name', 'Unknown')
                backend_logger.debug(f"Added user_name '{status['user_name']}' to status: {status}")
                row['user_status'].append(status)

            zentrale_table['rows'].append(row)

        structured_tables[group_name] = {
            'checklists': checklist_table,
            'pflichtaufgaben': pflicht_table,
            'zentrale_leistungsnachweise': zentrale_table
        }

    return structured_tables

@app.route('/api/debug/excluded-names')
def debug_excluded_names():
    """Debug-Endpoint um ausgeschlossene Namen anzuzeigen"""
    logger = api_logger
    logger.info("API endpoint /api/debug/excluded-names called")

    try:
        excluded_names = load_excluded_names()
        return jsonify({
            'count': len(excluded_names),
            'names': sorted(list(excluded_names)),
            'file_path': 'config/exclude_names.txt'
        })
    except Exception as e:
        logger.error(f"Error loading excluded names: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/groups')
def get_groups():
    """API-Endpoint nur für Gruppen-Liste"""
    logger = api_logger
    logger.info("API endpoint /api/groups called")

    try:
        latest_file = find_latest_file()
        if not latest_file:
            return jsonify({'error': 'Keine Export-Datei gefunden'}), 404

        data = load_json_data(latest_file)
        if not data:
            return jsonify({'error': 'Fehler beim Laden der Daten'}), 500

        excluded_names = load_excluded_names()
        ignored_groups = load_ignored_groups()

        groups = []
        for group in data.get('groups', []):
            group_name = group.get('name', 'Unknown')

            if group_name not in ignored_groups:
                group_users = [user for user in group.get('users', [])
                              if user.get('name') not in excluded_names]
                if group_users:  # Nur Gruppen mit Benutzern
                    groups.append({
                        'name': group_name,
                        'user_count': len(group_users)
                    })

        logger.info(f"Returned {len(groups)} groups")
        return jsonify({'groups': groups})

    except Exception as e:
        logger.error(f"Error in get_groups: {e}")
        return jsonify({'error': str(e)}), 500

# Globale Variable für Export-Status
export_status = {
    'running': False,
    'progress': 0,
    'message': '',
    'error': None,
    'details': {
        'assignments': {'current': 0, 'total': 0},
        'checklists': {'current': 0, 'total': 0},
        'quizzes': {'current': 0, 'total': 0}
    },
    'start_time': None,
    'estimated_time_remaining': None
}

def run_export_script():
    """Führt src/export/exporter.py als Hintergrundprozess aus"""
    global export_status
    logger = api_logger

    try:
        logger.info("run_export_script() called")
        export_status['running'] = True
        export_status['progress'] = 0
        export_status['message'] = 'Export wird gestartet...'
        export_status['error'] = None
        export_status['start_time'] = time_module.time()
        export_status['details'] = {
            'assignments': {'current': 0, 'total': 0},
            'checklists': {'current': 0, 'total': 0},
            'quizzes': {'current': 0, 'total': 0}
        }

        logger.info("Status initialized, starting export script...")

        # Führe exporter.py aus (verschoben nach src/export/)
        import sys
        script_path = os.path.join(os.path.dirname(__file__), '..', 'export', 'exporter.py')
        script_path = os.path.abspath(script_path)  # Konvertiere zu absolutem Pfad
        logger.info(f"Script path: {script_path}")
        logger.info(f"Python executable: {sys.executable}")

        if not os.path.exists(script_path):
            raise FileNotFoundError(f"exporter.py not found at {script_path}")

        logger.info("Creating subprocess...")
        process = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        logger.info(f"Subprocess created with PID: {process.pid}")

        # Lese Output
        for line in process.stdout:
            line = line.strip()
            if line:
                logger.info(f"Export: {line}")

                # Parse PROGRESS Meldungen: PROGRESS|type|current|total
                if line.startswith('PROGRESS|'):
                    try:
                        parts = line.split('|')
                        activity_type = parts[1]
                        current = int(parts[2])
                        total = int(parts[3])

                        export_status['details'][activity_type] = {
                            'current': current,
                            'total': total
                        }

                        # Berechne Gesamtfortschritt
                        total_items = sum(d['total'] for d in export_status['details'].values())
                        completed_items = sum(d['current'] for d in export_status['details'].values())

                        if total_items > 0:
                            export_status['progress'] = int((completed_items / total_items) * 85)  # 0-85%

                        # Berechne geschätzte verbleibende Zeit
                        if completed_items > 0:
                            elapsed_time = time_module.time() - export_status['start_time']
                            avg_time_per_item = elapsed_time / completed_items
                            remaining_items = total_items - completed_items
                            estimated_remaining = avg_time_per_item * remaining_items
                            export_status['estimated_time_remaining'] = int(estimated_remaining)

                        # Aktualisiere Nachricht
                        export_status['message'] = f"Verarbeite {activity_type}: {current}/{total}"

                    except (IndexError, ValueError) as e:
                        logger.warning(f"Failed to parse progress line: {line} - {e}")
                else:
                    # Normale Nachricht
                    export_status['message'] = line

                # Spezielle Status-Nachrichten
                if 'Speichere Daten' in line:
                    export_status['progress'] = 90
                    export_status['message'] = 'Speichere Daten...'
                elif 'EXPORT ABGESCHLOSSEN' in line:
                    export_status['progress'] = 100
                    export_status['estimated_time_remaining'] = 0

        # Warte auf Prozessende
        return_code = process.wait()

        if return_code == 0:
            export_status['running'] = False
            export_status['progress'] = 100
            export_status['message'] = 'Export erfolgreich abgeschlossen'
            logger.info("Export completed successfully")
        else:
            # Lese stderr für detaillierte Fehlermeldung
            stderr_output = process.stderr.read()
            export_status['running'] = False

            # Unterscheide zwischen Validierungsfehlern und anderen Fehlern
            if "VALIDIERUNGSFEHLER" in export_status.get('message', ''):
                export_status['error'] = "Export abgebrochen: Validierungsfehler (siehe Log)"
            elif "NEUER EXPORT IST KLEINER" in export_status.get('message', ''):
                export_status['error'] = "Export abgelehnt: Neuer Export wäre kleiner als vorheriger"
            else:
                export_status['error'] = f"Export fehlgeschlagen: {stderr_output[:200]}" if stderr_output else "Export fehlgeschlagen (unbekannter Fehler)"

            logger.error(f"Export failed with return code {return_code}: {stderr_output}")

    except Exception as e:
        export_status['running'] = False
        export_status['error'] = str(e)
        logger.error(f"Error running export: {e}")

@app.route('/api/export/start', methods=['POST'])
def start_export():
    """Startet den Datenexport"""
    logger = api_logger

    try:
        logger.info("Export start request received")

        if export_status['running']:
            logger.warning("Export already running")
            return jsonify({
                'success': False,
                'message': 'Export läuft bereits'
            }), 409

        # Starte Export in separatem Thread
        logger.info("Starting export thread...")
        export_thread = threading.Thread(target=run_export_script)
        export_thread.daemon = True
        export_thread.start()

        logger.info("Export thread started successfully")

        return jsonify({
            'success': True,
            'message': 'Export wurde gestartet'
        })

    except Exception as e:
        logger.error(f"Error starting export: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/export/status')
def get_export_status():
    """Gibt den aktuellen Export-Status zurück"""
    return jsonify(export_status)

@app.route('/api/generate-review-pdf', methods=['POST'])
def generate_review_pdf():
    """Generiert ein Code-Review PDF"""
    logger = api_logger
    logger.info("PDF generation request received")

    try:
        # Hole Daten aus Request
        data = request.get_json()

        if not data:
            logger.error("No data provided in request")
            return jsonify({'error': 'Keine Daten übermittelt'}), 400

        logger.info(f"Generating PDF for group: {data.get('group')}, Review-Nr: {data.get('reviewNr')}")

        # Erstelle PDF Generator
        generator = ReviewPDFGeneratorMulti()

        # Generiere PDF(s) - Generator gibt jetzt immer einen einzelnen PDF-Pfad zurück (merged bei Multi-Group)
        pdf_path = generator.generate_pdf(data)
        if not pdf_path or not isinstance(pdf_path, str) or not os.path.exists(pdf_path):
            logger.error("PDF generation failed - no file created")
            return jsonify({'error': 'PDF-Generierung fehlgeschlagen'}), 500

        logger.info(f"PDF generated successfully: {pdf_path}")

        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"Code_Review_{data.get('group', 'Unknown')}_Review{data.get('reviewNr', '1')}.pdf",
            mimetype='application/pdf'
        )

    except FileNotFoundError as e:
        logger.error(f"Template file not found: {e}")
        return jsonify({'error': f'Vorlage nicht gefunden: {str(e)}'}), 404
    except Exception as e:
        logger.error(f"Error generating PDF: {e}", exc_info=True)
        return jsonify({'error': f'Fehler bei der PDF-Generierung: {str(e)}'}), 500

if __name__ == '__main__':
    flask_config = config_manager.get_flask_config()
    backend_logger.info("Starting Mebis Dashboard Backend")
    backend_logger.info(f"Dashboard available at: http://{flask_config['host']}:{flask_config['port']}")

    app.run(
        debug=flask_config['debug'],
        host=flask_config['host'],
        port=flask_config['port']
    )