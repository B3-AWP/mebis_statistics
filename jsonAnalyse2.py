import os
import json
import glob
import webbrowser
import configparser
import math

def find_latest_file(directory):
    files = glob.glob(os.path.join(directory, 'output_*.json'))
    latest_file = max(files, key=os.path.getctime)
    return latest_file

def load_json_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data

def load_excluded_names(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        excluded_names = {line.strip() for line in file.readlines()}
    return excluded_names

def parse_selection(choice_str):
    """
    Parse a selection string that can contain:
    - Single numbers: "1,2,3"
    - Ranges: "1-3,5-7"
    - Combinations: "2,5-7,10"
    Returns a list of indices
    """
    indices = []
    parts = choice_str.split(",")

    for part in parts:
        part = part.strip()
        if "-" in part:
            # Handle range like "1-3"
            try:
                start, end = part.split("-")
                start = int(start.strip())
                end = int(end.strip())
                indices.extend(range(start, end + 1))
            except ValueError:
                continue
        else:
            # Handle single number
            try:
                indices.append(int(part))
            except ValueError:
                continue

    return sorted(list(set(indices)))  # Remove duplicates and sort

def select_group(groups):
    groups_with_users = [group for group in groups if group['users']]

    print("Wählen Sie Gruppen aus:")
    for i, group in enumerate(groups_with_users):
        print(f"{i} - {group['name']}")
    print("A - Alle Gruppen")
    print("Unterstützte Formate: '0,1,2' (einzeln), '0-2' (Bereich), '0,2-4,6' (gemischt)")
    choice = input("Ihre Auswahl: ")
    if choice.upper() == 'A':
        return groups_with_users
    else:
        try:
            # Parse selection with range support
            indices = parse_selection(choice)
            selected_groups = [groups_with_users[i] for i in indices if 0 <= i < len(groups_with_users)]
            if not selected_groups:
                print("Keine gültigen Gruppen ausgewählt. Verwende alle Gruppen.")
                return groups_with_users
            return selected_groups
        except (ValueError, IndexError):
            print("Ungültige Eingabe. Verwende alle Gruppen.")
            return groups_with_users

def select_categories(categories):
    print("Wählen Sie die Kategorien aus:")
    for i, category in enumerate(categories):
        print(f"{i + 1} - {category['category_name']}")
    print("0 - Alle")
    print("Unterstützte Formate: '1,2,3' (einzeln), '1-3' (Bereich), '1,3-5,7' (gemischt)")
    choice = input("Ihre Auswahl: ")
    if choice.strip() == "0":
        return categories
    else:
        try:
            # Parse selection with range support, adjust for 1-based indexing
            indices = parse_selection(choice)
            # Convert from 1-based to 0-based indexing
            indices = [i - 1 for i in indices if i > 0]
            selected_categories = [categories[i] for i in indices if 0 <= i < len(categories)]
            if not selected_categories:
                print("Keine gültigen Kategorien ausgewählt. Verwende alle Kategorien.")
                return categories
            return selected_categories
        except (ValueError, IndexError):
            print("Ungültige Eingabe. Verwende alle Kategorien.")
            return categories

def get_assignment_details(assignments_by_category):
    assignment_details = {}
    for category in assignments_by_category:
        # Assignments hinzufügen
        for assignment in category.get('assignments', []):
            assignment_details[assignment['id']] = {
                'title': assignment['title'],
                'url': assignment['url'],
                'category_name': category['category_name']
            }

        # Quizzes hinzufügen
        for quiz in category.get('quizzes', []):
            assignment_details[quiz['id']] = {
                'title': quiz['title'],
                'url': quiz['url'],
                'category_name': category['category_name']
            }

        # Checklists hinzufügen
        for checklist in category.get('checklists', []):
            assignment_details[checklist['id']] = {
                'title': checklist['title'],
                'url': checklist['url'],
                'category_name': category['category_name']
            }

        # Feedbacks hinzufügen
        for feedback in category.get('feedbacks', []):
            assignment_details[feedback['id']] = {
                'title': feedback['title'],
                'url': feedback['url'],
                'category_name': category['category_name']
            }
    return assignment_details

def calculate_user_progress(user, assignment_details, categories, current_week, total_weeks):
    user_data = {
        "name": user['name'],
        "assignments": {
            "reviewed_count": 0,
            "submitted_count": 0,
            "grades": {},
            "percent_submitted": 0,
            "percent_submitted_timed": 0
        },
        "checklists": {
            "required_100_count": 0,
            "avg_required_progress": 0,
            "avg_all_progress": 0,
            "avg_required_progress_timed": 0,
            "avg_all_progress_timed": 0
        }
    }

    # Nur Pflichtaufgaben berücksichtigen
    pflicht_categories = [c for c in categories if c['category_name'] == "🎯Pflichtaufgaben"]

    if not pflicht_categories:
        # Fallback: wenn keine Pflichtaufgaben-Kategorie gefunden wird
        print("WARNUNG: Keine Kategorie 'Pflichtaufgaben' gefunden!")
        return user_data

    pflicht_category = pflicht_categories[0]
    pflicht_category_id = pflicht_category['id']

    # DEBUG: Alle Pflichtaufgaben in der Kategorie ausgeben
    print(f"\nDEBUG - Pflichtaufgaben in Kategorie (ID: {pflicht_category_id}):")
    print(f"   Assignments: {len(pflicht_category.get('assignments', []))}")
    for assignment in pflicht_category.get('assignments', []):
        print(f"      - {assignment.get('title', 'Unbekannt')} (ID: {assignment.get('id')})")

    print(f"   Quizzes: {len(pflicht_category.get('quizzes', []))}")
    for quiz in pflicht_category.get('quizzes', []):
        print(f"      - {quiz.get('title', 'Unbekannt')} (ID: {quiz.get('id')})")

    print(f"   Checklists: {len(pflicht_category.get('checklists', []))}")
    for checklist in pflicht_category.get('checklists', []):
        print(f"      - {checklist.get('title', 'Unbekannt')} (ID: {checklist.get('id')})")

    print(f"   Feedbacks: {len(pflicht_category.get('feedbacks', []))}")
    for feedback in pflicht_category.get('feedbacks', []):
        print(f"      - {feedback.get('title', 'Unbekannt')} (ID: {feedback.get('id')})")

    # Alle Pflichtaufgaben (assignments, quizzes, etc.) des Benutzers
    user_assignments = user['activities'].get('assignments', [])
    user_quizzes = user['activities'].get('quizzes', [])
    user_checklists = user['activities'].get('checklists', [])
    user_feedbacks = user['activities'].get('feedbacks', [])

    print(f"\nUser '{user['name']}' Aktivitaeten:")
    print(f"   User Assignments: {len(user_assignments)}")
    print(f"   User Quizzes: {len(user_quizzes)}")
    print(f"   User Checklists: {len(user_checklists)}")
    print(f"   User Feedbacks: {len(user_feedbacks)}")

    # Alle Pflichtaufgaben des Benutzers sammeln
    pflicht_assignments = [a for a in user_assignments if a.get('category_id') == pflicht_category_id]
    pflicht_quizzes = [q for q in user_quizzes if q.get('category_id') == pflicht_category_id]
    pflicht_checklists = [c for c in user_checklists if c.get('category_id') == pflicht_category_id]
    pflicht_feedbacks = [f for f in user_feedbacks if f.get('category_id') == pflicht_category_id]

    print(f"\nUser '{user['name']}' Pflichtaufgaben:")
    print(f"   Pflicht Assignments: {len(pflicht_assignments)}")
    print(f"   Pflicht Quizzes: {len(pflicht_quizzes)}")
    print(f"   Pflicht Checklists: {len(pflicht_checklists)}")
    print(f"   Pflicht Feedbacks: {len(pflicht_feedbacks)}")

    # Alle Pflichtaktivitäten kombinieren
    all_pflicht_activities = pflicht_assignments + pflicht_quizzes + pflicht_checklists + pflicht_feedbacks

    print(f"   GESAMT bearbeitete Pflichtaufgaben: {len(all_pflicht_activities)}")
    for activity in all_pflicht_activities:
        print(f"      - {activity.get('id')} (Status: {activity.get('status', {}).get('status', 'Unbekannt')})")

    # Gesamtanzahl aller Pflichtaufgaben in der Kategorie berechnen
    total_pflicht_activities = (
        len(pflicht_category.get('assignments', [])) +
        len(pflicht_category.get('quizzes', [])) +
        len(pflicht_category.get('checklists', [])) +
        len(pflicht_category.get('feedbacks', []))
    )

    print(f"   GESAMT Pflichtaufgaben in Kategorie: {total_pflicht_activities}")
    print("-" * 60)

    # Bewertete und eingereichte Aktivitäten aus allen Pflichtaktivitäten
    reviewed_activities = [a for a in all_pflicht_activities if a.get('status', {}).get('status2') == "Bewertet"]
    submitted_activities = [a for a in all_pflicht_activities if a.get('status', {}).get('status') == "Zur Bewertung abgegeben"]

    reviewed_count = len(reviewed_activities)
    submitted_count = len(submitted_activities)

    print(f"   Bewertete Pflichtaufgaben: {reviewed_count}")
    print(f"   Eingereichte Pflichtaufgaben: {submitted_count}")

    user_data['assignments']['reviewed_count'] = reviewed_count
    user_data['assignments']['submitted_count'] = submitted_count
    user_data['assignments']['grades'] = {"Pflichtaufgaben": []}

    for activity in submitted_activities:
        activity_id = activity['id']
        details = assignment_details.get(activity_id, {})
        title = details.get('title', 'N/A')
        url = details.get('url', '#')
        grade = activity.get('status', {}).get('grade', 'Nicht bewertet')
        user_data['assignments']['grades']["Pflichtaufgaben"].append((title, grade, url))

    # Prozentberechnung basierend auf Gesamtanzahl der Pflichtaufgaben
    user_data['assignments']['percent_submitted'] = round((submitted_count / total_pflicht_activities) * 100, 2) if total_pflicht_activities > 0 else 0

    # Referenzwoche-basierte Berechnung: Erwartete Anzahl der Pflichtaufgaben für die aktuelle Woche (aufgerundet)
    expected_pflicht_for_week = math.ceil((total_pflicht_activities / total_weeks) * current_week)
    user_data['assignments']['percent_submitted_timed'] = round((submitted_count / expected_pflicht_for_week) * 100, 2) if expected_pflicht_for_week > 0 else 0

    checklists = user['activities'].get('checklists', [])
    total_checklists = len(checklists)

    required_100 = [c for c in checklists if c['progress']['required_progress'] == "100%"]
    user_data['checklists']['required_100_count'] = len(required_100)

    if total_checklists > 0:
        user_data['checklists']['avg_required_progress'] = round(
            sum(float(c['progress']['required_progress'].strip('%')) for c in checklists if c['progress']['required_progress']) / total_checklists, 2)
        user_data['checklists']['avg_all_progress'] = round(
            sum(float(c['progress']['all_progress'].strip('%')) for c in checklists if c['progress']['all_progress']) / total_checklists, 2)
    else:
        user_data['checklists']['avg_required_progress'] = 0
        user_data['checklists']['avg_all_progress'] = 0

    if current_week > 0:
        user_data['checklists']['avg_required_progress_timed'] = round((user_data['checklists']['avg_required_progress'] / current_week) * total_weeks, 2)
        user_data['checklists']['avg_all_progress_timed'] = round((user_data['checklists']['avg_all_progress'] / current_week) * total_weeks, 2)
    else:
        user_data['checklists']['avg_required_progress_timed'] = 0
        user_data['checklists']['avg_all_progress_timed'] = 0

    return user_data

def calculate_group_averages(users_data, current_week, total_weeks):
    group_data = {
        "assignments": {
            "total_reviewed": sum(user['assignments']['reviewed_count'] for user in users_data),
            "total_submitted": sum(user['assignments']['submitted_count'] for user in users_data),
            "total_assignments": 0,  # Wird unten korrekt berechnet
            "percent_submitted": 0,
            "percent_submitted_timed": 0
        },
        "checklists": {
            "total_required_100": sum(user['checklists']['required_100_count'] for user in users_data),
            "avg_required_progress": 0,
            "avg_all_progress": 0,
            "avg_required_progress_timed": 0,
            "avg_all_progress_timed": 0
        }
    }

    total_users = len(users_data)
    if total_users > 0:
        # Durchschnittliche Prozentsätze der Benutzer verwenden
        avg_percent_submitted = sum(user['assignments']['percent_submitted'] for user in users_data) / total_users
        avg_percent_submitted_timed = sum(user['assignments']['percent_submitted_timed'] for user in users_data) / total_users

        group_data['assignments']['percent_submitted'] = round(avg_percent_submitted, 2)
        group_data['assignments']['percent_submitted_timed'] = round(avg_percent_submitted_timed, 2)

        all_required_progress = [user['checklists']['avg_required_progress'] for user in users_data]
        all_all_progress = [user['checklists']['avg_all_progress'] for user in users_data]
        group_data['checklists']['avg_required_progress'] = round(sum(all_required_progress) / total_users, 2) if all_required_progress else 0
        group_data['checklists']['avg_all_progress'] = round(sum(all_all_progress) / total_users, 2) if all_all_progress else 0
        group_data['checklists']['avg_required_progress_timed'] = round((group_data['checklists']['avg_required_progress'] / current_week) * total_weeks, 2) if all_required_progress else 0
        group_data['checklists']['avg_all_progress_timed'] = round((group_data['checklists']['avg_all_progress'] / current_week) * total_weeks, 2) if all_all_progress else 0

    return group_data

def generate_html_report(groups, categories, current_week, total_weeks, assignment_details, excluded_names):
    # Nur Pflichtaufgaben-Kategorie berücksichtigen
    pflicht_categories = [c for c in categories if c['category_name'] == "🎯Pflichtaufgaben"]

    if pflicht_categories:
        pflicht_category = pflicht_categories[0]
        total_pflicht_activities = (
            len(pflicht_category.get('assignments', [])) +
            len(pflicht_category.get('quizzes', [])) +
            len(pflicht_category.get('checklists', [])) +
            len(pflicht_category.get('feedbacks', []))
        )
    else:
        total_pflicht_activities = 0

    total_checklists = sum(len(category['checklists']) for category in categories)

    expected_pflicht_activities = (total_pflicht_activities / total_weeks) * current_week
    expected_checklists = (total_checklists / total_weeks) * current_week

    percent_pflicht_activities = round((expected_pflicht_activities / total_pflicht_activities) * 100, 2) if total_pflicht_activities > 0 else 0
    percent_checklists = round((expected_checklists / total_checklists) * 100, 2) if total_checklists > 0 else 0

    html = """
    <html>
    <head>
        <title>Auswertung</title>
        <style>
            body { font-family: Arial, sans-serif; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            td.numeric { text-align: right; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            th { background-color: #4CAF50; color: white; }
        </style>
    </head>
    <body>
    """
    html += f"<h1>Auswertung für Referenzwoche {current_week} (von {total_weeks}) - Nur Pflichtaufgaben</h1>"
    html += f"<p>Checklisten ({math.ceil(expected_checklists)} von {total_checklists} --> {percent_checklists:.2f}% des Schuljahres abgeschlossen)</p>"
    html += f"<p>Pflichtaufgaben ({math.ceil(expected_pflicht_activities)} von {total_pflicht_activities} --> {percent_pflicht_activities:.2f}% des Schuljahres abgeschlossen)</p>"
    html += f"<p><strong>Hinweis:</strong> Diese Auswertung berücksichtigt nur Aktivitäten aus der Kategorie 'Pflichtaufgaben'</p>"

    for group in groups:
        users_data = [calculate_user_progress(user, assignment_details, categories, current_week, total_weeks)
                      for user in group['users'] if user['name'] not in excluded_names]
        group_data = calculate_group_averages(users_data, current_week, total_weeks)

        html += f"<h2>Gruppe: {group['name']}</h2>"
        html += "<table><tr><th>Benutzername</th><th>Eingereichte Pflichtaufgaben</th><th>Bewertete Pflichtaufgaben</th><th>Bewertungen und Noten</th><th>Prozentsatz Eingereicht</th><th>Prozentsatz Eingereicht (Referenzwoche)</th>"
        html += "<th>Pflichtaufgaben Soll (Aktuelle Woche)</th><th>Pflichtaufgaben Soll (Gesamtzeitraum)</th><th>Checklisten 100% Erfüllt</th><th>Checkliste Pflicht (%)</th><th>Checkliste Gesamt (%)</th>"
        html += "<th>Checkliste Pflicht (%) (Aktuelle Woche)</th><th>Checkliste Gesamt (%) (Aktuelle Woche)</th><th>Checklisten Soll (Aktuelle Woche)</th><th>Checklisten Soll (Gesamtzeitraum)</th></tr>"

        for user_data in users_data:
            html += f"<tr><td>{user_data['name']}</td>"
            html += f"<td class='numeric'>{user_data['assignments']['submitted_count']}</td>"
            html += f"<td class='numeric'>{user_data['assignments']['reviewed_count']}</td>"

            html += "<td>"
            for category_name, grades in user_data['assignments']['grades'].items():
                if grades:
                    html += f"<h5>{category_name}</h5>"
                    html += "<table>"
                    for title, grade, url in grades:
                        html += f"<tr><td><a href='{url}'>{title}</a></td><td>{grade}</td></tr>"
                    html += "</table>"
            html += "</td>"

            html += f"<td class='numeric'>{user_data['assignments']['percent_submitted']:.2f}%</td>"
            html += f"<td class='numeric'>{user_data['assignments']['percent_submitted_timed']:.2f}%</td>"
            html += f"<td class='numeric'>{math.ceil(expected_pflicht_activities)}</td>"
            html += f"<td class='numeric'>{total_pflicht_activities}</td>"
            html += f"<td class='numeric'>{user_data['checklists']['required_100_count']}</td>"
            html += f"<td class='numeric'>{user_data['checklists']['avg_required_progress']:.2f}%</td>"
            html += f"<td class='numeric'>{user_data['checklists']['avg_all_progress']:.2f}%</td>"
            html += f"<td class='numeric'>{user_data['checklists']['avg_required_progress_timed']:.2f}%</td>"
            html += f"<td class='numeric'>{user_data['checklists']['avg_all_progress_timed']:.2f}%</td>"
            html += f"<td class='numeric'>{int(expected_checklists)}</td>"
            html += f"<td class='numeric'>{total_checklists}</td></tr>"

        html += "</table>"

        html += "<h3>Durchschnittswerte für die gesamte Gruppe</h3>"
        html += "<table><tr><th>Prozentsatz Eingereicht</th><th>Prozentsatz Eingereicht (Zeitbasiert)</th><th>Checklisten 100% Erfüllt</th>"
        html += "<th>Checkliste Pflicht (%)</th><th>Checkliste Gesamt (%)</th><th>Checkliste Pflicht (%) (Aktuelle Woche)</th><th>Checkliste Gesamt (%) (Aktuelle Woche)</th></tr>"

        html += f"<tr><td class='numeric'>{group_data['assignments']['percent_submitted']:.2f}%</td>"
        html += f"<td class='numeric'>{group_data['assignments']['percent_submitted_timed']:.2f}%</td>"
        html += f"<td class='numeric'>{group_data['checklists']['total_required_100']}</td>"
        html += f"<td class='numeric'>{group_data['checklists']['avg_required_progress']:.2f}%</td>"
        html += f"<td class='numeric'>{group_data['checklists']['avg_all_progress']:.2f}%</td>"
        html += f"<td class='numeric'>{group_data['checklists']['avg_required_progress_timed']:.2f}%</td>"
        html += f"<td class='numeric'>{group_data['checklists']['avg_all_progress_timed']:.2f}%</td></tr>"

        html += "</table>"

    html += "</body></html>"

    return html

def main():
    # Load configuration
    config = configparser.ConfigParser()
    config.read('config.ini')

    directory = config.get('General', 'Directory', fallback='export')
    filename = config.get('General', 'Filename', fallback='report.html')
    total_weeks = config.getint('General', 'TotalWeeks', fallback=10)
    show_command_dialog = config.getboolean('General', 'ShowCommandDialog', fallback=True)
    default_current_week = config.getint('General', 'DefaultCurrentWeek', fallback=1)

    latest_file = find_latest_file(directory)
    data = load_json_data(latest_file)

    groups = data['groups']
    selected_groups = select_group(groups) if show_command_dialog else groups

    categories = data['activities_by_category']
    selected_categories = select_categories(categories) if show_command_dialog else categories

    assignment_details = get_assignment_details(categories)

    excluded_names_file = 'exclude_names.txt'
    excluded_names = load_excluded_names(excluded_names_file)

    current_week = int(input("Aktuelle Unterrichtswoche: ")) if show_command_dialog else default_current_week

    html_report = generate_html_report(selected_groups, selected_categories, current_week, total_weeks, assignment_details, excluded_names)

    # Save the HTML report
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(html_report)

    print(f"Der Bericht wurde als '{filename}' gespeichert.")
    webbrowser.open(filename)

if __name__ == "__main__":
    main()