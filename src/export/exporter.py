import os
import sys

# Add project root to path for imports
# This allows the file to be run directly from src/export/ or via wrapper scripts
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, WebDriverException,
    StaleElementReferenceException, NoSuchElementException
)
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
import functools

# Sichere Konfiguration
from config.config_manager import config_manager

# TensorFlow-Logstufe auf ERROR setzen
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

def retry(max_retries=3, base_delay=1.0, backoff_factor=2.0,
          exceptions=(TimeoutException, WebDriverException)):
    """Decorator für automatische Wiederholungsversuche mit exponentiellem Backoff"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (backoff_factor ** attempt)
                        print(f"[RETRY] {func.__name__} Versuch {attempt+1}/{max_retries} "
                              f"fehlgeschlagen: {type(e).__name__}. Warte {delay:.1f}s...")
                        time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator


def parse_german_datetime(datetime_str):
    """
    Konvertiert deutsche Zeitangaben in ISO-Format
    Unterstützt mehrere Formate:
    - 'Dienstag, 23. September 2025, 07:46'
    - '24. September 2025 08:12'
    - '16. September 2025  11:31' (doppeltes Leerzeichen aus Quiz-Reports)
    """
    if not datetime_str or datetime_str in ["Keine Abgabe", "-", ""]:
        return None

    try:
        # Normalisiere mehrfache Leerzeichen zu einem einzigen
        datetime_str = re.sub(r'\s+', ' ', datetime_str.strip())

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
            "%d. %B %Y %H:%M",        # "24. September 2025 08:12" (nach Normalisierung auch für Quiz-Format)
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
        options.add_argument('--headless=new')  # Neues Headless-Mode
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        # Wichtig für Headless: Window-Size setzen
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        # User-Agent für bessere Kompatibilität
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

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

@retry(max_retries=3, base_delay=2.0)
def login(driver, username, password, waittime):
    """Robuster Login mit mehreren Fallback-Strategien"""
    try:
        # Warte bis die Seite vollständig geladen ist
        WebDriverWait(driver, waittime).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        # Strategie 1: Warte auf visibility_of_element
        try:
            username_field = WebDriverWait(driver, waittime).until(
                EC.visibility_of_element_located((By.ID, "input-username"))
            )
        except (TimeoutException, WebDriverException):
            # Strategie 2: Warte nur auf presence (für headless mode)
            print("[INFO] Visibility fehlgeschlagen, versuche presence_of_element...")
            username_field = WebDriverWait(driver, waittime).until(
                EC.presence_of_element_located((By.ID, "input-username"))
            )

        # Lösche vorhandenen Text und gebe Username ein
        username_field.clear()
        username_field.send_keys(username)

        # Passwort-Feld
        password_field = driver.find_element(By.ID, "input-password")
        password_field.clear()
        password_field.send_keys(password)

        # Login-Button
        login_button = driver.find_element(By.ID, "button-do-log-in")
        login_button.click()

        # Warte bis Login durchgeführt wurde (URL wechselt weg von Login-Seite)
        WebDriverWait(driver, waittime).until(
            lambda d: "login" not in d.current_url
        )

    except Exception as e:
        print(f"[FEHLER] Login fehlgeschlagen: {e}")
        import traceback
        try:
            print(f"[FEHLER] Traceback: {traceback.format_exc()}")
        except UnicodeEncodeError:
            print(f"[FEHLER] Traceback enthaelt Unicode-Zeichen")
        raise

def get_select_options(driver, select_name, waittime):
    try:
        select_element = WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.NAME, select_name))
        )
        options = select_element.find_elements(By.TAG_NAME, "option")
        return [{"value": option.get_attribute("value"), "name": option.text} for option in options]
    except TimeoutException:
        print(f"[FEHLER] Select '{select_name}' nicht gefunden nach {waittime}s")
        return []

def get_user_ids_from_group(driver, group_value, base_url, course_id):
    try:
        group_url = f"{base_url}?course={course_id}&group={group_value}"
        driver.get(group_url)
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        user_elements = driver.find_elements(By.CSS_SELECTOR, "#completion-progress tbody th[scope='row'] a")
        users = [{"id": re.search(r'id=(\d+)', user.get_attribute("href")).group(1), "name": user.text} for user in user_elements]
        return users
    except (TimeoutException, WebDriverException) as e:
        print(f"[FEHLER] Benutzer für Gruppe {group_value} nicht ladbar: {e}")
        return []

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

def get_checklist_progress_optimized(driver, checklist_url, sesskey, course_id):
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

def get_checklists_mandatory_status(driver, course_id):
    """
    Ermittelt für alle Checklisten, ob sie Pflicht-Elemente enthalten.
    Gibt ein Dictionary zurück: {checklist_id: is_mandatory (bool)}
    """
    mandatory_status = {}

    # Lade die Übersichtsseite aller Checklisten
    overview_url = f"https://lernplattform.bycs.de/mod/checklist/index.php?id={course_id}"
    driver.get(overview_url)

    try:
        # Warte auf die Tabelle
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
        )

        # Finde alle Zeilen in der Tabelle
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")

        for row in rows:
            try:
                # Extrahiere die Checklisten-ID aus dem Link in der ersten Spalte
                link = row.find_element(By.CSS_SELECTOR, "td.cell.c0 a")
                href = link.get_attribute("href")
                checklist_id_match = re.search(r'id=(\d+)', href)

                if not checklist_id_match:
                    continue

                checklist_id = checklist_id_match.group(1)

                # Prüfe, ob in der zweiten Spalte ein Progress-Bar-Element vorhanden ist
                # Falls ja: Pflicht-Checkliste, falls nein: keine Pflicht
                try:
                    row.find_element(By.CSS_SELECTOR, "td.cell.c1 div.checklist_progress_outer")
                    # Element gefunden = Pflicht-Checkliste
                    mandatory_status[checklist_id] = True
                except NoSuchElementException:
                    # Element nicht gefunden = keine Pflicht-Checkliste
                    mandatory_status[checklist_id] = False

            except Exception as e:
                # Fehler beim Verarbeiten dieser Zeile - überspringe
                continue

    except Exception as e:
        print(f"Fehler beim Laden der Checklisten-Übersicht: {e}")

    return mandatory_status

def extract_progress(driver):
    progress_data = {}
    user_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='user/view.php?id=']")
    progress_elements = driver.find_elements(By.CSS_SELECTOR, "div.checklist_percentcomplete")

    # Wenn keine User-Links gefunden wurden, versuche zeilenweise zu parsen
    if len(user_links) == 0:
        # Versuche, die Tabelle zeilenweise zu parsen
        rows = driver.find_elements(By.CSS_SELECTOR, "table.generaltable tbody tr")

        for row in rows:
            try:
                # Suche User-Link in der Zeile
                user_link = row.find_element(By.CSS_SELECTOR, "a[href*='user/view.php?id=']")
                user_id = re.search(r'id=(\d+)', user_link.get_attribute("href")).group(1)

                # Suche Progress-Element in derselben Zeile
                try:
                    progress_elem = row.find_element(By.CSS_SELECTOR, "div.checklist_percentcomplete")
                    progress_percent = progress_elem.text.strip()
                    progress_data[user_id] = progress_percent
                except NoSuchElementException:
                    # Kein Progress-Element in dieser Zeile
                    pass
            except (NoSuchElementException, AttributeError):
                # Keine User-ID in dieser Zeile
                continue

        return progress_data

    # Wenn keine Progress-Elemente gefunden wurden, versuche alternative Selektoren
    if len(progress_elements) == 0:
        # Versuche span.checklist_percentcomplete
        progress_elements = driver.find_elements(By.CSS_SELECTOR, "span.checklist_percentcomplete")

        if len(progress_elements) == 0:
            # Versuche beliebige Elemente mit checklist_percentcomplete
            progress_elements = driver.find_elements(By.CSS_SELECTOR, "[class*='checklist_percentcomplete']")

        if len(progress_elements) == 0:
            # Versuche td-Elemente mit Prozent-Zeichen
            progress_elements = driver.find_elements(By.XPATH, "//td[contains(text(), '%')]")

    for link, progress in zip(user_links, progress_elements):
        user_id = re.search(r'id=(\d+)', link.get_attribute("href")).group(1)
        progress_percent = progress.text.strip()
        progress_data[user_id] = progress_percent

    return progress_data

def get_assignment_groups(driver, assignment_url, waittime):
    """
    Extrahiert die Gruppierungsinformationen für ein Assignment

    Returns:
        str: "all" wenn für alle Gruppen, oder der Gruppenname wenn nur für eine spezifische Gruppe
    """
    try:
        # Navigiere zur Assignment-Seite
        driver.get(assignment_url)
        WebDriverWait(driver, waittime).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        # Suche nach dem Form mit id="selectgroup"
        try:
            form_element = driver.find_element(By.ID, "selectgroup")

            # Finde das Label innerhalb des Forms
            label_element = form_element.find_element(By.TAG_NAME, "label")
            label_text = label_element.text.strip()

            # Analysiere den Label-Text
            # Prüfe ob es einen Gruppennamen in Klammern gibt
            group_match = re.search(r'Getrennte Gruppen \(([^)]+)\)', label_text)
            if group_match:
                # Spezifische Gruppe gefunden
                return group_match.group(1)
            elif "Getrennte Gruppen" in label_text:
                # "Getrennte Gruppen" ohne spezifischen Namen = alle Gruppen
                return "all"
            else:
                # Unerwarteter Label-Text
                return "all"

        except Exception as e:
            # Form nicht gefunden oder Fehler beim Parsen = keine Gruppenbeschränkung
            return "all"

    except Exception as e:
        print(f"[FEHLER] Fehler beim Extrahieren der Gruppierungsinformationen: {e}")
        return "all"

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
        except NoSuchElementException:
            status = "Nicht eingereicht"

        try:
            status2 = row.find_element(By.CSS_SELECTOR, "div.submissiongraded").text
        except NoSuchElementException:
            status2 = "Nicht bewertet"

        try:
            submission = row.find_element(By.CSS_SELECTOR, "div.assignsubmission_onlinetext .no-overflow p").text
        except NoSuchElementException:
            submission = "Keine Abgabe"

        # grade_options werden leer gelassen (wie gewünscht)
        grade_options = []

        # Verwende die ermittelte Klasse, um die Endbewertung abzurufen (ursprüngliche Methode)
        try:
            grade = row.find_element(By.CSS_SELECTOR, f"td.cell.{grade_column_class}").text
        except NoSuchElementException:
            grade = "Keine Bewertung"

        # Extrahiere den Abgabezeitpunkt, falls die Spalte vorhanden ist
        submission_time = None
        if submission_time_column_class:
            try:
                submission_time_raw = row.find_element(By.CSS_SELECTOR, f"td.cell.{submission_time_column_class}").text.strip()
                # Konvertiere deutsche Zeitangabe in ISO-Format
                submission_time = parse_german_datetime(submission_time_raw)
            except NoSuchElementException:
                submission_time = None

        # Korrigiere Status basierend auf der Bewertung
        # Wenn eine gültige Bewertung vorhanden ist, sollte der Status nicht "Nicht eingereicht" sein
        if grade and grade not in ["Keine Bewertung", "-", ""]:
            # Es gibt eine Bewertung
            if status == "Nicht eingereicht":
                status = "Zur Bewertung abgegeben"
            if status2 == "Nicht bewertet":
                status2 = "Bewertet"

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

def get_grader_report_data(driver, course_id, group_id, waittime):
    """
    Extrahiert alle Bewertungsdaten aus der Grader-Report-Seite
    Diese Seite zeigt alle Aktivitäten (Quizzes, Assignments, etc.) in einer Tabelle
    mit Personen in Zeilen und Aktivitäten in Spalten
    """
    grader_url = f"https://lernplattform.bycs.de/grade/report/grader/index.php?id={course_id}&groupsearchvalue=&group={group_id}"
    driver.get(grader_url)

    try:
        # Warte auf das Laden der Haupttabelle
        table_element = WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.gradereport-grader-table#user-grades"))
        )
    except TimeoutException:
        print(f"Grader-Report-Tabelle für Kurs {course_id}, Gruppe {group_id} nicht gefunden")
        return {}

    # Extrahiere die Header-Struktur (Aktivitäten) und erstelle Spalten-Mapping
    quizzes = {}
    column_to_quiz = {}

    try:
        # Finde alle Header-Links zu Aktivitäten
        header_links = driver.find_elements(By.CSS_SELECTOR, "table.gradereport-grader-table th a.gradeitemheader")

        for link in header_links:
            href = link.get_attribute("href")
            title = link.get_attribute("title") or link.text

            # Extrahiere Aktivitäts-ID und Typ aus der URL
            if "mod/quiz/view.php?id=" in href:
                activity_id = re.search(r'id=(\d+)', href).group(1)

                # Finde das übergeordnete th-Element
                header = link.find_element(By.XPATH, "./ancestor::th")

                # Extrahiere die Spalten-Klasse (z.B. "c15")
                header_class = header.get_attribute("class")
                col_class_match = re.search(r'\bc(\d+)\b', header_class)

                if col_class_match and activity_id not in quizzes:
                    col_class = f"c{col_class_match.group(1)}"

                    quizzes[activity_id] = {
                        "type": "quiz",
                        "title": title,
                        "url": href,
                        "column_class": col_class,
                        "grades": {}
                    }
                    column_to_quiz[col_class] = activity_id

            elif "mod/assign/view.php?id=" in href:
                activity_id = re.search(r'id=(\d+)', href).group(1)

                # Finde das übergeordnete th-Element
                header = link.find_element(By.XPATH, "./ancestor::th")

                # Extrahiere die Spalten-Klasse (z.B. "c15")
                header_class = header.get_attribute("class")
                col_class_match = re.search(r'\bc(\d+)\b', header_class)

                if col_class_match and activity_id not in quizzes:
                    col_class = f"c{col_class_match.group(1)}"

                    quizzes[activity_id] = {
                        "type": "assignment",
                        "title": title,
                        "url": href,
                        "column_class": col_class,
                        "grades": {}
                    }
                    column_to_quiz[col_class] = activity_id

    except Exception as e:
        print(f"Fehler beim Extrahieren der Activity-Header: {e}")

    # Extrahiere die Benutzerdaten (Zeilen)
    try:
        tbody = table_element.find_element(By.CSS_SELECTOR, "tbody")
        rows = tbody.find_elements(By.CSS_SELECTOR, "tr")

        for row in rows:
            try:
                # Extrahiere User-ID aus dem Link
                user_link = row.find_element(By.CSS_SELECTOR, "th a[href*='user/view.php?id=']")
                user_href = user_link.get_attribute("href")
                user_id_match = re.search(r'id=(\d+)', user_href)
                if not user_id_match:
                    continue
                user_id = user_id_match.group(1)

                # Finde alle Bewertungs-Zellen in dieser Zeile
                grade_cells = row.find_elements(By.CSS_SELECTOR, "td")

                # Durchlaufe alle Zellen und versuche, Bewertungen zu extrahieren
                for cell in grade_cells:
                    try:
                        # Extrahiere die Spalten-Klasse aus der Zelle
                        cell_class = cell.get_attribute("class")
                        col_class_match = re.search(r'\bc(\d+)\b', cell_class)

                        if not col_class_match:
                            continue

                        col_class = f"c{col_class_match.group(1)}"

                        # Prüfe ob diese Spalte ein Quiz/Assignment ist
                        if col_class in column_to_quiz:
                            activity_id = column_to_quiz[col_class]

                            # Extrahiere die Bewertung aus der Zelle
                            grade_text = cell.text.strip()

                            # Entferne "Zellaktionen" und andere Menü-Texte
                            grade_text = grade_text.split('\n')[0].strip()

                            # Speichere die Bewertung für diese Aktivität und diesen Benutzer
                            quizzes[activity_id]["grades"][user_id] = grade_text

                    except (NoSuchElementException, StaleElementReferenceException):
                        continue

            except (NoSuchElementException, StaleElementReferenceException):
                # Keine User-Zeile, überspringe
                continue

    except Exception as e:
        print(f"Fehler beim Extrahieren der Benutzerdaten: {e}")

    return quizzes


def get_singleview_grades(driver, course_id, item_id, base_url, waittime):
    """
    Liest Bewertungen für ein einzelnes Bewertungselement aus dem Moodle-Singleview-Report.
    URL-Muster: /grade/report/singleview/index.php?id={course_id}&item=grade&itemid={item_id}
    Gibt {vollständiger_name: bewertung_str} zurück.
    """
    domain = base_url.split('/report/')[0]
    url = f"{domain}/grade/report/singleview/index.php?id={course_id}&userid=&itemid={item_id}&item=grade&page=0&perpage=0&group=0"
    driver.get(url)

    try:
        WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table#singleview-grades"))
        )
    except TimeoutException:
        print(f"  Singleview-Tabelle für itemid={item_id} nicht gefunden")
        return {}

    grades = {}
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "table#singleview-grades tbody tr")
        for row in rows:
            try:
                user_link = row.find_element(By.CSS_SELECTOR, "th.user a")
                user_href = user_link.get_attribute("href") or ""
                user_id_match = re.search(r'[?&]id=(\d+)', user_href)
                if not user_id_match:
                    continue
                user_id = user_id_match.group(1)
                grade_el = row.find_element(By.CSS_SELECTOR, "td.grade.cell.c2")
                grade_text = grade_el.text.strip()
                if user_id and grade_text:
                    grades[user_id] = grade_text
            except Exception:
                continue
    except Exception as e:
        print(f"  Fehler beim Lesen der Singleview-Daten für itemid={item_id}: {e}")

    return grades


def get_quiz_status(driver, quiz_url, waittime):
    """
    VERALTET: Diese Funktion wird nicht mehr verwendet.
    Verwende stattdessen get_grader_report_data()
    """
    print("[WARNUNG] get_quiz_status ist veraltet. Verwende get_grader_report_data()")
    return []

def get_quiz_submission_times(driver, quiz_url, waittime):
    """
    Extrahiert die submission_time für alle User eines Quiz

    Args:
        driver: Selenium WebDriver
        quiz_url: URL zum Quiz (z.B. "https://lernplattform.bycs.de/mod/quiz/view.php?id=72039961")
        waittime: Wartezeit in Sekunden

    Returns:
        dict: {user_id: submission_time_iso_string}
              Nur User mit mindestens einem Versuch sind enthalten
    """
    submission_times = {}

    # Extrahiere Quiz-ID aus der URL
    quiz_id_match = re.search(r'id=(\d+)', quiz_url)
    if not quiz_id_match:
        print(f"[FEHLER] Konnte Quiz-ID aus URL nicht extrahieren: {quiz_url}")
        return submission_times

    quiz_id = quiz_id_match.group(1)

    # Baue die Report-URL mit Sortierung (absteigend nach Beendet-Zeit)
    report_url = f"https://lernplattform.bycs.de/mod/quiz/report.php?id={quiz_id}&mode=overview&attempts=enrolled_with&onlygraded&group=0&onlyregraded=0&slotmarks=1&tsort=timefinish&tdir=3"

    try:
        driver.get(report_url)
        WebDriverWait(driver, waittime).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception as e:
        print(f"[FEHLER] Konnte Quiz-Report-Seite nicht laden (Quiz {quiz_id}): {e}")
        return submission_times

    try:
        # Warte auf die Tabelle mit den Versuchen
        table_element = WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.ID, "attempts"))
        )
    except TimeoutException:
        # Keine Versuche vorhanden - das ist normal
        return submission_times
    except Exception as e:
        print(f"[FEHLER] Fehler beim Warten auf Tabelle für Quiz {quiz_id}: {e}")
        return submission_times

    try:
        # Ermittle die "Beendet"-Spalte dynamisch aus den Tabellenheadern
        finish_col_class = None
        headers = table_element.find_elements(By.CSS_SELECTOR, "th")
        for header in headers:
            header_text = header.text.strip()
            if "Beendet" in header_text or "timefinish" in (header.get_attribute("data-sortby") or ""):
                col_match = re.search(r'\bc\d+\b', header.get_attribute("class") or "")
                if col_match:
                    finish_col_class = col_match.group(0)
                    break
        if not finish_col_class:
            finish_col_class = "c7"  # Fallback

        # Finde alle Zeilen in der Tabelle (tbody tr)
        tbody = table_element.find_element(By.TAG_NAME, "tbody")
        rows = tbody.find_elements(By.CSS_SELECTOR, "tr")

        # Durchlaufe alle Zeilen
        for row in rows:
            try:
                # Extrahiere User-ID – Fallback-Kette für verschiedene Moodle-Layouts
                user_link = None
                for selector in [
                    "td.cell.c2 a[href*='user/view.php?id=']",
                    "td.cell.c1 a[href*='user/view.php?id=']",
                    "td a[href*='user/view.php?id=']",
                ]:
                    try:
                        user_link = row.find_element(By.CSS_SELECTOR, selector)
                        break
                    except NoSuchElementException:
                        continue

                if not user_link:
                    continue

                user_href = user_link.get_attribute("href")
                user_id_match = re.search(r'id=(\d+)', user_href)

                if not user_id_match:
                    continue

                user_id = user_id_match.group(1)

                # Wenn dieser User bereits erfasst wurde, überspringe (wir wollen nur den neuesten)
                if user_id in submission_times:
                    continue

                # Extrahiere submission_time aus der dynamisch ermittelten "Beendet"-Spalte
                submission_time_cell = None
                submission_time_raw = None

                try:
                    submission_time_cell = row.find_element(By.CSS_SELECTOR, f"td.cell.{finish_col_class}")
                    submission_time_raw = submission_time_cell.text.strip()
                except NoSuchElementException:
                    continue

                if not submission_time_raw or submission_time_raw == "":
                    continue

                # Konvertiere in ISO-Format
                submission_time = parse_german_datetime(submission_time_raw)

                # Speichere nur, wenn erfolgreich geparst
                if submission_time:
                    submission_times[user_id] = submission_time

            except Exception as e:
                # Zeile konnte nicht verarbeitet werden, überspringe
                continue

    except Exception as e:
        print(f"[FEHLER] Fehler beim Extrahieren der Quiz-Submission-Times für Quiz {quiz_id}: {e}")
        import traceback
        print(f"[FEHLER] Traceback: {traceback.format_exc()}")

    return submission_times

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

    print("[FEHLER] Sesskey konnte nach allen Versuchen nicht extrahiert werden")
    return None

# Thread-local storage for WebDriver instances
thread_local = threading.local()
_all_thread_drivers = []
_driver_lock = threading.Lock()

def get_thread_driver(isheadless, username=None, password=None, base_url=None, course_id=None, waittime=10):
    """Get or create a WebDriver instance for the current thread"""
    if not hasattr(thread_local, 'driver'):
        try:
            thread_local.driver = create_webdriver(headless=isheadless)
            with _driver_lock:
                _all_thread_drivers.append(thread_local.driver)
            thread_local.logged_in = False
            thread_local.sesskey = None
        except Exception as e:
            print(f"[FEHLER] Fehler beim Erstellen des WebDrivers: {e}")
            return None

    # Login und sesskey für jeden Thread
    if not thread_local.logged_in and username and password:
        try:
            thread_local.driver.get(f"{base_url}?course={course_id}")

            # Warte bis Seite geladen ist
            WebDriverWait(thread_local.driver, waittime).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

            if "login" in thread_local.driver.current_url:
                login(thread_local.driver, username, password, waittime)

            # Extrahiere sesskey für diesen Thread mit robuster Funktion
            thread_local.sesskey = get_sesskey(thread_local.driver, waittime)

            if thread_local.sesskey:
                thread_local.logged_in = True
                print(f"[OK] Thread-Login erfolgreich, sesskey: {thread_local.sesskey[:10]}...")
            else:
                print("[WARNUNG] Thread-Login abgeschlossen, aber sesskey fehlt")

        except Exception as e:
            print(f"[FEHLER] Fehler beim Thread-Login: {e}")
            thread_local.logged_in = False

    return thread_local.driver

def get_thread_sesskey():
    """Get the sesskey for the current thread"""
    if hasattr(thread_local, 'sesskey'):
        return thread_local.sesskey
    return None

def get_grade_history_time(driver, course_id, grade_item_id, user_id, waittime=10):
    """
    Liest das Datum der letzten Bewertungsänderung aus der Moodle-Bewertungshistorie.
    Wird verwendet, wenn submission_time fehlt aber eine Bewertung vorhanden ist
    (z.B. bei manuell im Notenbuch eingetragenen Bewertungen ohne echte Abgabe).
    URL-Parameter: itemid = grade_item_id, userids = user_id, tsort/tdir = nach Zeit absteigend
    """
    if not grade_item_id or not user_id:
        return None

    url = (
        f"https://lernplattform.bycs.de/grade/report/history/index.php"
        f"?id={course_id}&showreport=1&itemid={grade_item_id}"
        f"&userids={user_id}&tsort=timemodified&tdir=3"
    )

    try:
        driver.get(url)
        # Warte auf Tabellen-Body; falls keine Zeilen, gibt es keine Historie
        WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.gradereport_history"))
        )
        first_cell = driver.find_element(
            By.CSS_SELECTOR, "table.gradereport_history tbody tr:first-child td.c0"
        )
        date_text = first_cell.text.strip()
        if not date_text or date_text in ['-', '']:
            return None
        return parse_german_datetime(date_text)
    except Exception:
        return None


def process_assignment_parallel(assignment, isheadless, waittime, username, password, base_url, course_id, index, total):
    """Process a single assignment in parallel"""
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id, waittime)

        if driver is None:
            print(f"[FEHLER] [{index+1}/{total}] Kein WebDriver verfügbar für Assignment {assignment.get('id', 'unknown')}")
            return assignment.get('id', 'unknown'), [], "all"

        assignment_id = assignment["id"]
        assignment_url = assignment["url"]
        assignment_title = assignment.get("title", f"Assignment {assignment_id}")

        print(f"[{index+1}/{total}] Verarbeite Assignment: {assignment_title[:50]}...")
        print(f"PROGRESS|assignments|{index+1}|{total}")
        sys.stdout.flush()
        start_time = time.time()

        # Extrahiere Gruppierungsinformationen
        groups = get_assignment_groups(driver, assignment_url, waittime)

        # Extrahiere Status
        status = get_assignment_status(driver, assignment_url, waittime)

        # Fallback: Datum aus Bewertungshistorie für Einträge mit Bewertung aber ohne Abgabezeit
        # (passiert bei manuell im Notenbuch eingetragenen Bewertungen)
        grade_item_id = assignment.get("grade_item_id")
        if grade_item_id:
            missing_time_count = 0
            for entry in status:
                grade_val = entry.get("grade", "")
                has_grade = grade_val and grade_val not in ["Keine Bewertung", "-", ""]
                if entry.get("submission_time") is None and has_grade:
                    history_time = get_grade_history_time(
                        driver, course_id, grade_item_id, entry["user_id"], waittime
                    )
                    if history_time:
                        entry["submission_time"] = history_time
                        missing_time_count += 1
            if missing_time_count:
                print(f"  Datum aus Bewertungshistorie ergänzt: {missing_time_count} Einträge")

        duration = time.time() - start_time
        print(f"  Abgeschlossen in {duration:.1f}s ({len(status)} Eintraege, groups: {groups})")
        return assignment_id, status, groups
    except Exception as e:
        import traceback
        try:
            print(f"[FEHLER] Fehler bei Assignment {assignment.get('id', 'unknown')}: {e}")
            print(f"[FEHLER] Traceback: {traceback.format_exc()}")
        except UnicodeEncodeError:
            print(f"[FEHLER] Fehler bei Assignment {assignment.get('id', 'unknown')}: {str(e).encode('ascii', 'replace').decode('ascii')}")
            print(f"[FEHLER] Traceback enthaelt Unicode-Zeichen")
        sys.stdout.flush()
        return assignment.get('id', 'unknown'), [], "all"

def process_checklist_parallel(checklist, isheadless, username, password, base_url, course_id, index, total, waittime=10):
    """Process a single checklist in parallel"""
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id, waittime)

        if driver is None:
            print(f"[FEHLER] [{index+1}/{total}] Kein WebDriver verfügbar für Checklist {checklist.get('id', 'unknown')}")
            return checklist.get('id', 'unknown'), {"required_progress": {}, "all_progress": {}}

        thread_sesskey = get_thread_sesskey()

        if not thread_sesskey:
            print(f"[FEHLER] [{index+1}/{total}] Kein sesskey für Checklist {checklist.get('id', 'unknown')}")
            return checklist.get('id', 'unknown'), {"required_progress": {}, "all_progress": {}}

        checklist_id = checklist["id"]
        checklist_url = checklist["url"]
        checklist_title = checklist.get("title", f"Checklist {checklist_id}")

        print(f"[{index+1}/{total}] Verarbeite Checklist: {checklist_title[:50]}...")
        print(f"PROGRESS|checklists|{index+1}|{total}")
        sys.stdout.flush()
        start_time = time.time()
        progress = get_checklist_progress_optimized(driver, checklist_url, thread_sesskey, course_id)
        duration = time.time() - start_time

        req_count = len(progress.get('required_progress', {}))
        all_count = len(progress.get('all_progress', {}))
        print(f"  [OK] Abgeschlossen in {duration:.1f}s ({req_count} req, {all_count} all)")
        return checklist_id, progress
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        # Encode error details to avoid Unicode issues on Windows
        try:
            print(f"[FEHLER] Fehler bei Checklist {checklist.get('id', 'unknown')}: {e}")
            print(f"[FEHLER] Traceback: {error_details}")
        except UnicodeEncodeError:
            # Fallback: nur ASCII-sichere Ausgabe
            print(f"[FEHLER] Fehler bei Checklist {checklist.get('id', 'unknown')}: {str(e).encode('ascii', 'replace').decode('ascii')}")
            print(f"[FEHLER] Traceback enthaelt Unicode-Zeichen (siehe Logfile)")
        sys.stdout.flush()
        return checklist.get('id', 'unknown'), {"required_progress": {}, "all_progress": {}}

def process_quiz_parallel(quiz, isheadless, waittime, username, password, base_url, course_id, index, total):
    """Process a single quiz in parallel - extracts submission times"""
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id, waittime)

        if driver is None:
            print(f"[FEHLER] [{index+1}/{total}] Kein WebDriver verfügbar für Quiz {quiz.get('id', 'unknown')}")
            return quiz.get('id', 'unknown'), {}

        quiz_id = quiz["id"]
        quiz_url = quiz["url"]
        quiz_title = quiz.get("title", f"Quiz {quiz_id}")

        print(f"[{index+1}/{total}] Verarbeite Quiz: {quiz_title[:50]}...")
        print(f"PROGRESS|quizzes|{index+1}|{total}")
        sys.stdout.flush()
        start_time = time.time()
        submission_times = get_quiz_submission_times(driver, quiz_url, waittime)
        duration = time.time() - start_time
        print(f"  Abgeschlossen in {duration:.1f}s ({len(submission_times)} Eintraege)")
        return quiz_id, submission_times
    except Exception as e:
        import traceback
        try:
            print(f"[FEHLER] Fehler bei Quiz {quiz.get('id', 'unknown')}: {e}")
            print(f"[FEHLER] Traceback: {traceback.format_exc()}")
        except UnicodeEncodeError:
            print(f"[FEHLER] Fehler bei Quiz {quiz.get('id', 'unknown')}: {str(e).encode('ascii', 'replace').decode('ascii')}")
            print(f"[FEHLER] Traceback enthaelt Unicode-Zeichen")
        sys.stdout.flush()
        return quiz.get('id', 'unknown'), {}
    

def get_all_activity_categories(driver, course_id):
    categories_data = {}

    # Lade die Seite nur einmal
    grade_url = f"https://lernplattform.bycs.de/grade/edit/tree/index.php?id={course_id}"
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
            # Bewertungs-ID (data-itemid auf dem TR) – unterscheidet sich von der Activity-ID
            grade_item_id = parent_tr.get_attribute("data-itemid") or None

            full_id = f"grade-item-{category_id}"
            category_tr = driver.find_element(By.ID, full_id)

            # Extrahiere den Kategorienamen aus dem `data-toggle-selectall` Attribut
            category_name = category_tr.find_element(By.CSS_SELECTOR, "input.itemselect").get_attribute("data-toggle-selectall")

            categories_data[activity_id] = {
                "category_id": category_id,
                "category_name": category_name,
                "grade_item_id": grade_item_id
            }

        except Exception as e:
            print(f"Fehler beim Verarbeiten der Aktivität: {e}")

    return categories_data

def get_activity_category(driver, activity_id, course_id, waittime):
    category_data = {"category_id": "-1", "category_name": "nicht bewertet"}
    print(f"Verarbeite Aktivität ID: {activity_id}")

    grade_url = f"https://lernplattform.bycs.de/grade/edit/tree/index.php?id={course_id}"
    driver.get(grade_url)
    
    try:
        # Verwenden Sie WebDriverWait, um sicherzustellen, dass das Element geladen ist
        activity_element = WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f"a[href*='?id={activity_id}'].gradeitemheader"))
        )
        parent_tr = activity_element.find_element(By.XPATH, "./ancestor::tr")
        category_id = parent_tr.get_attribute("data-parent-category")
        grade_item_id = parent_tr.get_attribute("data-itemid") or None

        full_id = f"grade-item-{category_id}"
        category_tr = driver.find_element(By.ID, full_id)

        # Extrahiere den Kategorienamen aus dem `data-toggle-selectall` Attribut
        category_name = category_tr.find_element(By.CSS_SELECTOR, "input.itemselect").get_attribute("data-toggle-selectall")

        category_data["category_id"] = category_id
        category_data["category_name"] = category_name
        category_data["grade_item_id"] = grade_item_id
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
    """Cleanup aller Thread-WebDriver-Instanzen"""
    with _driver_lock:
        for driver in _all_thread_drivers:
            try:
                driver.quit()
            except Exception:
                pass
        _all_thread_drivers.clear()

# Cloud functionality removed

# Cloud upload functionality removed


def main():
    # Startzeit des Skripts
    start_time = time.time()
    print("Starte Mebis-Datenexport...")
    print(f"Startzeit: {datetime.now().strftime('%H:%M:%S')}")
    sys.stdout.flush()

    # Lade Konfiguration über config_manager
    print("Lade Konfiguration...")
    sys.stdout.flush()
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

    print("Erstelle WebDriver...")
    sys.stdout.flush()
    driver = create_webdriver(headless=isheadless)
    driver.get(f"{base_url}?course={course_id}")

    print("Führe Login durch...")
    sys.stdout.flush()
    login(driver, username, password, waittime)

    # Extrahiere den sesskey nach dem Login
    print("Extrahiere Sesskey...")
    sys.stdout.flush()
    sesskey = get_sesskey(driver)
    if not sesskey:
        print("Sesskey konnte nicht extrahiert werden. Überprüfe den Login-Prozess.")
        driver.quit()
        return

    print("Lade Gruppen und Optionen...")
    sys.stdout.flush()
    group_options = get_select_options(driver, "group", waittime)
    activityinclude_options = get_select_options(driver, "activityinclude", waittime)
    activitysection_options = get_select_options(driver, "activitysection", waittime)

    # Erfasse die Aktivitäten einmalig
    print("Erfasse Aktivitäten...")
    sys.stdout.flush()
    activities = get_activity_urls(driver)

    # Ermittle den Pflicht-Status aller Checklisten (vor der Kategorisierung)
    print("Ermittle Pflicht-Status der Checklisten...")
    sys.stdout.flush()
    checklists_mandatory = get_checklists_mandatory_status(driver, course_id)
    print(f"  Pflicht-Status für {len(checklists_mandatory)} Checklisten ermittelt")

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

            # Füge is_mandatory zu Checklisten hinzu
            if activity_type == "checklists":
                activity["is_mandatory"] = checklists_mandatory.get(activity["id"], False)

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
    print(f"PROGRESS|assignments|0|{len(activities['assignments'])}")
    sys.stdout.flush()
    assignments_status = {}
    assignments_groups = {}

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
                assignment_id, status, groups = future.result()
                assignments_status[assignment_id] = status
                assignments_groups[assignment_id] = groups

    # Füge die "groups"-Informationen zu den Assignment-Objekten in activities_by_category hinzu
    print("Aktualisiere Gruppierungsinformationen in activities_by_category...")
    sys.stdout.flush()
    for category in activities_by_category:
        if "assignments" in category:
            for assignment in category["assignments"]:
                assignment_id = assignment["id"]
                if assignment_id in assignments_groups:
                    assignment["groups"] = assignments_groups[assignment_id]
                else:
                    assignment["groups"] = "all"  # Standard-Fallback

    # Note: user_status is handled by dashboard_backend.py using existing user.activities data
    # No need to duplicate data structure here

    print("Analysiere Status Checkliste (parallel)")
    print(f"PROGRESS|checklists|0|{len(activities['checklists'])}")
    sys.stdout.flush()
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

    print("Analysiere Quiz Submission Times (parallel)")
    print(f"PROGRESS|quizzes|0|{len(activities['quizzes'])}")
    sys.stdout.flush()
    quiz_submission_times = {}

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
                quiz_id, submission_times = future.result()
                quiz_submission_times[quiz_id] = submission_times

    print("Quiz-Bewertungen werden aus Grader-Report extrahiert (siehe unten bei Gruppen-Verarbeitung)")
    sys.stdout.flush()

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

    # Extrahiere Grader-Report-Daten (einmalig für alle Gruppen mit group=0)
    print("\nExtrahiere Bewertungsdaten aus Grader-Report (alle Gruppen)...")
    sys.stdout.flush()
    grader_data = get_grader_report_data(driver, course_id, "0", waittime)
    print(f"  Gefunden: {len(grader_data)} Aktivitäten mit Bewertungen")

    # Manuelle Elemente aus .env-Konfiguration (MANUAL_GRADE_ITEM_IDS)
    tree_manual_ids = config_manager.get_manual_grade_item_ids()
    print(f"  {len(tree_manual_ids)} manuelle Bewertungselemente aus Konfiguration: {list(tree_manual_ids.values())}")

    # Bewertungen für manuelle Elemente via Singleview holen (direkt mit Schülernamen)
    manual_grade_items = {}
    for item_id, title in tree_manual_ids.items():
        print(f"  Hole Singleview-Bewertungen für '{title}' (itemid={item_id})...")
        sys.stdout.flush()
        user_grades = get_singleview_grades(driver, course_id, item_id, base_url, waittime)
        manual_grade_items[item_id] = {
            "title": title,
            "user_grades": user_grades
        }
        print(f"    -> {len(user_grades)} Bewertungen gelesen")
    data["manual_grade_items"] = manual_grade_items
    if manual_grade_items:
        titles = [v["title"] for v in manual_grade_items.values()]
        print(f"  Manuelle Bewertungselemente: {titles}")

    for group in data["groups"]:

        for user in group["users"]:
            user["activities"] = {
                "assignments": [],
                "checklists": [],
                "feedbacks": [],
                "quizzes": [],
                "manual_grades": []
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
                        "is_mandatory": checklists_mandatory.get(checklist["id"], False),
                        "progress": {
                            "required_progress": required_progress,
                            "all_progress": all_progress
                        }
                        # ,
                        # "category_id": checklist.get("category_id"),
                        # "category_name": checklist.get("category_name")
                    })

            # Verwende die Grader-Report-Daten für Quiz-Status
            for quiz in activities["quizzes"]:
                quiz_id = quiz["id"]
                # Suche Quiz-Daten im Grader-Report
                if quiz_id in grader_data and user["id"] in grader_data[quiz_id]["grades"]:
                    grade = grader_data[quiz_id]["grades"][user["id"]]

                    # Bestimme Status basierend auf der Bewertung
                    if grade == "-" or grade == "" or "Nicht bewertet" in grade:
                        status = "Nicht eingereicht"
                        status2 = "Nicht bewertet"
                    else:
                        status = "Zur Bewertung abgegeben"
                        status2 = "Bewertet"

                    # Hole submission_time aus den parallel erfassten Daten
                    submission_time = None
                    if quiz_id in quiz_submission_times and user["id"] in quiz_submission_times[quiz_id]:
                        submission_time = quiz_submission_times[quiz_id][user["id"]]

                    user["activities"]["quizzes"].append({
                        "id": quiz_id,
                        "status": {
                            "user_id": user["id"],
                            "status": status,
                            "status2": status2,
                            "submission": "Quiz abgeschlossen" if status2 == "Bewertet" else "Nicht abgeschlossen",
                            "submission_time": submission_time,
                            "grade_options": [],
                            "grade": grade
                        },
                        "category_id": quiz.get("category_id"),
                        "category_name": quiz.get("category_name")
                    })

            # Füge manuelle Bewertungselemente zum User hinzu
            for item_id, item_data in manual_grade_items.items():
                grade = item_data["user_grades"].get(user["id"])
                user["activities"]["manual_grades"].append({
                    "id": item_id,
                    "title": item_data["title"],
                    "grade": grade  # None wenn keine Bewertung vorhanden
                })

    # =====================================================
    # VALIDIERUNG: Prüfe ob kritische Daten vorhanden sind
    # =====================================================
    print("\n" + "="*60)
    print("VALIDIERUNG DER EXPORTIERTEN DATEN")
    print("="*60)

    validation_errors = []

    # Prüfe Aktivitäten
    if not activities["assignments"] and not activities["checklists"] and not activities["quizzes"]:
        validation_errors.append("FEHLER: Keine Aktivitäten gefunden (keine Assignments, Checklisten oder Quizzes)")

    # Prüfe Gruppen
    if not data["groups"]:
        validation_errors.append("FEHLER: Keine Gruppen gefunden")
    else:
        # Prüfe ob Gruppen Benutzer haben
        total_users_check = sum(len(group["users"]) for group in data["groups"])
        if total_users_check == 0:
            validation_errors.append("FEHLER: Keine Benutzer in Gruppen gefunden")

    # Prüfe Kategorien
    if not activities_by_category:
        validation_errors.append("WARNUNG: Keine Kategorien gefunden")

    # Prüfe Checklisten-Progress
    if activities["checklists"] and not checklist_progress:
        validation_errors.append("FEHLER: Checklisten gefunden, aber keine Fortschrittsdaten")

    # Prüfe Assignments-Status
    if activities["assignments"] and not assignments_status:
        validation_errors.append("FEHLER: Assignments gefunden, aber keine Status-Daten")

    # Ausgabe der Validierungsergebnisse
    if validation_errors:
        print("\n[!] VALIDIERUNGSFEHLER GEFUNDEN:")
        sys.stdout.flush()  # Stelle sicher, dass Backend diese Meldung sieht
        for error in validation_errors:
            print(f"  - {error}")
            sys.stdout.flush()

        # Unterscheide zwischen Fehlern und Warnungen
        critical_errors = [e for e in validation_errors if e.startswith("FEHLER:")]
        if critical_errors:
            print("\n" + "="*60)
            print("[ABBRUCH] Kritische Fehler gefunden!")
            print("Export wird NICHT gespeichert.")
            print("="*60)
            sys.stdout.flush()
            print("\nBitte prüfen Sie:")
            print("  1. Die Netzwerkverbindung zu Mebis")
            print("  2. Die Login-Credentials in der Konfiguration")
            print("  3. Die Kurs-ID in der Konfiguration")
            print("  4. Die Logausgaben auf weitere Hinweise")
            sys.stdout.flush()
            driver.quit()
            sys.exit(1)
        else:
            print("\n[INFO] Nur Warnungen gefunden, Export wird fortgesetzt.")
            sys.stdout.flush()
    else:
        print("[OK] Alle Validierungen bestanden")
        sys.stdout.flush()

    print("="*60 + "\n")

    print("Speichere Daten lokal...")
    save_start_time = time.time()

    # Zeitstempel hinzufügen
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_filename = f'output_{timestamp}.json'

    # Hole Export-Ordner aus Konfiguration
    export_folder = config_manager.get_export_folder()

    # Make export_folder absolute if it's relative
    if not os.path.isabs(export_folder):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        export_folder = os.path.join(project_root, export_folder)

    local_filename = os.path.join(export_folder, json_filename)

    try:
        os.makedirs(export_folder, exist_ok=True)
        with open(local_filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        save_duration = time.time() - save_start_time
        print(f"Daten erfolgreich lokal gespeichert in {save_duration:.1f}s: {local_filename}")
        save_success = True

        # =====================================================
        # GRÖSSENVERGLEICH: Prüfe ob neuer Export kleiner ist
        # =====================================================
        new_file_size = os.path.getsize(local_filename)
        print(f"\nGröße der neuen Datei: {new_file_size:,} bytes ({new_file_size / 1024:.1f} KB)")

        # Finde vorherige Export-Dateien
        import glob
        previous_exports = glob.glob(os.path.join(export_folder, 'output_*.json'))
        previous_exports = [f for f in previous_exports if f != local_filename]  # Schließe neue Datei aus

        if previous_exports:
            # Sortiere nach Erstellungsdatum (neueste zuerst)
            previous_exports.sort(key=os.path.getctime, reverse=True)
            latest_previous = previous_exports[0]
            previous_file_size = os.path.getsize(latest_previous)

            print(f"Größe der vorherigen Datei: {previous_file_size:,} bytes ({previous_file_size / 1024:.1f} KB)")
            print(f"Vorherige Datei: {os.path.basename(latest_previous)}")

            # Berechne Differenz
            size_diff = new_file_size - previous_file_size
            size_diff_percent = (size_diff / previous_file_size) * 100 if previous_file_size > 0 else 0

            print(f"Differenz: {size_diff:+,} bytes ({size_diff_percent:+.1f}%)")

            # Warnung bei kleineren Exporten
            if new_file_size < previous_file_size:
                print("\n" + "="*60)
                print("⚠️  WARNUNG: NEUER EXPORT IST KLEINER!")
                print("="*60)
                sys.stdout.flush()
                print(f"Der neue Export ist {abs(size_diff):,} bytes ({abs(size_diff_percent):.1f}%) kleiner.")
                print(f"Dies könnte auf einen unvollständigen Export hinweisen.")
                print("")
                print(f"Neue Datei:      {new_file_size:>12,} bytes  {os.path.basename(local_filename)}")
                print(f"Vorherige Datei: {previous_file_size:>12,} bytes  {os.path.basename(latest_previous)}")
                print("")
                sys.stdout.flush()

                # Prüfe ob stdin interaktiv ist (Terminal vorhanden)
                is_interactive = sys.stdin.isatty() if hasattr(sys.stdin, 'isatty') else False

                if is_interactive:
                    # Interaktiver Modus: Frage Benutzer
                    print("[INTERAKTIV] Sie werden um Bestätigung gebeten.")
                    sys.stdout.flush()
                    try:
                        response = input("Möchten Sie den neuen (kleineren) Export behalten? (j/n): ").strip().lower()
                        if response not in ['j', 'ja', 'y', 'yes']:
                            print("\n[ABBRUCH] Export wird verworfen...")
                            os.remove(local_filename)
                            print(f"Datei gelöscht: {local_filename}")
                            print("Der vorherige Export bleibt erhalten.")
                            sys.stdout.flush()
                            save_success = False
                        else:
                            print("\n[OK] Neuer Export wird behalten.")
                            sys.stdout.flush()
                    except (KeyboardInterrupt, EOFError):
                        print("\n\n[ABBRUCH] Export wird verworfen...")
                        os.remove(local_filename)
                        print(f"Datei gelöscht: {local_filename}")
                        sys.stdout.flush()
                        save_success = False
                else:
                    # Nicht-interaktiver Modus: Ablehnen wenn >1% kleiner (sollte nicht vorkommen)
                    if abs(size_diff_percent) > 1:
                        print("[NICHT-INTERAKTIV] Export ist kleiner als vorher – wird automatisch abgelehnt.")
                        print("\n[ABBRUCH] Export wird verworfen (automatisch)...")
                        sys.stdout.flush()
                        os.remove(local_filename)
                        print(f"Datei gelöscht: {local_filename}")
                        print("Der vorherige Export bleibt erhalten.")
                        sys.stdout.flush()
                        save_success = False
                    else:
                        print(f"[NICHT-INTERAKTIV] Kleinerer Export akzeptiert (nur {abs(size_diff_percent):.1f}% Differenz)")
                        sys.stdout.flush()

                print("="*60)
                sys.stdout.flush()
            elif size_diff_percent > 50:
                print("\n[INFO] Export ist signifikant größer (+{:.1f}%). Dies ist normal bei mehr Daten.".format(size_diff_percent))
            else:
                print("\n[OK] Dateigröße ist plausibel.")
        else:
            print("\n[INFO] Kein vorheriger Export gefunden, Größenvergleich übersprungen.")

    except Exception as e:
        print(f"Lokale Speicherung fehlgeschlagen: {e}")
        save_success = False

    # Cleanup: Schließe alle WebDriver-Instanzen
    driver.quit()

    # Cleanup aller Thread-spezifischen WebDriver
    cleanup_thread_drivers()

    # Endzeit des Skripts
    end_time = time.time()
    duration = end_time - start_time
    duration_minutes = duration / 60  # Umrechnung von Sekunden in Minuten

    # Performance-Statistiken
    total_activities = len(activities["assignments"]) + len(activities["checklists"]) + len(activities["quizzes"])
    total_groups = len(data["groups"])
    total_users = sum(len(group["users"]) for group in data["groups"])

    print("\n" + "="*60)
    if save_success:
        print("EXPORT ERFOLGREICH ABGESCHLOSSEN")
    else:
        print("EXPORT FEHLGESCHLAGEN ODER ABGEBROCHEN")
    print("="*60)
    print(f"Gesamtdauer: {duration_minutes:.2f} Minuten ({duration:.1f} Sekunden)")
    print(f"Aktivitaeten: {total_activities} ({len(activities['assignments'])} Assignments, {len(activities['checklists'])} Checklists, {len(activities['quizzes'])} Quizzes)")
    print(f"Gruppen: {total_groups} mit insgesamt {total_users} Benutzern")
    if total_activities > 0:
        print(f"Durchschnitt: {(duration / total_activities):.1f}s pro Aktivitaet")
    if save_success:
        print(f"Lokale Datei: {local_filename}")
    else:
        print(f"[FEHLER] Export wurde nicht gespeichert oder abgebrochen")
    print(f"Endzeit: {datetime.now().strftime('%H:%M:%S')}")
    print("="*60)

    # Beende mit Fehlercode wenn Export fehlgeschlagen ist
    if not save_success:
        sys.exit(1)

if __name__ == "__main__":
    main()





    