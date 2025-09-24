"""
Neuer Ansatz: Noten direkt aus dem Grader-Report extrahieren
URL: https://lernplattform.mebis.bycs.de/grade/report/grader/index.php?id=2036416
"""

import os
import configparser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
import json
import re
import time
from datetime import datetime

def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

def create_webdriver(headless=False):
    options = Options()
    if headless == "True":
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

    # Performance-Optimierungen
    options.add_argument('--disable-images')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-logging')
    options.add_argument('--log-level=3')

    return webdriver.Chrome(options=options)

def login(driver, username, password, waittime):
    WebDriverWait(driver, waittime).until(EC.visibility_of_element_located((By.ID, "input-username"))).send_keys(username)
    driver.find_element(By.ID, "input-password").send_keys(password)
    driver.find_element(By.ID, "button-do-log-in").click()

def extract_grades_from_grader(driver, course_id, target_assignment_ids, waittime):
    """
    Extrahiert Noten direkt aus der Grader-Tabelle
    """
    grader_url = f"https://lernplattform.mebis.bycs.de/grade/report/grader/index.php?id={course_id}"
    driver.get(grader_url)

    try:
        # Warte auf Tabelle
        table = WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.gradereport-grader-table"))
        )
    except TimeoutException:
        print("Grader-Tabelle nicht gefunden")
        return {}

    print("Grader-Tabelle gefunden, analysiere Struktur...")

    # 1. Finde Assignment-Spalten anhand der Links
    assignment_columns = {}
    header_cells = driver.find_elements(By.CSS_SELECTOR, "th[data-itemid]")

    for header in header_cells:
        # Suche nach Assignment-Links in der Spalte
        assignment_link = header.find_elements(By.CSS_SELECTOR, "a[href*='mod/assign/view.php']")
        if assignment_link:
            href = assignment_link[0].get_attribute('href')
            assignment_id_match = re.search(r'id=(\d+)', href)
            if assignment_id_match:
                assignment_id = int(assignment_id_match.group(1))
                if assignment_id in target_assignment_ids:
                    item_id = header.get_attribute('data-itemid')
                    column_class = None
                    # Extrahiere Spaltenklasse (z.B. c3, c4, etc.)
                    classes = header.get_attribute('class').split()
                    for cls in classes:
                        if cls.startswith('c') and cls[1:].isdigit():
                            column_class = cls
                            break

                    assignment_title = assignment_link[0].text.strip()
                    assignment_columns[assignment_id] = {
                        'item_id': item_id,
                        'column_class': column_class,
                        'title': assignment_title
                    }
                    print(f"Gefunden: Assignment {assignment_id} = {assignment_title} (Spalte {column_class})")

    if not assignment_columns:
        print("Keine der gesuchten Assignments in Grader-Tabelle gefunden")
        return {}

    # 2. Extrahiere Benutzerzeilen und Noten
    results = {}
    user_rows = driver.find_elements(By.CSS_SELECTOR, "tr.userrow[data-uid]")

    print(f"Gefunden: {len(user_rows)} Benutzerzeilen")

    for row in user_rows:
        user_id = row.get_attribute('data-uid')

        # Benutzername extrahieren
        username_element = row.find_element(By.CSS_SELECTOR, "a.username")
        username = username_element.text.strip()

        user_data = {
            'user_id': user_id,
            'username': username,
            'assignments': {}
        }

        # Für jede Assignment-Spalte die Note extrahieren
        for assignment_id, column_info in assignment_columns.items():
            column_class = column_info['column_class']
            if column_class:
                try:
                    # Suche Notenzelle in der entsprechenden Spalte
                    grade_cell = row.find_element(By.CSS_SELECTOR, f"td.{column_class}")

                    # Verschiedene Möglichkeiten für Noteninput/display
                    grade_value = None
                    grade_input = grade_cell.find_elements(By.CSS_SELECTOR, "input")
                    if grade_input:
                        grade_value = grade_input[0].get_attribute('value')
                    else:
                        # Fallback: Text der Zelle
                        grade_value = grade_cell.text.strip()

                    user_data['assignments'][assignment_id] = {
                        'title': column_info['title'],
                        'grade': grade_value if grade_value else "Keine Bewertung"
                    }

                except Exception as e:
                    user_data['assignments'][assignment_id] = {
                        'title': column_info['title'],
                        'grade': "Fehler beim Abrufen",
                        'error': str(e)
                    }

        results[user_id] = user_data

    return results

def test_grader_export():
    """Test der neuen Grader-basierten Notenextraktion"""

    # Target Assignment IDs
    target_assignments = [77140327, 72027838, 71532031]

    print("Starte Grader-basierten Export...")

    # Config laden
    try:
        config = load_config()
        username = config.get('login', 'username')
        password = config.get('login', 'password')
        base_url = config.get('urls', 'base_url')
        course_id = config.get('courses', 'course_ifa12')
        waittime = int(config.get('mode', 'waittime', fallback=10))
        headless = config.get('mode', 'headless', fallback='False')
    except Exception as e:
        print(f"Fehler beim Laden der Konfiguration: {e}")
        return

    # WebDriver erstellen
    driver = create_webdriver(headless)

    results = {
        'method': 'grader_report',
        'course_id': course_id,
        'target_assignments': target_assignments,
        'users': {},
        'export_time': datetime.now().isoformat()
    }

    try:
        # Login
        print("Führe Login durch...")
        driver.get(f"{base_url}?course={course_id}")
        login(driver, username, password, waittime)

        # Warte auf erfolgreichen Login
        WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
        )
        print("Login erfolgreich!")

        # Extrahiere Noten aus Grader-Report
        print(f"\n=== Extrahiere Noten aus Grader-Report für Course {course_id} ===")
        user_grades = extract_grades_from_grader(driver, course_id, target_assignments, waittime)

        results['users'] = user_grades

        print(f"\n✓ Erfolgreich {len(user_grades)} Benutzer verarbeitet")
        for user_id, user_data in user_grades.items():
            assignment_count = len(user_data['assignments'])
            print(f"  - {user_data['username']} (ID: {user_id}): {assignment_count} Assignments")

    except Exception as e:
        print(f"Fehler während des Exports: {e}")
        results['error'] = str(e)

    finally:
        driver.quit()

    # Ergebnisse speichern
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"grader_export_{timestamp}.json"

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n=== Export abgeschlossen ===")
    print(f"Ergebnisse gespeichert in: {output_file}")

    return results

if __name__ == "__main__":
    test_grader_export()