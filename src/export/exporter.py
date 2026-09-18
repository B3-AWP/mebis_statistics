import os
import sys
import argparse

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
from bs4 import BeautifulSoup
import io
import functools

# Sichere Konfiguration
from config.config_manager import config_manager
from config.logger_config import get_logger

logger = get_logger('exporter')

# Checklisten-Export deaktivieren (True = exportieren, False = überspringen)
EXPORT_CHECKLISTS = False

# TensorFlow-Logstufe auf ERROR setzen
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


# =====================================================
# Phasen-Timer für Performance-Analyse
# =====================================================
class PhaseTimer:
    """Sammelt Timing-Daten für jede Export-Phase"""

    def __init__(self):
        self.phases = []
        self._current_phase = None
        self._current_start = None

    def start(self, name):
        """Startet eine neue Phase"""
        if self._current_phase:
            self.stop()
        self._current_phase = name
        self._current_start = time.time()
        logger.info(f"--- Phase: {name} ---")

    @staticmethod
    def format_duration(seconds):
        """Formatiert Sekunden: ab 60s in Minuten, sonst Sekunden"""
        if seconds >= 60:
            minutes = seconds / 60
            return f"{minutes:.1f}min"
        return f"{seconds:.1f}s"

    def stop(self, details=None):
        """Stoppt die aktuelle Phase und speichert die Dauer"""
        if not self._current_phase:
            return
        duration = time.time() - self._current_start
        entry = {
            "name": self._current_phase,
            "duration": duration,
        }
        if details:
            entry.update(details)
        self.phases.append(entry)
        detail_str = ""
        if details:
            detail_str = " | " + ", ".join(f"{k}={v}" for k, v in details.items())
        logger.info(f"  Phase '{self._current_phase}' abgeschlossen in {self.format_duration(duration)}{detail_str}")
        self._current_phase = None
        self._current_start = None

    def summary(self):
        """Gibt eine Zusammenfassung aller Phasen aus"""
        logger.info("")
        logger.info("=" * 65)
        logger.info("PHASEN-TIMING ZUSAMMENFASSUNG")
        logger.info("-" * 65)
        logger.info(f"{'Phase':<35} {'Dauer':>8} {'Details'}")
        logger.info("-" * 65)
        total = 0
        for p in self.phases:
            dur = p["duration"]
            total += dur
            extras = {k: v for k, v in p.items() if k not in ("name", "duration")}
            detail_str = ", ".join(f"{k}={v}" for k, v in extras.items()) if extras else ""
            logger.info(f"  {p['name']:<33} {self.format_duration(dur):>8}  {detail_str}")
        logger.info("-" * 65)
        logger.info(f"  {'GESAMT':<33} {self.format_duration(total):>8}")
        logger.info("=" * 65)


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
                        logger.warning(f"[RETRY] {func.__name__} Versuch {attempt+1}/{max_retries} "
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
            "%d.%m.%Y %H:%M",         # "09.01.2026 14:30" (Singleview-Format mit Zeit)
            "%d.%m.%Y",               # "09.01.2026" (Singleview-Format ohne Zeit)
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(datetime_str_en, fmt)
                return dt.isoformat()
            except ValueError:
                continue

        # Wenn kein Format passt
        logger.warning(f"Kein Datumsformat erkannt für '{datetime_str}' – wird ignoriert")
        return None

    except Exception as e:
        logger.warning(f"Fehler beim Parsen der Zeitangabe '{datetime_str}': {e}")
        return None

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
            logger.info("Visibility fehlgeschlagen, versuche presence_of_element...")
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
        logger.error(f"Login fehlgeschlagen: {e}")
        import traceback
        try:
            logger.error(f"Traceback: {traceback.format_exc()}")
        except UnicodeEncodeError:
            logger.error("Traceback enthaelt Unicode-Zeichen")
        raise

def get_select_options(driver, select_name, waittime):
    try:
        select_element = WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.NAME, select_name))
        )
        options = select_element.find_elements(By.TAG_NAME, "option")
        return [{"value": option.get_attribute("value"), "name": option.text} for option in options]
    except TimeoutException:
        logger.error(f"Select '{select_name}' nicht gefunden nach {waittime}s")
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
        logger.error(f"Benutzer für Gruppe {group_value} nicht ladbar: {e}")
        return []

def get_user_ids_from_group_fast(session, group_value, base_url, course_id):
    """Lädt User-IDs via requests+BeautifulSoup statt Selenium (viel schneller)"""
    try:
        url = f"{base_url}?course={course_id}&group={group_value}"
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        users = []
        for a in soup.select('#completion-progress tbody th[scope="row"] a'):
            href = a.get('href', '')
            m = re.search(r'id=(\d+)', href)
            if m:
                users.append({"id": m.group(1), "name": a.get_text(strip=True)})
        return users
    except Exception as e:
        logger.error(f"Benutzer für Gruppe {group_value} nicht ladbar (fast): {e}")
        return []

def create_requests_session_from_driver(driver):
    """Erstellt eine requests.Session mit den Cookies des Selenium-Drivers"""
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    return session

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
        logger.warning("No activity elements found in completion progress.")
    else:
        logger.info(f"Found {len(activity_elements)} activities in completion progress.")

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
    logger.info("Searching gradebook for additional activities...")
    try:
        # Look for gradebook item headers that might contain additional assignments
        gradebook_elements = driver.find_elements(By.CSS_SELECTOR, "a.gradeitemheader")
        logger.info(f"Found {len(gradebook_elements)} items in gradebook.")

        for element in gradebook_elements:
            href = element.get_attribute("href")
            if href and "mod/assign/view.php?id=" in href:
                activity_id = re.search(r'id=(\d+)', href).group(1)
                if activity_id not in activity_ids_found:
                    title = element.text or element.get_attribute("title") or f"Assignment {activity_id}"
                    activity_urls["assignments"].append({"id": activity_id, "title": title, "url": href})
                    activity_ids_found.add(activity_id)
                    logger.info(f"Found additional assignment in gradebook: {activity_id} - {title}")
            elif href and "mod/checklist/view.php?id=" in href:
                activity_id = re.search(r'id=(\d+)', href).group(1)
                if activity_id not in activity_ids_found:
                    title = element.text or element.get_attribute("title") or f"Checklist {activity_id}"
                    activity_urls["checklists"].append({"id": activity_id, "title": title, "url": href})
                    activity_ids_found.add(activity_id)
                    logger.info(f"Found additional checklist in gradebook: {activity_id} - {title}")
            elif href and "mod/feedback/view.php?id=" in href:
                activity_id = re.search(r'id=(\d+)', href).group(1)
                if activity_id not in activity_ids_found:
                    title = element.text or element.get_attribute("title") or f"Feedback {activity_id}"
                    activity_urls["feedbacks"].append({"id": activity_id, "title": title, "url": href})
                    activity_ids_found.add(activity_id)
                    logger.info(f"Found additional feedback in gradebook: {activity_id} - {title}")
            elif href and "mod/quiz/view.php?id=" in href:
                activity_id = re.search(r'id=(\d+)', href).group(1)
                if activity_id not in activity_ids_found:
                    title = element.text or element.get_attribute("title") or f"Quiz {activity_id}"
                    activity_urls["quizzes"].append({"id": activity_id, "title": title, "url": href})
                    activity_ids_found.add(activity_id)
                    logger.info(f"Found additional quiz in gradebook: {activity_id} - {title}")

    except Exception as e:
        logger.error(f"Error searching gradebook for additional activities: {e}")

    logger.info(f"Total activities found: {len(activity_urls['assignments'])} assignments, {len(activity_urls['checklists'])} checklists, {len(activity_urls['feedbacks'])} feedbacks, {len(activity_urls['quizzes'])} quizzes")
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
        logger.error(f"Fehler beim Laden der Checklisten-Übersicht: {e}")

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
        logger.error(f"Fehler beim Extrahieren der Gruppierungsinformationen: {e}")
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
        logger.warning("Spalte 'Endbewertung' nicht gefunden.")
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
    Extrahiert alle Bewertungsdaten aus der Grader-Report-Seite.
    Nutzt JavaScript-Extraktion statt einzelner Selenium-Aufrufe (>50x schneller).
    """
    grader_url = f"https://lernplattform.bycs.de/grade/report/grader/index.php?id={course_id}&groupsearchvalue=&group={group_id}"
    driver.get(grader_url)

    try:
        WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.gradereport-grader-table#user-grades"))
        )
    except TimeoutException:
        logger.warning(f"Grader-Report-Tabelle für Kurs {course_id}, Gruppe {group_id} nicht gefunden")
        return {}

    # Extrahiere alle Daten in einem einzigen JavaScript-Aufruf
    try:
        result = driver.execute_script("""
            var table = document.querySelector('table.gradereport-grader-table#user-grades');
            if (!table) return null;

            // 1. Header: Spalten-Mapping erstellen (col_class -> activity info)
            var columnMap = {};
            var headers = table.querySelectorAll('th a.gradeitemheader');
            headers.forEach(function(link) {
                var href = link.getAttribute('href') || '';
                var title = link.getAttribute('title') || link.textContent;
                var th = link.closest('th');
                if (!th) return;
                var classMatch = (th.className || '').match(/\\b(c\\d+)\\b/);
                if (!classMatch) return;
                var colClass = classMatch[1];

                var idMatch = href.match(/id=(\\d+)/);
                if (!idMatch) return;

                var type = null;
                if (href.indexOf('mod/quiz/') >= 0) type = 'quiz';
                else if (href.indexOf('mod/assign/') >= 0) type = 'assignment';
                if (!type) return;

                if (!columnMap[colClass]) {
                    columnMap[colClass] = {id: idMatch[1], type: type, title: title, url: href};
                }
            });

            // 2. Ergebnis-Struktur initialisieren
            var activities = {};
            Object.keys(columnMap).forEach(function(col) {
                var info = columnMap[col];
                activities[info.id] = {
                    type: info.type, title: info.title,
                    url: info.url, column_class: col, grades: {}
                };
            });

            // 3. Hilfsfunktion: Notentext aus Zelle extrahieren
            //    Moodle 4.x Zellen enthalten Dropdown-Buttons und Menüs neben der Note.
            //    Strategie: Nur direkte Text-Nodes der Zelle lesen (keine Button/Dropdown-Texte)
            function extractGradeText(cell) {
                // Versuch 1: Suche ein dediziertes Noten-Element
                var gradeEl = cell.querySelector('.gradevalue, .gradetext');
                if (gradeEl) return gradeEl.textContent.trim();

                // Versuch 2: Sammle nur direkte Text-Nodes der Zelle (ignoriere Buttons/Dropdowns)
                var text = '';
                for (var i = 0; i < cell.childNodes.length; i++) {
                    var node = cell.childNodes[i];
                    if (node.nodeType === 3) { // TEXT_NODE
                        text += node.textContent;
                    }
                }
                text = text.trim();
                if (text) return text;

                // Versuch 3: Fallback - gesamten textContent nehmen, aber Dropdown-Text entfernen
                var clone = cell.cloneNode(true);
                var dropdowns = clone.querySelectorAll('.dropdown, button, .dropdown-menu, [role="menu"]');
                dropdowns.forEach(function(el) { el.remove(); });
                text = clone.textContent.trim();
                if (text) return text;

                // Versuch 4: Letzter Fallback - ersten sichtbaren Text nehmen
                return (cell.textContent || '').replace(/Zellaktionen/g, '').trim().split('\\n')[0].trim();
            }

            // 4. Zeilen durchlaufen: User-Bewertungen extrahieren
            var rows = table.querySelectorAll('tbody tr');
            rows.forEach(function(row) {
                var userLink = row.querySelector('th a[href*="user/view.php?id="]');
                if (!userLink) return;
                var userMatch = (userLink.getAttribute('href') || '').match(/id=(\\d+)/);
                if (!userMatch) return;
                var userId = userMatch[1];

                var cells = row.querySelectorAll('td');
                cells.forEach(function(cell) {
                    var cm = (cell.className || '').match(/\\b(c\\d+)\\b/);
                    if (!cm || !columnMap[cm[1]]) return;
                    var text = extractGradeText(cell);
                    activities[columnMap[cm[1]].id].grades[userId] = text;
                });
            });

            return activities;
        """)

        if result is None:
            logger.warning("JavaScript-Extraktion lieferte kein Ergebnis")
            return {}

        # Debug-Logging: Zeige Stichprobe der extrahierten Daten
        total_grades = sum(len(a.get("grades", {})) for a in result.values())
        non_empty = sum(1 for a in result.values() for g in a.get("grades", {}).values() if g and g != "-")
        logger.info(f"  Grader-Report: {len(result)} Aktivitäten, {total_grades} Grade-Einträge, {non_empty} mit Bewertung")
        # Zeige erste nicht-leere Note als Beispiel
        for aid, adata in result.items():
            for uid, grade in adata.get("grades", {}).items():
                if grade and grade != "-":
                    logger.info(f"  Beispiel: Aktivität {aid} ({adata.get('type')}), User {uid}: '{grade}'")
                    break
            else:
                continue
            break

        return result

    except Exception as e:
        logger.error(f"Fehler bei JavaScript-Extraktion des Grader-Reports: {e}")
        return {}


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
        logger.warning(f"  Singleview-Tabelle für itemid={item_id} nicht gefunden")
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
        logger.error(f"  Fehler beim Lesen der Singleview-Daten für itemid={item_id}: {e}")

    return grades


def get_quiz_status(driver, quiz_url, waittime):
    """
    VERALTET: Diese Funktion wird nicht mehr verwendet.
    Verwende stattdessen get_grader_report_data()
    """
    logger.warning("get_quiz_status ist veraltet. Verwende get_grader_report_data()")
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
        logger.error(f"Konnte Quiz-ID aus URL nicht extrahieren: {quiz_url}")
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
        logger.error(f"Konnte Quiz-Report-Seite nicht laden (Quiz {quiz_id}): {e}")
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
        logger.error(f"Fehler beim Warten auf Tabelle für Quiz {quiz_id}: {e}")
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
        logger.error(f"Fehler beim Extrahieren der Quiz-Submission-Times für Quiz {quiz_id}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

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
                logger.warning(f"Sesskey gefunden, aber leer (Versuch {attempt + 1}/{max_retries})")
                time.sleep(1)

        except TimeoutException:
            logger.warning(f"Timeout beim Warten auf sesskey (Versuch {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2)
        except Exception as e:
            logger.error(f"Fehler beim Extrahieren des sesskey (Versuch {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)

    logger.error("Sesskey konnte nach allen Versuchen nicht extrahiert werden")
    return None

# Thread-local storage for WebDriver instances
thread_local = threading.local()
_all_thread_drivers = []
_driver_lock = threading.Lock()

def get_thread_driver(isheadless, username=None, password=None, base_url=None, course_id=None, waittime=10):
    """Get or create a WebDriver instance for the current thread.
    Thread-Driver werden wiederverwendet wenn der Thread bereits eingeloggt ist."""
    if not hasattr(thread_local, 'driver'):
        try:
            thread_local.driver = create_webdriver(headless=isheadless)
            with _driver_lock:
                _all_thread_drivers.append(thread_local.driver)
            thread_local.logged_in = False
            thread_local.sesskey = None
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des WebDrivers: {e}")
            return None

    # Login nur wenn noch nicht eingeloggt
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
                logger.info(f"Thread-Login erfolgreich, sesskey: {thread_local.sesskey[:10]}...")
            else:
                logger.warning("Thread-Login abgeschlossen, aber sesskey fehlt")

        except Exception as e:
            logger.error(f"Fehler beim Thread-Login: {e}")
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


def get_singleview_feedback_dates(driver, course_id, grade_item_id, waittime):
    """
    Liest Feedback-Datumsangaben aus der Singleview-Seite für ein Assignment.
    itemid = grade_item_id (BewertungsID), nicht die Assignment-Modul-ID.
    Gibt ein Dict {user_id: feedback_date_iso} zurück.
    Nur Einträge mit tatsächlichem Datum werden aufgenommen.
    """
    url = (
        f"https://lernplattform.bycs.de/grade/report/singleview/index.php"
        f"?id={course_id}&userid=0&itemid={grade_item_id}&item=grade&page=0&perpage=0"
    )
    try:
        driver.get(url)
        WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table#singleview-grades"))
        )
    except TimeoutException:
        logger.warning(f"Singleview-Tabelle für grade_item_id {grade_item_id} nicht gefunden.")
        return {}

    feedback_dates = {}
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "table#singleview-grades tbody tr")
        logger.info(f"  Singleview: {len(rows)} Zeilen für grade_item_id {grade_item_id}")

        for row in rows:
            # UserID aus dem ersten User-Link in der Zeile (Spalte c0)
            try:
                user_link = row.find_element(By.CSS_SELECTOR, "a[href*='user/view.php?id=']")
                href = user_link.get_attribute("href") or ""
                uid_match = re.search(r'user/view\.php\?id=(\d+)', href)
                if not uid_match:
                    continue
                user_id = uid_match.group(1)
            except NoSuchElementException:
                continue

            # Feedback-Text aus Spalte c4:
            # Moodle rendert den Wert je nach Modus als textarea, input oder sichtbaren Text
            feedback_text = None
            try:
                feedback_cell = row.find_element(By.CSS_SELECTOR, "td.cell.c4")
                # 1. Versuch: sichtbarer Text (read-only Ansicht)
                feedback_text = feedback_cell.text.strip()
                # 2. Versuch: textarea-Inhalt (edit-Modus)
                if not feedback_text:
                    try:
                        ta = feedback_cell.find_element(By.TAG_NAME, "textarea")
                        feedback_text = ta.get_attribute("value") or ""
                    except NoSuchElementException:
                        pass
                # 3. Versuch: input-Wert
                if not feedback_text:
                    try:
                        inp = feedback_cell.find_element(By.CSS_SELECTOR, "input[type='text']")
                        feedback_text = inp.get_attribute("value") or ""
                    except NoSuchElementException:
                        pass
            except NoSuchElementException:
                continue

            if not feedback_text:
                continue

            feedback_date = parse_german_datetime(feedback_text.strip())
            if feedback_date:
                feedback_dates[user_id] = feedback_date

    except Exception as e:
        logger.error(f"Fehler beim Parsen der Singleview für grade_item_id {grade_item_id}: {e}")

    logger.info(f"  Singleview: {len(feedback_dates)} Feedback-Daten extrahiert")
    return feedback_dates


def process_assignment_parallel(assignment, isheadless, waittime, username, password, base_url, course_id, index, total):
    """Process a single assignment in parallel"""
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id, waittime)

        if driver is None:
            logger.error(f"[{index+1}/{total}] Kein WebDriver verfügbar für Assignment {assignment.get('id', 'unknown')}")
            return assignment.get('id', 'unknown'), [], "all"

        assignment_id = assignment["id"]
        assignment_url = assignment["url"]
        assignment_title = assignment.get("title", f"Assignment {assignment_id}")

        logger.info(f"[{index+1}/{total}] Verarbeite Assignment: {assignment_title[:50]}...")
        print(f"PROGRESS|assignments|{index+1}|{total}")
        sys.stdout.flush()
        start_time = time.time()

        # Extrahiere Gruppierungsinformationen
        groups = get_assignment_groups(driver, assignment_url, waittime)

        # Extrahiere Status
        status = get_assignment_status(driver, assignment_url, waittime)

        grade_item_id = assignment.get("grade_item_id")

        # Priorität 1: Feedback-Datum aus Singleview überschreibt submission_time
        # itemid = grade_item_id (BewertungsID), nicht assignment_id
        if grade_item_id:
            feedback_dates = get_singleview_feedback_dates(driver, course_id, grade_item_id, waittime)
            feedback_count = 0
            for entry in status:
                fd = feedback_dates.get(entry["user_id"])
                if fd:
                    entry["submission_time"] = fd
                    feedback_count += 1
            if feedback_count:
                logger.info(f"  Datum aus Feedback (Singleview) gesetzt: {feedback_count} Einträge")

        # Priorität 2 (Fallback): Datum aus Bewertungshistorie für Einträge mit Bewertung aber ohne Abgabezeit
        # (passiert bei manuell im Notenbuch eingetragenen Bewertungen)
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
                logger.info(f"  Datum aus Bewertungshistorie ergänzt: {missing_time_count} Einträge")

        duration = time.time() - start_time

        # Detailliertes Ergebnis-Logging
        with_grade = sum(1 for s in status if s.get("grade") and s["grade"] not in ["Keine Bewertung", "-", ""])
        with_time = sum(1 for s in status if s.get("submission_time"))
        logger.info(f"  Abgeschlossen in {duration:.1f}s | {len(status)} User | {with_grade} mit Bewertung | {with_time} mit Zeitstempel | groups={groups}")

        return assignment_id, status, groups
    except Exception as e:
        import traceback
        try:
            logger.error(f"Fehler bei Assignment {assignment.get('id', 'unknown')}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        except UnicodeEncodeError:
            logger.error(f"Fehler bei Assignment {assignment.get('id', 'unknown')}: {str(e).encode('ascii', 'replace').decode('ascii')}")
            logger.error("Traceback enthaelt Unicode-Zeichen")
        sys.stdout.flush()
        return assignment.get('id', 'unknown'), [], "all"

def process_checklist_parallel(checklist, isheadless, username, password, base_url, course_id, index, total, waittime=10):
    """Process a single checklist in parallel"""
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id, waittime)

        if driver is None:
            logger.error(f"[{index+1}/{total}] Kein WebDriver verfügbar für Checklist {checklist.get('id', 'unknown')}")
            return checklist.get('id', 'unknown'), {"required_progress": {}, "all_progress": {}}

        thread_sesskey = get_thread_sesskey()

        if not thread_sesskey:
            logger.error(f"[{index+1}/{total}] Kein sesskey für Checklist {checklist.get('id', 'unknown')}")
            return checklist.get('id', 'unknown'), {"required_progress": {}, "all_progress": {}}

        checklist_id = checklist["id"]
        checklist_url = checklist["url"]
        checklist_title = checklist.get("title", f"Checklist {checklist_id}")

        logger.info(f"[{index+1}/{total}] Verarbeite Checklist: {checklist_title[:50]}...")
        print(f"PROGRESS|checklists|{index+1}|{total}")
        sys.stdout.flush()
        start_time = time.time()
        progress = get_checklist_progress_optimized(driver, checklist_url, thread_sesskey, course_id)
        duration = time.time() - start_time

        req_count = len(progress.get('required_progress', {}))
        all_count = len(progress.get('all_progress', {}))
        logger.info(f"  Abgeschlossen in {duration:.1f}s | {req_count} User mit required_progress | {all_count} User mit all_progress")
        return checklist_id, progress
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        # Encode error details to avoid Unicode issues on Windows
        try:
            logger.error(f"Fehler bei Checklist {checklist.get('id', 'unknown')}: {e}")
            logger.error(f"Traceback: {error_details}")
        except UnicodeEncodeError:
            # Fallback: nur ASCII-sichere Ausgabe
            logger.error(f"Fehler bei Checklist {checklist.get('id', 'unknown')}: {str(e).encode('ascii', 'replace').decode('ascii')}")
            logger.error("Traceback enthaelt Unicode-Zeichen (siehe Logfile)")
        sys.stdout.flush()
        return checklist.get('id', 'unknown'), {"required_progress": {}, "all_progress": {}}

def process_quiz_parallel(quiz, isheadless, waittime, username, password, base_url, course_id, index, total):
    """Process a single quiz in parallel - extracts submission times"""
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id, waittime)

        if driver is None:
            logger.error(f"[{index+1}/{total}] Kein WebDriver verfügbar für Quiz {quiz.get('id', 'unknown')}")
            return quiz.get('id', 'unknown'), {}

        quiz_id = quiz["id"]
        quiz_url = quiz["url"]
        quiz_title = quiz.get("title", f"Quiz {quiz_id}")

        logger.info(f"[{index+1}/{total}] Verarbeite Quiz: {quiz_title[:50]}...")
        print(f"PROGRESS|quizzes|{index+1}|{total}")
        sys.stdout.flush()
        start_time = time.time()
        submission_times = get_quiz_submission_times(driver, quiz_url, waittime)

        # Fallback: Singleview-Feedback-Datum für User ohne submission_time
        grade_item_id = quiz.get("grade_item_id")
        if grade_item_id:
            feedback_dates = get_singleview_feedback_dates(driver, course_id, grade_item_id, waittime)
            fallback_count = 0
            for user_id, feedback_date in feedback_dates.items():
                if user_id not in submission_times:
                    submission_times[user_id] = feedback_date
                    fallback_count += 1
            if fallback_count:
                logger.info(f"  Datum aus Singleview-Feedback ergänzt: {fallback_count} Einträge")

        duration = time.time() - start_time
        logger.info(f"  Abgeschlossen in {duration:.1f}s | {len(submission_times)} submission_times gefunden")
        return quiz_id, submission_times
    except Exception as e:
        import traceback
        try:
            logger.error(f"Fehler bei Quiz {quiz.get('id', 'unknown')}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        except UnicodeEncodeError:
            logger.error(f"Fehler bei Quiz {quiz.get('id', 'unknown')}: {str(e).encode('ascii', 'replace').decode('ascii')}")
            logger.error("Traceback enthaelt Unicode-Zeichen")
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
            logger.warning(f"Fehler beim Verarbeiten der Aktivität: {e}")

    return categories_data

def get_activity_category(driver, activity_id, course_id, waittime):
    category_data = {"category_id": "-1", "category_name": "nicht bewertet"}
    logger.debug(f"Verarbeite Aktivität ID: {activity_id}")

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
        logger.warning(f"Fehler beim Verarbeiten der Aktivität ID {activity_id}: {e}")

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


def main(test_mode=False):
    # Startzeit des Skripts
    start_time = time.time()
    timer = PhaseTimer()

    test_limit = 5  # Anzahl Items pro Typ im Testmodus

    if test_mode:
        logger.info("=" * 60)
        logger.info(f"[TESTMODUS] Export limitiert auf {test_limit} Einträge pro Aktivitätstyp")
        logger.info(f"[TESTMODUS] Dateiname wird 'test_output_...' sein")
        logger.info("=" * 60)

    logger.info("Starte Mebis-Datenexport...")
    logger.info(f"Startzeit: {datetime.now().strftime('%H:%M:%S')}")

    # Lade Konfiguration über config_manager
    timer.start("Konfiguration laden")
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
    timer.stop()

    timer.start("WebDriver erstellen & Login")
    driver = create_webdriver(headless=isheadless)
    driver.get(f"{base_url}?course={course_id}")

    logger.info("Führe Login durch...")
    login(driver, username, password, waittime)

    # Extrahiere den sesskey nach dem Login
    logger.info("Extrahiere Sesskey...")
    sesskey = get_sesskey(driver)
    if not sesskey:
        logger.error("Sesskey konnte nicht extrahiert werden. Überprüfe den Login-Prozess.")
        driver.quit()
        return

    timer.stop()

    timer.start("Gruppen & Optionen laden")
    group_options = get_select_options(driver, "group", waittime)
    activityinclude_options = get_select_options(driver, "activityinclude", waittime)
    activitysection_options = get_select_options(driver, "activitysection", waittime)
    timer.stop({"gruppen": len(group_options)})

    # Erfasse die Aktivitäten einmalig
    timer.start("Aktivitäten erfassen")
    activities = get_activity_urls(driver)
    timer.stop({
        "assignments": len(activities["assignments"]),
        "checklists": len(activities["checklists"]),
        "quizzes": len(activities["quizzes"]),
        "feedbacks": len(activities["feedbacks"]),
    })

    # Im Testmodus: Limitiere auf test_limit Items pro Typ
    if test_mode:
        for act_type in ["assignments", "checklists", "quizzes", "feedbacks"]:
            original_count = len(activities[act_type])
            activities[act_type] = activities[act_type][:test_limit]
            if original_count > test_limit:
                logger.info(f"[TESTMODUS] {act_type}: {original_count} -> {len(activities[act_type])} (limitiert)")

    # Checklisten-Export überspringen wenn deaktiviert
    if not EXPORT_CHECKLISTS:
        activities["checklists"] = []
        logger.info("Checklisten-Export deaktiviert (EXPORT_CHECKLISTS=False) – wird übersprungen")

    # Ermittle den Pflicht-Status aller Checklisten (vor der Kategorisierung)
    if EXPORT_CHECKLISTS:
        timer.start("Checklisten Pflicht-Status")
        checklists_mandatory = get_checklists_mandatory_status(driver, course_id)
        timer.stop({"checklisten": len(checklists_mandatory)})
    else:
        checklists_mandatory = {}

    # Erfasse alle Kategorieninformationen in einem einzigen Aufruf
    timer.start("Kategorien laden")
    all_categories_data = get_all_activity_categories(driver, course_id)
    timer.stop({"kategorien": len(all_categories_data)})

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


    # Geteilter ThreadPool für alle parallelen Phasen (Threads + Browser werden wiederverwendet)
    shared_executor = ThreadPoolExecutor(max_workers=2)

    try:
        timer.start("Assignments verarbeiten (parallel)")
        logger.info(f"Analysiere Status Assignments ({len(activities['assignments'])} Stück)")
        print(f"PROGRESS|assignments|0|{len(activities['assignments'])}")
        sys.stdout.flush()
        assignments_status = {}
        assignments_groups = {}

        if activities["assignments"]:
            future_to_assignment = {
                shared_executor.submit(process_assignment_parallel, assignment, isheadless, waittime, username, password, base_url, course_id, idx, len(activities["assignments"])): assignment
                for idx, assignment in enumerate(activities["assignments"])
            }
            for future in as_completed(future_to_assignment):
                assignment_id, status, groups = future.result()
                assignments_status[assignment_id] = status
                assignments_groups[assignment_id] = groups

        # Ergebnis-Logging für Assignments
        total_assignment_users = sum(len(s) for s in assignments_status.values())
        assignments_missing_grade = 0
        assignments_missing_time = 0
        for aid, statuses in assignments_status.items():
            for s in statuses:
                if not s.get("grade") or s["grade"] in ["Keine Bewertung", "-", ""]:
                    assignments_missing_grade += 1
                if not s.get("submission_time"):
                    assignments_missing_time += 1
        timer.stop({
            "assignments": len(assignments_status),
            "user_einträge": total_assignment_users,
            "ohne_bewertung": assignments_missing_grade,
            "ohne_zeitstempel": assignments_missing_time,
        })

        # Füge die "groups"-Informationen zu den Assignment-Objekten in activities_by_category hinzu
        logger.info("Aktualisiere Gruppierungsinformationen in activities_by_category...")
        for category in activities_by_category:
            if "assignments" in category:
                for assignment in category["assignments"]:
                    assignment_id = assignment["id"]
                    if assignment_id in assignments_groups:
                        assignment["groups"] = assignments_groups[assignment_id]
                    else:
                        assignment["groups"] = "all"  # Standard-Fallback

        timer.start("Checklisten verarbeiten (parallel)")
        logger.info(f"Analysiere Status Checkliste ({len(activities['checklists'])} Stück)")
        print(f"PROGRESS|checklists|0|{len(activities['checklists'])}")
        sys.stdout.flush()
        checklist_progress = {}

        if activities["checklists"]:
            future_to_checklist = {
                shared_executor.submit(process_checklist_parallel, checklist, isheadless, username, password, base_url, course_id, idx, len(activities["checklists"])): checklist
                for idx, checklist in enumerate(activities["checklists"])
            }
            for future in as_completed(future_to_checklist):
                checklist_id, progress = future.result()
                checklist_progress[checklist_id] = progress

        # Ergebnis-Logging für Checklisten
        checklists_empty_req = sum(1 for cp in checklist_progress.values() if not cp.get("required_progress"))
        checklists_empty_all = sum(1 for cp in checklist_progress.values() if not cp.get("all_progress"))
        timer.stop({
            "checklisten": len(checklist_progress),
            "ohne_required": checklists_empty_req,
            "ohne_all": checklists_empty_all,
        })

        timer.start("Quiz Submission Times (parallel)")
        logger.info(f"Analysiere Quiz Submission Times ({len(activities['quizzes'])} Stück)")
        print(f"PROGRESS|quizzes|0|{len(activities['quizzes'])}")
        sys.stdout.flush()
        quiz_submission_times = {}

        if activities["quizzes"]:
            future_to_quiz = {
                shared_executor.submit(process_quiz_parallel, quiz, isheadless, waittime, username, password, base_url, course_id, idx, len(activities["quizzes"])): quiz
                for idx, quiz in enumerate(activities["quizzes"])
            }
            for future in as_completed(future_to_quiz):
                quiz_id, submission_times = future.result()
                quiz_submission_times[quiz_id] = submission_times

        total_quiz_times = sum(len(st) for st in quiz_submission_times.values())
        quizzes_without_times = sum(1 for st in quiz_submission_times.values() if not st)
        timer.stop({
            "quizzes": len(quiz_submission_times),
            "submission_times_gesamt": total_quiz_times,
            "quizzes_ohne_times": quizzes_without_times,
        })

    finally:
        shared_executor.shutdown(wait=True)
        # Thread-Driver sofort aufräumen um Speicher freizugeben vor dem Grader-Report
        cleanup_thread_drivers()
        logger.info("Thread-Driver aufgeräumt (Speicher freigegeben)")

    logger.info("Quiz-Bewertungen werden aus Grader-Report extrahiert (siehe unten bei Gruppen-Verarbeitung)")

    # Zentralisierte Speicherung der Aktivitäten
    data = {
        "activities_by_category": activities_by_category,
        "groups": [],
        "activityincludes": activityinclude_options,
        "activitysections": activitysection_options
    }

    timer.start("Gruppen-User laden (parallel)")
    # Erstelle requests.Session mit Selenium-Cookies für schnelleres Laden
    http_session = create_requests_session_from_driver(driver)
    filtered_groups = [g for g in group_options if g["value"] != "0"]

    def _load_group(group):
        users = get_user_ids_from_group_fast(http_session, group["value"], base_url, course_id)
        return {"name": group["name"], "value": group["value"], "users": users}

    with ThreadPoolExecutor(max_workers=4) as executor:
        group_futures = {executor.submit(_load_group, g): g for g in filtered_groups}
        for future in as_completed(group_futures):
            data["groups"].append(future.result())

    total_users = sum(len(g["users"]) for g in data["groups"])
    timer.stop({"gruppen": len(data["groups"]), "user_gesamt": total_users})

    # Extrahiere Grader-Report-Daten (einmalig für alle Gruppen mit group=0)
    timer.start("Grader-Report laden")
    grader_data = get_grader_report_data(driver, course_id, "0", waittime)
    timer.stop({"aktivitäten_mit_bewertungen": len(grader_data)})

    # Manuelle Elemente aus .env-Konfiguration (MANUAL_GRADE_ITEM_IDS)
    timer.start("Manuelle Bewertungselemente")
    tree_manual_ids = config_manager.get_manual_grade_item_ids()
    logger.info(f"  {len(tree_manual_ids)} manuelle Bewertungselemente aus Konfiguration: {list(tree_manual_ids.values())}")

    # Bewertungen für manuelle Elemente via Singleview holen (direkt mit Schülernamen)
    manual_grade_items = {}
    for item_id, title in tree_manual_ids.items():
        logger.info(f"  Hole Singleview-Bewertungen für '{title}' (itemid={item_id})...")
        user_grades = get_singleview_grades(driver, course_id, item_id, base_url, waittime)
        manual_grade_items[item_id] = {
            "title": title,
            "user_grades": user_grades
        }
        logger.info(f"    -> {len(user_grades)} Bewertungen gelesen")
    data["manual_grade_items"] = manual_grade_items
    if manual_grade_items:
        titles = [v["title"] for v in manual_grade_items.values()]
        logger.info(f"  Manuelle Bewertungselemente: {titles}")
    timer.stop({"elemente": len(manual_grade_items)})

    timer.start("User-Daten zusammenführen")
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
    timer.stop()

    # =====================================================
    # VALIDIERUNG: Prüfe ob kritische Daten vorhanden sind
    # =====================================================
    logger.info("")
    logger.info("=" * 60)
    logger.info("VALIDIERUNG DER EXPORTIERTEN DATEN")
    logger.info("=" * 60)

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
        logger.warning("[!] VALIDIERUNGSFEHLER GEFUNDEN:")
        for error in validation_errors:
            logger.warning(f"  - {error}")

        # Unterscheide zwischen Fehlern und Warnungen
        critical_errors = [e for e in validation_errors if e.startswith("FEHLER:")]
        if critical_errors:
            logger.error("=" * 60)
            logger.error("[ABBRUCH] Kritische Fehler gefunden!")
            logger.error("Export wird NICHT gespeichert.")
            logger.error("=" * 60)
            logger.error("Bitte prüfen Sie:")
            logger.error("  1. Die Netzwerkverbindung zu Mebis")
            logger.error("  2. Die Login-Credentials in der Konfiguration")
            logger.error("  3. Die Kurs-ID in der Konfiguration")
            logger.error("  4. Die Logausgaben auf weitere Hinweise")
            driver.quit()
            sys.exit(1)
        else:
            logger.info("Nur Warnungen gefunden, Export wird fortgesetzt.")
    else:
        logger.info("[OK] Alle Validierungen bestanden")

    logger.info("=" * 60)

    # =====================================================
    # FEHLENDE-DATEN-REPORT
    # =====================================================
    logger.info("")
    logger.info("DATEN-VOLLSTÄNDIGKEITS-REPORT")
    logger.info("-" * 60)

    incomplete_activities = []
    for aid, statuses in assignments_status.items():
        title = next((a["title"] for a in activities["assignments"] if a["id"] == aid), aid)
        missing_grade = sum(1 for s in statuses if not s.get("grade") or s["grade"] in ["Keine Bewertung", "-", ""])
        missing_time = sum(1 for s in statuses if not s.get("submission_time"))
        if missing_grade > 0 or missing_time > 0:
            incomplete_activities.append(f"  Assignment '{title[:40]}': {missing_grade} ohne Bewertung, {missing_time} ohne Zeitstempel (von {len(statuses)})")

    for cid, progress in checklist_progress.items():
        title = next((c["title"] for c in activities["checklists"] if c["id"] == cid), cid)
        req = len(progress.get("required_progress", {}))
        all_p = len(progress.get("all_progress", {}))
        if req == 0 and all_p == 0:
            incomplete_activities.append(f"  Checklist '{title[:40]}': KEINE Daten extrahiert")
        elif req == 0:
            incomplete_activities.append(f"  Checklist '{title[:40]}': required_progress leer ({all_p} all_progress)")

    for qid, times in quiz_submission_times.items():
        title = next((q["title"] for q in activities["quizzes"] if q["id"] == qid), qid)
        if not times:
            incomplete_activities.append(f"  Quiz '{title[:40]}': KEINE submission_times extrahiert")

    if incomplete_activities:
        logger.warning(f"{len(incomplete_activities)} Aktivitäten mit unvollständigen Daten:")
        for line in incomplete_activities:
            logger.warning(line)
    else:
        logger.info("[OK] Alle Aktivitäten haben vollständige Daten")
    logger.info("-" * 60)

    timer.start("Daten speichern")
    save_start_time = time.time()

    # Zeitstempel hinzufügen
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if test_mode:
        json_filename = f'test_output_{timestamp}.json'
    else:
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
        json_bytes = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        new_file_size = len(json_bytes)
        with open(local_filename, 'wb') as f:
            f.write(json_bytes)
        save_duration = time.time() - save_start_time
        logger.info(f"Daten erfolgreich lokal gespeichert in {save_duration:.1f}s: {local_filename}")
        save_success = True

        # =====================================================
        # GRÖSSENVERGLEICH: Prüfe ob neuer Export kleiner ist
        # (Nur im normalen Modus – im Testmodus überspringen)
        # =====================================================
        logger.info(f"Größe der neuen Datei: {new_file_size:,} bytes ({new_file_size / 1024:.1f} KB)")

        if test_mode:
            logger.info("[TESTMODUS] Größenvergleich übersprungen")
        else:
            # Finde vorherige Export-Dateien
            import glob
            previous_exports = glob.glob(os.path.join(export_folder, 'output_*.json'))
            previous_exports = [f for f in previous_exports if f != local_filename]  # Schließe neue Datei aus

            if previous_exports:
                # Sortiere nach Erstellungsdatum (neueste zuerst)
                previous_exports.sort(key=os.path.getctime, reverse=True)
                latest_previous = previous_exports[0]
                previous_file_size = os.path.getsize(latest_previous)

                logger.info(f"Größe der vorherigen Datei: {previous_file_size:,} bytes ({previous_file_size / 1024:.1f} KB)")
                logger.info(f"Vorherige Datei: {os.path.basename(latest_previous)}")

                # Berechne Differenz
                size_diff = new_file_size - previous_file_size
                size_diff_percent = (size_diff / previous_file_size) * 100 if previous_file_size > 0 else 0

                logger.info(f"Differenz: {size_diff:+,} bytes ({size_diff_percent:+.1f}%)")

                # Warnung bei kleineren Exporten
                if new_file_size < previous_file_size:
                    logger.warning("=" * 60)
                    logger.warning("WARNUNG: NEUER EXPORT IST KLEINER!")
                    logger.warning("=" * 60)
                    logger.warning(f"Der neue Export ist {abs(size_diff):,} bytes ({abs(size_diff_percent):.1f}%) kleiner.")
                    logger.warning(f"Dies könnte auf einen unvollständigen Export hinweisen.")
                    logger.warning(f"Neue Datei:      {new_file_size:>12,} bytes  {os.path.basename(local_filename)}")
                    logger.warning(f"Vorherige Datei: {previous_file_size:>12,} bytes  {os.path.basename(latest_previous)}")

                    # Prüfe ob stdin interaktiv ist (Terminal vorhanden)
                    is_interactive = sys.stdin.isatty() if hasattr(sys.stdin, 'isatty') else False

                    if is_interactive:
                        # Interaktiver Modus: Frage Benutzer
                        logger.info("[INTERAKTIV] Sie werden um Bestätigung gebeten.")
                        try:
                            response = input("Möchten Sie den neuen (kleineren) Export behalten? (j/n): ").strip().lower()
                            if response not in ['j', 'ja', 'y', 'yes']:
                                logger.info("[ABBRUCH] Export wird verworfen...")
                                os.remove(local_filename)
                                logger.info(f"Datei gelöscht: {local_filename}")
                                logger.info("Der vorherige Export bleibt erhalten.")
                                save_success = False
                            else:
                                logger.info("[OK] Neuer Export wird behalten.")
                        except (KeyboardInterrupt, EOFError):
                            logger.info("[ABBRUCH] Export wird verworfen...")
                            os.remove(local_filename)
                            logger.info(f"Datei gelöscht: {local_filename}")
                            save_success = False
                    else:
                        # Nicht-interaktiver Modus: Ablehnen wenn >1% kleiner (sollte nicht vorkommen)
                        if abs(size_diff_percent) > 1:
                            logger.warning("[NICHT-INTERAKTIV] Export ist kleiner als vorher – wird automatisch abgelehnt.")
                            logger.info("[ABBRUCH] Export wird verworfen (automatisch)...")
                            os.remove(local_filename)
                            logger.info(f"Datei gelöscht: {local_filename}")
                            logger.info("Der vorherige Export bleibt erhalten.")
                            save_success = False
                        else:
                            logger.info(f"[NICHT-INTERAKTIV] Kleinerer Export akzeptiert (nur {abs(size_diff_percent):.1f}% Differenz)")

                    logger.info("=" * 60)
                elif size_diff_percent > 50:
                    logger.info(f"Export ist signifikant größer (+{size_diff_percent:.1f}%). Dies ist normal bei mehr Daten.")
                else:
                    logger.info("[OK] Dateigröße ist plausibel.")
            else:
                logger.info("Kein vorheriger Export gefunden, Größenvergleich übersprungen.")

    except Exception as e:
        logger.error(f"Lokale Speicherung fehlgeschlagen: {e}")
        save_success = False

    timer.stop()

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

    logger.info("")
    logger.info("=" * 60)
    if save_success:
        if test_mode:
            logger.info("TEST-EXPORT ERFOLGREICH ABGESCHLOSSEN")
        else:
            logger.info("EXPORT ERFOLGREICH ABGESCHLOSSEN")
    else:
        logger.error("EXPORT FEHLGESCHLAGEN ODER ABGEBROCHEN")
    logger.info("=" * 60)
    logger.info(f"Gesamtdauer: {duration_minutes:.2f} Minuten ({duration:.1f} Sekunden)")
    logger.info(f"Aktivitaeten: {total_activities} ({len(activities['assignments'])} Assignments, {len(activities['checklists'])} Checklists, {len(activities['quizzes'])} Quizzes)")
    logger.info(f"Gruppen: {total_groups} mit insgesamt {total_users} Benutzern")
    if total_activities > 0:
        logger.info(f"Durchschnitt: {(duration / total_activities):.1f}s pro Aktivitaet")
    if save_success:
        logger.info(f"Lokale Datei: {local_filename}")
    else:
        logger.error("Export wurde nicht gespeichert oder abgebrochen")
    logger.info(f"Endzeit: {datetime.now().strftime('%H:%M:%S')}")
    logger.info("=" * 60)

    # Phasen-Timing-Zusammenfassung
    timer.summary()

    # Beende mit Fehlercode wenn Export fehlgeschlagen ist
    if not save_success:
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mebis Daten-Export")
    parser.add_argument("--test", action="store_true", help="Testmodus: nur 5 Einträge pro Typ exportieren")
    args = parser.parse_args()
    main(test_mode=args.test)
