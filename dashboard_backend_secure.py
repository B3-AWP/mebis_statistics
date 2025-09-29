#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mebis Statistik Dashboard - Sicheres Backend
Refactored Version mit professionellem Logging und Environment Variables Support
"""

import os
import json
import glob
import math
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

# Sichere Konfiguration und Logging
from config_manager import config_manager
from logger_config import get_logger, backend_logger, api_logger, data_logger

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

def find_latest_file(directory='export'):
    """
    Findet die neueste JSON-Datei im Export-Ordner

    Args:
        directory: Verzeichnis zum Durchsuchen

    Returns:
        str: Pfad zur neuesten Datei oder None
    """
    logger = data_logger

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

def load_excluded_names(file_path='exclude_names.txt'):
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

        # Response erstellen
        response_data = {
            'groups': groups_data,
            'overall_stats': overall_stats,
            'assignment_details': assignment_details,
            'activities_by_category': data.get('activities_by_category', []),
            'structured_tables': structured_data,
            'ignored_groups': list(ignored_groups),
            'last_updated': latest_file
        }

        logger.info(f"API response created successfully with {len(groups_data)} groups")
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

# Platzhalter für komplexe Funktionen (werden in Phase 2 modularisiert)
def calculate_user_progress(user, assignment_details, categories, current_week, total_weeks):
    """Platzhalter - wird in Phase 2 modularisiert"""
    # Vereinfachte Version für jetzt
    return create_fallback_user(user, user.get('group', 'Unknown'))

def calculate_group_averages(users_data):
    """Platzhalter - wird in Phase 2 modularisiert"""
    return {
        "assignments": {"avg_percent_submitted": 0, "avg_percent_submitted_timed": 0, "avg_grade": None},
        "checklists": {"total_required_100": 0, "avg_required_progress": 0, "avg_all_progress": 0}
    }

def create_structured_tables(groups_data, categories):
    """Platzhalter - wird in Phase 2 modularisiert"""
    return {}

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

if __name__ == '__main__':
    flask_config = config_manager.get_flask_config()
    backend_logger.info("Starting Mebis Dashboard Backend (Secure Version)")
    backend_logger.info(f"Dashboard available at: http://{flask_config['host']}:{flask_config['port']}")

    app.run(
        debug=flask_config['debug'],
        host=flask_config['host'],
        port=flask_config['port']
    )