#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mebis Quiz Scraper für Leistungsnachweise
Scrapt Quizzes und speichert strukturierte Daten für PDF-Generierung
"""

import os
import sys

# Add project root to path for imports
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import json
import time
import re
import requests
from datetime import datetime
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Import aus bestehendem Code
from src.export.exporter import (
    create_webdriver,
    login,
    get_sesskey,
    parse_german_datetime
)
from src.exam.utils import QuizParser, ImageDownloader
from src.common.group_utils import extract_group_prefix
from config.config_manager import config_manager
from config.logger_config import get_logger

# Logger Setup
scraper_logger = get_logger('exam_scraper')


def parse_user_date(date_str: str) -> Optional[datetime]:
    """
    Parsed Benutzereingabe im Format TT.MM.YYYY zu datetime

    Args:
        date_str: Datum-String im Format "28.01.2025"

    Returns:
        datetime-Objekt oder None bei Fehler
    """
    if not date_str or not date_str.strip():
        return None

    try:
        # Parse TT.MM.YYYY Format
        return datetime.strptime(date_str.strip(), "%d.%m.%Y")
    except ValueError as e:
        scraper_logger.error(f"Invalid date format '{date_str}'. Expected DD.MM.YYYY (e.g., 28.01.2025)")
        return None


def parse_selection_input(input_str: str, max_num: int) -> List[int]:
    """
    Parst User-Input für Auswahl (z.B. "1,3,5" oder "1-3" oder "all")

    Args:
        input_str: User-Input String
        max_num: Maximale Nummer (Anzahl der Items)

    Returns:
        List[int]: Liste der ausgewählten Indizes (0-basiert)
    """
    input_str = input_str.strip().lower()

    if input_str == 'all' or input_str == 'alle':
        return list(range(max_num))

    selected = []
    parts = input_str.split(',')

    for part in parts:
        part = part.strip()
        if '-' in part:
            # Range (z.B. "1-3")
            try:
                start, end = part.split('-')
                start = int(start.strip())
                end = int(end.strip())
                # Konvertiere zu 0-basiert
                selected.extend(range(start - 1, end))
            except ValueError:
                continue
        else:
            # Einzelne Nummer
            try:
                num = int(part)
                # Konvertiere zu 0-basiert
                selected.append(num - 1)
            except ValueError:
                continue

    # Filtere ungültige Nummern
    selected = [i for i in selected if 0 <= i < max_num]

    return selected


def select_items_interactive(items: List[Dict], item_name: str = "Item") -> List[Dict]:
    """
    Zeigt eine Liste von Items an und lässt User auswählen

    Args:
        items: Liste von Dictionaries mit 'id' und 'name'/'quiz_name'/'group_name'
        item_name: Name des Item-Typs (z.B. "Quiz", "Gruppe")

    Returns:
        List[Dict]: Ausgewählte Items
    """
    if not items:
        print(f"Keine {item_name}s gefunden.")
        return []

    # Prüfe ob es Gruppen sind - wenn ja, nach Präfix gruppieren
    is_groups = all('group_name' in item for item in items)

    if is_groups:
        # Gruppiere nach Präfix
        from collections import defaultdict
        prefix_groups = defaultdict(list)

        for item in items:
            group_name = item.get('group_name', '')
            prefix = extract_group_prefix(group_name)
            prefix_groups[prefix].append(item)

        # Erstelle Display-Liste: [(prefix, [items])]
        display_items = sorted(prefix_groups.items())

        print(f"\n{'='*70}")
        print(f"Verfügbare {item_name}s ({len(display_items)} Präfixe, {len(items)} Teams):")
        print(f"{'='*70}")

        for idx, (prefix, group_items) in enumerate(display_items, 1):
            # Sammle alle IDs
            ids = [item.get('group_id', 'N/A') for item in group_items]
            ids_str = ', '.join(ids)

            print(f"{idx:3}. {prefix[:50]:<50} (IDs: {ids_str})")

        print(f"{'='*70}")
        print(f"\nHinweis: Auswahl eines Präfix wählt automatisch alle zugehörigen Teams aus.")

    else:
        # Normale Anzeige (für Quizzes)
        print(f"\n{'='*70}")
        print(f"Verfügbare {item_name}n ({len(items)}):")
        print(f"{'='*70}")

        for idx, item in enumerate(items, 1):
            name = item.get('quiz_name') or item.get('name', 'Unbekannt')
            item_id = item.get('quiz_id') or item.get('id', 'N/A')

            # Zusätzliche Info (z.B. Deadline bei Quizzes)
            extra_info = ''
            if 'deadline' in item and item['deadline']:
                extra_info = f" (Deadline: {item['deadline']})"

            print(f"{idx:3}. {name[:50]:<50} [ID: {item_id}]{extra_info}")

        print(f"{'='*70}")

    print(f"\nAuswahl-Optionen:")
    print(f"  - 'all' oder 'alle': Alle {item_name}n auswählen")
    print(f"  - Einzelne Nummern: '1,3,5' (wählt Nr. 1, 3 und 5)")
    print(f"  - Bereiche: '1-3' (wählt Nr. 1, 2 und 3)")
    print(f"  - Kombiniert: '1,3-5,7' (wählt Nr. 1, 3, 4, 5 und 7)")
    print(f"  - 'q' oder 'quit': Abbrechen")

    while True:
        user_input = input(f"\nWelche {item_name}n möchten Sie scrapen? ").strip()

        if user_input.lower() in ['q', 'quit', 'exit']:
            print("Abbruch durch User.")
            return []

        if is_groups:
            # Parse Auswahl basierend auf Präfix-Anzahl
            selected_indices = parse_selection_input(user_input, len(display_items))

            if not selected_indices:
                print(f"Keine gültige Auswahl. Bitte versuchen Sie es erneut.")
                continue

            # Sammle alle Items aus den ausgewählten Präfixen
            selected_items = []
            selected_prefixes = []
            for idx in selected_indices:
                prefix, group_items = display_items[idx]
                selected_items.extend(group_items)
                selected_prefixes.append(prefix)

            # Zeige Auswahl
            print(f"\nAusgewählte {item_name}s ({len(selected_prefixes)} Präfixe, {len(selected_items)} Teams):")
            for prefix in selected_prefixes:
                print(f"  - {prefix}")

        else:
            # Normal (für Quizzes)
            selected_indices = parse_selection_input(user_input, len(items))

            if not selected_indices:
                print(f"Keine gültige Auswahl. Bitte versuchen Sie es erneut.")
                continue

            selected_items = [items[i] for i in selected_indices]
            print(f"\nAusgewählte {item_name}s ({len(selected_items)}):")
            for item in selected_items:
                name = item.get('quiz_name') or item.get('name', 'Unbekannt')
                print(f"  - {name}")

        # Keine Bestätigung mehr - direkt zurückgeben
        return selected_items


class QuizScraper:
    """Scraper für Mebis Leistungsnachweise"""

    def __init__(self, headless: bool = True, waittime: int = 10):
        """
        Initialisiert den Scraper

        Args:
            headless: Headless-Modus für Browser
            waittime: Wartezeit für Selenium
        """
        self.headless = headless
        self.waittime = waittime
        self.driver = None
        self.sesskey = None
        self.base_url = 'https://lernplattform.bycs.de'
        self.logger = scraper_logger

        # Konfiguration laden
        credentials = config_manager.get_login_credentials()
        self.username = credentials['username']
        self.password = credentials['password']
        self.course_id = config_manager.get_course_id()

        # Output-Verzeichnisse (absolute Pfade vom Projekt-Root)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_dir = os.path.join(project_root, 'data', 'quiz_data')
        self.output_dir = os.path.join(project_root, 'data', 'LNW')

        self.logger.info("QuizScraper initialized")

    def start_session(self):
        """Startet Browser-Session und führt Login durch"""
        self.logger.info("Starting browser session...")

        # WebDriver erstellen
        self.driver = create_webdriver(headless=str(self.headless))

        # Login
        progress_url = f"{self.base_url}/report/progress/index.php?course={self.course_id}"
        self.driver.get(progress_url)
        time.sleep(2)

        if "login" in self.driver.current_url:
            self.logger.info("Performing login...")
            login(self.driver, self.username, self.password, self.waittime)
            time.sleep(2)

        # Sesskey extrahieren
        self.sesskey = get_sesskey(self.driver, self.waittime)
        if not self.sesskey:
            raise Exception("Failed to obtain sesskey")

        self.logger.info(f"Session started successfully (sesskey: {self.sesskey[:10]}...)")

    def close_session(self):
        """Schließt Browser-Session"""
        if self.driver:
            self.driver.quit()
            self.logger.info("Browser session closed")

    def discover_quizzes(self) -> List[Dict]:
        """
        Findet alle Leistungsnachweise (Quizzes mit "(Leistungsnachweis)" im Namen)

        Returns:
            List[Dict]: Liste mit Quiz-Informationen (id, name, url, deadline)
        """
        self.logger.info("Discovering quizzes with '(Leistungsnachweis)' in name...")

        quiz_index_url = f"{self.base_url}/mod/quiz/index.php?id={self.course_id}"
        self.driver.get(quiz_index_url)
        time.sleep(2)

        quizzes = []

        try:
            # Warte auf Tabelle
            WebDriverWait(self.driver, self.waittime).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
            )

            # Parse HTML
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            table = soup.find('table', class_='course-overview-table')

            if not table:
                self.logger.warning(f"Quiz table not found at URL: {quiz_index_url}")
                return quizzes

            rows = table.find('tbody').find_all('tr')

            for row in rows:
                try:
                    # Quiz-ID aus Row-Attribut
                    quiz_id = row.get('data-mdl-overview-cmid')
                    if not quiz_id:
                        continue

                    # Name-Spalte
                    name_cell = row.find('td', attrs={'data-mdl-overview-item': 'name'})
                    if not name_cell:
                        continue

                    link = name_cell.find('a', class_='activityname')
                    if not link:
                        continue

                    quiz_name = link.get_text(strip=True)

                    # Filter: Nur Leistungsnachweise
                    if '(Leistungsnachweis)' not in quiz_name:
                        continue

                    # Deadline
                    deadline_cell = row.find('td', attrs={'data-mdl-overview-item': 'duedate'})
                    deadline = 'Kein Abgabedatum'
                    if deadline_cell:
                        date_span = deadline_cell.find('span', class_='date')
                        if date_span:
                            deadline = date_span.get_text(strip=True)
                        else:
                            text = deadline_cell.get_text(strip=True)
                            if text and text != '-':
                                deadline = text

                    quizzes.append({
                        'quiz_id': quiz_id,
                        'quiz_name': quiz_name,
                        'quiz_url': f"{self.base_url}/mod/quiz/view.php?id={quiz_id}",
                        'deadline': deadline
                    })

                    self.logger.info(f"Found quiz: {quiz_name} (ID: {quiz_id})")

                except Exception as e:
                    self.logger.warning(f"Error parsing quiz row: {e}")
                    continue

        except Exception as e:
            self.logger.error(f"Error discovering quizzes: {e}")

        self.logger.info(f"Discovered {len(quizzes)} Leistungsnachweise")
        return quizzes

    def get_groups(self) -> List[Dict]:
        """
        Holt Gruppenliste aus der Konfiguration oder vom Server

        Returns:
            List[Dict]: Liste mit Gruppeninformationen (id, name)
        """
        self.logger.info("Fetching groups...")

        # Lade ignorierte Gruppen aus Konfiguration
        ignored_groups = config_manager.get_ignored_groups()
        if ignored_groups:
            self.logger.info(f"Ignoring {len(ignored_groups)} groups from configuration: {', '.join(ignored_groups)}")

        # Verwende die gleiche Logik wie exportData.py
        # Navigiere zur Progress-Seite und hole Gruppen-Dropdown
        progress_url = f"{self.base_url}/report/progress/index.php?course={self.course_id}"
        self.driver.get(progress_url)
        time.sleep(2)

        groups = []

        try:
            # Warte auf Gruppen-Select
            WebDriverWait(self.driver, self.waittime).until(
                EC.presence_of_element_located((By.NAME, "group"))
            )

            # Parse Optionen
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            select_elem = soup.find('select', {'name': 'group'})

            if select_elem:
                options = select_elem.find_all('option')

                for option in options:
                    group_id = option.get('value')
                    group_name = option.get_text(strip=True)

                    # Überspringe Gruppe 0 (alle Gruppen)
                    if group_id == '0':
                        continue

                    # Überspringe ignorierte Gruppen
                    if group_name in ignored_groups:
                        self.logger.debug(f"Skipping ignored group: {group_name}")
                        continue

                    groups.append({
                        'group_id': group_id,
                        'group_name': group_name
                    })

                    # Log nur den Präfix (z.B. "IFA12A" statt "IFA12A - Team 3")
                    group_prefix = extract_group_prefix(group_name)
                    self.logger.info(f"Found group: {group_prefix} (ID: {group_id})")

        except Exception as e:
            self.logger.error(f"Error fetching groups: {e}")

        self.logger.info(f"Found {len(groups)} groups")
        return groups

    def get_attempts_for_group(self, quiz_id: str, group_id: str, since_date: Optional[datetime] = None) -> List[Dict]:
        """
        Holt alle Versuche für ein Quiz und eine Gruppe

        Args:
            quiz_id: Quiz-ID
            group_id: Gruppen-ID
            since_date: Optional - Nur Versuche seit diesem Datum (inklusiv)

        Returns:
            List[Dict]: Liste mit Versuchsinformationen (user_id, user_name, attempt_id, finished_time)
        """
        if since_date:
            self.logger.info(f"Fetching attempts for quiz {quiz_id}, group {group_id} since {since_date.strftime('%d.%m.%Y')}...")
        else:
            self.logger.info(f"Fetching attempts for quiz {quiz_id}, group {group_id}...")

        # Report-URL mit Gruppierungsparameter
        report_url = (f"{self.base_url}/mod/quiz/report.php?id={quiz_id}"
                     f"&mode=overview&attempts=enrolled_with&onlygraded="
                     f"&group={group_id}&onlyregraded=0&slotmarks=1")

        self.driver.get(report_url)
        time.sleep(2)

        attempts = []

        try:
            # Warte auf Tabelle (oder akzeptiere, dass keine Versuche vorhanden sind)
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, "attempts"))
                )
            except:
                self.logger.info("No attempts table found (possibly no submissions)")
                return attempts

            # Parse HTML
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            table = soup.find('table', id='attempts')

            if not table:
                return attempts

            tbody = table.find('tbody')
            if not tbody:
                return attempts

            rows = tbody.find_all('tr')

            # Dictionary für neueste Versuche pro Benutzer
            user_attempts = {}

            for row in rows:
                try:
                    # User-Link (in c1 oder c2, je nach Spaltenstruktur)
                    user_link = None
                    for cell in row.find_all('td'):
                        link = cell.find('a', href=re.compile(r'user/view.php\?id='))
                        if link:
                            user_link = link
                            break

                    if not user_link:
                        continue

                    # User-ID und Name
                    user_href = user_link.get('href', '')
                    user_id_match = re.search(r'id=(\d+)', user_href)
                    if not user_id_match:
                        continue

                    user_id = user_id_match.group(1)

                    # User-Name: Bevorzugt aus title-Attribut (vollständiger Name)
                    # sonst aus Link-Text
                    user_name = user_link.get('title', '') or user_link.get_text(strip=True)

                    # Review-Link (für attempt_id)
                    review_link = row.find('a', class_='reviewlink')
                    if not review_link:
                        # Kein Review-Link = nicht abgeschlossen/bewertet
                        continue

                    review_href = review_link.get('href', '')
                    attempt_id_match = re.search(r'attempt=(\d+)', review_href)
                    if not attempt_id_match:
                        continue

                    attempt_id = attempt_id_match.group(1)

                    # Abschluss-Zeit (c7 - "Beendet")
                    finished_cell = row.find('td', class_='c7')
                    finished_time_raw = finished_cell.get_text(strip=True) if finished_cell else None
                    finished_time_str = parse_german_datetime(finished_time_raw) if finished_time_raw else None
                    try:
                        finished_time = datetime.fromisoformat(finished_time_str) if finished_time_str else None
                    except (ValueError, TypeError):
                        finished_time = None

                    # Datumsfilter: Überspringe Versuche vor since_date
                    if since_date and finished_time:
                        if finished_time < since_date:
                            continue

                    # Speichere nur den neuesten Versuch pro User
                    # (Annahme: Tabelle ist nach Zeit sortiert, erste Zeile = neuester)
                    if user_id not in user_attempts:
                        user_attempts[user_id] = {
                            'user_id': user_id,
                            'user_name': user_name,
                            'attempt_id': attempt_id,
                            'finished_time': finished_time
                        }

                except Exception as e:
                    self.logger.warning(f"Error parsing attempt row: {e}")
                    continue

            attempts = list(user_attempts.values())

            if since_date:
                self.logger.info(f"Found {len(attempts)} unique student attempts since {since_date.strftime('%d.%m.%Y')}")
            else:
                self.logger.info(f"Found {len(attempts)} unique student attempts")

        except Exception as e:
            self.logger.error(f"Error fetching attempts: {e}")

        return attempts

    def scrape_review_page(self, attempt_id: str, output_dir: str) -> Dict:
        """
        Scrapt eine Review-Seite für einen Versuch

        Args:
            attempt_id: Attempt-ID
            output_dir: Ausgabeverzeichnis für Daten und Bilder

        Returns:
            Dict: Geparste Review-Daten (metadata, sections)
        """
        self.logger.info(f"Scraping review page for attempt {attempt_id}...")

        review_url = f"{self.base_url}/mod/quiz/review.php?attempt={attempt_id}"
        self.driver.get(review_url)
        time.sleep(2)

        try:
            # Warte auf Seiteninhalt
            WebDriverWait(self.driver, self.waittime).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # HTML-Content holen
            html_content = self.driver.page_source

            # Session mit Cookies vom WebDriver erstellen
            session = requests.Session()
            for cookie in self.driver.get_cookies():
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))

            # Image Downloader mit Session und WebDriver erstellen
            img_downloader = ImageDownloader(session=session, driver=self.driver)

            # Parser verwenden - übergebe attempt_id und URL
            parser = QuizParser(image_downloader=img_downloader)
            review_data = parser.parse_review_page(html_content, output_dir, attempt_id=attempt_id, review_url=review_url)

            self.logger.info(f"Successfully scraped review for attempt {attempt_id}")
            return review_data

        except Exception as e:
            self.logger.error(f"Error scraping review page: {e}")
            return {'metadata': {}, 'sections': []}

    @staticmethod
    def _scrape_attempt_worker(attempt: Dict, output_dir: str, base_url: str,
                                username: str, password: str, course_id: str,
                                headless: bool, waittime: int, idx: int, total: int) -> Dict:
        """
        Worker-Funktion für paralleles Scraping eines einzelnen Attempts
        Jeder Worker erstellt seine eigene WebDriver-Instanz

        Args:
            attempt: Attempt-Daten (user_id, user_name, attempt_id)
            output_dir: Ausgabeverzeichnis
            base_url: Mebis Base URL
            username: Login Username
            password: Login Passwort
            course_id: Kurs-ID
            headless: Headless-Modus
            waittime: Wartezeit
            idx: Aktueller Index
            total: Gesamtanzahl

        Returns:
            Dict: Student-Daten oder None bei Fehler
        """
        driver = None
        logger = get_logger('exam_scraper_worker')

        try:
            logger.info(f"[{idx}/{total}] Starting worker for {attempt['user_name']}...")

            # Eigene WebDriver-Instanz erstellen
            driver = create_webdriver(headless=str(headless))

            # Login
            progress_url = f"{base_url}/report/progress/index.php?course={course_id}"
            driver.get(progress_url)
            time.sleep(2)

            if "login" in driver.current_url:
                logger.info(f"[{idx}/{total}] Performing login...")
                login(driver, username, password, waittime)
                time.sleep(2)

            # Review-Seite scrapen
            attempt_id = attempt['attempt_id']
            review_url = f"{base_url}/mod/quiz/review.php?attempt={attempt_id}"
            driver.get(review_url)
            time.sleep(2)

            # Warte auf Seiteninhalt
            WebDriverWait(driver, waittime).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # HTML-Content holen
            html_content = driver.page_source

            # Session mit Cookies vom WebDriver erstellen
            session = requests.Session()
            for cookie in driver.get_cookies():
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))

            # Image Downloader mit Session und WebDriver erstellen
            img_downloader = ImageDownloader(session=session, driver=driver)

            # Parser verwenden
            parser = QuizParser(image_downloader=img_downloader)
            review_data = parser.parse_review_page(html_content, output_dir, attempt_id=attempt_id, review_url=review_url)

            # Bevorzuge User-Name aus Review-Seite Metadaten
            user_name = review_data['metadata'].get('user_name') or attempt['user_name']

            student_data = {
                'user_id': attempt['user_id'],
                'user_name': user_name,
                'attempt_id': attempt['attempt_id'],
                'metadata': review_data['metadata'],
                'sections': review_data['sections']
            }

            logger.info(f"[{idx}/{total}] Successfully scraped {user_name}")
            return student_data

        except Exception as e:
            logger.error(f"[{idx}/{total}] Error in worker for {attempt['user_name']}: {e}")
            return None

        finally:
            # WebDriver schließen
            if driver:
                try:
                    driver.quit()
                except:
                    pass

    def scrape_quiz_for_group(self, quiz_info: Dict, group_info: Dict, force_rescrape: bool = True, max_workers: int = 3, since_date: Optional[datetime] = None):
        """
        Scrapt ein Quiz für eine spezifische Gruppe mit paralleler Verarbeitung

        Args:
            quiz_info: Dict mit Quiz-Informationen
            group_info: Dict mit Gruppen-Informationen
            force_rescrape: Wenn True (Standard), überschreibe vorhandene Daten
            max_workers: Anzahl paralleler Browser-Threads (Standard: 3)
            since_date: Optional - Nur Versuche seit diesem Datum scrapen
        """
        quiz_id = quiz_info['quiz_id']
        quiz_name = quiz_info['quiz_name']
        group_id = group_info['group_id']
        group_name = group_info['group_name']

        # Extrahiere Präfix für Log-Ausgaben (z.B. "IFA12A" statt "IFA12A - Team 3")
        group_prefix = extract_group_prefix(group_name)

        self.logger.info(f"Processing quiz '{quiz_name}' for group '{group_prefix}'...")

        # Output-Verzeichnis: Gruppe → Quiz (geändert von Quiz → Gruppe)
        output_dir = os.path.join(self.data_dir, group_prefix, quiz_name)
        # Verwende group_id für eindeutige Dateinamen (falls mehrere Teams pro Präfix)
        data_file = os.path.join(output_dir, f'data_{group_id}.json')

        # Prüfe ob bereits gescrapt (außer force)
        if os.path.exists(data_file) and not force_rescrape:
            self.logger.info(f"Data already exists for {quiz_name}/{group_prefix}, skipping")
            return

        # Wenn Daten bereits existieren und überschrieben werden
        if os.path.exists(data_file) and force_rescrape:
            self.logger.info(f"Overwriting existing data for {quiz_name}/{group_prefix}")

        # Hole Versuche (mit optionalem Datumsfilter)
        attempts = self.get_attempts_for_group(quiz_id, group_id, since_date)

        if not attempts:
            self.logger.warning(f"No attempts found for quiz '{quiz_name}', group '{group_prefix}' - skipping file creation")
            return

        # Erstelle Output-Verzeichnis nur wenn Daten vorhanden sind
        os.makedirs(output_dir, exist_ok=True)

        # Scrape jede Review-Seite parallel
        students_data = []

        self.logger.info(f"Starting parallel scraping with {max_workers} workers...")

        # ThreadPoolExecutor für paralleles Scraping
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Erstelle Futures für alle Attempts
            future_to_attempt = {}
            for idx, attempt in enumerate(attempts, 1):
                future = executor.submit(
                    self._scrape_attempt_worker,
                    attempt=attempt,
                    output_dir=output_dir,
                    base_url=self.base_url,
                    username=self.username,
                    password=self.password,
                    course_id=self.course_id,
                    headless=self.headless,
                    waittime=self.waittime,
                    idx=idx,
                    total=len(attempts)
                )
                future_to_attempt[future] = attempt

            # Sammle Ergebnisse wenn sie fertig sind
            for future in as_completed(future_to_attempt):
                attempt = future_to_attempt[future]
                try:
                    student_data = future.result()
                    if student_data:
                        # Füge group_id und group_name hinzu (fehlt in Worker-Funktion)
                        student_data['group_id'] = group_id
                        student_data['group_name'] = group_name
                        students_data.append(student_data)
                except Exception as e:
                    self.logger.error(f"Error processing result for {attempt['user_name']}: {e}")
                    continue

        # Speichere Daten
        final_data = {
            'quiz_info': {
                'quiz_id': quiz_id,
                'quiz_name': quiz_name,
                'group_id': group_id,
                'group_name': group_name,
                'scraped_date': datetime.now().isoformat()
            },
            'students': students_data
        }

        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Successfully saved data for {len(students_data)} students to {data_file}")

    def run(self, quiz_id: Optional[str] = None, group_id: Optional[str] = None, force_rescrape: bool = True, interactive: bool = True, max_workers: int = 3, since_date: Optional[datetime] = None):
        """
        Hauptmethode zum Ausführen des Scrapers

        Args:
            quiz_id: Optional - Nur ein spezifisches Quiz scrapen
            group_id: Optional - Nur eine spezifische Gruppe scrapen
            force_rescrape: Wenn True (Standard), überschreibe vorhandene Daten
            interactive: Wenn True, zeige interaktive Auswahl (Standard: True wenn keine CLI-Parameter)
            max_workers: Anzahl paralleler Browser-Threads (Standard: 3)
            since_date: Optional - Nur Versuche seit diesem Datum scrapen
        """
        start_time = time.time()

        try:
            # Session starten
            self.start_session()

            # Quizzes finden
            if quiz_id:
                # Spezifisches Quiz (Info manuell erstellen) - CLI-Parameter überschreibt interaktiven Modus
                quizzes = [{
                    'quiz_id': quiz_id,
                    'quiz_name': f'Quiz_{quiz_id}',  # Name wird beim Scraping aktualisiert
                    'quiz_url': f"{self.base_url}/mod/quiz/view.php?id={quiz_id}",
                    'deadline': 'Unknown'
                }]
                interactive = False  # Keine interaktive Auswahl wenn CLI-Parameter verwendet
            else:
                all_quizzes = self.discover_quizzes()

                if not all_quizzes:
                    self.logger.warning("No quizzes found to scrape")
                    return

                # Interaktive Auswahl wenn kein quiz_id Parameter
                if interactive:
                    quizzes = select_items_interactive(all_quizzes, "Quiz")
                    if not quizzes:
                        self.logger.info("No quizzes selected. Exiting.")
                        return
                else:
                    quizzes = all_quizzes

            # Gruppen holen
            if group_id:
                # Spezifische Gruppe - CLI-Parameter überschreibt interaktiven Modus
                groups = [{
                    'group_id': group_id,
                    'group_name': f'Group_{group_id}'  # Name wird beim Scraping aktualisiert
                }]
            else:
                all_groups = self.get_groups()

                if not all_groups:
                    self.logger.warning("No groups found")
                    return

                # Interaktive Auswahl wenn kein group_id Parameter UND interactive mode
                if interactive and not quiz_id:  # Nur fragen wenn auch Quizzes interaktiv gewählt
                    groups = select_items_interactive(all_groups, "Gruppe")
                    if not groups:
                        self.logger.info("No groups selected. Exiting.")
                        return
                else:
                    groups = all_groups

            # Datumsfilter (interaktiv oder CLI)
            if interactive and not since_date:
                print("\n" + "="*60)
                print("DATUMSFILTER (OPTIONAL)")
                print("="*60)
                date_input = input("Nur Versuche seit Datum (TT.MM.YYYY) [alle]: ").strip()

                if date_input:
                    since_date = parse_user_date(date_input)
                    if since_date:
                        print(f"✓ Filtere Versuche seit {since_date.strftime('%d.%m.%Y')}")
                    else:
                        print("✗ Ungültiges Datum - verwende alle Versuche")
                        since_date = None
                else:
                    print("✓ Verwende alle Versuche")
                print("="*60 + "\n")

            # Scrape jede Kombination
            total = len(quizzes) * len(groups)
            current = 0

            for quiz in quizzes:
                for group in groups:
                    current += 1
                    self.logger.info(f"\n{'='*60}")
                    self.logger.info(f"Progress: {current}/{total}")
                    self.logger.info(f"{'='*60}")

                    self.scrape_quiz_for_group(quiz, group, force_rescrape, max_workers, since_date)

            # Berechne Gesamtzeit
            elapsed_time = time.time() - start_time
            minutes = int(elapsed_time // 60)
            seconds = int(elapsed_time % 60)

            self.logger.info("\n" + "="*60)
            self.logger.info("SCRAPING COMPLETED")
            self.logger.info("="*60)
            self.logger.info(f"Processed {len(quizzes)} quizzes x {len(groups)} groups = {total} combinations")
            self.logger.info(f"Total time: {minutes} minutes {seconds} seconds ({elapsed_time:.1f}s)")

        except Exception as e:
            self.logger.error(f"Fatal error in scraper: {e}", exc_info=True)
            raise

        finally:
            self.close_session()


def main():
    """CLI Entry Point"""
    import argparse

    parser = argparse.ArgumentParser(description='Mebis Quiz Scraper für Leistungsnachweise')
    parser.add_argument('--quiz-id', type=str, help='Nur ein spezifisches Quiz scrapen (Quiz-ID)')
    parser.add_argument('--group', type=str, help='Nur eine spezifische Gruppe scrapen (Gruppen-ID)')
    parser.add_argument('--skip-existing', action='store_true', help='Überspringe bereits vorhandene Daten (standardmäßig werden Daten überschrieben)')
    parser.add_argument('--headless', type=str, default='True', choices=['True', 'False'],
                       help='Browser im Headless-Modus ausführen')
    parser.add_argument('--max-workers', type=int, default=3,
                       help='Anzahl paralleler Browser-Threads (Standard: 3)')
    parser.add_argument('--since-date', type=str,
                       help='Nur Versuche seit diesem Datum scrapen (Format: TT.MM.YYYY, z.B. 28.01.2025)')

    args = parser.parse_args()

    # Konfiguration
    headless = args.headless == 'True'
    mode_settings = config_manager.get_mode_settings()
    waittime = mode_settings['waittime']

    scraper_logger.info("Starting Mebis Quiz Scraper...")
    scraper_logger.info(f"Headless: {headless}, Waittime: {waittime}s")

    # Parse since_date wenn angegeben
    since_date = None
    if args.since_date:
        since_date = parse_user_date(args.since_date)
        if not since_date:
            scraper_logger.error("Invalid date format. Use DD.MM.YYYY (e.g., 28.01.2025)")
            return

    # Scraper erstellen und ausführen
    scraper = QuizScraper(headless=headless, waittime=waittime)
    scraper_logger.info(f"Parallel workers: {args.max_workers}")
    if since_date:
        scraper_logger.info(f"Date filter: Only attempts since {since_date.strftime('%d.%m.%Y')}")

    scraper.run(
        quiz_id=args.quiz_id,
        group_id=args.group,
        force_rescrape=not args.skip_existing,  # Standardmäßig True (überschreiben), außer --skip-existing gesetzt
        max_workers=args.max_workers,
        since_date=since_date
    )


if __name__ == '__main__':
    main()
