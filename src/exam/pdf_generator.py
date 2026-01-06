#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PDF Generator für Mebis Leistungsnachweise
Erstellt druckfähige PDFs aus gescrapten Quiz-Daten
"""

import os
import sys

# Add project root to path for imports
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import json
from datetime import datetime
from typing import Dict, List
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, Flowable
)
from reportlab.pdfgen import canvas as pdfgen_canvas
from config.logger_config import get_logger
from src.common.group_utils import extract_group_prefix

# Logger Setup
pdf_logger = get_logger('exam_pdf_generator')


class NumberedCanvas(pdfgen_canvas.Canvas):
    """Canvas mit Seitenzählung für 'Seite x von y'"""

    def __init__(self, *args, **kwargs):
        pdfgen_canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        """Fügt Seitenzahlen hinzu, nachdem alle Seiten bekannt sind"""
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            pdfgen_canvas.Canvas.showPage(self)
        pdfgen_canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        """Wird von der Haupt-Klasse überschrieben"""
        pass


class StatusIcon(Flowable):
    """Flowable für Status-Icons (✓/✗) in Graustufen"""

    def __init__(self, status: str, size: int = 12):
        """
        Args:
            status: 'correct', 'incorrect', 'partial', 'none'
            size: Größe in Punkten
        """
        Flowable.__init__(self)
        self.status = status.lower()
        self.size = size
        self.width = size
        self.height = size

    def draw(self):
        """Zeichnet das Icon"""
        c = self.canv

        if self.status in ['richtig', 'correct']:
            # Checkmark in dunkelgrau
            c.setFillColorRGB(0.2, 0.2, 0.2)
            c.setFont('Helvetica-Bold', self.size)
            c.drawString(0, 0, '✓')
        elif self.status in ['falsch', 'incorrect']:
            # X in mittelgrau
            c.setFillColorRGB(0.4, 0.4, 0.4)
            c.setFont('Helvetica-Bold', self.size)
            c.drawString(0, 0, '✗')
        elif self.status in ['teilweise richtig', 'partial', 'partiallycorrect']:
            # Halbes Checkmark in grau
            c.setFillColorRGB(0.5, 0.5, 0.5)
            c.setFont('Helvetica', self.size)
            c.drawString(0, 0, '◐')


class ExamPDFGenerator:
    """Generator für Leistungsnachweis-PDFs"""

    def __init__(self):
        """Initialisiert den PDF Generator"""
        self.logger = pdf_logger

        # Seitenkonfiguration (kompakt) - mehr Platz für Kopf/Fußzeile
        self.pagesize = A4
        self.margin_top = 2.5 * cm  # Erhöht für Kopfzeile
        self.margin_bottom = 2.0 * cm  # Erhöht für Fußzeile
        self.margin_left = 1.5 * cm
        self.margin_right = 1.5 * cm

        # Stilvorlagen
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

        # Für Kopf-/Fußzeile (wird pro PDF gesetzt)
        self.current_student_name = None
        self.current_quiz_title = None

        # Filter-Option: Nur fehlerhafte Fragen ausgeben (Papier sparen)
        self.only_incorrect = False

    def _setup_custom_styles(self):
        """Erstellt benutzerdefinierte Stilvorlagen (kompakt)"""

        # Hauptüberschrift
        self.styles.add(ParagraphStyle(
            name='QuizTitle',
            parent=self.styles['Heading1'],
            fontSize=12,
            leading=14,
            textColor=colors.black,
            spaceAfter=3 * mm,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))

        # Metadaten
        self.styles.add(ParagraphStyle(
            name='Metadata',
            parent=self.styles['Normal'],
            fontSize=9,
            leading=11,
            spaceAfter=2 * mm,
            fontName='Helvetica',
            textColor=colors.HexColor('#8B0000')  # Dunkelrot
        ))

        # Sektionsüberschrift
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=10,
            leading=12,
            textColor=colors.HexColor('#404040'),
            spaceAfter=3 * mm,
            spaceBefore=4 * mm,
            fontName='Helvetica-Bold',
            borderWidth=0.5,
            borderColor=colors.grey,
            borderPadding=2 * mm,
            backColor=colors.HexColor('#F0F0F0')
        ))

        # Fragenkopf
        self.styles.add(ParagraphStyle(
            name='QuestionHeader',
            parent=self.styles['Normal'],
            fontSize=9,
            leading=11,
            fontName='Helvetica-Bold',
            spaceAfter=2 * mm
        ))

        # Fragetext
        self.styles.add(ParagraphStyle(
            name='QuestionText',
            parent=self.styles['Normal'],
            fontSize=10,
            leading=12,
            spaceAfter=3 * mm,
            fontName='Helvetica'
        ))

        # Antwort/Details
        self.styles.add(ParagraphStyle(
            name='Answer',
            parent=self.styles['Normal'],
            fontSize=8,
            leading=10,
            leftIndent=5 * mm,
            spaceAfter=2 * mm,
            fontName='Helvetica'
        ))

        # Feedback
        self.styles.add(ParagraphStyle(
            name='Feedback',
            parent=self.styles['Normal'],
            fontSize=8,
            leading=10,
            leftIndent=5 * mm,
            spaceAfter=2 * mm,
            fontName='Helvetica-Oblique',
            textColor=colors.HexColor('#8B0000')  # Dunkelrot
        ))

        # Richtig-Marker (dunkelgrün)
        self.styles.add(ParagraphStyle(
            name='CorrectMarker',
            parent=self.styles['Normal'],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#006400'),  # Dunkelgrün
            fontName='Helvetica-Oblique'
        ))

        # Falsch-Marker (dunkelrot)
        self.styles.add(ParagraphStyle(
            name='IncorrectMarker',
            parent=self.styles['Normal'],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#8B0000'),  # Dunkelrot
            fontName='Helvetica-Oblique'
        ))

        # Kommentar
        self.styles.add(ParagraphStyle(
            name='Comment',
            parent=self.styles['Normal'],
            fontSize=8,
            leading=10,
            leftIndent=5 * mm,
            spaceAfter=2 * mm,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#8B0000')  # Dunkelrot
        ))

    def _create_grading_scale(self, metadata: Dict) -> List:
        """
        Erstellt kompakte Notenschlüssel-Anzeige basierend auf maximalen Punkten

        Args:
            metadata: Metadaten des Quiz-Versuchs

        Returns:
            List: Flowables für den Notenschlüssel
        """
        elements = []

        # Extrahiere maximale Punkte aus "47,50/57,00" Format
        points_str = metadata.get('points', '')

        # Prüfe ob points_str valid ist
        if not points_str:
            return elements

        try:
            # Parse "erreichte/maximale" Format
            if '/' in points_str:
                max_points_str = points_str.split('/')[1].strip()
                max_points = float(max_points_str.replace(',', '.'))

                # Notengrenzen (fixe Prozentsätze)
                grade_thresholds = {
                    1: 0.92,  # 92%
                    2: 0.81,  # 81%
                    3: 0.67,  # 67%
                    4: 0.50,  # 50%
                    5: 0.23   # 23%
                }

                # Berechne Punktgrenzen und runde auf 0,5
                def round_to_half(value):
                    """Rundet auf nächste 0,5er Stelle"""
                    return round(value * 2) / 2

                grade_points = {}
                for grade, percentage in grade_thresholds.items():
                    points = max_points * percentage
                    grade_points[grade] = round_to_half(points)

                # Formatiere Ausgabe kompakt
                # Format: "Note 1 ab X P. | Note 2 ab X P. | ..."
                scale_parts = []
                for grade in sorted(grade_points.keys()):
                    points = grade_points[grade]
                    # Formatiere mit Komma als Dezimaltrennzeichen
                    points_formatted = f"{points:.1f}".replace('.', ',')
                    scale_parts.append(f"Note {grade} ab {points_formatted} P.")

                scale_text = " | ".join(scale_parts)
                scale_para = Paragraph(
                    f"<b>Notenschlüssel:</b> {scale_text}",
                    self.styles['Metadata']
                )
                elements.append(scale_para)
                elements.append(Spacer(1, 2 * mm))

        except (ValueError, IndexError) as e:
            # Bei Fehler einfach keinen Notenschlüssel anzeigen
            self.logger.debug(f"Could not parse points for grading scale: {e}")

        return elements

    def _create_header(self, quiz_info: Dict, student: Dict) -> List:
        """
        Erstellt den Kopfbereich für einen Schüler

        Args:
            quiz_info: Quiz-Informationen
            student: Schüler-Daten

        Returns:
            List: Flowables für den Kopfbereich
        """
        elements = []

        # Titel (LNW statt LEISTUNGSNACHWEIS, Leerzeichen durch _ ersetzen)
        quiz_name_formatted = quiz_info['quiz_name'].replace(' ', '_')
        title = Paragraph(f"<b>LNW: {quiz_name_formatted}</b>", self.styles['QuizTitle'])
        elements.append(title)

        # Trennlinie
        line_table = Table([['']], colWidths=[self.pagesize[0] - self.margin_left - self.margin_right])
        line_table.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (-1, 0), 2, colors.black),
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.black),
        ]))
        elements.append(line_table)
        elements.append(Spacer(1, 3 * mm))

        # Metadaten-Tabelle (2 Spalten)
        metadata = student.get('metadata', {})

        # Extrahiere nur den Präfix aus dem Gruppennamen
        group_name_full = student.get('group_name', 'N/A')
        group_prefix = extract_group_prefix(group_name_full) if group_name_full != 'N/A' else 'N/A'

        meta_data = [
            ['Name:', student.get('user_name', 'N/A'), 'Gruppe:', group_prefix],
            ['Begonnen:', metadata.get('started', 'N/A'), 'Dauer:', metadata.get('duration', 'N/A')],
            ['Punkte:', metadata.get('points', 'N/A'), 'Prozent:', metadata.get('grade', 'N/A')]
        ]

        meta_table = Table(meta_data, colWidths=[25 * mm, 65 * mm, 25 * mm, 65 * mm])
        meta_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2 * mm),
            ('TOPPADDING', (0, 0), (-1, -1), 1 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1 * mm),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 3 * mm))

        # Feedback (falls vorhanden)
        feedback = metadata.get('feedback')
        if feedback:
            # Normalisiere Leerzeilen, dann Zeilenumbrüche erhalten
            normalized_feedback = self._normalize_linebreaks(feedback)
            escaped_feedback = self._escape_html(normalized_feedback)
            feedback_with_breaks = escaped_feedback.replace('\n', '<br/>')
            feedback_para = Paragraph(f"<b>Feedback:</b> {feedback_with_breaks}", self.styles['Metadata'])
            elements.append(feedback_para)
            elements.append(Spacer(1, 2 * mm))

        # Notenschlüssel
        elements.extend(self._create_grading_scale(metadata))

        # Trennlinie
        separator_table = Table([['']], colWidths=[self.pagesize[0] - self.margin_left - self.margin_right])
        separator_table.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (-1, 0), 0.5, colors.grey),
        ]))
        elements.append(separator_table)
        elements.append(Spacer(1, 4 * mm))

        return elements

    def _add_page_header_footer(self, canvas_obj, doc):
        """
        Fügt Kopf- und Fußzeile zu jeder Seite hinzu

        Args:
            canvas_obj: ReportLab Canvas-Objekt
            doc: Document-Objekt
        """
        canvas_obj.saveState()

        # Kopfzeile
        if self.current_student_name and self.current_quiz_title:
            # Linke Seite: Name
            canvas_obj.setFont('Helvetica-Bold', 10)
            canvas_obj.drawString(self.margin_left, self.pagesize[1] - 1.5 * cm,
                                 self.current_student_name)

            # Rechte Seite: Quiz-Titel
            canvas_obj.setFont('Helvetica', 9)
            title_width = canvas_obj.stringWidth(self.current_quiz_title, 'Helvetica', 9)
            canvas_obj.drawString(self.pagesize[0] - self.margin_right - title_width,
                                 self.pagesize[1] - 1.5 * cm,
                                 self.current_quiz_title)

            # Trennlinie unter Kopfzeile
            canvas_obj.setStrokeColor(colors.grey)
            canvas_obj.setLineWidth(0.5)
            canvas_obj.line(self.margin_left,
                           self.pagesize[1] - 1.8 * cm,
                           self.pagesize[0] - self.margin_right,
                           self.pagesize[1] - 1.8 * cm)

        # Fußzeile wird vom NumberedCanvas hinzugefügt
        # (siehe _add_page_number Methode)

        canvas_obj.restoreState()

    def _add_page_number(self, canvas_obj, page_num, total_pages):
        """Fügt Seitenzahl hinzu (wird vom NumberedCanvas aufgerufen)"""
        footer_text = f"Seite {page_num} von {total_pages}"
        canvas_obj.setFont('Helvetica', 8)

        # Zentriert
        text_width = canvas_obj.stringWidth(footer_text, 'Helvetica', 8)
        canvas_obj.drawString((self.pagesize[0] - text_width) / 2,
                             1.0 * cm,
                             footer_text)

    def _escape_html(self, text: str) -> str:
        """Escaped HTML-Sonderzeichen für ReportLab"""
        if not text:
            return ''
        text = str(text)

        # Dekodiere erst existierende HTML-Entities
        import html
        text = html.unescape(text)

        # Dann escape für ReportLab (aber behalte bereits escaped & )
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        return text

    def _normalize_linebreaks(self, text: str) -> str:
        """Reduziert mehrfache Leerzeilen auf eine einzelne"""
        if not text:
            return ''
        # Ersetze mehrfache Zeilenumbrüche durch maximal zwei (= eine Leerzeile)
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    def _convert_html_to_reportlab(self, comment_html: str) -> str:
        """
        Konvertiert Mebis-HTML in ReportLab-kompatibles HTML

        Args:
            comment_html: HTML-String des Kommentars

        Returns:
            str: ReportLab-kompatibles HTML mit Formatierung
        """
        if not comment_html:
            return ''

        from bs4 import BeautifulSoup
        import html as html_module

        try:
            soup = BeautifulSoup(comment_html, 'html.parser')

            # Entferne "Kommentar:" Label
            for div in soup.find_all('div', class_='comment'):
                kommentar_text = div.find(text=lambda t: t and 'Kommentar:' in t)
                if kommentar_text:
                    kommentar_text.replace_with('')

            def process_element(element, indent_level=0) -> str:
                """Verarbeitet HTML-Element rekursiv zu ReportLab-HTML"""

                # Text-Knoten
                if element.name is None:
                    text = str(element)
                    # HTML-Entities dekodieren
                    text = html_module.unescape(text)
                    # &nbsp; -> normales Leerzeichen
                    text = text.replace('\xa0', ' ')
                    # XML-escape für ReportLab (ZUERST escapen)
                    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    # Zeilenumbrüche (\n) in <br/> umwandeln (NACH dem Escaping)
                    text = text.replace('\n', '<br/>')
                    return text

                # <br> bleibt <br/>
                if element.name == 'br':
                    return '<br/>'

                # <code> -> grauer Hintergrund mit Monospace
                if element.name == 'code':
                    code_text = element.get_text()
                    code_text = html_module.unescape(code_text)
                    code_text = code_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    return f'<font face="Courier" color="#333333" backColor="#f5f5f5">{code_text}</font>'

                # <strong> oder <b> -> <b>
                if element.name in ['strong', 'b']:
                    content = ''.join(process_element(child, indent_level) for child in element.children)
                    return f'<b>{content}</b>'

                # <i> oder <em> -> <i>
                if element.name in ['i', 'em']:
                    content = ''.join(process_element(child, indent_level) for child in element.children)
                    return f'<i>{content}</i>'

                # Listen-Elemente
                if element.name == 'li':
                    indent = '&nbsp;&nbsp;&nbsp;&nbsp;' * indent_level
                    content = ''.join(process_element(child, indent_level) for child in element.children)
                    return f'{indent}• {content}<br/>'

                # Absätze
                if element.name == 'p':
                    content = ''.join(process_element(child, indent_level) for child in element.children)
                    if content.strip():
                        return f'{content}<br/><br/>'
                    return ''

                # Spans mit Farbe und Hintergrundfarbe
                if element.name == 'span':
                    style = element.get('style', '') or element.get('data-mce-style', '')
                    content = ''.join(process_element(child, indent_level) for child in element.children)

                    import re

                    # Extrahiere Textfarbe (color)
                    text_color = None
                    color_match = re.search(r'color:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})', style)
                    if color_match:
                        text_color = color_match.group(1)

                    # Extrahiere Hintergrundfarbe (background-color)
                    bg_color = None
                    bg_match = re.search(r'background-color:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})', style)
                    if bg_match:
                        bg_color = bg_match.group(1)

                    # Baue font-Tag mit Farben
                    if text_color or bg_color:
                        font_attrs = []

                        # Wenn Hintergrundfarbe vorhanden: Text immer schwarz für Lesbarkeit
                        if bg_color:
                            font_attrs.append('color="#000000"')
                            font_attrs.append(f'backColor="{bg_color}"')
                        elif text_color:
                            # Nur Textfarbe ohne Hintergrund
                            font_attrs.append(f'color="{text_color}"')

                        font_tag = ' '.join(font_attrs)
                        return f'<font {font_tag}>{content}</font>'

                    return content

                # Listen-Container (ul/ol) - erhöhe Einrückung
                if element.name in ['ul', 'ol']:
                    content = ''.join(process_element(child, indent_level + 1) for child in element.children)
                    return content

                # Default: Verarbeite Kinder rekursiv
                return ''.join(process_element(child, indent_level) for child in element.children)

            # Verarbeite das gesamte HTML
            result = process_element(soup)

            # Bereinige übermäßige Leerzeilen
            import re
            result = re.sub(r'(<br/>){3,}', '<br/><br/>', result)
            result = re.sub(r'^Kommentare?\s*:?\s*', '', result, flags=re.IGNORECASE)

            return result.strip()

        except Exception as e:
            self.logger.warning(f"Failed to convert HTML to ReportLab format: {e}")
            # Fallback: Einfache Text-Extraktion
            try:
                return soup.get_text(separator='<br/>', strip=True) if soup else ''
            except:
                return ''

    def _extract_comment_from_html(self, comment_html: str) -> str:
        """
        Wrapper für Rückwärtskompatibilität - verwendet neue ReportLab-Konvertierung

        Args:
            comment_html: HTML-String des Kommentars

        Returns:
            str: ReportLab-kompatibles HTML
        """
        return self._convert_html_to_reportlab(comment_html)

    def _render_question(self, question: Dict, base_path: str) -> List:
        """
        Rendert eine einzelne Frage

        Args:
            question: Frage-Daten
            base_path: Basis-Pfad für Bilder

        Returns:
            List: Flowables für die Frage
        """
        # Fragenkopf (Nummer, Typ, Status, Punkte)
        q_num = question.get('question_number', '?')
        q_type = question.get('question_type', 'unknown')
        status = question.get('status', 'none')
        points = question.get('points', 'N/A')

        # Description-Fragen überspringen (nur Informationstexte, keine Bewertung)
        if q_type == 'description':
            return []

        # Filtere vollständig richtige Fragen wenn only_incorrect aktiviert
        if self.only_incorrect:
            # Prüfe ob Frage vollständig richtig ist anhand der Punkte
            # (Status-Text ist nicht zuverlässig)
            is_fully_correct = False

            # Parse Punkte: "Erreichte Punkte 7,00 von 7,00" -> prüfe ob volle Punktzahl
            import re
            points_match = re.search(r'([\d,]+)\s+von\s+([\d,]+)', points)
            if points_match:
                achieved = points_match.group(1).replace(',', '.')
                maximum = points_match.group(2).replace(',', '.')
                try:
                    # Volle Punktzahl erreicht?
                    if float(achieved) >= float(maximum):
                        is_fully_correct = True
                except ValueError:
                    pass

            if is_fully_correct:
                return []  # Vollständig richtig -> überspringen

        elements = []

        # Für Description/Information Items: Kein Header mit Status
        if q_type != 'description':
            # Status-Icon
            status_icon = StatusIcon(status, size=10)

            # Punkte-Format kürzen: "1,00 von 3,00 Punkten" statt "Punkte: Erreichte Punkte ..."
            import re
            if points and 'Erreichte Punkte' in points:
                # Parse "Erreichte Punkte 1,00 von 3,00" -> "1,00 von 3,00 Punkten"
                match = re.search(r'([\d,]+)\s+von\s+([\d,]+)', points)
                if match:
                    points_short = f"{match.group(1)} von {match.group(2)} Punkten"
                else:
                    points_short = points
            else:
                points_short = points

            # Status-Icon als String (mit Farben)
            status_icon_str = ''
            if 'richtig' in status.lower() and 'teilweise' not in status.lower():
                status_icon_str = '<font color="#006400">✓</font>'
            elif 'falsch' in status.lower():
                status_icon_str = '<font color="#8B0000">✗</font>'
            elif 'teilweise' in status.lower():
                status_icon_str = '◐'

            # Kopfzeile als Tabelle (zweispaltig: links Frage+Status, rechts Punkte rechtsbündig)
            header_data = [[
                Paragraph(f"<b>Frage {q_num}</b>  {status_icon_str} <i>{status}</i>", self.styles['QuestionHeader']),
                Paragraph(f"<para align='right'><i>{points_short}</i></para>", self.styles['QuestionHeader'])
            ]]

            header_table = Table(header_data, colWidths=[None, 45 * mm])
            header_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ]))

            elements.append(header_table)
            elements.append(Spacer(1, 2 * mm))
        else:
            # Für Description: Kein extra Header, nur Inhalt wird gezeigt
            pass

        # Fragetext (überspringe bei Screenshot-basierten Fragen)
        # Bei ddmarker, multianswer, gapselect und ordering ist der Text im Screenshot enthalten
        skip_question_text = q_type in ['ddmarker', 'ddmarker-readonly', 'multianswer', 'gapselect', 'ordering']

        q_text = question.get('question_text', '')
        if q_text and not skip_question_text:
            normalized_q_text = self._normalize_linebreaks(q_text)
            escaped_q_text = self._escape_html(normalized_q_text)
            q_text_with_breaks = escaped_q_text.replace('\n', '<br/>')
            q_para = Paragraph(q_text_with_breaks, self.styles['QuestionText'])
            elements.append(q_para)
            elements.append(Spacer(1, 2 * mm))

        # Typ-spezifisches Rendering
        if q_type in ['ddmarker', 'ddmarker-readonly']:
            elements.extend(self._render_ddmarker(question, base_path))
        elif q_type == 'multianswer':
            elements.extend(self._render_multianswer(question, base_path))
        elif q_type == 'gapselect':
            elements.extend(self._render_gapselect(question, base_path))
        elif q_type == 'ordering':
            elements.extend(self._render_ordering(question, base_path))
        elif q_type == 'match':
            elements.extend(self._render_match(question))
        elif q_type in ['multichoice', 'truefalse']:
            elements.extend(self._render_multichoice(question))
        elif q_type in ['essay', 'shortanswer']:
            elements.extend(self._render_essay(question))
        elif q_type == 'description':
            elements.extend(self._render_description(question))
        else:
            # Unbekannter Typ: Hinweis
            elements.append(Paragraph(
                f"<i>[Fragentyp '{q_type}' - Details siehe Online-Version]</i>",
                self.styles['Answer']
            ))

        # Feedback
        feedback = question.get('feedback')
        if feedback:
            elements.extend(self._render_feedback(feedback, base_path))

        # Kommentar (Lehrer-Kommentar) - nur wenn nicht leer oder "e"
        comment = question.get('comment')
        comment_html_legacy = question.get('comment_html')  # Alte Struktur (Rückwärtskompatibilität)

        # Kommentar kann entweder String (alter Code) oder Dictionary (neuer Code) sein
        comment_text_raw = None
        comment_images = []
        comment_html = None

        if isinstance(comment, dict):
            # Neuer Code: Dictionary mit text, images und html
            comment_text_raw = comment.get('text', '')
            comment_images = comment.get('images', [])
            comment_html = comment.get('html', '')  # HTML-Version (falls vorhanden)
        elif isinstance(comment, str):
            # Alter Code: Einfacher String
            comment_text_raw = comment

        # Versuche zuerst HTML-Version für bessere Formatierung
        # Priorität: 1) comment.html (neu), 2) comment_html (alt)
        if comment_html:
            comment_text = self._extract_comment_from_html(comment_html)
        elif comment_html_legacy:
            comment_text = self._extract_comment_from_html(comment_html_legacy)
        elif comment_text_raw:
            # Fallback: Einfacher Text-Kommentar
            # 1. Escape HTML-Zeichen
            import html as html_module
            comment_text = html_module.escape(comment_text_raw)
            # 2. Konvertiere \n zu <br/>
            comment_text = comment_text.replace('\n', '<br/>')
        else:
            comment_text = None

        if comment_text and comment_text.strip() and comment_text.strip().lower() != 'e':
            # Der Text ist bereits ReportLab-HTML (von _convert_html_to_reportlab)
            # NICHT escapen, da es bereits formatiertes HTML ist
            comment_para = Paragraph(f"<b>Kommentar:</b><br/>{comment_text}", self.styles['Comment'])
            elements.append(comment_para)

        # Füge Kommentar-Bilder hinzu (falls vorhanden)
        if comment_images:
            for img_info in comment_images:
                img_path = os.path.join(base_path, img_info.get('local_path', ''))
                if os.path.exists(img_path):
                    try:
                        img = Image(img_path)
                        # Skaliere Bild auf max. 150mm Breite
                        img_width = 150 * mm
                        aspect = img.imageHeight / img.imageWidth
                        img.drawHeight = img_width * aspect
                        img.drawWidth = img_width
                        elements.append(img)
                        elements.append(Spacer(1, 3 * mm))
                    except Exception as e:
                        self.logger.warning(f"Failed to load comment image {img_path}: {e}")

        # Abstand zur nächsten Frage
        elements.append(Spacer(1, 5 * mm))

        # Rahmen um die Frage
        question_box = KeepTogether(elements)
        return [question_box]

    def _render_ddmarker(self, question: Dict, base_path: str) -> List:
        """Rendert Drag & Drop Marker Frage"""
        elements = []

        # Hintergrundbild
        bg_image_info = question.get('background_image')
        if bg_image_info:
            # Versuche lokales Bild zuerst
            img_loaded = False
            if bg_image_info.get('local_path'):
                local_path_str = bg_image_info['local_path']
                # Prüfe ob absoluter oder relativer Pfad
                if os.path.isabs(local_path_str):
                    img_path = local_path_str
                else:
                    img_path = os.path.join(base_path, local_path_str)

                if os.path.exists(img_path):
                    try:
                        # Bildgröße ermitteln
                        pil_img = PILImage.open(img_path)
                        img_width, img_height = pil_img.size

                        # Auf 50% der ursprünglichen Größe skalieren
                        # ReportLab arbeitet in Points (72 DPI), PIL in Pixels (üblicherweise 96 DPI)
                        # Konvertierung: Pixel * 72/96 = Points
                        width_points = (img_width * 72 / 96) * 0.5
                        height_points = (img_height * 72 / 96) * 0.5

                        img = Image(img_path, width=width_points, height=height_points)
                        elements.append(img)
                        elements.append(Spacer(1, 2 * mm))
                        img_loaded = True
                    except Exception as e:
                        self.logger.warning(f"Could not load local image {img_path}: {e}")

            # Platzhalter wenn lokales Bild nicht geladen werden konnte
            if not img_loaded:
                local_path = bg_image_info.get('local_path', 'N/A')
                elements.append(Paragraph(f"[Bild nicht verfügbar: {local_path}]", self.styles['Answer']))
        else:
            elements.append(Paragraph("[Hintergrundbild nicht verfügbar]", self.styles['Answer']))

        # Platzierte Marker - NICHT anzeigen, da im Screenshot sichtbar
        # markers = question.get('markers', [])
        # if markers:
        #     elements.append(Paragraph("<b>Ihre Antworten:</b>", self.styles['Answer']))
        #     for marker in markers:
        #         marker_text = f"• {marker['text']}"
        #         if marker.get('position'):
        #             marker_text += f" (Position: {marker['position']})"
        #         elements.append(Paragraph(marker_text, self.styles['Answer']))

        return elements

    def _render_multichoice(self, question: Dict) -> List:
        """Rendert Multiple-Choice Frage mit verbesserter Checkbox-Darstellung"""
        elements = []

        choices = question.get('choices', [])
        if choices:
            elements.append(Paragraph("<b>Antworten:</b>", self.styles['Answer']))
            for choice in choices:
                is_selected = choice.get('selected', False)
                is_correct = choice.get('correct', False)
                is_incorrect = choice.get('incorrect', False)
                is_partial = choice.get('partial', False)

                # Bestimme Symbol und Markierung
                if is_selected:
                    symbol = '<b>[x]</b>'
                    if is_correct:
                        marker = ' <font color="#006400"><i>(✓ richtig)</i></font>'
                    elif is_incorrect:
                        marker = ' <font color="#8B0000"><i>(✗ falsch)</i></font>'
                    elif is_partial:
                        marker = ' <i>(◐ teilweise)</i>'
                    else:
                        marker = ''
                else:
                    symbol = '[ ]'
                    # Zeige an ob es korrekt wäre anzukreuzen
                    if is_correct:
                        marker = ' <font color="#006400"><i>(✓ sollte angekreuzt sein)</i></font>'
                    else:
                        marker = ''

                # Line breaks in choice text
                normalized_choice_text = self._normalize_linebreaks(choice['text'])
                escaped_choice_text = self._escape_html(normalized_choice_text)
                choice_text_with_breaks = escaped_choice_text.replace('\n', '<br/>')

                choice_text = f"{symbol} {choice_text_with_breaks}{marker}"
                elements.append(Paragraph(choice_text, self.styles['Answer']))

        return elements

    def _render_essay(self, question: Dict) -> List:
        """Rendert Essay/Freitext Frage"""
        elements = []

        answer = question.get('student_answer', '')
        if answer:
            elements.append(Paragraph("<b>Ihre Antwort:</b>", self.styles['Answer']))
            # Mehrzeilige Antwort: Normalisiere Leerzeilen, dann Zeilenumbrüche erhalten
            normalized_answer = self._normalize_linebreaks(answer)
            escaped_answer = self._escape_html(normalized_answer)
            answer_with_breaks = escaped_answer.replace('\n', '<br/>')
            answer_para = Paragraph(answer_with_breaks, self.styles['Answer'])
            elements.append(answer_para)

        return elements

    def _render_multianswer(self, question: Dict, base_path: str = '') -> List:
        """Rendert Multianswer (Embedded Answers/Cloze) Frage"""
        elements = []

        # Screenshot anzeigen falls vorhanden
        screenshot_info = question.get('screenshot')
        if screenshot_info and screenshot_info.get('local_path'):
            local_path_str = screenshot_info['local_path']
            # Prüfe ob absoluter oder relativer Pfad
            if os.path.isabs(local_path_str):
                screenshot_path = local_path_str
            else:
                screenshot_path = os.path.join(base_path, local_path_str)

            if os.path.exists(screenshot_path):
                try:
                    # Bildgröße ermitteln
                    pil_img = PILImage.open(screenshot_path)
                    img_width, img_height = pil_img.size

                    # Auf 50% der ursprünglichen Größe skalieren (wie bei ddmarker)
                    # ReportLab arbeitet in Points (72 DPI), PIL in Pixels (üblicherweise 96 DPI)
                    # Konvertierung: Pixel * 72/96 = Points
                    width_points = (img_width * 72 / 96) * 0.5
                    height_points = (img_height * 72 / 96) * 0.5

                    img = Image(screenshot_path, width=width_points, height=height_points)
                    elements.append(img)
                    elements.append(Spacer(1, 3 * mm))
                    self.logger.debug(f"Screenshot included for multianswer question {question.get('question_number')}")
                except Exception as e:
                    self.logger.error(f"Failed to load screenshot: {e}")
                    elements.append(Paragraph(
                        f"<i>[Screenshot konnte nicht geladen werden: {os.path.basename(screenshot_path)}]</i>",
                        self.styles['Answer']
                    ))
            else:
                self.logger.warning(f"Screenshot not found: {screenshot_path}")

        # Neues Format: Inline-Lücken (blanks)
        blanks = question.get('blanks', [])
        if blanks:
            # Filtere Blanks wenn only_incorrect aktiviert
            if self.only_incorrect:
                # Zeige nur falsche Lücken
                filtered_blanks = [b for b in blanks if b.get('incorrect', False)]
            else:
                # Zeige alle Lücken
                filtered_blanks = blanks

            # Nur anzeigen wenn es Lücken zu zeigen gibt
            if filtered_blanks:
                elements.append(Paragraph("<b>Ihre Antworten:</b>", self.styles['Answer']))
                for blank in filtered_blanks:
                    answer = blank.get('answer', '')
                    is_correct = blank.get('correct', False)
                    is_incorrect = blank.get('incorrect', False)
                    correct_answer = blank.get('correct_answer')
                    points = blank.get('points')

                    # Status-Marker mit Farben
                    if is_correct:
                        marker = ' <font color="#006400"><i>(✓ richtig)</i></font>'
                    elif is_incorrect:
                        marker = ' <font color="#8B0000"><i>(✗ falsch)</i></font>'
                    else:
                        marker = ''

                    # Punkte-Format kürzen und direkt an Antwort anhängen
                    import re
                    if points and 'Erreichte Punkte' in points:
                        match = re.search(r'([\d,]+)\s+von\s+([\d,]+)', points)
                        if match:
                            points_short = f"({match.group(1)} von {match.group(2)} Punkten)"
                        else:
                            points_short = f"({points})"
                    elif points:
                        points_short = f"({points})"
                    else:
                        points_short = ''

                    # Line breaks in blank answer
                    normalized_answer = self._normalize_linebreaks(answer)
                    escaped_answer = self._escape_html(normalized_answer)
                    answer_with_breaks = escaped_answer.replace('\n', '<br/>')

                    blank_text = f"Lücke {blank['number']}: <b>{answer_with_breaks}</b>{marker} <i>{points_short}</i>"
                    elements.append(Paragraph(blank_text, self.styles['Answer']))

                    # Korrekte Antwort anzeigen wenn falsch
                    if correct_answer and is_incorrect:
                        # Line breaks in correct answer
                        normalized_correct = self._normalize_linebreaks(correct_answer)
                        escaped_correct = self._escape_html(normalized_correct)
                        correct_with_breaks = escaped_correct.replace('\n', '<br/>')
                        elements.append(Paragraph(
                            f"  <i>Richtige Antwort: {correct_with_breaks}</i>",
                            self.styles['Answer']
                        ))

            return elements

        # Altes Format: Sub-Fragen mit Checkboxen
        sub_questions = question.get('sub_questions', [])
        if sub_questions:
            # Filtere Sub-Questions wenn only_incorrect aktiviert
            if self.only_incorrect:
                # Prüfe jede Sub-Question ob sie Fehler enthält
                filtered_sub_questions = []
                for sub_q in sub_questions:
                    # Eine Sub-Question ist fehlerhaft wenn:
                    # - Es falsche Antworten gibt (incorrect=True)
                    # - Oder richtige Antworten nicht ausgewählt wurden
                    has_errors = False
                    choices = sub_q.get('choices', [])
                    for choice in choices:
                        is_selected = choice.get('selected', False)
                        is_correct_choice = choice.get('correct', False)
                        is_incorrect = choice.get('incorrect', False)

                        # Fehler wenn falsche Antwort ausgewählt ODER richtige nicht ausgewählt
                        if is_incorrect or (is_correct_choice and not is_selected):
                            has_errors = True
                            break

                    if has_errors:
                        filtered_sub_questions.append(sub_q)
            else:
                filtered_sub_questions = sub_questions

            # Nur anzeigen wenn es Sub-Questions zu zeigen gibt
            if filtered_sub_questions:
                elements.append(Paragraph("<b>Teilfragen:</b>", self.styles['Answer']))

            for idx, sub_q in enumerate(filtered_sub_questions, 1):
                # Sub-Frage-Überschrift mit Punkten direkt dahinter
                sub_q_text = sub_q.get('question_text', '')
                points = sub_q.get('points')

                if sub_q_text:
                    # Punkte-Format kürzen
                    import re
                    if points and 'Erreichte Punkte' in points:
                        match = re.search(r'([\d,]+)\s+von\s+([\d,]+)', points)
                        if match:
                            points_short = f"({match.group(1)} von {match.group(2)} Punkten)"
                        else:
                            points_short = f"({points})"
                    elif points:
                        points_short = f"({points})"
                    else:
                        points_short = ''

                    # Line breaks in sub-question text
                    normalized_sub_q_text = self._normalize_linebreaks(sub_q_text)
                    escaped_sub_q_text = self._escape_html(normalized_sub_q_text)
                    sub_q_text_with_breaks = escaped_sub_q_text.replace('\n', '<br/>')

                    elements.append(Paragraph(
                        f"<b>{idx}. {sub_q_text_with_breaks}</b> <i>{points_short}</i>",
                        self.styles['Answer']
                    ))

                # Antworten (Checkboxen)
                choices = sub_q.get('choices', [])
                for choice in choices:
                    is_selected = choice.get('selected', False)
                    is_correct = choice.get('correct', False)
                    is_incorrect = choice.get('incorrect', False)
                    is_partial = choice.get('partial', False)

                    # Symbol bestimmen
                    if is_selected:
                        symbol = '<b>[x]</b>'
                        if is_correct:
                            marker = ' <font color="#006400"><i>(✓)</i></font>'
                        elif is_incorrect:
                            marker = ' <font color="#8B0000"><i>(✗)</i></font>'
                        elif is_partial:
                            marker = ' <i>(◐)</i>'
                        else:
                            marker = ''
                    else:
                        symbol = '[ ]'
                        if is_correct:
                            marker = ' <font color="#006400"><i>(✓ sollte angekreuzt sein)</i></font>'
                        else:
                            marker = ''

                    choice_text = f"  {symbol} {self._escape_html(choice['text'])}{marker}"
                    elements.append(Paragraph(choice_text, self.styles['Answer']))

                # Korrekte Antwort
                correct_answer = sub_q.get('correct_answer')
                if correct_answer:
                    correct_text = ', '.join(correct_answer)
                    elements.append(Paragraph(
                        f"  <i>Richtige Antwort: {self._escape_html(correct_text)}</i>",
                        self.styles['Answer']
                    ))

                elements.append(Spacer(1, 2 * mm))

        return elements

    def _render_gapselect(self, question: Dict, base_path: str = '') -> List:
        """Rendert Gapselect (Dropdown-Auswahl) Frage - IMMER mit Screenshot"""
        elements = []

        # Screenshot anzeigen (Hauptdarstellung für gapselect)
        screenshot_info = question.get('screenshot')
        if screenshot_info and screenshot_info.get('local_path'):
            local_path_str = screenshot_info['local_path']
            # Prüfe ob absoluter oder relativer Pfad
            if os.path.isabs(local_path_str):
                screenshot_path = local_path_str
            else:
                screenshot_path = os.path.join(base_path, local_path_str)

            if os.path.exists(screenshot_path):
                try:
                    # Bildgröße ermitteln
                    pil_img = PILImage.open(screenshot_path)
                    img_width, img_height = pil_img.size

                    # Auf 50% der ursprünglichen Größe skalieren (wie bei multianswer)
                    # ReportLab arbeitet in Points (72 DPI), PIL in Pixels (üblicherweise 96 DPI)
                    # Konvertierung: Pixel * 72/96 = Points
                    width_points = (img_width * 72 / 96) * 0.5
                    height_points = (img_height * 72 / 96) * 0.5

                    img = Image(screenshot_path, width=width_points, height=height_points)
                    elements.append(img)
                    elements.append(Spacer(1, 3 * mm))
                    self.logger.debug(f"Screenshot included for gapselect question {question.get('question_number')}")
                except Exception as e:
                    self.logger.error(f"Failed to load gapselect screenshot: {e}")
                    elements.append(Paragraph(
                        f"<i>[Screenshot konnte nicht geladen werden: {os.path.basename(screenshot_path)}]</i>",
                        self.styles['Answer']
                    ))
            else:
                self.logger.warning(f"Gapselect screenshot not found: {screenshot_path}")
                # Fallback: Zeige generischen Hinweis
                elements.append(Paragraph(
                    "<i>[Screenshot nicht verfügbar - Details siehe Online-Version]</i>",
                    self.styles['Answer']
                ))
        else:
            # Kein Screenshot vorhanden (sollte nicht passieren)
            self.logger.warning(f"No screenshot data for gapselect question {question.get('question_number')}")
            elements.append(Paragraph(
                "<i>[Screenshot nicht verfügbar - Details siehe Online-Version]</i>",
                self.styles['Answer']
            ))

        # Optional: Dropdown-Werte anzeigen (falls extrahiert)
        dropdowns = question.get('dropdowns', [])
        if dropdowns:
            # Filtere Dropdowns wenn only_incorrect aktiviert
            if self.only_incorrect:
                filtered_dropdowns = [d for d in dropdowns if d.get('incorrect', False)]
            else:
                filtered_dropdowns = dropdowns

            if filtered_dropdowns:
                elements.append(Paragraph("<b>Ihre Auswahl:</b>", self.styles['Answer']))
                for dropdown in filtered_dropdowns:
                    number = dropdown.get('number', '?')
                    selected = dropdown.get('selected', 'Nicht ausgewählt')
                    is_correct = dropdown.get('correct', False)
                    is_incorrect = dropdown.get('incorrect', False)

                    # Status-Marker mit Farben
                    if is_correct:
                        marker = ' <font color="#006400"><i>(✓ richtig)</i></font>'
                    elif is_incorrect:
                        marker = ' <font color="#8B0000"><i>(✗ falsch)</i></font>'
                    else:
                        marker = ''

                    elements.append(Paragraph(
                        f"  Lücke {number}: {self._escape_html(selected)}{marker}",
                        self.styles['Answer']
                    ))

        return elements

    def _render_ordering(self, question: Dict, base_path: str = '') -> List:
        """Rendert Ordering (Sortierungs) Frage - IMMER mit Screenshot"""
        elements = []

        # Screenshot anzeigen (Hauptdarstellung für ordering)
        screenshot_info = question.get('screenshot')
        if screenshot_info and screenshot_info.get('local_path'):
            local_path_str = screenshot_info['local_path']
            # Prüfe ob absoluter oder relativer Pfad
            if os.path.isabs(local_path_str):
                screenshot_path = local_path_str
            else:
                screenshot_path = os.path.join(base_path, local_path_str)

            if os.path.exists(screenshot_path):
                try:
                    # Bildgröße ermitteln
                    pil_img = PILImage.open(screenshot_path)
                    img_width, img_height = pil_img.size

                    # Auf 50% der ursprünglichen Größe skalieren (wie bei gapselect)
                    # ReportLab arbeitet in Points (72 DPI), PIL in Pixels (üblicherweise 96 DPI)
                    # Konvertierung: Pixel * 72/96 = Points
                    width_points = (img_width * 72 / 96) * 0.5
                    height_points = (img_height * 72 / 96) * 0.5

                    img = Image(screenshot_path, width=width_points, height=height_points)
                    elements.append(img)
                    elements.append(Spacer(1, 3 * mm))
                    self.logger.debug(f"Screenshot included for ordering question {question.get('question_number')}")
                except Exception as e:
                    self.logger.error(f"Failed to load ordering screenshot: {e}")
                    elements.append(Paragraph(
                        f"<i>[Screenshot konnte nicht geladen werden: {os.path.basename(screenshot_path)}]</i>",
                        self.styles['Answer']
                    ))
            else:
                self.logger.warning(f"Ordering screenshot not found: {screenshot_path}")
                # Fallback: Zeige generischen Hinweis
                elements.append(Paragraph(
                    "<i>[Screenshot nicht verfügbar - Details siehe Online-Version]</i>",
                    self.styles['Answer']
                ))
        else:
            # Kein Screenshot vorhanden (sollte nicht passieren)
            self.logger.warning(f"No screenshot data for ordering question {question.get('question_number')}")
            elements.append(Paragraph(
                "<i>[Screenshot nicht verfügbar - Details siehe Online-Version]</i>",
                self.styles['Answer']
            ))

        # Optional: Ordering-Items anzeigen (falls extrahiert)
        ordering_items = question.get('ordering_items', [])
        if ordering_items:
            # Filtere Items wenn only_incorrect aktiviert
            if self.only_incorrect:
                filtered_items = [item for item in ordering_items if item.get('incorrect', False)]
            else:
                filtered_items = ordering_items

            if filtered_items:
                elements.append(Paragraph("<b>Ihre Reihenfolge:</b>", self.styles['Answer']))
                for item in filtered_items:
                    position = item.get('position', '?')
                    text = item.get('text', 'Unbekannt')
                    is_correct = item.get('correct', False)
                    is_incorrect = item.get('incorrect', False)

                    # Status-Marker mit Farben
                    if is_correct:
                        marker = ' <font color="#006400"><i>(✓ richtig)</i></font>'
                    elif is_incorrect:
                        marker = ' <font color="#8B0000"><i>(✗ falsch)</i></font>'
                    else:
                        marker = ''

                    elements.append(Paragraph(
                        f"  {position}. {self._escape_html(text)}{marker}",
                        self.styles['Answer']
                    ))

        return elements

    def _render_match(self, question: Dict) -> List:
        """Rendert Match (Zuordnungs) Frage"""
        elements = []

        matches = question.get('matches', [])
        if matches:
            elements.append(Paragraph("<b>Zuordnungen:</b>", self.styles['Answer']))

            for match in matches:
                question_text = match.get('question', '')
                selected = match.get('selected', 'Nicht ausgewählt')
                is_correct = match.get('correct', False)
                is_incorrect = match.get('incorrect', False)

                # Korrektheit-Marker mit Farben
                if is_correct:
                    marker = ' <font color="#006400"><i>(✓ richtig)</i></font>'
                elif is_incorrect:
                    marker = ' <font color="#8B0000"><i>(✗ falsch)</i></font>'
                else:
                    marker = ''

                # Line breaks in match question and selected answer
                normalized_match_q = self._normalize_linebreaks(question_text)
                escaped_match_q = self._escape_html(normalized_match_q)
                match_q_with_breaks = escaped_match_q.replace('\n', '<br/>')

                normalized_selected = self._normalize_linebreaks(selected)
                escaped_selected = self._escape_html(normalized_selected)
                selected_with_breaks = escaped_selected.replace('\n', '<br/>')

                match_text = f"• {match_q_with_breaks} → <b>{selected_with_breaks}</b>{marker}"
                elements.append(Paragraph(match_text, self.styles['Answer']))

        return elements

    def _render_description(self, question: Dict) -> List:
        """Rendert Description (Information Item) - keine eigentliche Frage"""
        elements = []

        content = question.get('content', '')
        if content:
            # Information ohne Status-Icon, nur Content mit Line breaks
            normalized_content = self._normalize_linebreaks(content)
            escaped_content = self._escape_html(normalized_content)
            content_with_breaks = escaped_content.replace('\n', '<br/>')
            elements.append(Paragraph(
                f"<i>{content_with_breaks}</i>",
                self.styles['QuestionText']
            ))

        return elements

    def _render_feedback(self, feedback: Dict, base_path: str) -> List:
        """Rendert Feedback-Bereich"""
        elements = []

        feedback_text = feedback.get('text', '')
        if feedback_text:
            # Normalisiere Leerzeilen, dann Zeilenumbrüche erhalten
            normalized_feedback_text = self._normalize_linebreaks(feedback_text)
            escaped_feedback_text = self._escape_html(normalized_feedback_text)
            feedback_text_with_breaks = escaped_feedback_text.replace('\n', '<br/>')
            feedback_para = Paragraph(f"<b>Feedback:</b> {feedback_text_with_breaks}", self.styles['Feedback'])
            elements.append(feedback_para)

        # Feedback-Bilder
        feedback_images = feedback.get('images', [])
        for img_info in feedback_images:
            img_loaded = False

            # Versuche lokales Bild zuerst
            if img_info.get('local_path'):
                local_path_str = img_info['local_path']
                # Prüfe ob absoluter oder relativer Pfad
                if os.path.isabs(local_path_str):
                    img_path = local_path_str
                else:
                    img_path = os.path.join(base_path, local_path_str)

                if os.path.exists(img_path):
                    try:
                        # Bildgröße ermitteln
                        pil_img = PILImage.open(img_path)
                        img_width, img_height = pil_img.size

                        # Auf 50% der ursprünglichen Größe skalieren
                        # ReportLab arbeitet in Points (72 DPI), PIL in Pixels (üblicherweise 96 DPI)
                        # Konvertierung: Pixel * 72/96 = Points
                        width_points = (img_width * 72 / 96) * 0.5
                        height_points = (img_height * 72 / 96) * 0.5

                        img = Image(img_path, width=width_points, height=height_points)
                        elements.append(img)
                        elements.append(Spacer(1, 2 * mm))
                        img_loaded = True
                    except Exception as e:
                        self.logger.warning(f"Could not load local feedback image {img_path}: {e}")

            # Platzhalter wenn lokales Bild nicht geladen werden konnte
            if not img_loaded:
                elements.append(Paragraph("[Feedback-Bild nicht verfügbar]", self.styles['Feedback']))

        return elements

    def generate_student_pdf(self, quiz_info: Dict, student: Dict, output_path: str, base_path: str):
        """
        Generiert ein PDF für einen Schüler

        Args:
            quiz_info: Quiz-Informationen
            student: Schüler-Daten
            output_path: Ausgabe-Pfad für das PDF
            base_path: Basis-Pfad für Bilder
        """
        self.logger.info(f"Generating PDF for student {student['user_name']}...")

        # Setze aktuelle Student/Quiz-Daten für Kopf-/Fußzeile
        self.current_student_name = student.get('user_name', 'N/A')
        self.current_quiz_title = quiz_info.get('quiz_name', 'N/A')

        # PDF-Dokument erstellen
        doc = SimpleDocTemplate(
            output_path,
            pagesize=self.pagesize,
            topMargin=self.margin_top,
            bottomMargin=self.margin_bottom,
            leftMargin=self.margin_left,
            rightMargin=self.margin_right
        )

        # Story (Flowables)
        story = []

        # Header
        story.extend(self._create_header(quiz_info, student))

        # Sektionen und Fragen
        sections = student.get('sections', [])
        for section in sections:
            section_name = section.get('section_name', 'Unbenannt')

            # Sammle alle Fragen dieser Section
            section_elements = []
            questions = section.get('questions', [])
            for question in questions:
                section_elements.extend(self._render_question(question, base_path))

            # Nur Section-Überschrift hinzufügen wenn Fragen vorhanden
            if section_elements:
                section_header = Paragraph(f"<b>{section_name.upper()}</b>", self.styles['SectionHeader'])
                story.append(section_header)
                story.append(Spacer(1, 3 * mm))
                story.extend(section_elements)

        # Erstelle Custom Canvas mit Seitenzählung
        def create_canvas(filename, **kwargs):
            """Factory für NumberedCanvas - akzeptiert alle ReportLab kwargs"""
            nc = NumberedCanvas(filename, **kwargs)
            # Setze draw_page_number Methode
            nc.draw_page_number = lambda total: self._add_page_number(nc, nc.getPageNumber(), total)
            return nc

        # PDF bauen mit Kopf-/Fußzeile und Seitenzählung
        doc.build(story, onFirstPage=self._add_page_header_footer, onLaterPages=self._add_page_header_footer, canvasmaker=create_canvas)
        self.logger.info(f"Successfully generated PDF: {output_path}")

    def generate_individual_pdfs(self, data_file: str, output_dir: str, only_incorrect: bool = False):
        """
        Generiert für jeden Schüler ein individuelles PDF aus einer data.json

        Args:
            data_file: Pfad zur data.json
            output_dir: Ausgabe-Verzeichnis für PDFs
            only_incorrect: Wenn True, nur falsche/teilweise richtige Fragen ausgeben

        Returns:
            List[str]: Liste der generierten PDF-Pfade
        """
        # Setze Filter-Option
        self.only_incorrect = only_incorrect
        self.logger.info(f"Loading data from {data_file}...")

        # Lade Daten
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        quiz_info = data['quiz_info']
        students = data['students']

        if not students:
            self.logger.warning(f"No students found in {data_file}, skipping PDF generation")
            return []

        quiz_name = quiz_info['quiz_name']
        group_name = quiz_info['group_name']

        # Basis-Pfad für Bilder (relativ zur data.json)
        base_path = os.path.dirname(data_file)

        # Output-Verzeichnis erstellen
        os.makedirs(output_dir, exist_ok=True)

        generated_pdfs = []

        # Für jeden Schüler ein eigenes PDF erstellen
        for student in students:
            user_name = student.get('user_name', 'Unbekannt')
            metadata = student.get('metadata', {})

            # Extrahiere Datum aus Metadaten (started oder completed)
            date_str = metadata.get('started', '')

            # Parse Datum: "Freitag, 17. Oktober 2025, 09:45" -> "20251017"
            date_prefix = ""
            if date_str:
                try:
                    import locale
                    from datetime import datetime

                    # Versuche verschiedene Formate
                    # Format: "Freitag, 17. Oktober 2025, 09:45"
                    date_parts = date_str.split(',')
                    if len(date_parts) >= 2:
                        date_part = date_parts[1].strip()  # "17. Oktober 2025"

                        # Monatsnamen mapping (deutsch)
                        months = {
                            'Januar': '01', 'Februar': '02', 'März': '03', 'April': '04',
                            'Mai': '05', 'Juni': '06', 'Juli': '07', 'August': '08',
                            'September': '09', 'Oktober': '10', 'November': '11', 'Dezember': '12'
                        }

                        parts = date_part.split()
                        if len(parts) >= 3:
                            day = parts[0].replace('.', '').zfill(2)
                            month = months.get(parts[1], '00')
                            year = parts[2]
                            date_prefix = f"{year}{month}{day}_"
                except Exception as e:
                    self.logger.warning(f"Could not parse date '{date_str}': {e}")
                    date_prefix = ""

            # Dateiname: YYYYMMDD_QuizName_Präfix_Username.pdf (bereinigt)
            # Extrahiere nur den Präfix aus dem Gruppennamen (z.B. "IFA12A - Team 3" -> "IFA12A")
            group_prefix = extract_group_prefix(group_name)

            # Entferne ungültige Zeichen aus Dateinamen
            safe_quiz_name = "".join(c for c in quiz_name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_group_prefix = "".join(c for c in group_prefix if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_user_name = "".join(c for c in user_name if c.isalnum() or c in (' ', '-', '_')).strip()
            output_filename = f"{date_prefix}{safe_quiz_name}_{safe_group_prefix}_{safe_user_name}.pdf"
            output_path = os.path.join(output_dir, output_filename)

            self.logger.info(f"Generating PDF for {user_name}...")

            # Setze Kopf-/Fußzeile für diesen Schüler
            self.current_student_name = user_name
            self.current_quiz_title = quiz_name

            # PDF-Dokument erstellen
            doc = SimpleDocTemplate(
                output_path,
                pagesize=self.pagesize,
                topMargin=self.margin_top,
                bottomMargin=self.margin_bottom,
                leftMargin=self.margin_left,
                rightMargin=self.margin_right
            )

            story = []

            # Header
            story.extend(self._create_header(quiz_info, student))

            # Sektionen und Fragen
            sections = student.get('sections', [])
            for section in sections:
                section_name = section.get('section_name', 'Unbenannt')

                # Sammle alle Fragen dieser Section
                section_elements = []
                questions = section.get('questions', [])
                for question in questions:
                    section_elements.extend(self._render_question(question, base_path))

                # Nur Section-Überschrift hinzufügen wenn Fragen vorhanden
                if section_elements:
                    section_header = Paragraph(f"<b>{section_name.upper()}</b>", self.styles['SectionHeader'])
                    story.append(section_header)
                    story.append(Spacer(1, 3 * mm))
                    story.extend(section_elements)

            # Erstelle Custom Canvas mit Seitenzählung
            def create_canvas(filename, **kwargs):
                """Factory für NumberedCanvas - akzeptiert alle ReportLab kwargs"""
                nc = NumberedCanvas(filename, **kwargs)
                # Setze draw_page_number Methode
                nc.draw_page_number = lambda total: self._add_page_number(nc, nc.getPageNumber(), total)
                return nc

            # PDF bauen mit Kopf-/Fußzeile und Seitenzählung
            doc.build(story, onFirstPage=self._add_page_header_footer, onLaterPages=self._add_page_header_footer, canvasmaker=create_canvas)
            self.logger.info(f"Successfully generated PDF: {output_path}")
            generated_pdfs.append(output_path)

        self.logger.info(f"Generated {len(generated_pdfs)} individual PDFs in {output_dir}")
        return generated_pdfs


def main():
    """CLI Entry Point"""
    import argparse

    # Compute default paths relative to project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_data_dir = os.path.join(project_root, 'data', 'quiz_data')
    default_output_dir = os.path.join(project_root, 'data', 'LNW')

    parser = argparse.ArgumentParser(description='PDF Generator für Mebis Leistungsnachweise')
    parser.add_argument('--data-dir', type=str, default=default_data_dir,
                       help='Verzeichnis mit gescrapten Daten')
    parser.add_argument('--output-dir', type=str, default=default_output_dir,
                       help='Ausgabe-Verzeichnis für PDFs')
    parser.add_argument('--only-incorrect', action='store_true',
                       help='Nur falsche/teilweise richtige Fragen ausgeben (Papier sparen)')

    args = parser.parse_args()

    data_dir = args.data_dir
    output_dir = args.output_dir
    only_incorrect = args.only_incorrect

    # Interaktive Abfrage wenn nicht per CLI übergeben
    if not only_incorrect:
        print("\n" + "="*60)
        print("PDF-GENERIERUNG - OPTIONEN")
        print("="*60)
        user_input = input("\nNur falsche/teilweise richtige Fragen ausgeben? (j/n) [n]: ").strip().lower()
        only_incorrect = user_input in ['j', 'ja', 'y', 'yes']

        if only_incorrect:
            print("✓ Nur fehlerhafte Fragen werden ausgegeben (Papier sparen)")
        else:
            print("✓ Alle Fragen werden ausgegeben")
        print("="*60 + "\n")

    if not os.path.exists(data_dir):
        pdf_logger.error(f"Data directory not found: {data_dir}")
        return

    pdf_logger.info("Starting PDF generation...")
    if only_incorrect:
        pdf_logger.info("Filter: Only incorrect/partially correct questions")

    generator = ExamPDFGenerator()

    # Durchsuche data_dir nach data*.json Dateien (data.json oder data_*.json)
    for root, dirs, files in os.walk(data_dir):
        # Finde alle data*.json Dateien im aktuellen Verzeichnis
        data_files = [f for f in files if f.startswith('data') and f.endswith('.json')]

        for data_filename in data_files:
            data_file = os.path.join(root, data_filename)

            # Lese group_name aus data*.json, um Präfix zu extrahieren
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    group_name = data.get('quiz_info', {}).get('group_name', '')
                    group_prefix = extract_group_prefix(group_name)
            except Exception as e:
                pdf_logger.error(f"Error reading group from {data_file}: {e}")
                group_prefix = ''

            # Bestimme relativen Pfad für Output
            # Neue Input-Struktur: quiz_data/{Präfix}/{QuizName}/data.json
            # Output-Struktur: LNW/{Präfix}/{QuizName}/
            rel_path = os.path.relpath(root, data_dir)

            # Extrahiere Präfix und QuizName aus Pfad
            # rel_path ist z.B. "IFA12A/Frontend" oder nur "Frontend" (alte Struktur)
            path_parts = rel_path.split(os.sep)

            if len(path_parts) >= 2:
                # Neue Struktur: {Präfix}/{QuizName}
                group_prefix_from_path = path_parts[0]
                quiz_name = path_parts[1]
                quiz_output_dir = os.path.join(output_dir, group_prefix_from_path, quiz_name)
            else:
                # Fallback: alte Struktur (nur QuizName) oder root
                quiz_name = path_parts[0] if path_parts[0] != '.' else 'Unknown'
                if group_prefix:
                    quiz_output_dir = os.path.join(output_dir, group_prefix, quiz_name)
                else:
                    quiz_output_dir = os.path.join(output_dir, quiz_name)

            try:
                generator.generate_individual_pdfs(data_file, quiz_output_dir, only_incorrect=only_incorrect)
            except Exception as e:
                pdf_logger.error(f"Error generating PDFs for {data_file}: {e}", exc_info=True)

    pdf_logger.info("PDF generation completed")


if __name__ == '__main__':
    main()
