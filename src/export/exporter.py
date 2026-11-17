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
from src.common.plan_loader import PlanFehler, get_plan
from src.export.pruefung import (
    MAX_SEITEN, SeiteUnvollstaendig, erste_seite, fuehre_gruppen_zusammen,
    gilt_fuer_gruppe, offene_seiten, seiten_url, seitenwerte,
    unbekannter_status, vergleiche_zaehlwerte, zaehlwerte,
)

logger = get_logger('exporter')

# Version des Exportformats. 2 = ein Export je Schuljahr mit mehreren Kursen
# unter "kurse". 3 = zusaetzlich unbekannter Status je Aufgabe
# ("unbekannt": true) und ein "pruefbericht". Das Dashboard lehnt aeltere
# Formate ab — ein Schema-2-Export kennt keine Luecken und wuerde jede als
# "nicht abgegeben" ausweisen.
EXPORT_SCHEMA_VERSION = 3

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
        logger.warning(f"Kein Datumsformat erkannt für '{_kuerze(datetime_str)}' – wird ignoriert")
        return None

    except Exception as e:
        logger.warning(f"Fehler beim Parsen der Zeitangabe '{_kuerze(datetime_str)}': {e}")
        return None


def _kuerze(text, max_len=80):
    """Kürzt lange Werte für Log-Ausgaben, damit kein HTML-Block das Log flutet."""
    text = str(text)
    return text if len(text) <= max_len else f"{text[:max_len]}… ({len(text)} Zeichen)"


# Ein Feedback-Feld gilt nur dann als Datums-Override, wenn es ausschließlich
# ein Datum enthält: '09.01.2026', '09.01.2026 14:30', '24. September 2025 08:12',
# 'Dienstag, 23. September 2025, 07:46'. Ein Datum mitten im Feedbacktext
# („Abgabe bis 09.01.2026 …") zählt bewusst nicht.
_FEEDBACK_DATUM_MUSTER = re.compile(
    r'^(?:[^\W\d_]+,\s*)?'                      # optionaler Wochentag
    r'\d{1,2}\.\s*(?:\d{1,2}\.\s*|[^\W\d_]+\s+)'  # Tag + Monat (numerisch oder Name)
    r'\d{4}'                                    # Jahr
    r'(?:,?\s+\d{1,2}:\d{2})?$'                 # optionale Uhrzeit
)


def feedback_als_datum(feedback):
    """
    Liest ein Datum aus dem Feedback-Feld der Singleview.

    Das Feld dient als Override für das Abgabedatum, enthält aber oft echtes
    Feedback als HTML. Tags werden entfernt; steht danach nur ein Datum da,
    wird es geparst, sonst ``None`` — ohne Warnung, denn Feedbacktext ist
    kein Fehler.
    """
    if not feedback:
        return None
    text = feedback
    if '<' in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = re.sub(r'\s+', ' ', text).strip()
    if not _FEEDBACK_DATUM_MUSTER.match(text):
        return None
    return parse_german_datetime(text)


# JS-Helfer für die Batch-Extraktion per execute_script: liest den sichtbaren
# Text eines Elements so, wie Seleniums `.text` ihn liefert (gerendert,
# geschützte Leerzeichen als normale Leerzeichen, an den Rändern getrimmt).
# Wird jedem Extraktions-Skript vorangestellt.
_JS_TEXT = """
    function txt(el) {
        return (el.innerText || '').replace(/\\u00a0/g, ' ').trim();
    }
"""

# Links der Seitenleiste(n). Die Buchstabenleiste (.initialbar) teilt sich
# in Moodle 4 die Klasse .pagination, ist aber ein Filter — sie bleibt
# draussen. Aus den Links wird ohnehin nur die Seitennummer gelesen
# (pruefung.seitenwerte).
_JS_SEITENLINKS = """
    var out = [];
    document.querySelectorAll('.pagination a[href], .paging a[href]').forEach(function(a) {
        if (a.closest('.initialbar')) return;
        out.push(a.getAttribute('href'));
    });
    return out;
"""

# Zaehlt nachgeladene Folgeseiten fuer den Pruefbericht (Threads teilen ihn).
_seiten_statistik = {"nachgeladen": 0}
_seiten_lock = threading.Lock()


def pruefe_angemeldet(driver):
    """Bricht ab, wenn Moodle statt des Inhalts die Anmeldeseite liefert."""
    if "login" in (driver.current_url or ""):
        raise SeiteUnvollstaendig("Anmeldeseite statt Inhalt — Sitzung abgelaufen?")


def lade_alle_seiten(driver, url, lese_seite):
    """
    Laedt eine Moodle-Seite samt aller Folgeseiten.

    Bewerterübersicht, Bewertungsseite und Testbericht teilen ihre Tabellen
    je nach den im Moodle-Konto gespeicherten Einstellungen auf. Ohne
    Nachladen fehlten Personen jenseits der ersten Seite — still, und in
    jedem Lauf gleich, also auch fuer einen Vergleich mit dem Vorlauf
    unsichtbar.

    Args:
        driver: WebDriver
        url: Basis-URL der ersten Seite
        lese_seite: Funktion(driver) -> Ergebnis einer Seite; wirft
            SeiteUnvollstaendig, wenn die Seite nicht wie erwartet aussieht

    Returns:
        Liste der Seitenergebnisse, erste Seite zuerst

    Raises:
        SeiteUnvollstaendig: Anmeldeseite, fehlende Tabelle, zu viele Seiten
    """
    driver.get(url)
    pruefe_angemeldet(driver)
    ergebnisse = [lese_seite(driver)]

    geladen = erste_seite(url)
    gefunden = seitenwerte(driver.execute_script(_JS_SEITENLINKS) or [])
    offen = offene_seiten(gefunden, geladen)

    while offen:
        if len(ergebnisse) >= MAX_SEITEN:
            raise SeiteUnvollstaendig(f"mehr als {MAX_SEITEN} Seiten — Seitenleiste unerwartet")
        param, wert = offen[0]
        driver.get(seiten_url(url, param, wert))
        pruefe_angemeldet(driver)
        ergebnisse.append(lese_seite(driver))
        geladen.setdefault(param, set()).add(wert)
        with _seiten_lock:
            _seiten_statistik["nachgeladen"] += 1

        # Eine lange Seitenleiste zeigt nicht alle Nummern auf einmal —
        # jede geladene Seite kann weitere verraten.
        for p, werte in seitenwerte(driver.execute_script(_JS_SEITENLINKS) or []).items():
            gefunden.setdefault(p, set()).update(werte)
        offen = offene_seiten(gefunden, geladen)

    if len(ergebnisse) > 1:
        logger.info(f"  {len(ergebnisse)} Seiten geladen (aufgeteilte Tabelle)")
    return ergebnisse


def warte_auf(driver, selektor, waittime, beschreibung):
    """Wartet auf ein Element; fehlt es, ist die Seite unvollstaendig."""
    try:
        WebDriverWait(driver, waittime).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selektor))
        )
    except TimeoutException:
        raise SeiteUnvollstaendig(f"{beschreibung} nicht gefunden")


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

def _lies_gruppenseite(session, url):
    """
    Liest eine Seite des Fortschrittsberichts per requests.

    Returns:
        (users, seitenlinks)

    Raises:
        SeiteUnvollstaendig: Anmeldeseite oder kein Fortschrittsbericht
    """
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    if "login" in resp.url:
        raise SeiteUnvollstaendig("Anmeldeseite statt Fortschrittsbericht")
    soup = BeautifulSoup(resp.text, 'html.parser')

    tabelle = soup.select_one('#completion-progress')
    if tabelle is None:
        # Eine leere Gruppe hat keine Tabelle, wohl aber die Gruppenauswahl
        # des Berichts. Fehlt beides, ist es nicht der Bericht.
        if soup.select_one('select[name="group"]') is None:
            raise SeiteUnvollstaendig("Fortschrittsbericht nicht erkannt")
        return [], []

    users = []
    for a in tabelle.select('tbody th[scope="row"] a'):
        m = re.search(r'id=(\d+)', a.get('href', ''))
        if m:
            users.append({"id": m.group(1), "name": a.get_text(strip=True)})

    links = [a.get('href') for a in soup.select('.pagination a[href], .paging a[href]')
             if not a.find_parent(class_='initialbar')]
    return users, links


def get_user_ids_from_group_fast(session, group_value, base_url, course_id):
    """
    Lädt die Mitglieder einer Gruppe via requests+BeautifulSoup.

    Der Fortschrittsbericht zeigt nur eine begrenzte Zahl Personen je Seite;
    die Folgeseiten werden nachgeladen. Die Mitglieder sind die Bezugsmenge
    aller weiteren Abgleiche — fehlt hier jemand, fehlt die Person im
    ganzen Dashboard. Deshalb wird ein Fehler nicht als leere Gruppe
    weitergegeben, sondern geworfen.

    Raises:
        SeiteUnvollstaendig, requests.RequestException
    """
    url = f"{base_url}?course={course_id}&group={group_value}"
    users, links = _lies_gruppenseite(session, url)

    geladen = erste_seite(url)
    gefunden = seitenwerte(links)
    offen = offene_seiten(gefunden, geladen)
    seiten = 1
    while offen:
        if seiten >= MAX_SEITEN:
            raise SeiteUnvollstaendig(f"mehr als {MAX_SEITEN} Seiten im Fortschrittsbericht")
        param, wert = offen[0]
        mehr, links = _lies_gruppenseite(session, seiten_url(url, param, wert))
        users.extend(mehr)
        seiten += 1
        geladen.setdefault(param, set()).add(wert)
        with _seiten_lock:
            _seiten_statistik["nachgeladen"] += 1
        for p, werte in seitenwerte(links).items():
            gefunden.setdefault(p, set()).update(werte)
        offen = offene_seiten(gefunden, geladen)

    # Doppelte Zeilen (z.B. bei ueberlappenden Seiten) entfernen
    eindeutig = {}
    for user in users:
        eindeutig.setdefault(user["id"], user)
    return list(eindeutig.values())

def create_requests_session_from_driver(driver):
    """Erstellt eine requests.Session mit den Cookies des Selenium-Drivers"""
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    return session

def get_activity_urls(driver, course_id=None):
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

    # Method 3: Quiz-Index des Kurses.
    #
    # Die Fortschrittsseite listet nur Aktivitaeten mit aktivierter
    # Abschlussverfolgung. Ein Quiz ohne diese Einstellung fehlt dort und
    # damit im Export — im Kurs 2491549 betraf das u.a. "OOP - SOLID"
    # (cmid 95572024), immerhin 8 der 58,5 Plan-Stunden. Der Quiz-Index
    # kennt dagegen alle Quizze des Kurses.
    if not course_id:
        # Rueckfallebene: Kurs-ID aus der gerade offenen Seite ziehen.
        match = re.search(r'[?&](?:course|id)=(\d+)', driver.current_url or '')
        course_id = match.group(1) if match else None

    if course_id:
        logger.info("Ergaenze Quizze aus dem Quiz-Index...")
        try:
            vorher = len(activity_urls["quizzes"])
            driver.get(f"https://lernplattform.bycs.de/mod/quiz/index.php?id={course_id}")
            time.sleep(2)
            for element in driver.find_elements(By.CSS_SELECTOR, "a[href*='mod/quiz/view.php']"):
                href = element.get_attribute("href") or ''
                id_match = re.search(r'id=(\d+)', href)
                if not id_match:
                    continue
                activity_id = id_match.group(1)
                if activity_id in activity_ids_found:
                    continue
                # .text ist auf der Index-Seite leer (Element nicht sichtbar
                # gerendert); textContent traegt den Titel.
                title = ((element.get_attribute("textContent") or '').strip()
                         or (element.text or '').strip()
                         or element.get_attribute("title")
                         or f"Quiz {activity_id}")
                activity_urls["quizzes"].append({"id": activity_id, "title": title, "url": href})
                activity_ids_found.add(activity_id)
                logger.info(f"  Quiz nur im Index gefunden: {activity_id} - {title}")
            neu = len(activity_urls["quizzes"]) - vorher
            if neu:
                logger.info(
                    f"  {neu} Quiz(ze) ergaenzt, die auf der Fortschrittsseite fehlen "
                    f"(vermutlich ohne Abschlussverfolgung)."
                )
        except Exception as e:
            logger.error(f"Quiz-Index konnte nicht gelesen werden: {e}")
    else:
        logger.warning("Keine Kurs-ID ermittelbar — Quiz-Index wird uebersprungen.")

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

@retry(max_retries=3, base_delay=2.0,
       exceptions=(TimeoutException, WebDriverException, SeiteUnvollstaendig))
def get_assignment_status(driver, assignment_url, waittime):
    """
    Liest die Bewertungsseite einer Aufgabe, alle Teilseiten.

    Returns:
        Liste der Status-Eintraege je Person

    Raises:
        SeiteUnvollstaendig: Tabelle oder Spalte "Endbewertung" fehlt, auch
            nach Wiederholung. Frueher wurde daraus eine leere Liste — und
            damit fuer die ganze Klasse "nicht abgegeben".
    """
    # Navigiere zur Bewertungsseite des Assignments mit allen nötigen Parametern
    # status: alle Benutzer anzeigen, auch die ohne Abgaben
    # quickgrading=0: vollständige Bewertungsansicht
    # group=0: alle Gruppen
    grading_url = f"{assignment_url}&action=grading&status&quickgrading=0&group=0"

    def lese_seite(drv):
        warte_auf(drv, "tbody", waittime, "Bewertungstabelle")
        tabelle = _lies_bewertungstabelle(drv)
        if not tabelle or not tabelle.get("gradeCol"):
            raise SeiteUnvollstaendig("Spalte 'Endbewertung' nicht gefunden")
        return tabelle["rows"]

    zeilen = []
    for seite in lade_alle_seiten(driver, grading_url, lese_seite):
        zeilen.extend(seite)
    return _bewertungszeilen_auswerten(zeilen)


def _lies_bewertungstabelle(driver):
    """Liest die geladene Bewertungstabelle in einem JS-Aufruf."""
    # Die ganze Tabelle in einem einzigen JS-Aufruf lesen. Zeilenweise
    # find_element/.text kostete ~10 WebDriver-Roundtrips je Schüler — bei
    # ~110 Zeilen der größte Einzelposten des Exports. Die Auswahl der
    # Elemente entspricht 1:1 der früheren Selenium-Abfrage; Defaults und
    # Datums-Parsing bleiben auf der Python-Seite.
    return driver.execute_script(_JS_TEXT + """
        // Spaltenklassen aus den Überschriften; wie zuvor gewinnt die letzte
        // Übereinstimmung, und die Klasse ist das zweite Token ("c14").
        var gradeCol = null, timeCol = null;
        document.querySelectorAll('th.header').forEach(function(h) {
            var t = txt(h);
            var cls = (h.getAttribute('class') || '').split(/\\s+/).filter(Boolean);
            var sortby = h.getAttribute('data-sortby') || '';
            if (t.indexOf('Endbewertung') >= 0) gradeCol = cls[1] || null;
            if (t.indexOf('Zuletzt geändert (Abgabe)') >= 0 || sortby.indexOf('timesubmitted') >= 0) {
                timeCol = cls[1] || null;
            }
        });
        if (!gradeCol) return {gradeCol: null, rows: []};

        function feld(row, sel) {
            var el = row.querySelector(sel);
            return el ? txt(el) : null;
        }
        var tbody = document.querySelector('tbody');
        var rows = [];
        tbody.querySelectorAll('tr').forEach(function(row) {
            rows.push({
                cls: row.getAttribute('class') || '',
                status: feld(row, 'div.submissionstatussubmitted'),
                status2: feld(row, 'div.submissiongraded'),
                submission: feld(row, 'div.assignsubmission_onlinetext .no-overflow p'),
                grade: feld(row, 'td.cell.' + gradeCol),
                time: timeCol ? feld(row, 'td.cell.' + timeCol) : null
            });
        });
        return {gradeCol: gradeCol, rows: rows};
    """)


def _bewertungszeilen_auswerten(zeilen):
    """Wandelt die Rohzeilen der Bewertungstabelle in Status-Eintraege."""
    user_statuses = []
    gesehen = set()

    for row in zeilen:
        # Extrahiere die UserID aus der class des tr-Elements
        user_id_match = re.search(r'user(\d+)', row["cls"])
        if not user_id_match:
            continue  # Überspringe Zeilen ohne UserID

        user_id = user_id_match.group(1)
        if user_id in gesehen:
            continue  # Zeile auf zwei Teilseiten
        gesehen.add(user_id)

        status = row["status"] if row["status"] is not None else "Nicht eingereicht"
        status2 = row["status2"] if row["status2"] is not None else "Nicht bewertet"
        submission = row["submission"] if row["submission"] is not None else "Keine Abgabe"
        grade = row["grade"] if row["grade"] is not None else "Keine Bewertung"

        # grade_options werden leer gelassen (wie gewünscht)
        grade_options = []

        # Konvertiere deutsche Zeitangabe in ISO-Format
        submission_time = parse_german_datetime(row["time"]) if row["time"] is not None else None

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

@retry(max_retries=3, base_delay=2.0,
       exceptions=(TimeoutException, WebDriverException, SeiteUnvollstaendig))
def get_grader_report_data(driver, course_id, group_id, waittime):
    """
    Extrahiert alle Bewertungsdaten aus der Grader-Report-Seite, alle Teilseiten.
    Nutzt JavaScript-Extraktion statt einzelner Selenium-Aufrufe (>50x schneller).

    Returns:
        (aktivitaeten, personen): {activity_id: {..., grades: {user_id: text}}}
        und die Menge der User-IDs mit einer Zeile im Bericht. Wer dort
        fehlt, hat keinen bekannten Teststatus.

    Raises:
        SeiteUnvollstaendig: Tabelle fehlt auch nach Wiederholung
    """
    grader_url = f"https://lernplattform.bycs.de/grade/report/grader/index.php?id={course_id}&groupsearchvalue=&group={group_id}"

    def lese_seite(drv):
        warte_auf(drv, "table.gradereport-grader-table#user-grades", waittime,
                  "Tabelle der Bewerterübersicht")
        ergebnis = _lies_bewerteruebersicht(drv)
        if ergebnis is None:
            raise SeiteUnvollstaendig("Bewerterübersicht nicht auslesbar")
        return ergebnis

    aktivitaeten = {}
    personen = set()
    for seite in lade_alle_seiten(driver, grader_url, lese_seite):
        personen.update(seite.get("personen", []))
        for aid, adata in seite.get("aktivitaeten", {}).items():
            ziel = aktivitaeten.setdefault(aid, {**adata, "grades": {}})
            ziel["grades"].update(adata.get("grades", {}))

    # Debug-Logging: Zeige Stichprobe der extrahierten Daten
    total_grades = sum(len(a.get("grades", {})) for a in aktivitaeten.values())
    non_empty = sum(1 for a in aktivitaeten.values() for g in a.get("grades", {}).values() if g and g != "-")
    logger.info(f"  Grader-Report: {len(aktivitaeten)} Aktivitäten, {len(personen)} Personen, "
                f"{total_grades} Grade-Einträge, {non_empty} mit Bewertung")
    return aktivitaeten, personen


def _lies_bewerteruebersicht(driver):
    """Liest die geladene Bewerterübersicht in einem JS-Aufruf."""
    # Extrahiere alle Daten in einem einzigen JavaScript-Aufruf
    return driver.execute_script("""
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

                // Bearbeitungsmodus: Note steht im Eingabefeld; daneben eine
                // versteckte Beschriftung "<Name> <Aktivitaet> Bewertung",
                // die nie als Note gelesen werden darf (Befund aus dem
                // Parallelvergleich mit dem Browser-Export, 17.11.2026).
                var input = cell.querySelector('input[type="text"], input:not([type])');
                if (input) return (input.getAttribute('value') || '').trim() || '-';

                // Versteckte Hilfstexte, Menues und Bedienelemente entfernen
                var clone = cell.cloneNode(true);
                clone.querySelectorAll('.accesshide, .sr-only, .visually-hidden, label, .dropdown, button, '
                                     + '.dropdown-menu, [role="menu"], input, select')
                    .forEach(function(el) { el.remove(); });

                // Versuch 2: nur direkte Text-Nodes
                var text = '';
                for (var i = 0; i < clone.childNodes.length; i++) {
                    if (clone.childNodes[i].nodeType === 3) text += clone.childNodes[i].textContent;
                }
                text = text.trim();
                if (text) return text;

                // Versuch 3: restlicher Text; leer heisst: keine Bewertung
                text = (clone.textContent || '').replace(/Zellaktionen/g, '').trim().split('\\n')[0].trim();
                return text || '-';
            }

            // 4. Zeilen durchlaufen: User-Bewertungen extrahieren
            var personen = [];
            var rows = table.querySelectorAll('tbody tr');
            rows.forEach(function(row) {
                var userLink = row.querySelector('th a[href*="user/view.php?id="]');
                if (!userLink) return;
                var userMatch = (userLink.getAttribute('href') || '').match(/id=(\\d+)/);
                if (!userMatch) return;
                var userId = userMatch[1];
                personen.push(userId);

                var cells = row.querySelectorAll('td');
                cells.forEach(function(cell) {
                    var cm = (cell.className || '').match(/\\b(c\\d+)\\b/);
                    if (!cm || !columnMap[cm[1]]) return;
                    var text = extractGradeText(cell);
                    activities[columnMap[cm[1]].id].grades[userId] = text;
                });
            });

            return {aktivitaeten: activities, personen: personen};
        """)


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

    # driver.get() kehrt erst nach dem load-Event zurück; ein zusätzliches
    # Warten auf #attempts kostete bei Quizzen ohne Versuche (dort gibt es
    # die Tabelle nicht) jedes Mal die volle waittime. Damit eine leere
    # Antwort trotzdem nicht als "keine Versuche" durchgeht, muss die Seite
    # als Testbericht erkennbar sein (Moodle setzt die body-ID nach dem
    # Seitentyp, hier page-mod-quiz-report).
    def lese_seite(drv):
        ist_bericht = drv.execute_script(
            "return (document.body && document.body.id || '').indexOf('mod-quiz-report') >= 0;")
        if not ist_bericht:
            raise SeiteUnvollstaendig("Testbericht nicht erkannt")
        return _lies_testversuche(drv) or []

    # Fehler laufen zum Aufrufer durch: process_quiz_parallel vermerkt sie im
    # Pruefbericht. Der Teststatus selbst stammt aus der Bewerterübersicht.
    tabelle = []
    for seite in lade_alle_seiten(driver, report_url, lese_seite):
        tabelle.extend(seite)

    # Zeilen sind nach Beendet-Zeit absteigend sortiert: der erste
    # erfolgreich geparste Eintrag je User ist der neueste.
    for user_href, submission_time_raw in tabelle:
        user_id_match = re.search(r'id=(\d+)', user_href or "")
        if not user_id_match:
            continue
        user_id = user_id_match.group(1)
        # Wenn dieser User bereits erfasst wurde, überspringe (wir wollen nur den neuesten)
        if user_id in submission_times or not submission_time_raw:
            continue
        submission_time = parse_german_datetime(submission_time_raw)
        if submission_time:
            submission_times[user_id] = submission_time

    return submission_times


def _lies_testversuche(driver):
    """Liest die Versuchstabelle eines Testberichts; None ohne Versuche."""
    # Ganze Tabelle in einem JS-Aufruf lesen (statt bis zu 6 Roundtrips je
    # Zeile). Auswahl der Elemente wie zuvor mit Selenium.
    return driver.execute_script(_JS_TEXT + """
            var table = document.getElementById('attempts');
            if (!table) return null;

            // "Beendet"-Spalte dynamisch aus den Überschriften; erste
            // Übereinstimmung mit Spaltenklasse gewinnt, sonst Fallback c7.
            var finishCol = null;
            var ths = table.querySelectorAll('th');
            for (var i = 0; i < ths.length && !finishCol; i++) {
                var t = txt(ths[i]);
                var sortby = ths[i].getAttribute('data-sortby') || '';
                if (t.indexOf('Beendet') >= 0 || sortby.indexOf('timefinish') >= 0) {
                    var m = (ths[i].getAttribute('class') || '').match(/\\bc\\d+\\b/);
                    if (m) finishCol = m[0];
                }
            }
            if (!finishCol) finishCol = 'c7';

            var tbody = table.querySelector('tbody');
            if (!tbody) return [];
            // User-Link mit Fallback-Kette für verschiedene Moodle-Layouts
            var linkSel = [
                "td.cell.c2 a[href*='user/view.php?id=']",
                "td.cell.c1 a[href*='user/view.php?id=']",
                "td a[href*='user/view.php?id=']"
            ];
            var rows = [];
            tbody.querySelectorAll('tr').forEach(function(row) {
                var link = null;
                for (var j = 0; j < linkSel.length && !link; j++) {
                    link = row.querySelector(linkSel[j]);
                }
                if (!link) return;
                var cell = row.querySelector('td.cell.' + finishCol);
                // .href liefert wie Seleniums get_attribute("href") die absolute URL
                rows.push([link.href, cell ? txt(cell) : null]);
            });
            return rows;
        """)


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
    feedback_ohne_datum = 0
    try:
        # Alle Zeilen in einem JS-Aufruf lesen statt ~5 Roundtrips je Zeile —
        # die Singleview wird für jedes Assignment und jedes Quiz geladen.
        # Rückgabe: Zeilenzahl + [href, feedback_text] je auswertbarer Zeile.
        ergebnis = driver.execute_script(_JS_TEXT + """
            var rows = document.querySelectorAll('table#singleview-grades tbody tr');
            var out = [];
            rows.forEach(function(row) {
                // UserID aus dem ersten User-Link in der Zeile (Spalte c0)
                var link = row.querySelector("a[href*='user/view.php?id=']");
                if (!link) return;
                // Feedback-Text aus Spalte c4: Moodle rendert den Wert je nach
                // Modus als sichtbaren Text, textarea oder input.
                var cell = row.querySelector('td.cell.c4');
                if (!cell) return;
                var text = txt(cell);
                if (!text) {
                    var ta = cell.querySelector('textarea');
                    if (ta) text = ta.value || '';
                }
                if (!text) {
                    var inp = cell.querySelector("input[type='text']");
                    if (inp) text = inp.value || '';
                }
                out.push([link.href, text]);
            });
            return {anzahl: rows.length, zeilen: out};
        """)
        logger.info(f"  Singleview: {ergebnis['anzahl']} Zeilen für grade_item_id {grade_item_id}")

        for href, feedback_text in ergebnis["zeilen"]:
            uid_match = re.search(r'user/view\.php\?id=(\d+)', href or "")
            if not uid_match:
                continue
            user_id = uid_match.group(1)

            if not feedback_text:
                continue

            feedback_date = feedback_als_datum(feedback_text)
            if feedback_date:
                feedback_dates[user_id] = feedback_date
            else:
                feedback_ohne_datum += 1

    except Exception as e:
        logger.error(f"Fehler beim Parsen der Singleview für grade_item_id {grade_item_id}: {e}")

    hinweis = f" ({feedback_ohne_datum} Feedback-Texte ohne Datum übersprungen)" if feedback_ohne_datum else ""
    logger.info(f"  Singleview: {len(feedback_dates)} Feedback-Daten extrahiert{hinweis}")
    return feedback_dates


def _fehlertext(e):
    """Kurzer Fehlertext (eine Zeile) fuer Log und Pruefbericht."""
    text = str(e) if isinstance(e, SeiteUnvollstaendig) else f"{type(e).__name__}: {e}"
    return text.splitlines()[0][:200] if text.strip() else type(e).__name__


def process_assignment_parallel(assignment, isheadless, waittime, username, password, base_url, course_id, index, total):
    """
    Verarbeitet eine Aufgabe in einem Arbeits-Thread.

    Returns:
        (assignment_id, status, groups, grund): ``status`` ist die Liste der
        Eintraege oder None, wenn die Bewertungsseite nicht vollstaendig
        gelesen werden konnte — dann nennt ``grund`` die Ursache. None wird
        spaeter zu "unbekannt", nie zu "nicht abgegeben".
    """
    assignment_id = assignment.get('id', 'unknown')
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id, waittime)

        if driver is None:
            logger.error(f"[{index+1}/{total}] Kein WebDriver verfügbar für Assignment {assignment_id}")
            return assignment_id, None, "all", "kein Browser verfügbar"

        assignment_url = assignment["url"]
        assignment_title = assignment.get("title", f"Assignment {assignment_id}")

        logger.info(f"[{index+1}/{total}] Verarbeite Assignment: {assignment_title[:50]}...")
        print(f"PROGRESS|assignments|{index+1}|{total}")
        sys.stdout.flush()
        start_time = time.time()

        # Keine Gruppenabfrage mehr: Die Aufgabenseite lieferte in allen
        # Exporten nur "all" (das Auswahlfeld zeigt die gerade gewaehlte Gruppe
        # der Lehrkraft, keine Einschraenkung der Aufgabe), und die
        # Bewertungsseite wird ohnehin mit group=0 gelesen. Spart einen
        # Seitenabruf je Aufgabe. Das Feld "groups" bleibt im Export.
        groups = "all"

        # Extrahiere Status — wirft bei unvollstaendiger Seite (nach Wiederholung)
        status = get_assignment_status(driver, assignment_url, waittime)

        grade_item_id = assignment.get("grade_item_id")

        # Priorität 1: Feedback-Datum aus Singleview überschreibt submission_time
        # itemid = grade_item_id (BewertungsID), nicht assignment_id.
        # Datumsangaben sind eine Ergaenzung: ein Fehler hier macht den
        # Status nicht unbekannt.
        if grade_item_id:
            try:
                feedback_dates = get_singleview_feedback_dates(driver, course_id, grade_item_id, waittime)
            except Exception as e:
                logger.warning(f"  Feedback-Daten nicht lesbar: {_fehlertext(e)}")
                feedback_dates = {}
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

        return assignment_id, status, groups, None
    except Exception as e:
        grund = _fehlertext(e)
        try:
            logger.error(f"Aufgabe {assignment_id}: Status UNBEKANNT — {grund}")
        except UnicodeEncodeError:
            logger.error(f"Aufgabe {assignment_id}: Status UNBEKANNT - {grund.encode('ascii', 'replace').decode('ascii')}")
        sys.stdout.flush()
        return assignment_id, None, "all", grund


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
    """
    Liest die Abgabezeiten eines Tests in einem Arbeits-Thread.

    Returns:
        (quiz_id, submission_times, grund): ``grund`` ist None oder nennt,
        warum der Testbericht nicht vollstaendig gelesen werden konnte.
        Der Teststatus haengt daran nicht — er kommt aus der
        Bewerterübersicht —, wohl aber das Abgabedatum.
    """
    quiz_id = quiz.get('id', 'unknown')
    submission_times = {}
    grund = None
    try:
        driver = get_thread_driver(isheadless, username, password, base_url, course_id, waittime)

        if driver is None:
            logger.error(f"[{index+1}/{total}] Kein WebDriver verfügbar für Quiz {quiz_id}")
            return quiz_id, {}, "kein Browser verfügbar"

        quiz_url = quiz["url"]
        quiz_title = quiz.get("title", f"Quiz {quiz_id}")

        logger.info(f"[{index+1}/{total}] Verarbeite Quiz: {quiz_title[:50]}...")
        print(f"PROGRESS|quizzes|{index+1}|{total}")
        sys.stdout.flush()
        start_time = time.time()
        try:
            submission_times = get_quiz_submission_times(driver, quiz_url, waittime)
        except Exception as e:
            grund = _fehlertext(e)
            logger.warning(f"  Testbericht unvollständig: {grund}")

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
        return quiz_id, submission_times, grund
    except Exception as e:
        grund = _fehlertext(e)
        logger.error(f"Fehler bei Quiz {quiz_id}: {grund}")
        sys.stdout.flush()
        return quiz_id, submission_times, grund


def get_all_activity_categories(driver, course_id):
    categories_data = {}

    # Lade die Seite nur einmal
    grade_url = f"https://lernplattform.bycs.de/grade/edit/tree/index.php?id={course_id}"
    driver.get(grade_url)

    # Verwenden Sie WebDriverWait, um sicherzustellen, dass die Elemente geladen sind
    WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.gradeitemheader"))
    )

    # Alle Aktivitäten in einem JS-Aufruf statt ~5 Roundtrips je Aktivität.
    eintraege = driver.execute_script("""
        var out = [];
        document.querySelectorAll('a.gradeitemheader').forEach(function(a) {
            // Wie zuvor XPath "./ancestor::tr" mit find_element: das erste
            // Treffer-Element in Dokumentreihenfolge, also das äußerste <tr>.
            var parentTr = null;
            for (var el = a.parentElement; el; el = el.parentElement) {
                if (el.tagName === 'TR') parentTr = el;
            }
            if (!parentTr) { out.push({href: a.href, fehler: 'kein übergeordnetes <tr>'}); return; }
            var categoryId = parentTr.getAttribute('data-parent-category');
            var categoryTr = document.getElementById('grade-item-' + categoryId);
            var input = categoryTr ? categoryTr.querySelector('input.itemselect') : null;
            if (!input) {
                out.push({href: a.href, fehler: 'Kategoriezeile grade-item-' + categoryId + ' nicht gefunden'});
                return;
            }
            out.push({
                href: a.href,
                category_id: categoryId,
                // Bewertungs-ID (data-itemid auf dem TR) – unterscheidet sich von der Activity-ID
                grade_item_id: parentTr.getAttribute('data-itemid'),
                // Kategoriename aus dem data-toggle-selectall-Attribut
                category_name: input.getAttribute('data-toggle-selectall')
            });
        });
        return out;
    """)

    for eintrag in eintraege:
        # Extrahiere die Aktivitäts-ID aus dem href-Attribut
        activity_id_match = re.search(r'\?id=(\d+)', eintrag.get("href") or "")
        if not activity_id_match:
            continue

        if eintrag.get("fehler"):
            logger.warning(f"Fehler beim Verarbeiten der Aktivität: {eintrag['fehler']}")
            continue

        categories_data[activity_id_match.group(1)] = {
            "category_id": eintrag["category_id"],
            "category_name": eintrag["category_name"],
            "grade_item_id": eintrag["grade_item_id"] or None
        }

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


class ExportValidationError(Exception):
    """Kritische Luecke in den Daten eines Kurses — dieser Kurs wird nicht gespeichert."""


def export_course(driver, course_id, course_title, base_url, username, password,
                  isheadless, waittime, test_mode, test_limit, timer):
    """
    Exportiert einen einzelnen Moodle-Kurs.

    Der Aufrufer haelt Driver und Login; hier wird nur der Kurskontext
    gesetzt. Dadurch teilen sich alle Kurse eine Sitzung.

    Args:
        driver: eingeloggter WebDriver
        course_id: Moodle-Kurs-ID
        course_title: Titel aus plan.json, nur fuer Logausgaben
        timer: PhaseTimer des Gesamtlaufs

    Returns:
        dict mit activities_by_category, groups, ...

    Raises:
        ExportValidationError: bei kritischen Luecken in den Kursdaten
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"KURS: {course_title} (ID {course_id})")
    logger.info("=" * 60)

    # Kurs-Kontext setzen: die Fortschrittsseite dieses Kurses oeffnen,
    # damit die folgenden Select-Optionen zum richtigen Kurs gehoeren.
    timer.start("Kurskontext setzen")
    driver.get(f"{base_url}?course={course_id}")
    timer.stop()

    timer.start("Gruppen & Optionen laden")
    group_options = get_select_options(driver, "group", waittime)
    activityinclude_options = get_select_options(driver, "activityinclude", waittime)
    activitysection_options = get_select_options(driver, "activitysection", waittime)
    timer.stop({"gruppen": len(group_options)})

    # Erfasse die Aktivitäten einmalig
    timer.start("Aktivitäten erfassen")
    activities = get_activity_urls(driver, course_id)
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


    # Pruefbericht dieses Kurses: Luecken machen einen Status unbekannt,
    # Hinweise betreffen nur Nebenangaben wie Abgabezeiten.
    luecken = []
    hinweise = []

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
                assignment_id, status, groups, grund = future.result()
                assignments_groups[assignment_id] = groups
                if status is None:
                    # Seite nicht vollstaendig gelesen: Status unbekannt
                    # fuer alle, nicht "nicht abgegeben".
                    aktivitaet = future_to_assignment[future]
                    luecken.append({
                        "cmid": assignment_id,
                        "titel": aktivitaet.get("title", assignment_id),
                        "typ": "assign",
                        "personen": "alle",
                        "grund": grund or "unbekannt",
                    })
                    continue
                assignments_status[assignment_id] = status

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
                quiz_id, submission_times, grund = future.result()
                quiz_submission_times[quiz_id] = submission_times
                if grund:
                    titel = future_to_quiz[future].get("title", quiz_id)
                    hinweise.append(f"Test '{titel}': Abgabezeiten unvollständig ({grund})")

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

    # Pflichtaufgaben dieses Kurses laut Plan: nur fuer sie ist eine fehlende
    # Bewertung eine Luecke. Uebungstests ohne Bewertung fehlen in der
    # Bewerterübersicht zu Recht.
    plan = get_plan()
    plan_kurs = plan.get_kurs_by_moodle_id(str(course_id))
    plan_cmids = {a['cmid'] for a in plan_kurs['aufgaben']} if plan_kurs else set()

    def _load_group(group):
        users = get_user_ids_from_group_fast(http_session, group["value"], base_url, course_id)
        return {"name": group["name"], "value": group["value"], "users": users}

    gruppen_fehler = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        group_futures = {executor.submit(_load_group, g): g for g in filtered_groups}
        for future in as_completed(group_futures):
            gruppe = group_futures[future]
            try:
                data["groups"].append(future.result())
            except Exception as e:
                grund = _fehlertext(e)
                logger.error(f"Gruppe '{gruppe['name']}': Mitglieder nicht ladbar — {grund}")
                # Nur Klassen aus dem Plan sind kritisch; andere Gruppen
                # (IF10B, Testgruppe, ...) fliessen ohnehin nicht ein.
                if plan.get_track_for_class(gruppe["name"]):
                    gruppen_fehler.append(f"{gruppe['name']}: {grund}")
                else:
                    hinweise.append(f"Gruppe '{gruppe['name']}' nicht ladbar ({grund}) — nicht im Plan, ohne Auswirkung")

    total_users = sum(len(g["users"]) for g in data["groups"])
    timer.stop({"gruppen": len(data["groups"]), "user_gesamt": total_users})

    # Extrahiere Grader-Report-Daten (einmalig für alle Gruppen mit group=0)
    timer.start("Grader-Report laden")
    grader_data, grader_personen, grader_grund = {}, set(), None
    try:
        grader_data, grader_personen = get_grader_report_data(driver, course_id, "0", waittime)
    except Exception as e:
        grader_grund = _fehlertext(e)
        logger.error(f"Bewerterübersicht nicht lesbar — Teststatus UNBEKANNT: {grader_grund}")
    timer.stop({"aktivitäten_mit_bewertungen": len(grader_data), "personen": len(grader_personen)})

    # Tests, die als Pflichtaufgabe gefuehrt werden, aber in der
    # Bewerterübersicht keine Spalte haben, sind fuer alle unbekannt.
    tests_unbekannt = {}
    for quiz in activities["quizzes"]:
        if quiz["id"] not in plan_cmids:
            continue
        if grader_grund:
            tests_unbekannt[quiz["id"]] = f"Bewerterübersicht: {grader_grund}"
        elif quiz["id"] not in grader_data:
            tests_unbekannt[quiz["id"]] = "keine Spalte in der Bewerterübersicht"
    for quiz in activities["quizzes"]:
        if quiz["id"] in tests_unbekannt:
            luecken.append({"cmid": quiz["id"], "titel": quiz.get("title", quiz["id"]),
                            "typ": "quiz", "personen": "alle", "grund": tests_unbekannt[quiz["id"]]})

    timer.start("User-Daten zusammenführen")
    # Abgleich (Ebene 2): wer laut Gruppe dazugehoert, aber in einer sonst
    # vollstaendig gelesenen Tabelle fehlt, hat dort einen unbekannten
    # Status. Gezaehlt je Aktivitaet fuer den Pruefbericht.
    fehlt_in_aufgabe = {}
    fehlt_in_uebersicht = set()
    status_je_aufgabe = {
        aid: {s["user_id"]: s for s in statuses}
        for aid, statuses in assignments_status.items()
    }
    luecken_cmids = {l["cmid"] for l in luecken}

    for group in data["groups"]:
        # Nur Klassen aus dem Plan werden abgeglichen: andere Gruppen im
        # Kurs fliessen nicht in die Auswertung ein.
        abgleichen = bool(plan.get_track_for_class(group["name"]))

        for user in group["users"]:
            user["activities"] = {
                "assignments": [],
                "checklists": [],
                "feedbacks": [],
                "quizzes": []
            }

            # Verwende die zuvor erfassten Assignment-Status
            for assignment in activities["assignments"]:
                aid = assignment["id"]
                if aid in luecken_cmids:
                    user_assignment_status = unbekannter_status(
                        user["id"], next(l["grund"] for l in luecken if l["cmid"] == aid))
                else:
                    user_assignment_status = status_je_aufgabe.get(aid, {}).get(user["id"])
                    if user_assignment_status is None and abgleichen and gilt_fuer_gruppe(
                            assignments_groups.get(aid), group["name"]):
                        user_assignment_status = unbekannter_status(
                            user["id"], "fehlt in der Bewertungstabelle")
                        fehlt_in_aufgabe.setdefault(aid, set()).add(user["id"])
                if user_assignment_status:
                    user["activities"]["assignments"].append({
                        "id": aid,
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
            fehlt_in_bewerterzeilen = (abgleichen and not grader_grund
                                       and user["id"] not in grader_personen)
            if fehlt_in_bewerterzeilen and plan_cmids & {q["id"] for q in activities["quizzes"]}:
                fehlt_in_uebersicht.add(user["id"])
            for quiz in activities["quizzes"]:
                quiz_id = quiz["id"]
                eintrag = None
                if quiz_id in tests_unbekannt:
                    eintrag = unbekannter_status(user["id"], tests_unbekannt[quiz_id])
                elif fehlt_in_bewerterzeilen and quiz_id in plan_cmids:
                    eintrag = unbekannter_status(user["id"], "fehlt in der Bewerterübersicht")
                # Suche Quiz-Daten im Grader-Report
                elif quiz_id in grader_data and user["id"] in grader_data[quiz_id]["grades"]:
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

                    eintrag = {
                        "user_id": user["id"],
                        "status": status,
                        "status2": status2,
                        "submission": "Quiz abgeschlossen" if status2 == "Bewertet" else "Nicht abgeschlossen",
                        "submission_time": submission_time,
                        "grade_options": [],
                        "grade": grade
                    }

                if eintrag:
                    user["activities"]["quizzes"].append({
                        "id": quiz_id,
                        "status": eintrag,
                        "category_id": quiz.get("category_id"),
                        "category_name": quiz.get("category_name")
                    })

    # Personen, die einzeln fehlen, als Luecke je Aufgabe vermerken
    for aid, personen in sorted(fehlt_in_aufgabe.items()):
        titel = next((a["title"] for a in activities["assignments"] if a["id"] == aid), aid)
        luecken.append({"cmid": aid, "titel": titel, "typ": "assign",
                        "personen": sorted(personen), "grund": "fehlt in der Bewertungstabelle"})
    if fehlt_in_uebersicht:
        for quiz in activities["quizzes"]:
            if quiz["id"] in plan_cmids and quiz["id"] not in tests_unbekannt:
                luecken.append({"cmid": quiz["id"], "titel": quiz.get("title", quiz["id"]),
                                "typ": "quiz", "personen": sorted(fehlt_in_uebersicht),
                                "grund": "fehlt in der Bewerterübersicht"})

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

    # Gruppen aus dem Plan, deren Mitglieder nicht ladbar waren: ohne sie
    # fehlt die ganze Klasse — das ist kein Fall fuer "vorlaeufig".
    for fehler in gruppen_fehler:
        validation_errors.append(f"FEHLER: Gruppenmitglieder nicht ladbar — {fehler}")

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

    # Prüfe Assignments-Status: nur wenn *keine einzige* Aufgabe lesbar war,
    # ist der Kurs unbrauchbar. Einzelne Ausfaelle sind Luecken (unbekannt).
    if activities["assignments"] and not assignments_status:
        validation_errors.append("FEHLER: Assignments gefunden, aber keine einzige Bewertungsseite lesbar")

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
            raise ExportValidationError(
                f"Kurs {course_id}: " + "; ".join(critical_errors)
            )
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

    # =====================================================
    # PRUEFBERICHT: Luecken (Status unbekannt) und Hinweise
    # =====================================================
    if luecken:
        logger.warning(f"[!] {len(luecken)} Lücke(n) — Status UNBEKANNT, Noten gelten als vorläufig:")
        for l in luecken:
            wer = "alle" if l["personen"] == "alle" else f"{len(l['personen'])} Person(en)"
            logger.warning(f"  {l['typ']:6} {l['titel'][:45]:45} {wer:>14}  {l['grund']}")
    else:
        logger.info("[OK] Keine Lücken: jeder Status ist bekannt")
    for h in hinweise:
        logger.warning(f"  Hinweis: {h}")

    data["course_id"] = str(course_id)
    data["titel"] = course_title
    data["pruefbericht"] = {
        "luecken": luecken,
        "hinweise": hinweise,
        "personen_gruppen": total_users,
        "personen_bewerteruebersicht": len(grader_personen),
    }
    return data


def _vergleiche_mit_vorlauf(export_folder, data):
    """
    Vergleicht die Zaehlwerte des neuen Exports mit dem letzten Lauf.

    Returns:
        (dateiname_des_vorlaufs oder None, Liste von Meldungen)
    """
    import glob
    vorherige = glob.glob(os.path.join(export_folder, 'output_*.json'))
    if not vorherige:
        logger.info("Kein vorheriger Export gefunden — Verlaufsvergleich übersprungen.")
        return None, []

    letzter = max(vorherige, key=os.path.getctime)
    try:
        with open(letzter, 'r', encoding='utf-8') as f:
            alt = json.load(f)
    except (OSError, ValueError) as e:
        logger.warning(f"Vorheriger Export {os.path.basename(letzter)} nicht lesbar: {e}")
        return os.path.basename(letzter), []

    titel = {}
    for kurs in data.get("kurse", {}).values():
        for kat in kurs.get("activities_by_category", []):
            for typ in ("assignments", "quizzes"):
                for act in kat.get(typ, []):
                    titel[str(act.get("id"))] = act.get("title", "")

    meldungen = vergleiche_zaehlwerte(zaehlwerte(alt), zaehlwerte(data), titel)
    return os.path.basename(letzter), meldungen


def _protokolliere_pruefbericht(bericht):
    """Gibt den Pruefbericht am Ende des Laufs gesammelt aus."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("PRÜFBERICHT")
    logger.info("=" * 60)
    luecken = bericht.get("luecken", [])
    if luecken:
        logger.warning(f"Lücken: {len(luecken)} — betroffene Noten gelten im Dashboard als vorläufig")
        for l in luecken:
            wer = "alle" if l["personen"] == "alle" else f"{len(l['personen'])} Person(en)"
            logger.warning(f"  {l['titel'][:50]:50} {wer:>14}  {l['grund']}")
    else:
        logger.info("Lücken: keine — jeder Status ist bekannt")

    if bericht.get("fehlende_kurse"):
        logger.warning(f"Fehlende Kurse: {', '.join(bericht['fehlende_kurse'])}")

    verlauf = bericht.get("verlauf", [])
    if bericht.get("vergleich_mit"):
        if verlauf:
            logger.warning(f"Rückgänge gegenüber {bericht['vergleich_mit']}: {len(verlauf)}")
            for m in verlauf:
                logger.warning(f"  {m}")
        else:
            logger.info(f"Verlauf: keine Rückgänge gegenüber {bericht['vergleich_mit']}")

    for h in bericht.get("hinweise", []):
        logger.warning(f"Hinweis: {h}")

    if bericht.get("seiten_nachgeladen"):
        logger.info(f"Aufgeteilte Tabellen: {bericht['seiten_nachgeladen']} Folgeseite(n) nachgeladen")
    logger.info("=" * 60)


def main(test_mode=False):
    # Startzeit des Skripts
    start_time = time.time()
    timer = PhaseTimer()

    test_limit = 5  # Anzahl Items pro Typ im Testmodus

    if test_mode:
        logger.info("=" * 60)
        logger.info(f"[TESTMODUS] Export limitiert auf {test_limit} Eintraege pro Aktivitaetstyp")
        logger.info(f"[TESTMODUS] Dateiname wird 'test_output_...' sein")
        logger.info("=" * 60)

    logger.info("Starte Mebis-Datenexport...")
    logger.info(f"Startzeit: {datetime.now().strftime('%H:%M:%S')}")

    # Lade Konfiguration ueber config_manager
    timer.start("Konfiguration laden")
    credentials = config_manager.get_login_credentials()
    username = credentials['username']
    password = credentials['password']

    urls = config_manager.get_urls()
    base_url = urls['base_url']

    mode_settings = config_manager.get_mode_settings()
    isheadless = str(mode_settings['headless'])
    waittime = mode_settings['waittime']

    # Kurse kommen aus plan.json, nicht mehr aus MEBIS_COURSE_ID.
    # Gesperrte Kurse werden uebersprungen: ihr Abruf lieferte nur eine
    # Fehler- oder Anmeldeseite, und das ist kein Verbindungsfehler.
    try:
        plan = get_plan()
    except PlanFehler as e:
        logger.error("Planungsdatei konnte nicht geladen werden:")
        for meldung in e.meldungen:
            logger.error(f"  - {meldung}")
        sys.exit(1)

    alle_kurse = plan.get_kurse()
    kurse = plan.get_kurse(nur_offene=True)
    uebersprungen = [k for k in alle_kurse if k['gesperrt']]

    logger.info(f"Plan: {plan.schuljahr}, {len(alle_kurse)} Kurse, "
                f"{plan.stunden_gesamt:.2f} geplante Stunden")
    for kurs in uebersprungen:
        frei = kurs['freischaltung'].isoformat() if kurs['freischaltung'] else 'offen'
        logger.info(f"  uebersprungen (gesperrt): {kurs['titel']} "
                    f"(ID {kurs['moodle_course_id']}), Freischaltung {frei}")

    if not kurse:
        logger.error("Kein scrapebarer Kurs in plan.json (alle gesperrt).")
        sys.exit(1)

    timer.stop({"kurse_gesamt": len(alle_kurse), "kurse_offen": len(kurse)})

    # Ein Driver und ein Login fuer alle Kurse.
    timer.start("WebDriver erstellen & Login")
    driver = create_webdriver(headless=isheadless)
    driver.get(f"{base_url}?course={kurse[0]['moodle_course_id']}")

    logger.info("Fuehre Login durch...")
    login(driver, username, password, waittime)

    logger.info("Extrahiere Sesskey...")
    sesskey = get_sesskey(driver)
    if not sesskey:
        logger.error("Sesskey konnte nicht extrahiert werden. Ueberpruefe den Login-Prozess.")
        driver.quit()
        sys.exit(1)
    timer.stop()

    kurs_daten = {}
    groups = []
    fehlende_kurse = []

    try:
        for kurs in kurse:
            course_id = kurs['moodle_course_id']
            try:
                daten = export_course(
                    driver=driver,
                    course_id=course_id,
                    course_title=kurs['titel'],
                    base_url=base_url,
                    username=username,
                    password=password,
                    isheadless=isheadless,
                    waittime=waittime,
                    test_mode=test_mode,
                    test_limit=test_limit,
                    timer=timer,
                )
            except ExportValidationError as e:
                logger.error(f"Kurs '{kurs['titel']}' uebersprungen: {e}")
                fehlende_kurse.append(kurs['titel'])
                continue

            # Die Gruppen sind kursuebergreifend dieselben Personen, ihre
            # Aktivitaeten aber je Kurs verschieden. Frueher wurden die
            # Gruppen nur vom ersten Kurs uebernommen — damit gingen alle
            # Abgaben spaeterer Kurse verloren. Jetzt werden sie je Person
            # zusammengefuehrt und aus den Kursdaten herausgehalten.
            fuehre_gruppen_zusammen(groups, daten.pop("groups", []))
            kurs_daten[str(course_id)] = daten

        if not kurs_daten:
            logger.error("Kein Kurs konnte exportiert werden.")
            sys.exit(1)

        data = {
            "schema": EXPORT_SCHEMA_VERSION,
            "exported_at": datetime.now().isoformat(timespec='seconds'),
            "schuljahr": plan.schuljahr,
            "kurse": kurs_daten,
            "groups": groups,
        }

        if fehlende_kurse:
            logger.warning(f"Unvollstaendig: {len(fehlende_kurse)} Kurs(e) fehlen "
                           f"im Export: {', '.join(fehlende_kurse)}")

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

        # =====================================================
        # VERLAUF: Zaehlwerte je Aufgabe und Klasse gegen den letzten Lauf.
        # Ersetzt den frueheren Groessenvergleich der Datei. Ein Rueckgang
        # ist eine Warnung im Pruefbericht, kein Grund zum Verwerfen:
        # Abmeldungen oder zurueckgesetzte Abgaben senken Zahlen zu Recht,
        # und eine echte Luecke ist bereits als "unbekannt" markiert.
        # =====================================================
        vorlauf, verlauf = (None, []) if test_mode else _vergleiche_mit_vorlauf(export_folder, data)

        data["pruefbericht"] = {
            "luecken": [
                {**l, "kurs": cid} for cid, k in kurs_daten.items()
                for l in k.get("pruefbericht", {}).get("luecken", [])
            ],
            "hinweise": [
                h for k in kurs_daten.values()
                for h in k.get("pruefbericht", {}).get("hinweise", [])
            ],
            "fehlende_kurse": fehlende_kurse,
            "verlauf": verlauf,
            "vergleich_mit": vorlauf,
            "seiten_nachgeladen": _seiten_statistik["nachgeladen"],
        }

        try:
            os.makedirs(export_folder, exist_ok=True)
            json_bytes = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            with open(local_filename, 'wb') as f:
                f.write(json_bytes)
            save_duration = time.time() - save_start_time
            logger.info(f"Daten erfolgreich lokal gespeichert in {save_duration:.1f}s: {local_filename}")
            save_success = True

            _protokolliere_pruefbericht(data["pruefbericht"])

        except Exception as e:
            logger.error(f"Lokale Speicherung fehlgeschlagen: {e}")
            save_success = False

        timer.stop()

    finally:
        # Cleanup: Schliesse alle WebDriver-Instanzen
        try:
            driver.quit()
        except Exception:
            pass
        # Cleanup aller Thread-spezifischen WebDriver
        cleanup_thread_drivers()

    # Endzeit des Skripts
    end_time = time.time()
    duration = end_time - start_time
    duration_minutes = duration / 60  # Umrechnung von Sekunden in Minuten

    # Performance-Statistiken
    def _count(kurs_daten, feld):
        return sum(
            len(kat.get(feld, []))
            for daten in kurs_daten.values()
            for kat in daten.get("activities_by_category", [])
        )

    n_assignments = _count(kurs_daten, "assignments")
    n_checklists = _count(kurs_daten, "checklists")
    n_quizzes = _count(kurs_daten, "quizzes")
    total_activities = n_assignments + n_checklists + n_quizzes
    total_groups = len(groups)
    total_users = sum(len(group["users"]) for group in groups)

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
    logger.info(f"Kurse: {len(kurs_daten)} exportiert" + (f", {len(fehlende_kurse)} fehlgeschlagen" if fehlende_kurse else ""))
    for cid, daten in kurs_daten.items():
        logger.info(f"  - {daten.get('titel', cid)} (ID {cid})")
    logger.info(f"Aktivitaeten: {total_activities} ({n_assignments} Assignments, {n_checklists} Checklists, {n_quizzes} Quizzes)")
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
