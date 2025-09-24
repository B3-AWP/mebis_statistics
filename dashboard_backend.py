#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import glob
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import math

app = Flask(__name__, static_folder='.')
CORS(app)

def find_latest_file(directory='export'):
    """Findet die neueste JSON-Datei im Export-Ordner"""
    pattern = os.path.join(directory, 'output_*.json')
    files = glob.glob(pattern)
    if not files:
        return None
    latest_file = max(files, key=os.path.getctime)
    return latest_file

def load_json_data(file_path):
    """Lädt JSON-Daten aus einer Datei"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return data
    except Exception as e:
        print(f"Error loading JSON data: {e}")
        return None

def load_excluded_names(file_path='exclude_names.txt'):
    """Lädt die Liste der ausgeschlossenen Namen"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            excluded_names = {line.strip() for line in file.readlines()}
        return excluded_names
    except FileNotFoundError:
        return set()
    except Exception as e:
        print(f"Error loading excluded names: {e}")
        return set()

def get_assignment_details(assignments_by_category):
    """Erstellt ein Dictionary mit Assignment-Details"""
    assignment_details = {}
    for category in assignments_by_category:
        # Assignments hinzufügen
        for assignment in category.get('assignments', []):
            assignment_details[assignment['id']] = {
                'title': assignment['title'],
                'url': assignment['url'],
                'category_name': category['category_name'],
                'type': 'assignment'
            }

        # Quizzes hinzufügen
        for quiz in category.get('quizzes', []):
            assignment_details[quiz['id']] = {
                'title': quiz['title'],
                'url': quiz['url'],
                'category_name': category['category_name'],
                'type': 'quiz'
            }

        # Checklists hinzufügen
        for checklist in category.get('checklists', []):
            assignment_details[checklist['id']] = {
                'title': checklist['title'],
                'url': checklist['url'],
                'category_name': category['category_name'],
                'type': 'checklist'
            }

        # Feedbacks hinzufügen
        for feedback in category.get('feedbacks', []):
            assignment_details[feedback['id']] = {
                'title': feedback['title'],
                'url': feedback['url'],
                'category_name': category['category_name'],
                'type': 'feedback'
            }
    return assignment_details

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

        user_data['assignments']['grades']["Pflichtaufgaben"].append({
            'title': title,
            'grade': grade_str,
            'url': url,
            'type': details.get('type', 'unknown')
        })

        # Versuche Note zu extrahieren (z.B. "1,5" oder "2")
        try:
            if grade_str and grade_str != 'Nicht bewertet':
                grade_clean = grade_str.replace(',', '.')
                grade_num = float(grade_clean)
                if 1 <= grade_num <= 6:  # Deutsche Notenskala
                    grades.append(grade_num)
        except:
            pass

    # Durchschnittsnote berechnen
    if grades:
        user_data['assignments']['average_grade'] = round(sum(grades) / len(grades), 2)

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
            "avg_required_progress_timed": round(sum(user['checklists']['avg_required_progress_timed'] for user in users_data) / total_users, 2),
            "avg_all_progress_timed": round(sum(user['checklists']['avg_all_progress_timed'] for user in users_data) / total_users, 2)
        }
    }

    # Durchschnittsnote berechnen
    grades = [user['assignments']['average_grade'] for user in users_data if user['assignments']['average_grade'] is not None]
    if grades:
        group_data['assignments']['avg_grade'] = round(sum(grades) / len(grades), 2)

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
                'category_name': category['category_name']
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

        # Zentrale Leistungsnachweise sammeln (nur aus Zentrale Leistungsnachweise-Kategorie)
        if category['category_name'] == "📊 Zentrale Leistungsnachweise":
            print(f"DEBUG: Gefunden Zentrale Leistungsnachweise Kategorie mit {len(category.get('assignments', []))} assignments und {len(category.get('quizzes', []))} quizzes")
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

    print(f"DEBUG: Zentrale Leistungsnachweise insgesamt gefunden: {len(zentrale_assignments)}")

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
                row['user_status'].append(status)

            zentrale_table['rows'].append(row)

        structured_tables[group_name] = {
            'checklists': checklist_table,
            'pflichtaufgaben': pflicht_table,
            'zentrale_leistungsnachweise': zentrale_table
        }

    return structured_tables

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
    # Suche in den User-Aktivitäten (assignments und quizzes)
    activities = user.get('activities', {})

    # Suche in assignments
    for assignment in activities.get('assignments', []):
        if assignment.get('id') == assignment_id:
            status_info = assignment.get('status', {})
            return {
                'status': status_info.get('status', 'Nicht eingereicht'),
                'status2': status_info.get('status2', ''),
                'grade': status_info.get('grade', '-')
            }

    # Suche in quizzes
    for quiz in activities.get('quizzes', []):
        if quiz.get('id') == assignment_id:
            status_info = quiz.get('status', {})
            return {
                'status': status_info.get('status', 'Nicht eingereicht'),
                'status2': status_info.get('status2', ''),
                'grade': status_info.get('grade', '-')
            }

    # Wenn nicht gefunden
    return {
        'status': 'Nicht eingereicht',
        'status2': '',
        'grade': '-'
    }

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
    """API-Endpoint für Dashboard-Daten"""
    print("DEBUG API: API-Endpoint /api/data aufgerufen!")
    try:
        # Neueste JSON-Datei finden
        latest_file = find_latest_file()
        if not latest_file:
            return jsonify({'error': 'Keine Export-Datei gefunden'}), 404

        # Daten laden
        data = load_json_data(latest_file)
        if not data:
            return jsonify({'error': 'Fehler beim Laden der Daten'}), 500

        excluded_names = load_excluded_names()
        assignment_details = get_assignment_details(data['activities_by_category'])

        # Benutzer nach Gruppen organisieren
        groups_data = {}
        for group in data['groups']:
            group_name = group['name']
            group_users = [user for user in group['users'] if user['name'] not in excluded_names]

            if group_users:  # Nur Gruppen mit Benutzern
                groups_data[group_name] = {
                    'name': group_name,
                    'users': []
                }

                for user in group_users:
                    # Setze die Gruppe für jeden Benutzer
                    user['group'] = group_name
                    user_progress = calculate_user_progress(
                        user, assignment_details, data['activities_by_category'], 10, 40
                    )
                    groups_data[group_name]['users'].append(user_progress)

        # Gesamtstatistiken für alle Gruppen
        all_users = []
        for group_data in groups_data.values():
            all_users.extend(group_data['users'])

        overall_stats = calculate_group_averages(all_users)

        # Strukturierte Daten für Tabellen erstellen
        print(f"DEBUG API: Erstelle strukturierte Tabellen für {len(groups_data)} Gruppen und {len(data['activities_by_category'])} Kategorien")
        structured_data = create_structured_tables(groups_data, data['activities_by_category'])
        print(f"DEBUG API: Strukturierte Tabellen erstellt: {list(structured_data.keys())}")

        # Debug: Prüfe zentrale Leistungsnachweise in jeder Gruppe
        for group_name, group_data in structured_data.items():
            zentral_data = group_data.get('zentrale_leistungsnachweise', {})
            zentral_rows = zentral_data.get('rows', [])
            print(f"DEBUG API: Gruppe '{group_name}' hat {len(zentral_rows)} zentrale Leistungsnachweise")

        response_data = {
            'groups': groups_data,
            'overall_stats': overall_stats,
            'assignment_details': assignment_details,
            'categories': data['activities_by_category'],
            'structured_tables': structured_data,
            'last_updated': latest_file
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"Error in get_data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/groups')
def get_groups():
    """API-Endpoint nur für Gruppen-Liste"""
    try:
        latest_file = find_latest_file()
        if not latest_file:
            return jsonify({'error': 'Keine Export-Datei gefunden'}), 404

        data = load_json_data(latest_file)
        if not data:
            return jsonify({'error': 'Fehler beim Laden der Daten'}), 500

        excluded_names = load_excluded_names()

        groups = []
        for group in data['groups']:
            group_users = [user for user in group['users'] if user['name'] not in excluded_names]
            if group_users:  # Nur Gruppen mit Benutzern
                groups.append({
                    'name': group['name'],
                    'user_count': len(group_users)
                })

        return jsonify({'groups': groups})

    except Exception as e:
        print(f"Error in get_groups: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Dashboard Backend startet...")
    print("Dashboard verfügbar unter: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)