import os
import json
import glob
import webbrowser
import configparser

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
        for assignment in category['assignments']:
            assignment_details[assignment['id']] = {
                'title': assignment['title'],
                'url': assignment['url'],
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

    assignments = user['activities'].get('assignments', [])
    category_ids = [c['id'] for c in categories]
    category_assignments = [a for a in assignments if a['category_id'] in category_ids]
    total_assignments = len(category_assignments)
    reviewed_assignments = [a for a in category_assignments if a['status']['status2'] == "Bewertet"]
    submitted_assignments = [a for a in category_assignments if a['status']['status'] == "Zur Bewertung abgegeben"]
    reviewed_count = len(reviewed_assignments)
    submitted_count = len(submitted_assignments)
    user_data['assignments']['reviewed_count'] = reviewed_count
    user_data['assignments']['submitted_count'] = submitted_count
    user_data['assignments']['grades'] = {c['category_name']: [] for c in categories}

    for assignment in submitted_assignments:
        assignment_id = assignment['id']
        details = assignment_details.get(assignment_id, {})
        category_name = details.get('category_name', 'Unbekannt')
        title = details.get('title', 'N/A')
        url = details.get('url', '#')
        grade = assignment['status'].get('grade', 'Nicht bewertet')
        user_data['assignments']['grades'][category_name].append((title, grade, url))

    user_data['assignments']['percent_submitted'] = round((submitted_count / total_assignments) * 100, 2) if total_assignments > 0 else 0
    user_data['assignments']['percent_submitted_timed'] = round((user_data['assignments']['percent_submitted'] / current_week) * total_weeks, 2) if total_assignments > 0 else 0

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
            "total_assignments": sum(len(user['assignments']['grades']) for user in users_data),
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
        group_data['assignments']['percent_submitted'] = round((group_data['assignments']['total_submitted'] / group_data['assignments']['total_assignments']) * 100, 2) if group_data['assignments']['total_assignments'] > 0 else 0
        group_data['assignments']['percent_submitted_timed'] = round((group_data['assignments']['percent_submitted'] / current_week) * total_weeks, 2) if group_data['assignments']['total_assignments'] > 0 else 0

        all_required_progress = [user['checklists']['avg_required_progress'] for user in users_data]
        all_all_progress = [user['checklists']['avg_all_progress'] for user in users_data]
        group_data['checklists']['avg_required_progress'] = round(sum(all_required_progress) / total_users, 2) if all_required_progress else 0
        group_data['checklists']['avg_all_progress'] = round(sum(all_all_progress) / total_users, 2) if all_all_progress else 0
        group_data['checklists']['avg_required_progress_timed'] = round((group_data['checklists']['avg_required_progress'] / current_week) * total_weeks, 2) if all_required_progress else 0
        group_data['checklists']['avg_all_progress_timed'] = round((group_data['checklists']['avg_all_progress'] / current_week) * total_weeks, 2) if all_all_progress else 0

    return group_data

def generate_html_report(groups, categories, current_week, total_weeks, assignment_details, excluded_names):
    total_assignments = sum(len(category['assignments']) for category in categories)
    total_checklists = sum(len(category['checklists']) for category in categories)

    expected_assignments = (total_assignments / total_weeks) * current_week
    expected_checklists = (total_checklists / total_weeks) * current_week

    percent_assignments = round((expected_assignments / total_assignments) * 100, 2) if total_assignments > 0 else 0
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
    html += f"<h1>Auswertung für Referenzwoche {current_week} (von {total_weeks})</h1>"
    html += f"<p>Checklisten ({int(expected_checklists)} von {total_checklists} --> {percent_checklists:.2f}% des Schuljahres abgeschlossen)</p>"
    html += f"<p>Assignments ({int(expected_assignments)} von {total_assignments} --> {percent_assignments:.2f}% des Schuljahres abgeschlossen)</p>"

    for group in groups:
        users_data = [calculate_user_progress(user, assignment_details, categories, current_week, total_weeks)
                      for user in group['users'] if user['name'] not in excluded_names]
        group_data = calculate_group_averages(users_data, current_week, total_weeks)

        html += f"<h2>Gruppe: {group['name']}</h2>"
        html += "<table><tr><th>Benutzername</th><th>Eingereichte Aufgaben</th><th>Bewertete Aufgaben</th><th>Bewertungen und Noten</th><th>Prozentsatz Eingereicht</th><th>Prozentsatz Eingereicht (Zeitbasiert)</th>"
        html += "<th>Aufgaben Soll (Aktuelle Woche)</th><th>Aufgaben Soll (Gesamtzeitraum)</th><th>Checklisten 100% Erfüllt</th><th>Checkliste Pflicht (%)</th><th>Checkliste Gesamt (%)</th>"
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
            html += f"<td class='numeric'>{int(expected_assignments)}</td>"
            html += f"<td class='numeric'>{total_assignments}</td>"
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

    latest_file = find_latest_file(directory)
    data = load_json_data(latest_file)

    groups = data['groups']
    selected_groups = select_group(groups) if show_command_dialog else groups

    categories = data['activities_by_category']
    selected_categories = select_categories(categories) if show_command_dialog else categories

    assignment_details = get_assignment_details(categories)

    excluded_names_file = 'exclude_names.txt'
    excluded_names = load_excluded_names(excluded_names_file)

    current_week = int(input("Aktuelle Unterrichtswoche: ")) if show_command_dialog else total_weeks

    html_report = generate_html_report(selected_groups, selected_categories, current_week, total_weeks, assignment_details, excluded_names)

    # Save the HTML report
    with open(filename, 'w', encoding='utf-8') as file:
        file.write(html_report)

    print(f"Der Bericht wurde als '{filename}' gespeichert.")
    webbrowser.open(filename)

if __name__ == "__main__":
    main()