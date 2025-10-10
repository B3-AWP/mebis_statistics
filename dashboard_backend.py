#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mebis Statistik Dashboard - Backend
Version mit professionellem Logging und Environment Variables Support
"""

import os
import json
import glob
import math
import subprocess
import threading
import time as time_module
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

# Sichere Konfiguration und Logging
from config.config_manager import config_manager
from config.logger_config import get_logger, backend_logger, api_logger, data_logger

# Flask App Setup mit sicherer Konfiguration
app = Flask(__name__, static_folder='.')
CORS(app)

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

        if isinstance(data, dict):
            logger.info(f"JSON file loaded successfully. Keys: {list(data.keys())}")
        else:
            logger.warning("Loaded JSON is not a dictionary")

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
        with open(file_path, 'r', encoding='utf-8') as file:
            excluded_names = {line.strip() for line in file.readlines() if line.strip()}

        logger.info(f"Loaded {len(excluded_names)} excluded names from {file_path}")
        return excluded_names

    except FileNotFoundError:
        logger.info(f"No excluded names file found at {file_path}")
        return set()
    except Exception as e:
        logger.error(f"Error loading excluded names from {file_path}: {e}")
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
                'grade': rounded_grade
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
                'grade': rounded_grade
            }
            logger.debug(f"QUIZ MATCH! {user.get('name')} - Quiz {assignment_id}: {result}")
            return result

    # Wenn nicht gefunden
    result = {
        'status': 'Nicht eingereicht',
        'status2': '',
        'grade': '-'
    }
    logger.debug(f"NOT FOUND! {user.get('name')} - Assignment {assignment_id}: {result}")
    return result

# API Endpoints
@app.route('/')
def index():
    """Serviert die Dashboard HTML-Datei"""
    return send_from_directory('.', 'dashboard.html')

@app.route('/<path:filename>')
def static_files(filename):
    """Serviert statische Dateien"""
    return send_from_directory('.', filename)

@app.route('/api/data')
def get_data():
    """
    API-Endpoint für Dashboard-Daten mit professionellem Error-Handling
    """
    logger = api_logger
    logger.info("API endpoint /api/data called")

    try:
        # Neueste JSON-Datei finden
        latest_file = find_latest_file()
        if not latest_file:
            logger.error("No export file found")
            return jsonify({'error': 'Keine Export-Datei gefunden'}), 404

        # Daten laden
        data = load_json_data(latest_file)
        if not data:
            logger.error("Failed to load JSON data")
            return jsonify({'error': 'Fehler beim Laden der Daten'}), 500

        # Hilfsdaten laden
        excluded_names = load_excluded_names()
        ignored_groups = load_ignored_groups()

        # Grade Mapping laden
        try:
            grade_mapping = config_manager.get_grade_mapping()
            logger.info(f"Grade mapping loaded: {len(grade_mapping)} entries - {grade_mapping}")
        except Exception as e:
            logger.error(f"Error loading grade_mapping: {e}")
            grade_mapping = {}

        # Assignment Details erstellen
        assignment_details = get_assignment_details(data.get('activities_by_category', []))

        # Benutzer nach Gruppen organisieren
        groups_data = {}

        for group in data.get('groups', []):
            group_name = group.get('name', 'Unknown')

            # Überspringe ignorierte Gruppen
            if group_name in ignored_groups:
                logger.debug(f"Skipping ignored group: {group_name}")
                continue

            group_users = [user for user in group.get('users', [])
                          if user.get('name') not in excluded_names]

            if group_users:  # Nur Gruppen mit Benutzern
                groups_data[group_name] = {
                    'name': group_name,
                    'users': []
                }

                for user in group_users:
                    try:
                        # Setze die Gruppe für jeden Benutzer
                        user['group'] = group_name
                        user_progress = calculate_user_progress(
                            user, assignment_details, data.get('activities_by_category', []), 10, 40
                        )
                        groups_data[group_name]['users'].append(user_progress)
                    except Exception as e:
                        logger.warning(f"Error processing user {user.get('name', 'Unknown')}: {e}")
                        # Füge einen Fallback-Benutzer hinzu
                        groups_data[group_name]['users'].append(create_fallback_user(user, group_name))

        # Statistiken berechnen
        for group_name, group_data in groups_data.items():
            group_stats = calculate_group_averages(group_data['users'])
            group_data.update(group_stats)

        # Gesamtstatistiken
        all_users = []
        for group_data in groups_data.values():
            all_users.extend(group_data['users'])
        overall_stats = calculate_group_averages(all_users)

        # Strukturierte Daten für Tabellen erstellen
        structured_data = create_structured_tables(groups_data, data.get('activities_by_category', []))

        # Debug: Prüfe zentrale Leistungsnachweise in jeder Gruppe
        for group_name, group_data in structured_data.items():
            zentral_data = group_data.get('zentrale_leistungsnachweise', {})
            zentral_rows = zentral_data.get('rows', [])
            logger.debug(f"Group '{group_name}' has {len(zentral_rows)} zentrale Leistungsnachweise")

        # Reorder activities_by_category to put "Pflichtaufgaben" first
        activities_ordered = []
        pflichtaufgaben_category = None
        other_categories = []

        for category in data.get('activities_by_category', []):
            if 'Pflichtaufgaben' in category.get('category_name', ''):
                pflichtaufgaben_category = category
            else:
                other_categories.append(category)

        if pflichtaufgaben_category:
            activities_ordered = [pflichtaufgaben_category] + other_categories
        else:
            activities_ordered = data.get('activities_by_category', [])

        # Add user_status to activities for frontend
        def add_user_status_to_activities(activities, data, groups_data):
            for category in activities:
                # Add user_status to assignments
                for assignment in category.get('assignments', []):
                    assignment['user_status'] = []
                    assignment_id = assignment.get('id')

                    # Find user grades for this assignment from original JSON data
                    for group in data.get('groups', []):
                        group_name = group.get('name', '')
                        # Skip users from ignored groups
                        if group_name in ignored_groups:
                            continue

                        group_users = group.get('users', [])
                        for user in group_users:
                            status = find_user_assignment_status(user, assignment_id)
                            assignment['user_status'].append({
                                'user_name': user.get('name', ''),
                                'user_id': user.get('id', ''),
                                'status': status.get('status', 'Nicht eingereicht'),
                                'grade': status.get('grade', '-')
                            })

                # Add user_status to quizzes
                for quiz in category.get('quizzes', []):
                    quiz['user_status'] = []
                    quiz_id = quiz.get('id')

                    # Find user grades for this quiz from original JSON data
                    for group in data.get('groups', []):
                        group_name = group.get('name', '')
                        # Skip users from ignored groups
                        if group_name in ignored_groups:
                            continue

                        group_users = group.get('users', [])
                        for user in group_users:
                            status = find_user_assignment_status(user, quiz_id)
                            quiz['user_status'].append({
                                'user_name': user.get('name', ''),
                                'user_id': user.get('id', ''),
                                'status': status.get('status', 'Nicht eingereicht'),
                                'grade': status.get('grade', '-')
                            })
            return activities

        activities_with_status = add_user_status_to_activities(activities_ordered, data, groups_data)

        # Environment-Settings für Frontend
        flask_config = config_manager.get_flask_config()
        environment_settings = {
            'mode': flask_config['env'],
            'debug': flask_config['debug']
        }

        # Response erstellen
        response_data = {
            'groups': groups_data,
            'overall_stats': overall_stats,
            'assignment_details': assignment_details,
            'categories': activities_with_status,
            'activities_by_category': activities_with_status,  # Korrekte Frontend-Erwartung
            'structured_tables': structured_data,
            'ignored_groups': list(ignored_groups),
            'grade_mapping': grade_mapping,
            'last_updated': latest_file,
            'environment': environment_settings
        }

        logger.info(f"API response created successfully with {len(groups_data)} groups")

        # JSON-Serialization test
        import json
        json_test = json.dumps(response_data, default=str, ensure_ascii=False)
        logger.debug(f"JSON serialization successful, size: {len(json_test)} characters")

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Unexpected error in get_data: {e}", exc_info=True)
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

def calculate_user_progress(user, assignment_details, categories, current_week, total_weeks):
    """Berechnet den Fortschritt eines Benutzers"""
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
        }
    }

    # Nur Pflichtaufgaben berücksichtigen
    pflicht_categories = [c for c in categories if c['category_name'] == "🎯Pflichtaufgaben"]

    if not pflicht_categories:
        return user_data

    pflicht_category = pflicht_categories[0]
    pflicht_category_id = pflicht_category['id']

    # Alle Pflichtaufgaben des Benutzers sammeln
    user_assignments = user['activities'].get('assignments', [])
    user_quizzes = user['activities'].get('quizzes', [])
    user_checklists = user['activities'].get('checklists', [])
    user_feedbacks = user['activities'].get('feedbacks', [])

    pflicht_assignments = [a for a in user_assignments if a.get('category_id') == pflicht_category_id]
    pflicht_quizzes = [q for q in user_quizzes if q.get('category_id') == pflicht_category_id]
    pflicht_checklists = [c for c in user_checklists if c.get('category_id') == pflicht_category_id]
    pflicht_feedbacks = [f for f in user_feedbacks if f.get('category_id') == pflicht_category_id]

    # Alle Pflichtaktivitäten kombinieren
    all_pflicht_activities = pflicht_assignments + pflicht_quizzes + pflicht_checklists + pflicht_feedbacks

    # Gesamtanzahl aller Pflichtaufgaben in der Kategorie berechnen
    total_pflicht_activities = (
        len(pflicht_category.get('assignments', [])) +
        len(pflicht_category.get('quizzes', [])) +
        len(pflicht_category.get('checklists', [])) +
        len(pflicht_category.get('feedbacks', []))
    )

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

    # Checklisten verarbeiten
    checklists = user['activities'].get('checklists', [])
    total_checklists = len(checklists)

    required_100 = [c for c in checklists if c['progress']['required_progress'] == "100%"]
    user_data['checklists']['required_100_count'] = len(required_100)

    # Individuelle Checklisten-Details sammeln
    for checklist in checklists:
        checklist_detail = {
            'id': checklist['id'],
            'title': checklist.get('title', 'Unbekannt'),
            'url': checklist.get('url', '#'),
            'required_progress': checklist['progress']['required_progress'],
            'all_progress': checklist['progress']['all_progress']
        }
        user_data['checklists']['individual_checklists'].append(checklist_detail)

    if total_checklists > 0:
        user_data['checklists']['avg_required_progress'] = round(
            sum(float(c['progress']['required_progress'].strip('%')) for c in checklists if c['progress']['required_progress']) / total_checklists, 2)
        user_data['checklists']['avg_all_progress'] = round(
            sum(float(c['progress']['all_progress'].strip('%')) for c in checklists if c['progress']['all_progress']) / total_checklists, 2)
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
    """Führt exportData.py als Hintergrundprozess aus"""
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

        # Führe exportData.py aus
        import sys
        script_path = os.path.join(os.path.dirname(__file__), 'exportData.py')
        logger.info(f"Script path: {script_path}")
        logger.info(f"Python executable: {sys.executable}")

        if not os.path.exists(script_path):
            raise FileNotFoundError(f"exportData.py not found at {script_path}")

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
            stderr_output = process.stderr.read()
            export_status['running'] = False
            export_status['error'] = f"Export fehlgeschlagen: {stderr_output}"
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

if __name__ == '__main__':
    flask_config = config_manager.get_flask_config()
    backend_logger.info("Starting Mebis Dashboard Backend")
    backend_logger.info(f"Dashboard available at: http://{flask_config['host']}:{flask_config['port']}")

    app.run(
        debug=flask_config['debug'],
        host=flask_config['host'],
        port=flask_config['port']
    )