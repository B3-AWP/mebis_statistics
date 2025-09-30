import os
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
import locale
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import requests
import io

# Sichere Konfiguration
from config.config_manager import config_manager

# TensorFlow-Logstufe auf ERROR setzen
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

def parse_german_datetime(datetime_str):
    """
    Konvertiert deutsche Zeitangaben in ISO-Format
    Unterstützt beide Formate:
    - 'Dienstag, 23. September 2025, 07:46'
    - '24. September 2025 08:12'
    """
    if not datetime_str or datetime_str in ["Keine Abgabe", "-", ""]:
        return None

    try:
        # Deutsche Wochentage und Monate mapping
        german_days = {
            'Montag': 'Monday', 'Dienstag': 'Tuesday', 'Mittwoch': 'Wednesday',
            'Donnerstag': 'Thursday', 'Freitag': 'Friday', 'Samstag': 'Saturday', 'Sonntag': 'Sunday'
        }
        german_months = {
            'Januar': 'January', 'Februar': 'February', 'März': 'March', 'April': 'April',
            'Mai': 'May', 'Juni': 'June', 'Juli': 'July', 'August': 'August',
            'September': 'September', 'Oktober': 'October', 'November': 'November', 'Dezember': 'December'
        }

        # Übersetze deutsche Begriffe ins Englische
        datetime_str_en = datetime_str
        for german, english in german_days.items():
            datetime_str_en = datetime_str_en.replace(german, english)
        for german, english in german_months.items():
            datetime_str_en = datetime_str_en.replace(german, english)

        # Versuche verschiedene Formate
        formats = [
            "%A, %d. %B %Y, %H:%M",  # "Tuesday, 23. September 2025, 07:46"
            "%d. %B %Y %H:%M",        # "24. September 2025 08:12"
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(datetime_str_en, fmt)
                return dt.isoformat()
            except ValueError:
                continue

        # Wenn kein Format passt
        print(f"Fehler beim Parsen der Zeitangabe '{datetime_str}': Kein passendes Format gefunden")
        return datetime_str

    except Exception as e:
        print(f"Fehler beim Parsen der Zeitangabe '{datetime_str}': {e}")
        return datetime_str  # Fallback: ursprünglichen Text zurückgeben

def create_webdriver(headless=False):
    options = Options()
    if headless == "True":
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

    # Performance-Optimierungen (sicher)
    options.add_argument('--disable-images')  # Bilder nicht laden
    options.add_argument('--disable-plugins') # Plugins deaktivieren
    options.add_argument('--disable-extensions') # Extensions deaktivieren
    options.add_argument('--disable-features=VizDisplayCompositor') # GPU deaktivieren
    options.add_argument('--disable-gpu')
    options.add_argument('--no-first-run')
    options.add_argument('--disable-default-apps')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-background-networking')
    options.add_argument('--disable-sync')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--disable-logging')
    options.add_argument('--log-level=3')
    options.add_argument('--disable-translate')
    options.add_argument('--hide-scrollbars')
    options.add_argument('--mute-audio')

    # Memory und CPU Optimierungen
    options.add_argument('--memory-pressure-off')
    options.add_argument('--max_old_space_size=4096')

    # Sicherere Performance-Einstellungen
    options.add_argument('--aggressive-cache-discard')
    options.add_argument('--disable-ipc-flooding-protection')

    return webdriver.Chrome(options=options)

def login(driver, username, password, waittime):
    WebDriverWait(driver, waittime).until(EC.visibility_of_element_located((By.ID, "input-username"))).send_keys(username)
    driver.find_element(By.ID, "input-password").send_keys(password)
    driver.find_element(By.ID, "button-do-log-in").click()

def get_select_options(driver, select_name, waittime):
    select_element = WebDriverWait(driver, waittime).until(
        EC.presence_of_element_located((By.NAME, select_name))
    )
    options = select_element.find_elements(By.TAG_NAME, "option")
    return [{"value": option.get_attribute("value"), "name": option.text} for option in options]

def get_user_ids_from_group(driver, group_value, base_url, course_id):
    group_url = f"{base_url}?course={course_id}&group={group_value}"
    driver.get(group_url)
    
    user_elements = driver.find_elements(By.CSS_SELECTOR, "#completion-progress tbody th[scope='row'] a")
    users = [{"id": re.search(r'id=(\d+)', user.get_attribute("href")).group(1), "name": user.text} for user in user_elements]
    return users

def get_activity_urls(driver):
    activity_urls = {
        "assignments": [],
        "checklists": [],
        "feedbacks": [],
        "quizzes": []
    }

    # Method 1: Search completion progress table (original method)
    activity_elements = driver.find_elements(By.CSS_SELECTOR, "#completion-progress thead th.completion-header a")
    if not activity_elements:
        print("No activity elements found in completion progress.")
    else:
        print(f"Found {len(activity_elements)} activities in completion progress.")

    activity_ids_found = set()

    for element in activity_elements:
        url = element.get_attribute("href")
        title = element.get_attribute("title")
        if "mod/assign/view.php?id=" in url:
            activity_id = re.search(r'id=(\d+)', url).group(1)
            if activity_id not in activity_ids_found:
                activity_urls["assignments"].append({"id": activity_id, "title": title, "url": url})
                activity_ids_found.add(activity_id)
        elif "mod/checklist/view.php?id=" in url:
            activity_id = re.search(r'id=(\d+)', url).group(1)
            if activity_id not in activity_ids_found:
                activity_urls["checklists"].append({"id": activity_id, "title": title, "url": url})
                activity_ids_found.add(activity_id)
        elif "mod/feedback/view.php?id=" in url:
            activity_id = re.search(r'id=(\d+)', url).group(1)
            if activity_id not in activity_ids_found:
                activity_urls["feedbacks"].append({"id": activity_id, "title": title, "url": url})
                activity_ids_found.add(activity_id)
        elif "mod/quiz/view.php?id=" in url:
            activity_id = re.search(r'id=(\d+)', url).group(1)
            if activity_id not in activity_ids_found:
                activity_urls["quizzes"].append({"id": activity_id, "title": title, "url": url})
                activity_ids_found.add(activity_id)

    # Method 2: Also search gradebook for any additional assignments that might be hidden from completion progress
    print("Searching gradebook for additional activities...")
    try:
        # Look for gradebook item headers that might contain additional assignments
        gradebook_elements = driver.find_elements(By.CSS_SELECTOR, "a.gradeitemheader")
        print(f"Found {len(gradebook_elements)} items in gradebook.")

        for element in gradebook_elements:
            href = element.get_attribute("href")
            if href and "mod/assign/view.php?id=" in href:
                activity_id = re.search(r'id=(\d+)', href).group(1)
                if activity_id not in activity_ids_found:
                    title = element.text or element.get_attribute("title") or f"Assignment {activity_id}"
                    activity_urls["assignments"].append({"id": activity_id, "title": title, "url": href})
                    activity_ids_found.add(activity_id)
                    print(f"Found additional assignment in gradebook: {activity_id} - {title}")
            elif href and "mod/checklist/view.php?id=" in href:
                activity_id = re.search(r'id=(\d+)', href).group(1)
                if activity_id not in activity_ids_found:
                    title = element.text or element.get_attribute("title") or f"Checklist {activity_id}"
                    activity_urls["checklists"].append({"id": activity_id, "title": title, "url": href})
                    activity_ids_found.add(activity_id)
                    print(f"Found additional checklist in gradebook: {activity_id} - {title}")
            elif href and "mod/feedback/view.php?id=" in href:
                activity_id = re.search(r'id=(\d+)', href).group(1)
                if activity_id not in activity_ids_found:
                    title = element.text or element.get_attribute("title") or f"Feedback {activity_id}"
                    activity_urls["feedbacks"].append({"id": activity_id, "title": title, "url": href})
                    activity_ids_found.add(activity_id)
                    print(f"Found additional feedback in gradebook: {activity_id} - {title}")
            elif href and "mod/quiz/view.php?id=" in href:
                activity_id = re.search(r'id=(\d+)', href).group(1)
                if activity_id not in activity_ids_found:
                    title = element.text or element.get_attribute("title") or f"Quiz {activity_id}"
                    activity_urls["quizzes"].append({"id": activity_id, "title": title, "url": href})
                    activity_ids_found.add(activity_id)
                    print(f"Found additional quiz in gradebook: {activity_id} - {title}")

    except Exception as e:
        print(f"Error searching gradebook for additional activities: {e}")

    print(f"Total activities found: {len(activity_urls['assignments'])} assignments, {len(activity_urls['checklists'])} checklists, {len(activity_urls['feedbacks'])} feedbacks, {len(activity_urls['quizzes'])} quizzes")
    return activity_urls

def get_checklist_progress_optimized(driver, checklist_url, sesskey):
    progress_data = {}

    # Erste URL mit 'showprogressbars', um die Fortschrittsbalken anzuzeigen
    url_show_progress_bars = checklist_url.replace('view.php', 'report.php')
    url_show_progress_bars += f"&sesskey={sesskey}&action=showprogressbars&perpage=300&group=0"
    driver.get(url_show_progress_bars)

    # URL zur Anzeige der Pflichtelemente
    url_hide_optional = checklist_url.replace('view.php', 'report.php')
    url_hide_optional += f"&sesskey={sesskey}&action=hideoptional&perpage=300&group=0"
    driver.get(url_hide_optional)

    # Extrahiere den required_progress
    progress_data['required_progress'] = extract_progress(driver)

    # URL zur Anzeige aller Elemente
    url_show_optional = checklist_url.replace('view.php', 'report.php')
    url_show_optional += f"&sesskey={sesskey}&action=showoptional&perpage=300&group=0"
    driver.get(url_show_optional)

    # Extrahiere den all_progress
    progress_data['all_progress'] = extract_progress(driver)

    return progress_data

def extract_progress(driver):
    progress_data = {}
    user_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='user/view.php?id=']")
    progress_elements = driver.find_elements(By.CSS_SELECTOR, "div.checklist_percentcomplete")

    for link, progress in zip(user_links, progress_elements):
        user_id = re.search(r'id=(\d+)', link.get_attribute("href")).group(1)
        progress_percent = progress.text.strip()
        progress_data[user_id] = progress_percent

    return progress_data

def get_assignment_status(driver, assignment_url, waittime):
    # Navigiere zur Bewertungsseite des Assignments mit allen nötigen Parametern
    # status: alle Benutzer anzeigen, auch die ohne Abgaben
    # quickgrading=0: vollständige Bewertungsansicht
    # group=0: alle Gruppen
    grading_url = f"{assignment_url}&action=grading&status&quickgrading=0&group=0"
    driver.get(grading_url)

    try:
        # Überprüfen, ob das tbody-Element vorhanden ist
        tbody_element = WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tbody"))
        )
    except TimeoutException:
        # Kein tbody gefunden, also gibt es keine Abgaben
        return []

    # Finde die Spaltenüberschriften, um die Klassen der relevanten Spalten zu ermitteln
    headers = driver.find_elements(By.CSS_SELECTOR, "th.header")
    grade_column_class = None
    submission_time_column_class = None

    for header in headers:
        if "Endbewertung" in header.text:
            # Extrahiere die Klasse, z.B. "c14"
            grade_column_class = header.get_attribute("class").split()[1]
        if "Zuletzt geändert (Abgabe)" in header.text or (header.get_attribute("data-sortby") and "timesubmitted" in header.get_attribute("data-sortby")):
            # Extrahiere die Klasse für die Abgabezeit-Spalte
            submission_time_column_class = header.get_attribute("class").split()[1]

    if not grade_column_class:
        print("Spalte 'Endbewertung' nicht gefunden.")
        return []

    # Finde alle Zeilen in der Tabelle
    rows = tbody_element.find_elements(By.CSS_SELECTOR, "tr")

    user_statuses = []

    for row in rows:
        # Extrahiere die UserID aus der class des tr-Elements
        class_attribute = row.get_attribute("class")
        user_id_match = re.search(r'user(\d+)', class_attribute)
        if not user_id_match:
            continue  # Überspringe Zeilen ohne UserID

        user_id = user_id_match.group(1)

        # Extrahiere die gewünschten Informationen aus den td-Elementen
        try:
            status = row.find_element(By.CSS_SELECTOR, "div.submissionstatussubmitted").text
        except:
            status = "Nicht eingereicht"

        try:
            status2 = row.find_element(By.CSS_SELECTOR, "div.submissiongraded").text
        except:
            status2 = "Nicht bewertet"

        try:
            submission = row.find_element(By.CSS_SELECTOR, "div.assignsubmission_onlinetext .no-overflow p").text
        except:
            submission = "Keine Abgabe"

        # grade_options werden leer gelassen (wie gewünscht)
        grade_options = []

        # Verwende die ermittelte Klasse, um die Endbewertung abzurufen (ursprüngliche Methode)
        try:
            grade = row.find_element(By.CSS_SELECTOR, f"td.cell.{grade_column_class}").text
        except:
            grade = "Keine Bewertung"

        # Extrahiere den Abgabezeitpunkt, falls die Spalte vorhanden ist
        submission_time = None
        if submission_time_column_class:
            try:
                submission_time_raw = row.find_element(By.CSS_SELECTOR, f"td.cell.{submission_time_column_class}").text.strip()
                # Konvertiere deutsche Zeitangabe in ISO-Format
                submission_time = parse_german_datetime(submission_time_raw)
            except:
                submission_time = None

        user_statuses.append({
            "user_id": user_id,
            "status": status,
            "status2": status2,
            "submission": submission,
            "submission_time": submission_time,
            "grade_options": grade_options,
            "grade": grade
        })

    return user_statuses

def get_quiz_status(driver, quiz_url, waittime):
    """Extrahiert Quiz-Status und Noten aus der Quiz-Report-Seite"""
    # Navigiere zur Quiz-Report-Seite mit den gewünschten Parametern
    # mode=overview: Übersichts-Modus
    # attempts=enrolled_with: alle eingeschriebenen Benutzer
    # onlygraded=1: nur bewertete Versuche
    # group=0: alle Gruppen
    # onlyregraded=0: alle Bewertungen
    # slotmarks=1: zeige Slot-Markierungen
    quiz_id = re.search(r'id=(\d+)', quiz_url).group(1)
    report_url = f"https://lernplattform.mebis.bycs.de/mod/quiz/report.php?id={quiz_id}&mode=overview&attempts=enrolled_with&onlygraded=1&group=0&onlyregraded=0&slotmarks=1"
    driver.get(report_url)

    try:
        # Warte auf das Laden der Tabelle
        table_element = WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.generaltable"))
        )
    except TimeoutException:
        print(f"Keine Quiz-Tabelle für Quiz {quiz_id} gefunden")
        return []

    # Finde die Header, um die korrekten Spalten zu identifizieren
    headers = driver.find_elements(By.CSS_SELECTOR, "th.header")
    time_finish_column_class = None
    grade_column_class = None

    for header in headers:
        header_text = header.text.strip()
        # Suche nach "Beendet"-Spalte (für das Datum)
        if "Beendet" in header_text:
            classes = header.get_attribute("class").split()
            for cls in classes:
                if cls.startswith("c") and cls[1:].isdigit():
                    time_finish_column_class = cls
                    break
        # Suche nach "Bewertung"-Spalte (für die Note)
        elif "Bewertung" in header_text and "/" in header_text:
            classes = header.get_attribute("class").split()
            for cls in classes:
                if cls.startswith("c") and cls[1:].isdigit():
                    grade_column_class = cls
                    break

    if not grade_column_class:
        print(f"Bewertungsspalte für Quiz {quiz_id} nicht gefunden")
        return []

    # Finde alle Zeilen der Tabelle
    tbody = table_element.find_element(By.CSS_SELECTOR, "tbody")
    rows = tbody.find_elements(By.CSS_SELECTOR, "tr")

    user_statuses = []

    for row in rows:
        try:
            # Extrahiere User-ID aus dem Link zur Benutzerseite
            try:
                user_link = row.find_element(By.CSS_SELECTOR, "td a[href*='user/view.php?id=']")
                user_href = user_link.get_attribute("href")
                user_id_match = re.search(r'id=(\d+)', user_href)
                if not user_id_match:
                    continue
                user_id = user_id_match.group(1)
            except:
                # Keine User-ID gefunden - überspringe diese Zeile (z.B. Zusammenfassungszeile)
                continue

            # Extrahiere die Bewertung
            grade = "-"
            try:
                grade_cell = row.find_element(By.CSS_SELECTOR, f"td.{grade_column_class}")
                grade = grade_cell.text.strip()
                if not grade or grade == "-":
                    grade = "Nicht bewertet"
            except:
                grade = "Nicht bewertet"

            # Extrahiere das Abschluss-Datum
            submission_time = None
            if time_finish_column_class:
                try:
                    time_cell = row.find_element(By.CSS_SELECTOR, f"td.{time_finish_column_class}")
                    time_text = time_cell.text.strip()
                    if time_text and time_text != "-":
                        # Konvertiere deutsche Zeitangabe in ISO-Format
                        submission_time = parse_german_datetime(time_text)
                except:
                    submission_time = None

            # Bestimme den Status basierend auf der Bewertung
            if grade == "Nicht bewertet" or grade == "-":
                status = "Nicht eingereicht"
                status2 = "Nicht bewertet"
            else:
                status = "Zur Bewertung abgegeben"
                status2 = "Bewertet"

            user_statuses.append({
                "user_id": user_id,
                "status": status,
                "status2": status2,
                "submission": "Quiz abgeschlossen",
                "submission_time": submission_time,
                "grade_options": [],
                "grade": grade
            })

        except Exception as e:
            print(f"Fehler beim Verarbeiten einer Quiz-Zeile für Quiz {quiz_id}: {e}")
            continue

    print(f"Quiz {quiz_id}: {len(user_statuses)} Benutzer-Status gefunden")
    return user_statuses

def get_sesskey(driver, waittime=10, max_retries=3):
    """
    Extrahiert den sesskey mit Wartezeit und Retry-Logik

    Args:
        driver: Selenium WebDriver
        waittime: Maximale Wartezeit in Sekunden
        max_retries: Maximale Anzahl an Wiederholungsversuchen

    Returns:
        str oder None: Der sesskey-Wert oder None bei Fehler
    """
    for attempt in range(max_retries):
        try:
            # Warte bis das Element verfügbar ist
            sesskey_element = WebDriverWait(driver, waittime).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='sesskey']"))
            )
            sesskey_value = sesskey_element.get_attribute("value")

            if sesskey_value:
                return sesskey_value
            else:
                print(f"Sesskey gefunden, aber leer (Versuch {attempt + 1}/{max_retries})")
                time.sleep(1)

        except TimeoutException:
            print(f"Timeout beim Warten auf sesskey (Versuch {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2)
        except Exception as e:
            print(f"Fehler beim Extrahieren des sesskey (Versuch {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)

    print("❌ Sesskey konnte nach allen Versuchen nicht extrahiert werden")
    return None

# Thread-local storage for WebDriver instances
thread_local = threading.local()

def get_thread_driver(isheadless, username=None, password=None, base_url=None, course_id=None, waittime=10):
    """Get or create a WebDriver instance for the current thread"""
    if not hasattr(thread_local, 'driver'):
        try:
            thread_local.driver = create_webdriver(headless=isheadless)
            thread_local.logged_in = False
            thread_local.sesskey = None
        except Exception as e:
            print(f"❌ Fehler beim Erstellen des WebDrivers: {e}")
            return None

    # Login und sesskey für jeden Thread
    if not thread_local.logged_in and username and password:
        try:
            thread_local.driver.get(f"{base_url}?course={course_id}")

            # Warte kurz bis Seite geladen ist
            time.sleep(2)

            if "login" in thread_local.driver.current_url:
                login(thread_local.driver, username, password, waittime)
                # Warte nach Login
                time.sleep(2)

            # Extrahiere sesskey für diesen Thread mit robuster Funktion
            thread_local.sesskey = get_sesskey(thread_local.driver, waittime)

            if thread_local.sesskey:
                thread_local.logged_in = True
                print(f"✓ Thread-Login erfolgreich, sesskey: {thread_local.sesskey[:10]}...")
            else:
                print("⚠ Thread-Login abgeschlossen, aber sesskey fehlt")

        except Exception as e:
            print(f"❌ Fehler beim Thread-Login: {e}")
            thread_local.logged_in = False

    return thread_local.driver

def get_thread_sesskey():
    """Get the sesskey for the current thread"""
    if hasattr(thread_local, 'sesskey'):
        return thread_local.sesskey
    return None

def process_assignment_parallel(assignment, isheadless, waittime, username, password, base_url, course_id, index, total):
    """Process a single assignment in parallel"""
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id, waittime)

        if driver is None:
            print(f"❌ [{index+1}/{total}] Kein WebDriver verfügbar für Assignment {assignment.get('id', 'unknown')}")
            return assignment.get('id', 'unknown'), []

        assignment_id = assignment["id"]
        assignment_url = assignment["url"]
        assignment_title = assignment.get("title", f"Assignment {assignment_id}")

        print(f"[{index+1}/{total}] Verarbeite Assignment: {assignment_title[:50]}...")
        start_time = time.time()
        status = get_assignment_status(driver, assignment_url, waittime)
        duration = time.time() - start_time
        print(f"  Abgeschlossen in {duration:.1f}s ({len(status)} Eintraege)")
        return assignment_id, status
    except Exception as e:
        print(f"❌ Fehler bei Assignment {assignment.get('id', 'unknown')}: {e}")
        return assignment.get('id', 'unknown'), []

def process_checklist_parallel(checklist, isheadless, username, password, base_url, course_id, index, total, waittime=10):
    """Process a single checklist in parallel"""
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id, waittime)

        if driver is None:
            print(f"❌ [{index+1}/{total}] Kein WebDriver verfügbar für Checklist {checklist.get('id', 'unknown')}")
            return checklist.get('id', 'unknown'), {"required_progress": {}, "all_progress": {}}

        thread_sesskey = get_thread_sesskey()

        if not thread_sesskey:
            print(f"❌ [{index+1}/{total}] Kein sesskey für Checklist {checklist.get('id', 'unknown')}")
            return checklist.get('id', 'unknown'), {"required_progress": {}, "all_progress": {}}

        checklist_id = checklist["id"]
        checklist_url = checklist["url"]
        checklist_title = checklist.get("title", f"Checklist {checklist_id}")

        print(f"[{index+1}/{total}] Verarbeite Checklist: {checklist_title[:50]}...")
        start_time = time.time()
        progress = get_checklist_progress_optimized(driver, checklist_url, thread_sesskey)
        duration = time.time() - start_time

        req_count = len(progress.get('required_progress', {}))
        all_count = len(progress.get('all_progress', {}))
        print(f"  └─ Abgeschlossen in {duration:.1f}s ({req_count} req, {all_count} all)")
        return checklist_id, progress
    except Exception as e:
        print(f"❌ Fehler bei Checklist {checklist.get('id', 'unknown')}: {e}")
        return checklist.get('id', 'unknown'), {"required_progress": {}, "all_progress": {}}

def process_quiz_parallel(quiz, isheadless, waittime, username, password, base_url, course_id, index, total):
    """Process a single quiz in parallel"""
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id, waittime)

        if driver is None:
            print(f"❌ [{index+1}/{total}] Kein WebDriver verfügbar für Quiz {quiz.get('id', 'unknown')}")
            return quiz.get('id', 'unknown'), []

        quiz_id = quiz["id"]
        quiz_url = quiz["url"]
        quiz_title = quiz.get("title", f"Quiz {quiz_id}")

        print(f"[{index+1}/{total}] Verarbeite Quiz: {quiz_title[:50]}...")
        start_time = time.time()
        status = get_quiz_status(driver, quiz_url, waittime)
        duration = time.time() - start_time
        print(f"  Abgeschlossen in {duration:.1f}s ({len(status)} Eintraege)")
        return quiz_id, status
    except Exception as e:
        print(f"❌ Fehler bei Quiz {quiz.get('id', 'unknown')}: {e}")
        return quiz.get('id', 'unknown'), []
    

def get_all_activity_categories(driver, course_id):
    categories_data = {}

    # Lade die Seite nur einmal
    grade_url = f"https://lernplattform.mebis.bycs.de/grade/edit/tree/index.php?id={course_id}"
    driver.get(grade_url)

    # Verwenden Sie WebDriverWait, um sicherzustellen, dass die Elemente geladen sind
    activity_elements = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.gradeitemheader"))
    )

    for activity_element in activity_elements:
        try:
            # Extrahiere die Aktivitäts-ID aus dem href-Attribut
            href = activity_element.get_attribute("href")
            activity_id_match = re.search(r'\?id=(\d+)', href)
            if not activity_id_match:
                continue

            activity_id = activity_id_match.group(1)

            # Finde die übergeordnete Kategorie
            parent_tr = activity_element.find_element(By.XPATH, "./ancestor::tr")
            category_id = parent_tr.get_attribute("data-parent-category")

            full_id = f"grade-item-{category_id}"
            category_tr = driver.find_element(By.ID, full_id)

            # Extrahiere den Kategorienamen aus dem `data-toggle-selectall` Attribut
            category_name = category_tr.find_element(By.CSS_SELECTOR, "input.itemselect").get_attribute("data-toggle-selectall")

            categories_data[activity_id] = {"category_id": category_id, "category_name": category_name}

        except Exception as e:
            print(f"Fehler beim Verarbeiten der Aktivität: {e}")

    return categories_data

def get_activity_category(driver, activity_id, course_id, waittime):
    category_data = {"category_id": "-1", "category_name": "nicht bewertet"}
    print(f"Verarbeite Aktivität ID: {activity_id}")

    grade_url = f"https://lernplattform.mebis.bycs.de/grade/edit/tree/index.php?id={course_id}"
    driver.get(grade_url)
    
    try:
        # Verwenden Sie WebDriverWait, um sicherzustellen, dass das Element geladen ist
        activity_element = WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f"a[href*='?id={activity_id}'].gradeitemheader"))
        )
        parent_tr = activity_element.find_element(By.XPATH, "./ancestor::tr")
        category_id = parent_tr.get_attribute("data-parent-category")
        
        full_id = f"grade-item-{category_id}"
        category_tr = driver.find_element(By.ID, full_id)

        # Extrahiere den Kategorienamen aus dem `data-toggle-selectall` Attribut
        category_name = category_tr.find_element(By.CSS_SELECTOR, "input.itemselect").get_attribute("data-toggle-selectall")
        
        category_data["category_id"] = category_id
        category_data["category_name"] = category_name
    except Exception as e:
        print(f"Fehler beim Verarbeiten der Aktivität ID {activity_id}: {e}")
    
    return category_data

def group_activities_by_category(activities):
    grouped_activities = {}
    for activity_type in activities:
        for activity in activities[activity_type]:
            category_id = activity.get("category_id")
            category_name = activity.get("category_name")
            if category_id not in grouped_activities:
                grouped_activities[category_id] = {
                    "category_name": category_name,
                    activity_type: []
                }
            grouped_activities[category_id][activity_type].append(activity)
    return grouped_activities

def add_activity_to_category(category_entry, activity_type, activity):
    if activity_type in category_entry:
        category_entry[activity_type].append(activity)
    else:
        category_entry[activity_type] = [activity]

def cleanup_thread_drivers():
    """Cleanup WebDriver instances in all threads"""
    try:
        if hasattr(thread_local, 'driver'):
            thread_local.driver.quit()
            delattr(thread_local, 'driver')
    except:
        pass

# Cloud functionality removed

# Cloud upload functionality removed


def main():
    # Startzeit des Skripts
    start_time = time.time()
    print("Starte Mebis-Datenexport...")
    print(f"Startzeit: {datetime.now().strftime('%H:%M:%S')}")

    # Lade Konfiguration über config_manager
    credentials = config_manager.get_login_credentials()
    username = credentials['username']
    password = credentials['password']

    urls = config_manager.get_urls()
    base_url = urls['base_url']

    courses = config_manager.get_courses()
    course_id = courses.get('course_ifa12')

    mode_settings = config_manager.get_mode_settings()
    isheadless = str(mode_settings['headless'])
    waittime = mode_settings['waittime']

    driver = create_webdriver(headless=isheadless)
    driver.get(f"{base_url}?course={course_id}")
    
    login(driver, username, password, waittime)

    # Extrahiere den sesskey nach dem Login
    sesskey = get_sesskey(driver)
    if not sesskey:
        print("Sesskey konnte nicht extrahiert werden. Überprüfe den Login-Prozess.")
        driver.quit()
        return

    group_options = get_select_options(driver, "group", waittime)
    activityinclude_options = get_select_options(driver, "activityinclude", waittime)
    activitysection_options = get_select_options(driver, "activitysection", waittime)

    # Erfasse die Aktivitäten einmalig
    activities = get_activity_urls(driver)

    # Aktualisiere Aktivitäten mit Kategorieinformationen
    activities_by_category = []


    # Erfasse alle Kategorieninformationen in einem einzigen Aufruf
    all_categories_data = get_all_activity_categories(driver, course_id)

    # Aktualisiere Aktivitäten mit Kategorieinformationen
    activities_by_category = []


    for activity_type in activities:
        for activity in activities[activity_type]:
            category_data = all_categories_data.get(activity["id"], {"category_id": "-1", "category_name": "nicht bewertet"})
            activity.update(category_data)

            # Suche oder erstelle die Kategorie in der Liste
            category_entry = next((cat for cat in activities_by_category if cat["id"] == category_data["category_id"]), None)
            if not category_entry:
                category_entry = {
                    "id": category_data["category_id"],
                    "category_name": category_data["category_name"],
                    "assignments": [],
                    "checklists": [],
                    "feedbacks": [],
                    "quizzes": []
                }
                activities_by_category.append(category_entry)

            # Füge die Aktivität zur entsprechenden Liste hinzu
            category_entry[activity_type].append(activity)


    print("Analysiere Status Assignments (parallel)")
    assignments_status = {}

    # Bestimme die Anzahl der Worker-Threads basierend auf der Anzahl der Assignments
    max_workers = min(2, len(activities["assignments"]))  # Maximal 2 parallel für Stabilität

    if activities["assignments"]:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Erstelle Future-Tasks für alle Assignments
            future_to_assignment = {
                executor.submit(process_assignment_parallel, assignment, isheadless, waittime, username, password, base_url, course_id, idx, len(activities["assignments"])): assignment
                for idx, assignment in enumerate(activities["assignments"])
            }

            # Sammle die Ergebnisse
            for future in as_completed(future_to_assignment):
                assignment_id, status = future.result()
                assignments_status[assignment_id] = status

    # Note: user_status is handled by dashboard_backend.py using existing user.activities data
    # No need to duplicate data structure here

    print("Analysiere Status Checkliste (parallel)")
    checklist_progress = {}

    # Bestimme die Anzahl der Worker-Threads basierend auf der Anzahl der Checklists
    max_workers = min(2, len(activities["checklists"]))

    if activities["checklists"]:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Erstelle Future-Tasks für alle Checklists
            future_to_checklist = {
                executor.submit(process_checklist_parallel, checklist, isheadless, username, password, base_url, course_id, idx, len(activities["checklists"])): checklist
                for idx, checklist in enumerate(activities["checklists"])
            }

            # Sammle die Ergebnisse
            for future in as_completed(future_to_checklist):
                checklist_id, progress = future.result()
                checklist_progress[checklist_id] = progress

    print("Analysiere Quiz Status (parallel)")
    quizzes_status = {}

    # Bestimme die Anzahl der Worker-Threads basierend auf der Anzahl der Quizzes
    max_workers = min(2, len(activities["quizzes"]))

    if activities["quizzes"]:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Erstelle Future-Tasks für alle Quizzes
            future_to_quiz = {
                executor.submit(process_quiz_parallel, quiz, isheadless, waittime, username, password, base_url, course_id, idx, len(activities["quizzes"])): quiz
                for idx, quiz in enumerate(activities["quizzes"])
            }

            # Sammle die Ergebnisse
            for future in as_completed(future_to_quiz):
                quiz_id, status = future.result()
                quizzes_status[quiz_id] = status

    # Zentralisierte Speicherung der Aktivitäten
    data = {
        "activities_by_category": activities_by_category,
        "groups": [],
        "activityincludes": activityinclude_options,
        "activitysections": activitysection_options
    }

    for group in group_options:
        if group["value"] == "0":
            continue  # Überspringe Gruppe 0
        group_data = {
            "name": group["name"],
            "value": group["value"],
            "users": get_user_ids_from_group(driver, group["value"], base_url, course_id)
        }
        data["groups"].append(group_data)

    for group in data["groups"]:
        for user in group["users"]:
            user["activities"] = {
                "assignments": [],
                "checklists": [],
                "feedbacks": [],
                "quizzes": []
            }
            
            # Verwende die zuvor erfassten Assignment-Status
            for assignment in activities["assignments"]:
                user_assignment_status = next((status for status in assignments_status[assignment["id"]] if status["user_id"] == user["id"]), None)
                if user_assignment_status:
                    user["activities"]["assignments"].append({
                        "id": assignment["id"],
                        "status": user_assignment_status,
                        "category_id": assignment.get("category_id"),
                        "category_name": assignment.get("category_name")
                    })

            # Verwende die zuvor erfassten Fortschritte der Checklisten
            for checklist in activities["checklists"]:
                user_checklist_progress = checklist_progress[checklist["id"]]
                required_progress = user_checklist_progress.get('required_progress', {}).get(user["id"])
                all_progress = user_checklist_progress.get('all_progress', {}).get(user["id"])
                if required_progress or all_progress:
                    user["activities"]["checklists"].append({
                        "id": checklist["id"],
                        "progress": {
                            "required_progress": required_progress,
                            "all_progress": all_progress
                        }
                        # ,
                        # "category_id": checklist.get("category_id"),
                        # "category_name": checklist.get("category_name")
                    })

            # Verwende die zuvor erfassten Quiz-Status
            for quiz in activities["quizzes"]:
                user_quiz_status = next((status for status in quizzes_status[quiz["id"]] if status["user_id"] == user["id"]), None)
                if user_quiz_status:
                    user["activities"]["quizzes"].append({
                        "id": quiz["id"],
                        "status": user_quiz_status,
                        "category_id": quiz.get("category_id"),
                        "category_name": quiz.get("category_name")
                    })

    print("Speichere Daten lokal...")
    save_start_time = time.time()

    # Zeitstempel hinzufügen
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_filename = f'output_{timestamp}.json'
    local_filename = f'./export/{json_filename}'

    try:
        os.makedirs('./export', exist_ok=True)
        with open(local_filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        save_duration = time.time() - save_start_time
        print(f"Daten erfolgreich lokal gespeichert in {save_duration:.1f}s: {local_filename}")
        save_success = True
    except Exception as e:
        print(f"Lokale Speicherung fehlgeschlagen: {e}")
        save_success = False

    # Cleanup: Schließe alle WebDriver-Instanzen
    driver.quit()

    # Cleanup aller Thread-spezifischen WebDriver
    import atexit
    atexit.register(cleanup_thread_drivers)

    # Endzeit des Skripts
    end_time = time.time()
    duration = end_time - start_time
    duration_minutes = duration / 60  # Umrechnung von Sekunden in Minuten

    # Performance-Statistiken
    total_activities = len(activities["assignments"]) + len(activities["checklists"]) + len(activities["quizzes"])
    total_groups = len(data["groups"])
    total_users = sum(len(group["users"]) for group in data["groups"])

    print("\n" + "="*60)
    print("EXPORT ABGESCHLOSSEN")
    print("="*60)
    print(f"Gesamtdauer: {duration_minutes:.2f} Minuten ({duration:.1f} Sekunden)")
    print(f"Aktivitaeten: {total_activities} ({len(activities['assignments'])} Assignments, {len(activities['checklists'])} Checklists, {len(activities['quizzes'])} Quizzes)")
    print(f"Gruppen: {total_groups} mit insgesamt {total_users} Benutzern")
    if total_activities > 0:
        print(f"Durchschnitt: {(duration / total_activities):.1f}s pro Aktivitaet")
    if save_success:
        print(f"Lokale Datei: ./export/{json_filename}")
    else:
        print(f"❌ Speicherung fehlgeschlagen")
    print(f"Endzeit: {datetime.now().strftime('%H:%M:%S')}")
    print("="*60)

if __name__ == "__main__":
    main()





    