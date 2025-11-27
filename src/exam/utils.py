#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Exam Utilities für Quiz-Scraping und -Verarbeitung
Enthält Parser, Image-Downloader und Fragetyp-Erkennung
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urljoin
from config.logger_config import get_logger

# Logger Setup
exam_logger = get_logger('exam_utils')


class QuestionTypeDetector:
    """Erkennt den Fragentyp aus HTML-Struktur"""

    @staticmethod
    def detect(question_element) -> str:
        """
        Erkennt den Fragentyp aus dem HTML-Element

        Args:
            question_element: BeautifulSoup Element (div.que)

        Returns:
            str: Fragentyp (z.B. 'ddmarker', 'multichoice', 'truefalse', etc.)
        """
        classes = question_element.get('class', [])

        # Information Items (description) speziell behandeln
        if 'description' in classes and 'informationitem' in classes:
            exam_logger.debug("Detected information item (description)")
            return 'description'

        # Mebis verwendet spezifische Klassen für Fragentypen
        # Format: que <qtype> <status>
        for cls in classes:
            if cls.startswith('qtype_'):
                qtype = cls.replace('qtype_', '')
                exam_logger.debug(f"Detected question type: {qtype}")
                return qtype

        # Fallback: Versuche aus anderen Klassen zu erkennen
        if 'ddmarker' in classes:
            return 'ddmarker'
        elif 'multianswer' in classes:
            return 'multianswer'
        elif 'multichoice' in classes:
            return 'multichoice'
        elif 'truefalse' in classes:
            return 'truefalse'
        elif 'shortanswer' in classes:
            return 'shortanswer'
        elif 'essay' in classes:
            return 'essay'
        elif 'match' in classes:
            return 'match'
        elif 'ddwtos' in classes:
            return 'ddwtos'
        elif 'description' in classes:
            return 'description'

        exam_logger.warning(f"Unknown question type for classes: {classes}")
        return 'unknown'


class ImageDownloader:
    """Lädt Bilder von Mebis herunter mit Retry-Logik"""

    def __init__(self, session=None, base_url='https://lernplattform.mebis.bycs.de', driver=None):
        """
        Initialisiert den Image Downloader

        Args:
            session: Requests Session (optional, für Cookie-basierte Auth)
            base_url: Basis-URL für relative Pfade
            driver: Selenium WebDriver (optional, für Screenshots)
        """
        self.session = session or requests.Session()
        self.base_url = base_url
        self.driver = driver
        self.logger = exam_logger

    def download(self, img_url: str, output_path: str, max_retries: int = 3) -> bool:
        """
        Lädt ein Bild herunter

        Args:
            img_url: URL des Bildes
            output_path: Lokaler Pfad zum Speichern
            max_retries: Maximale Anzahl Wiederholungsversuche

        Returns:
            bool: True wenn erfolgreich, False sonst
        """
        # Vollständige URL erstellen
        if not img_url.startswith('http'):
            img_url = urljoin(self.base_url, img_url)

        # Output-Verzeichnis erstellen
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        for attempt in range(max_retries):
            try:
                self.logger.debug(f"Downloading image (attempt {attempt + 1}/{max_retries}): {img_url}")

                response = self.session.get(img_url, timeout=10)
                response.raise_for_status()

                # Prüfe ob es tatsächlich ein Bild ist (nicht HTML)
                content_type = response.headers.get('Content-Type', '')
                if not content_type.startswith('image/'):
                    self.logger.warning(f"Downloaded content is not an image (Content-Type: {content_type})")
                    # Prüfe auch den Content
                    if response.content[:100].decode('utf-8', errors='ignore').strip().startswith('<!DOCTYPE') or \
                       response.content[:100].decode('utf-8', errors='ignore').strip().startswith('<html'):
                        self.logger.error(f"Downloaded HTML instead of image - likely authentication issue. URL: {img_url}")
                        return False

                # Speichern
                with open(output_path, 'wb') as f:
                    f.write(response.content)

                self.logger.info(f"Successfully downloaded: {os.path.basename(output_path)}")
                return True

            except requests.RequestException as e:
                self.logger.warning(f"Download failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

        self.logger.error(f"Failed to download image after {max_retries} attempts: {img_url}")
        return False

    def extract_and_download_images(self, html_element, output_dir: str, prefix: str = '', base_dir: str = None) -> List[Dict[str, str]]:
        """
        Extrahiert alle Bilder aus einem HTML-Element und lädt sie herunter

        Args:
            html_element: BeautifulSoup Element
            output_dir: Verzeichnis zum Speichern der Bilder (absoluter Pfad)
            prefix: Präfix für Dateinamen
            base_dir: Basis-Verzeichnis für relative Pfade (optional)

        Returns:
            List[Dict]: Liste mit {'original_url', 'local_path', 'success'}
        """
        images = []
        img_tags = html_element.find_all('img')

        for idx, img in enumerate(img_tags, 1):
            src = img.get('src')
            if not src:
                continue

            # Dateiname erstellen
            parsed_url = urlparse(src)
            ext = os.path.splitext(parsed_url.path)[1] or '.png'
            filename = f"{prefix}_{idx}{ext}" if prefix else f"image_{idx}{ext}"
            absolute_path = os.path.join(output_dir, filename)

            # Download
            success = self.download(src, absolute_path)

            # Speichere relativen Pfad wenn base_dir gegeben, sonst absolut
            if base_dir and success:
                relative_path = os.path.relpath(absolute_path, base_dir)
            else:
                relative_path = absolute_path if success else None

            images.append({
                'original_url': src,
                'local_path': relative_path,
                'success': success,
                'alt': img.get('alt', ''),
                'title': img.get('title', '')
            })

        return images

    def take_element_screenshot(self, element_selector: str, output_path: str, soup_element=None, timeout: int = 2) -> bool:
        """
        Macht einen Screenshot eines HTML-Elements (Fallback wenn Bild-Download fehlschlägt)

        Args:
            element_selector: CSS-Selector für das Element (z.B. 'div.ddarea')
            output_path: Lokaler Pfad zum Speichern
            soup_element: BeautifulSoup Element (optional, für ID-basierte Selektion)
            timeout: Maximale Wartezeit in Sekunden (Standard: 2)

        Returns:
            bool: True wenn erfolgreich, False sonst
        """
        if not self.driver:
            self.logger.warning("No WebDriver available for screenshots")
            return False

        try:
            # Output-Verzeichnis erstellen
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Element finden mit WebDriverWait
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

            web_element = None

            # Versuche verschiedene Strategien, um das Element zu finden
            try:
                if soup_element and soup_element.get('id'):
                    # Strategie 1: Verwende ID wenn verfügbar (am zuverlässigsten)
                    element_id = soup_element.get('id')
                    self.logger.debug(f"Waiting for element with ID: {element_id}")
                    web_element = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.ID, element_id))
                    )
                else:
                    # Strategie 2: CSS Selector mit kürzerem Timeout
                    self.logger.debug(f"Waiting for element with selector: {element_selector}")
                    web_element = WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, element_selector))
                    )
            except TimeoutException:
                # Strategie 3: Versuche simplifizierten Selektor
                self.logger.warning(f"Timeout waiting for {element_selector}, trying simplified selector...")
                # Extrahiere Question-ID aus Selektor (z.B. "#question-123 div.formulation" -> "question-123")
                if '#question-' in element_selector:
                    question_id = element_selector.split()[0].replace('#', '')
                    try:
                        # Versuche nur das Question-Element zu finden
                        web_element = self.driver.find_element(By.ID, question_id)
                        # Dann finde die formulation darin
                        web_element = web_element.find_element(By.CSS_SELECTOR, 'div.formulation')
                    except:
                        pass

                # Letzter Fallback: Direkter find ohne Warten
                if not web_element:
                    try:
                        web_element = self.driver.find_element(By.CSS_SELECTOR, element_selector)
                    except:
                        pass

            if not web_element:
                self.logger.warning(f"Could not find element: {element_selector}")
                return False

            # Scrolle zum Element und stelle sicher, dass es vollständig sichtbar ist
            try:
                # Scrolle zum Element (block: 'start' stellt sicher, dass das ganze Element sichtbar ist)
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'start'});", web_element)

                # Scrolle ein bisschen nach oben, damit das Element nicht am oberen Rand klebt
                self.driver.execute_script("window.scrollBy(0, -100);")

                # Warte auf vollständiges Rendering
                time.sleep(0.5)

                # Prüfe ob das Element vollständig im Viewport ist
                is_in_view = self.driver.execute_script("""
                    var elem = arguments[0];
                    var rect = elem.getBoundingClientRect();
                    return (
                        rect.top >= 0 &&
                        rect.left >= 0 &&
                        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
                    );
                """, web_element)

                if not is_in_view:
                    # Element ist zu groß für Viewport - scrolle zum Anfang des Elements
                    self.logger.debug(f"Element extends beyond viewport, adjusting scroll...")
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'start'});", web_element)
                    time.sleep(0.3)

            except Exception as scroll_error:
                self.logger.warning(f"Scroll adjustment failed: {scroll_error}")

            # Screenshot machen mit Timeout-Handling
            try:
                web_element.screenshot(output_path)
                self.logger.info(f"Successfully created screenshot: {os.path.basename(output_path)}")
                return True
            except WebDriverException as e:
                if 'timeout' in str(e).lower():
                    self.logger.warning(f"Screenshot timeout for {element_selector}, skipping...")
                    return False
                raise

        except Exception as e:
            self.logger.error(f"Failed to create screenshot for {element_selector}: {e}")
            return False


class QuizParser:
    """Parser für Mebis Quiz-HTML zu strukturiertem JSON"""

    def __init__(self, image_downloader: Optional[ImageDownloader] = None):
        """
        Initialisiert den Quiz Parser

        Args:
            image_downloader: ImageDownloader-Instanz (optional)
        """
        self.image_downloader = image_downloader or ImageDownloader()
        self.logger = exam_logger
        self.current_review_url = None  # Für Fehler-Logging

    def parse_metadata(self, soup: BeautifulSoup) -> Dict:
        """
        Extrahiert Metadaten aus der Review-Seite

        Args:
            soup: BeautifulSoup-Objekt der Review-Seite

        Returns:
            Dict mit Metadaten (started, duration, points, grade, feedback, user_name)
        """
        metadata = {
            'started': None,
            'duration': None,
            'points': None,
            'grade': None,
            'feedback': None,
            'user_name': None
        }

        # User-Name aus user-picture extrahieren
        try:
            user_picture = soup.find('div', id='user-picture')
            if user_picture:
                # Versuche aus title-Attribut des span
                userinitials = user_picture.find('span', class_='userinitials')
                if userinitials:
                    user_name = userinitials.get('title') or userinitials.get('aria-label')
                    if user_name:
                        metadata['user_name'] = user_name

                # Fallback: Aus dem div-Text
                if not metadata['user_name']:
                    div_text = user_picture.find('div')
                    if div_text:
                        metadata['user_name'] = div_text.get_text(strip=True)
        except Exception as e:
            self.logger.warning(f"Could not extract user name from user-picture: {e}")

        try:
            # Metadaten stehen in einer Tabelle am Anfang
            # Suche nach spezifischen Zeilen
            rows = soup.find_all('tr')

            for row in rows:
                th = row.find('th')
                td = row.find('td')

                if not th or not td:
                    continue

                label = th.get_text(strip=True)

                # Für Feedback: Zeilenumbrüche erhalten
                if 'Feedback' in label:
                    # Extrahiere mit Zeilenumbrüchen
                    feedback_value = td.get_text(separator='\n', strip=True)
                    metadata['feedback'] = feedback_value
                    continue

                # Für andere Felder: normaler Text
                value = td.get_text(strip=True)

                if 'Begonnen' in label:
                    metadata['started'] = value
                elif 'Dauer' in label or 'Zeit' in label:
                    metadata['duration'] = value
                elif 'Punkte' in label:
                    metadata['points'] = value
                elif 'Bewertung' in label:
                    metadata['grade'] = value

            # Fallback: Feedback aus separatem Div (falls nicht in Tabelle gefunden)
            if not metadata['feedback']:
                feedback_div = soup.find('div', class_='gradingdetails')
                if feedback_div:
                    feedback_text = feedback_div.get_text(separator='\n', strip=True)
                    # Entferne "Feedback" Label falls vorhanden
                    feedback_text = re.sub(r'^Feedback\s*:?\s*', '', feedback_text)
                    metadata['feedback'] = feedback_text

        except Exception as e:
            self.logger.error(f"Error parsing metadata: {e}")

        return metadata

    def parse_navigation(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Extrahiert die Navigation (Fragen-Struktur) aus dem Navigationsblock

        Args:
            soup: BeautifulSoup-Objekt

        Returns:
            List[Dict]: Strukturierte Navigationsdaten mit Sektionen und Fragen
        """
        navigation = []

        try:
            nav_block = soup.find('section', id='mod_quiz_navblock')
            if not nav_block:
                self.logger.warning("Navigation block not found")
                return navigation

            # Finde alle Sektions-Überschriften und zugehörige Fragen
            current_section = None

            for element in nav_block.find_all(['h3', 'a']):
                if element.name == 'h3' and 'mod_quiz-section-heading' in element.get('class', []):
                    # Neue Sektion
                    current_section = {
                        'section_name': element.get_text(strip=True),
                        'questions': []
                    }
                    navigation.append(current_section)

                elif element.name == 'a' and 'qnbutton' in element.get('class', []):
                    # Frage-Button
                    if current_section is None:
                        # Sektion ohne Namen
                        current_section = {
                            'section_name': 'Allgemein',
                            'questions': []
                        }
                        navigation.append(current_section)

                    question_text = element.get_text(strip=True)
                    question_href = element.get('href', '')

                    # Extrahiere Frage-ID aus href (z.B. #question-10596283-2)
                    match = re.search(r'#question-([^"\']+)', question_href)
                    question_id = match.group(1) if match else None

                    current_section['questions'].append({
                        'question_id': question_id,
                        'question_label': question_text
                    })

        except Exception as e:
            self.logger.error(f"Error parsing navigation: {e}")

        return navigation

    def parse_question_generic(self, question_elem, output_dir: str) -> Dict:
        """
        Extrahiert generische Fragedaten (funktioniert für alle Typen)

        Args:
            question_elem: BeautifulSoup Element (div.que)
            output_dir: Verzeichnis für Bilder

        Returns:
            Dict mit Fragedaten
        """
        question_data = {
            'question_id': None,
            'question_number': None,
            'question_type': None,
            'question_text': None,
            'status': None,
            'points': None,
            'feedback': None,
            'comment': None,
            'raw_html': None
        }

        try:
            # ID aus dem Element
            question_data['question_id'] = question_elem.get('id', '').replace('question-', '')

            # Fragentyp
            question_data['question_type'] = QuestionTypeDetector.detect(question_elem)

            # Info-Bereich (Nummer, Status, Punkte)
            info_div = question_elem.find('div', class_='info')
            if info_div:
                # Fragennummer
                qno = info_div.find('span', class_='qno')
                if qno:
                    question_data['question_number'] = qno.get_text(strip=True)

                # Status
                state = info_div.find('div', class_='state')
                if state:
                    question_data['status'] = state.get_text(strip=True).lower()

                # Punkte
                grade = info_div.find('div', class_='grade')
                if grade:
                    question_data['points'] = grade.get_text(strip=True)

            # Fragetext
            qtext = question_elem.find('div', class_='qtext')
            if qtext:
                question_data['question_text'] = qtext.get_text(separator='\n', strip=True)

            # Feedback (OHNE comment) - extrahiere ALLE Feedback-Typen
            feedback_div = question_elem.find('div', class_='feedback')
            if feedback_div:
                # Entferne comment-Div falls vorhanden
                comment_div = feedback_div.find('div', class_='comment')
                if comment_div:
                    comment_div.extract()

                # Sammle alle Feedback-Texte
                feedback_texts = []
                feedback_images = []

                # Specific Feedback
                specific_feedback = feedback_div.find('div', class_='specificfeedback')
                if specific_feedback:
                    text = specific_feedback.get_text(separator='\n', strip=True)
                    if text:
                        feedback_texts.append(text)

                    # Extrahiere Bilder im Specific Feedback
                    images = self.image_downloader.extract_and_download_images(
                        specific_feedback,
                        os.path.join(output_dir, 'images'),
                        prefix=f"q{question_data['question_number']}_feedback_specific",
                        base_dir=output_dir
                    )
                    feedback_images.extend(images)

                # General Feedback
                general_feedback = feedback_div.find('div', class_='generalfeedback')
                if general_feedback:
                    text = general_feedback.get_text(separator='\n', strip=True)
                    if text:
                        feedback_texts.append(text)

                    # Extrahiere Bilder im General Feedback
                    images = self.image_downloader.extract_and_download_images(
                        general_feedback,
                        os.path.join(output_dir, 'images'),
                        prefix=f"q{question_data['question_number']}_feedback_general",
                        base_dir=output_dir
                    )
                    feedback_images.extend(images)

                # Kombiniere Feedback-Texte
                if feedback_texts or feedback_images:
                    question_data['feedback'] = {
                        'text': '\n\n'.join(feedback_texts),
                        'images': feedback_images
                    }

            # Kommentar (separat) - mit Formatierung
            comment_div = question_elem.find('div', class_='comment')
            if comment_div:
                # Entferne versteckte Elemente und Links
                for hidden in comment_div.find_all(class_='accesshide'):
                    hidden.extract()
                for link in comment_div.find_all('a'):
                    link.extract()
                for div_commentlink in comment_div.find_all('div', class_='commentlink'):
                    div_commentlink.extract()

                # Hole den Kommentar-Text
                comment_text = comment_div.get_text(separator='\n', strip=True)

                # Entferne "Kommentar:" Label und andere Label-Texte
                comment_text = re.sub(r'^Kommentare?\s*:?\s*', '', comment_text, flags=re.IGNORECASE | re.MULTILINE)
                comment_text = comment_text.strip()

                # Nur speichern wenn tatsächlich Text vorhanden (nicht nur Whitespace oder einzelne Buchstaben)
                if comment_text and len(comment_text) > 1:
                    # Hole HTML für spätere Verwendung
                    comment_html = str(comment_div)
                    question_data['comment'] = comment_text
                    question_data['comment_html'] = comment_html

            # Speichere Raw HTML für unbekannte Typen
            if question_data['question_type'] == 'unknown':
                question_data['raw_html'] = str(question_elem)

        except Exception as e:
            url_info = f" - URL: {self.current_review_url}" if self.current_review_url else ""
            self.logger.error(f"Error parsing generic question data: {e}{url_info}")

        return question_data

    def parse_ddmarker_question(self, question_elem, base_data: Dict, output_dir: str, attempt_id: str = None) -> Dict:
        """
        Parst Drag-and-Drop Marker Fragen - IMMER mit Screenshot

        Args:
            question_elem: BeautifulSoup Element
            base_data: Generische Fragedaten
            output_dir: Verzeichnis für Bilder
            attempt_id: Attempt-ID für eindeutige Dateinamen (optional)

        Returns:
            Dict mit erweiterten Fragedaten
        """
        data = base_data.copy()

        try:
            # IMMER Screenshot machen - kein Fallback auf Bild-Download
            ddarea_div = question_elem.find('div', class_='ddarea')

            if ddarea_div:
                # Suche nach droparea für Screenshot
                droparea_div = ddarea_div.find('div', class_='droparea')
                if droparea_div:
                    # Screenshot der droparea - erfasst Hintergrundbild UND platzierte Marker
                    # Dateiname mit attempt_id für Eindeutigkeit (mehrere Personen pro Gruppe)
                    if attempt_id:
                        screenshot_filename = f"q{data['question_number']}_attempt{attempt_id}_ddmarker_screenshot.png"
                    else:
                        screenshot_filename = f"q{data['question_number']}_ddmarker_screenshot.png"

                    screenshot_path = os.path.join(output_dir, 'images', screenshot_filename)

                    self.logger.info(f"Creating screenshot for ddmarker question {data['question_number']} (attempt {attempt_id})...")
                    screenshot_success = self.image_downloader.take_element_screenshot(
                        'div.droparea',
                        screenshot_path,
                        soup_element=droparea_div
                    )

                    if screenshot_success:
                        # Speichere Screenshot als background_image
                        data['background_image'] = {
                            'local_path': os.path.relpath(screenshot_path, output_dir),
                            'success': True,
                            'alt': 'Drag-and-Drop Screenshot mit Markern',
                            'title': 'Drag-and-Drop mit platzierten Markern'
                        }
                        self.logger.info(f"✓ Screenshot created for question {data['question_number']}")
                    else:
                        url_info = f" - URL: {self.current_review_url}" if self.current_review_url else ""
                        self.logger.error(f"✗ Screenshot failed for ddmarker question {data['question_number']}{url_info}")

            # Platzierte Marker (für Textdarstellung als zusätzliche Info)
            markers = []
            marker_spans = question_elem.find_all('span', class_='marker')

            for marker in marker_spans:
                # Nur die tatsächlich platzierten Marker (nicht die im draghomes)
                if 'dragplaceholder' in marker.get('class', []):
                    continue
                if 'unneeded' in marker.get('class', []):
                    continue

                # Prüfe ob Marker im droparea ist (nicht in draghomes)
                parent_droparea = marker.find_parent('div', class_='droparea')
                if not parent_droparea:
                    continue

                marker_text_elem = marker.find('span', class_='markertext')
                marker_text = marker_text_elem.get_text(strip=True) if marker_text_elem else ''

                # Position aus Style-Attribut (z.B. "left: 100px; top: 50px;")
                style = marker.get('style', '')
                position_match = re.search(r'left:\s*([^;]+).*?top:\s*([^;]+)', style, re.DOTALL)
                position = position_match.groups() if position_match.groups() and position_match.groups()[0] else (None, None)

                if marker_text:  # Nur wenn Text vorhanden
                    markers.append({
                        'text': marker_text,
                        'position': f"{position[0].strip()} / {position[1].strip()}" if position[0] else None
                    })

            data['markers'] = markers
            if markers:
                self.logger.info(f"Found {len(markers)} placed markers for question {data['question_number']}")

        except Exception as e:
            url_info = f" - URL: {self.current_review_url}" if self.current_review_url else ""
            self.logger.error(f"Error parsing ddmarker question: {e}{url_info}")

        return data

    def parse_multichoice_question(self, question_elem, base_data: Dict) -> Dict:
        """
        Parst Multiple-Choice Fragen

        Args:
            question_elem: BeautifulSoup Element
            base_data: Generische Fragedaten

        Returns:
            Dict mit erweiterten Fragedaten
        """
        data = base_data.copy()

        try:
            choices = []

            # Finde alle Antwort-Optionen
            answer_divs = question_elem.find_all('div', class_=re.compile(r'(r0|r1)'))  # Moodle nutzt r0, r1 für Antworten

            for answer_div in answer_divs:
                choice_text = answer_div.get_text(strip=True)

                # Prüfe ob ausgewählt (kann verschiedene Marker haben)
                is_selected = bool(answer_div.find('input', checked=True))

                # Prüfe ob korrekt (oft durch Icons oder Klassen markiert)
                is_correct = 'correct' in answer_div.get('class', [])

                choices.append({
                    'text': choice_text,
                    'selected': is_selected,
                    'correct': is_correct
                })

            data['choices'] = choices

        except Exception as e:
            self.logger.error(f"Error parsing multichoice question: {e}")

        return data

    def parse_essay_question(self, question_elem, base_data: Dict) -> Dict:
        """
        Parst Essay/Freitext Fragen

        Args:
            question_elem: BeautifulSoup Element
            base_data: Generische Fragedaten

        Returns:
            Dict mit erweiterten Fragedaten
        """
        data = base_data.copy()

        try:
            # Antwort des Schülers - suche in div.ablock > div.answer
            ablock = question_elem.find('div', class_='ablock')
            if ablock:
                answer_div = ablock.find('div', class_='answer')
                if answer_div:
                    # Suche nach textarea
                    textarea = answer_div.find('textarea')
                    if textarea:
                        # Zeilenumbrüche erhalten
                        data['student_answer'] = textarea.get_text(separator='\n', strip=True)
                    else:
                        # Fallback: Hole Text aus answer_div
                        # Entferne Label zuerst
                        for label in answer_div.find_all('label'):
                            label.extract()
                        # Zeilenumbrüche erhalten
                        data['student_answer'] = answer_div.get_text(separator='\n', strip=True)

        except Exception as e:
            self.logger.error(f"Error parsing essay question: {e}")

        return data

    def parse_multianswer_question(self, question_elem, base_data: Dict, output_dir: str, attempt_id: Optional[str] = None) -> Dict:
        """
        Parst Multianswer (Embedded Answers/Cloze) Fragen

        Args:
            question_elem: BeautifulSoup Element
            base_data: Generische Fragedaten
            output_dir: Verzeichnis für Bilder
            attempt_id: Versuchs-ID für eindeutige Dateinamen

        Returns:
            Dict mit erweiterten Fragedaten
        """
        data = base_data.copy()

        try:
            formulation_div = question_elem.find('div', class_='formulation')
            if not formulation_div:
                return data

            # Prüfe auf inline subquestions (Format mit <span class="subquestion">)
            subquestion_spans = formulation_div.find_all('span', class_='subquestion')

            if subquestion_spans:
                # Neues Format: Inline-Lückentext mit <input> Feldern
                # Extrahiere den vollständigen Text mit Lücken
                text_with_blanks = []
                blanks = []

                # Klone formulation_div für Parsing
                p_elem = formulation_div.find('p')
                if p_elem:
                    # Iteriere durch alle Kinder und baue Text auf
                    for idx, subq_span in enumerate(subquestion_spans, 1):
                        input_elem = subq_span.find('input', type='text')
                        if input_elem:
                            answer = input_elem.get('value', '')
                            is_correct = 'correct' in input_elem.get('class', [])
                            is_incorrect = 'incorrect' in input_elem.get('class', [])

                            # Extrahiere Feedback aus Popover
                            popover_link = subq_span.find('a', class_='feedbacktrigger')
                            feedback = ''
                            correct_answer = None
                            points = None

                            if popover_link:
                                feedback_content = popover_link.get('data-bs-content', '')
                                # Parse Feedback: "Richtig<br />Die richtige Antwort ist: &lt;a<br />Erreichte Punkte 1,00 von 1,00"
                                if 'Die richtige Antwort ist:' in feedback_content:
                                    match = re.search(r'Die richtige Antwort ist:\s*([^<]+)', feedback_content)
                                    if match:
                                        correct_answer = match.group(1).strip()
                                if 'Erreichte Punkte' in feedback_content:
                                    match = re.search(r'Erreichte Punkte\s+([\d,]+)\s+von\s+([\d,]+)', feedback_content)
                                    if match:
                                        points = f"{match.group(1)} von {match.group(2)}"

                            blanks.append({
                                'number': idx,
                                'answer': answer,
                                'correct': is_correct,
                                'incorrect': is_incorrect,
                                'feedback': feedback,
                                'correct_answer': correct_answer,
                                'points': points
                            })

                    # Hole den gesamten Text (mit Platzhaltern für Blanks)
                    full_text = p_elem.get_text(separator=' ', strip=True)
                    # Entferne "Antwort X Frage Y" Labels
                    full_text = re.sub(r'Antwort\s+\d+\s+Frage\s+\d+', '', full_text)

                    data['question_text'] = full_text
                    data['blanks'] = blanks

                # Screenshot der multianswer-Frage erstellen
                if attempt_id:
                    screenshot_filename = f"q{data['question_number']}_attempt{attempt_id}_multianswer_screenshot.png"
                else:
                    screenshot_filename = f"q{data['question_number']}_multianswer_screenshot.png"

                screenshot_path = os.path.join(output_dir, 'images', screenshot_filename)

                self.logger.info(f"Creating screenshot for multianswer question {data['question_number']} (attempt {attempt_id})...")
                # Verwende das gesamte Question-Element für vollständigen Screenshot
                # Erst versuchen mit der Formulation, dann mit dem gesamten Question-Container als Fallback
                unique_selector = f"#question-{data['question_id']} div.formulation"
                screenshot_success = self.image_downloader.take_element_screenshot(
                    unique_selector,
                    screenshot_path,
                    soup_element=None,
                    timeout=5  # Längerer Timeout für komplexe Multianswer-Fragen
                )

                # Fallback: Wenn Formulation fehlschlägt, versuche das gesamte Question-Element
                if not screenshot_success:
                    self.logger.warning(f"Formulation screenshot failed, trying entire question element...")
                    fallback_selector = f"#question-{data['question_id']}"
                    screenshot_success = self.image_downloader.take_element_screenshot(
                        fallback_selector,
                        screenshot_path,
                        soup_element=None,
                        timeout=5
                    )

                if screenshot_success:
                    data['screenshot'] = {
                        'local_path': os.path.relpath(screenshot_path, output_dir),
                        'success': True,
                        'alt': 'Multianswer Question Screenshot',
                        'title': 'Multianswer Frage mit Lückentext'
                    }
                    self.logger.info(f"✓ Screenshot created for question {data['question_number']}")
                else:
                    self.logger.warning(f"Failed to create screenshot for question {data['question_number']}")

                return data

            # Altes Format: <ol> mit Checkboxen
            qtext_div = question_elem.find('div', class_='qtext')
            if qtext_div:
                # Hole nur den Text vor der <ol>
                main_text_parts = []
                for child in qtext_div.children:
                    if child.name == 'ol':
                        break
                    if hasattr(child, 'get_text'):
                        text = child.get_text(strip=True)
                        if text:
                            main_text_parts.append(text)
                    elif isinstance(child, str):
                        text = child.strip()
                        if text:
                            main_text_parts.append(text)

                data['question_text'] = '\n'.join(main_text_parts)

            # Sub-Fragen aus <ol>
            sub_questions = []
            ol_elem = question_elem.find('ol')

            if ol_elem:
                for li in ol_elem.find_all('li', recursive=False):
                    sub_q = {
                        'question_text': None,
                        'choices': [],
                        'points': None,
                        'correct_answer': None
                    }

                    # Sub-Fragentext (vor der Tabelle)
                    text_parts = []
                    for child in li.children:
                        if child.name == 'table':
                            break
                        if hasattr(child, 'get_text'):
                            text = child.get_text(strip=True)
                            if text and not text.startswith('Erreichte Punkte'):
                                text_parts.append(text)
                        elif isinstance(child, str):
                            text = child.strip()
                            if text and not text.startswith('Erreichte Punkte'):
                                text_parts.append(text)

                    sub_q['question_text'] = ' '.join(text_parts)

                    # Antwort-Tabelle
                    answer_table = li.find('table', class_='answer')
                    if answer_table:
                        for td in answer_table.find_all('td', class_='form-check'):
                            checkbox = td.find('input', type='checkbox')
                            label = td.find('label')

                            if checkbox and label:
                                choice_text = label.get_text(strip=True)
                                is_selected = checkbox.get('checked') is not None
                                is_correct = 'correct' in td.get('class', [])
                                is_incorrect = 'incorrect' in td.get('class', [])
                                is_partial = 'partiallycorrect' in td.get('class', [])

                                sub_q['choices'].append({
                                    'text': choice_text,
                                    'selected': is_selected,
                                    'correct': is_correct,
                                    'incorrect': is_incorrect,
                                    'partial': is_partial
                                })

                    # Punkte und korrekte Antwort aus div.outcome
                    outcome_div = li.find('div', class_='outcome')
                    if outcome_div:
                        # Punkte
                        points_text = outcome_div.get_text()
                        points_match = re.search(r'Erreichte Punkte\s+([-\d,]+)\s+von\s+([\d,]+)', points_text)
                        if points_match:
                            sub_q['points'] = f"{points_match.group(1)} von {points_match.group(2)}"

                        # Korrekte Antwort
                        correct_ul = outcome_div.find('ul')
                        if correct_ul:
                            correct_items = [li.get_text(strip=True) for li in correct_ul.find_all('li')]
                            sub_q['correct_answer'] = correct_items

                    sub_questions.append(sub_q)

            data['sub_questions'] = sub_questions

            # Screenshot der multianswer-Frage erstellen (auch für altes Format)
            if attempt_id:
                screenshot_filename = f"q{data['question_number']}_attempt{attempt_id}_multianswer_screenshot.png"
            else:
                screenshot_filename = f"q{data['question_number']}_multianswer_screenshot.png"

            screenshot_path = os.path.join(output_dir, 'images', screenshot_filename)

            self.logger.info(f"Creating screenshot for multianswer question {data['question_number']} (attempt {attempt_id})...")
            # Verwende eindeutigen Selektor mit Question-ID
            unique_selector = f"#question-{data['question_id']} div.formulation"
            screenshot_success = self.image_downloader.take_element_screenshot(
                unique_selector,  # Eindeutiger Selektor für diese spezifische Frage
                screenshot_path,
                soup_element=None  # Kein soup_element, nur Selektor verwenden
            )

            if screenshot_success:
                data['screenshot'] = {
                    'local_path': os.path.relpath(screenshot_path, output_dir),
                    'success': True,
                    'alt': 'Multianswer Question Screenshot',
                    'title': 'Multianswer Frage'
                }
                self.logger.info(f"✓ Screenshot created for question {data['question_number']}")
            else:
                self.logger.warning(f"Failed to create screenshot for question {data['question_number']}")

        except Exception as e:
            self.logger.error(f"Error parsing multianswer question: {e}")

        return data

    def parse_match_question(self, question_elem, base_data: Dict) -> Dict:
        """
        Parst Match (Zuordnungs) Fragen mit Dropdown-Selects

        Args:
            question_elem: BeautifulSoup Element
            base_data: Generische Fragedaten

        Returns:
            Dict mit erweiterten Fragedaten
        """
        data = base_data.copy()

        try:
            # Antwort-Tabelle
            answer_table = question_elem.find('table', class_='answer')
            if not answer_table:
                return data

            matches = []

            for row in answer_table.find_all('tr', role='presentation'):
                # Text-Zelle (was zugeordnet werden soll)
                text_cell = row.find('td', class_='text')
                if not text_cell:
                    continue

                question_text = text_cell.get_text(strip=True)

                # Select-Element (Zuordnung)
                select_elem = row.find('select')
                if not select_elem:
                    continue

                # Alle Optionen
                all_options = []
                selected_option = None

                for option in select_elem.find_all('option'):
                    option_text = option.get_text(strip=True)
                    option_value = option.get('value', '')

                    if option.get('selected'):
                        selected_option = option_text

                    all_options.append({
                        'value': option_value,
                        'text': option_text
                    })

                # Korrektheit aus Control-Zelle
                control_cell = row.find('td', class_='control')
                is_correct = 'correct' in control_cell.get('class', []) if control_cell else False
                is_incorrect = 'incorrect' in control_cell.get('class', []) if control_cell else False

                matches.append({
                    'question': question_text,
                    'all_options': all_options,
                    'selected': selected_option,
                    'correct': is_correct,
                    'incorrect': is_incorrect
                })

            data['matches'] = matches

        except Exception as e:
            self.logger.error(f"Error parsing match question: {e}")

        return data

    def parse_description_question(self, question_elem, base_data: Dict) -> Dict:
        """
        Parst Description (Information Items) - keine eigentliche Frage

        Args:
            question_elem: BeautifulSoup Element
            base_data: Generische Fragedaten

        Returns:
            Dict mit Content
        """
        data = base_data.copy()

        try:
            # Nur der eigentliche Content (ohne "Fragetext", "Informationstext" Labels)
            qtext_div = question_elem.find('div', class_='qtext')
            if qtext_div:
                # Suche nach dem clearfix div innerhalb von qtext
                clearfix_div = qtext_div.find('div', class_='clearfix')
                if clearfix_div:
                    data['content'] = clearfix_div.get_text(separator='\n', strip=True)
                else:
                    # Fallback: gesamter qtext
                    data['content'] = qtext_div.get_text(separator='\n', strip=True)

        except Exception as e:
            self.logger.error(f"Error parsing description question: {e}")

        return data

    def parse_question(self, question_elem, output_dir: str, attempt_id: str = None) -> Dict:
        """
        Hauptmethode zum Parsen einer Frage (erkennt Typ und ruft spezialisierte Methode auf)

        Args:
            question_elem: BeautifulSoup Element (div.que)
            output_dir: Verzeichnis für Bilder
            attempt_id: Attempt-ID für eindeutige Dateinamen (optional)

        Returns:
            Dict mit vollständigen Fragedaten
        """
        # Generische Daten extrahieren
        base_data = self.parse_question_generic(question_elem, output_dir)

        # Typ-spezifische Daten hinzufügen
        qtype = base_data['question_type']

        if qtype in ['ddmarker', 'ddmarker-readonly']:
            return self.parse_ddmarker_question(question_elem, base_data, output_dir, attempt_id=attempt_id)
        elif qtype == 'multianswer':
            return self.parse_multianswer_question(question_elem, base_data, output_dir, attempt_id=attempt_id)
        elif qtype == 'match':
            return self.parse_match_question(question_elem, base_data)
        elif qtype in ['multichoice', 'truefalse']:
            return self.parse_multichoice_question(question_elem, base_data)
        elif qtype in ['essay', 'shortanswer']:
            return self.parse_essay_question(question_elem, base_data)
        elif qtype == 'description':
            return self.parse_description_question(question_elem, base_data)
        else:
            # Für unbekannte Typen: gebe generische Daten zurück
            self.logger.warning(f"No specialized parser for question type: {qtype}")
            return base_data

    def parse_review_page(self, html_content: str, output_dir: str, attempt_id: str = None, review_url: str = None) -> Dict:
        """
        Parst eine komplette Review-Seite

        Args:
            html_content: HTML-String der Review-Seite
            output_dir: Verzeichnis für Bilder und Daten
            attempt_id: Attempt-ID für eindeutige Dateinamen (optional)
            review_url: URL der Review-Seite für Fehler-Logging (optional)

        Returns:
            Dict mit allen Daten (metadata, navigation, sections mit questions)
        """
        # Speichere URL für Fehler-Logging
        self.current_review_url = review_url

        soup = BeautifulSoup(html_content, 'html.parser')

        # Metadaten
        metadata = self.parse_metadata(soup)

        # Navigation (für Sektionen-Struktur)
        navigation = self.parse_navigation(soup)

        # Fragen parsen
        question_elements = soup.find_all('div', class_='que')
        parsed_questions = {}

        for q_elem in question_elements:
            question_data = self.parse_question(q_elem, output_dir, attempt_id=attempt_id)
            q_id = question_data['question_id']
            if q_id:
                parsed_questions[q_id] = question_data

        # Fragen in Sektionen einordnen
        sections = []
        for section in navigation:
            section_data = {
                'section_name': section['section_name'],
                'questions': []
            }

            for q_info in section['questions']:
                q_id = q_info['question_id']
                if q_id in parsed_questions:
                    section_data['questions'].append(parsed_questions[q_id])

            sections.append(section_data)

        # Falls Fragen ohne Sektion existieren
        orphan_questions = [q for q_id, q in parsed_questions.items()
                           if not any(q in s['questions'] for s in sections)]
        if orphan_questions:
            sections.append({
                'section_name': 'Weitere Fragen',
                'questions': orphan_questions
            })

        return {
            'metadata': metadata,
            'sections': sections
        }
