#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Schüler-Übersichtsbericht Generator

Erstellt pro Schüler eine druckbare PDF-Übersicht mit:
- Leistungsnachweisen (aus quiz_data/)
- Pflichtaufgaben (aus dem neuesten Export-JSON), A→Z sortiert
"""

import os
import sys
import glob
import json
import html
import io
from datetime import datetime
from typing import Dict, List, Optional, Tuple

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from src.common.group_utils import extract_group_prefix
from config.logger_config import get_logger
from config.config_manager import config_manager

logger = get_logger('report_generator')

# Gruppen die keine Schülerklassen sind
IGNORED_GROUP_PATTERNS = ['Lehrkraft', 'Lehrer', 'Admin']

# Deutsche Umlaut-Normalisierung für korrekte alphabetische Sortierung
_UMLAUT_TABLE = str.maketrans({'ä': 'a', 'ö': 'o', 'ü': 'u',
                                'Ä': 'a', 'Ö': 'o', 'Ü': 'u', 'ß': 'ss'})

# Tabellen-Farben (einheitlich mit bestehendem PDF-Generator)
COLOR_HEADER = colors.HexColor('#2c3e50')
COLOR_ROW_ALT = colors.HexColor('#f7f7f7')
COLOR_GRID = colors.HexColor('#cccccc')
COLOR_SECTION = colors.HexColor('#2c3e50')
COLOR_META = colors.HexColor('#555555')
COLOR_MISSING = colors.HexColor('#888888')

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 1.0 * cm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN


class ReportGenerator:
    """Generiert Schüler-Übersichtsberichte als PDF"""

    def __init__(self):
        self.project_root = _project_root
        self.data_dir = os.path.join(self.project_root, 'data', 'quiz_data')
        # EXPORT_FOLDER aus .env (absoluter oder relativer Pfad)
        export_folder = config_manager.get_export_folder()
        self.export_dir = export_folder if os.path.isabs(export_folder) else os.path.join(self.project_root, export_folder)
        self.output_base = os.path.join(self.project_root, 'data', 'report')
        self.export_date = datetime.now().strftime('%Y%m%d')
        self.export_date_display = datetime.now().strftime('%d.%m.%Y')
        self.exclude_names = self._load_exclude_names()

    def _load_exclude_names(self) -> set:
        """Lädt ausgeschlossene Namen aus config/exclude_names.txt"""
        path = os.path.join(self.project_root, 'config', 'exclude_names.txt')
        if not os.path.exists(path):
            return set()
        with open(path, 'r', encoding='utf-8') as f:
            return {line.strip() for line in f if line.strip()}

    # ------------------------------------------------------------------ #
    #  Datenladen                                                          #
    # ------------------------------------------------------------------ #

    def _load_latest_export(self) -> Dict:
        """Lädt die neueste output_*.json aus data/export/"""
        files = glob.glob(os.path.join(self.export_dir, 'output_*.json'))
        if not files:
            raise FileNotFoundError(f"Keine Export-Datei in {self.export_dir}")
        latest = max(files, key=os.path.getmtime)
        basename = os.path.basename(latest)
        logger.info(f"Export: {basename}")
        # Datum aus Dateiname extrahieren (output_YYYYMMDD_HHMMSS.json)
        try:
            date_part = basename.split('_')[1]  # 'YYYYMMDD'
            self.export_date = date_part
            self.export_date_display = datetime.strptime(date_part, '%Y%m%d').strftime('%d.%m.%Y')
        except (IndexError, ValueError):
            pass  # Fallback: datetime.now() aus __init__ bleibt erhalten
        with open(latest, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_second_export(self) -> Optional[Tuple[Dict, str, str]]:
        """Lädt die zweit-neueste output_*.json für den Diff-Report.

        Returns:
            (data, prev_date_raw, prev_date_display) oder None wenn < 2 Dateien.
        """
        files = glob.glob(os.path.join(self.export_dir, 'output_*.json'))
        if len(files) < 2:
            return None
        sorted_files = sorted(files, key=os.path.getmtime)
        prev_file = sorted_files[-2]
        basename = os.path.basename(prev_file)
        try:
            date_raw = basename.split('_')[1]
            date_display = datetime.strptime(date_raw, '%Y%m%d').strftime('%d.%m.%Y')
        except (IndexError, ValueError):
            date_raw = 'unbekannt'
            date_display = '—'
        with open(prev_file, 'r', encoding='utf-8') as f:
            return json.load(f), date_raw, date_display

    def _get_pflichtaufgaben_items(self, export_data: Dict) -> Dict[str, Dict]:
        """
        Gibt {id: {'title': str, 'type': 'assignment'|'quiz'}} für alle
        Pflichtaufgaben zurück (sowohl Assignment- als auch Quiz-Typen).
        HTML-Entities werden dekodiert.
        """
        items = {}
        for cat in export_data.get('activities_by_category', []):
            if 'Pflicht' in cat.get('category_name', ''):
                for a in cat.get('assignments', []):
                    items[a['id']] = {'title': html.unescape(a['title']), 'type': 'assignment'}
                for q in cat.get('quizzes', []):
                    items[q['id']] = {'title': html.unescape(q['title']), 'type': 'quiz'}
        return items

    def _get_lnw_items(self, export_data: Dict) -> List[Dict]:
        """
        Gibt alle LNW-Items aus der Kategorie 'Zentrale Leistungsnachweise' zurück.
        Enthält sowohl Quiz-Typen (mit Punkte/Note aus quiz_data) als auch
        Assignment-Typen (Code-Review, Review-Talk - mit Status aus Export).

        Items mit gleichem Titel werden zusammengeführt (mehrere IDs möglich,
        z.B. wenn verschiedene Gruppen eigene Assignments haben).

        Returns:
            Liste in Mebis-Kursreihenfolge (Assignments vor Quizzes):
            {'type': 'quiz'|'assignment', 'title': str, 'ids': [str]}
        """
        # Reihenfolge aus dem Export beibehalten (= Mebis-Kursreihenfolge).
        # Assignments kommen in Mebis vor den Quizzes, daher erst Assignments iterieren.
        items_by_title: Dict[str, Dict] = {}

        for cat in export_data.get('activities_by_category', []):
            if 'Zentrale Leistungsnachweise' not in cat.get('category_name', ''):
                continue
            for a in cat.get('assignments', []):
                title = html.unescape(a['title'])
                if title not in items_by_title:
                    items_by_title[title] = {'type': 'assignment', 'ids': [a['id']]}
                else:
                    items_by_title[title]['ids'].append(a['id'])
            for q in cat.get('quizzes', []):
                title = html.unescape(q['title'])
                if title not in items_by_title:
                    items_by_title[title] = {'type': 'quiz', 'ids': [q['id']]}
                else:
                    items_by_title[title]['ids'].append(q['id'])

        # Insertionsreihenfolge beibehalten (Python-Dict seit 3.7 geordnet)
        return [{'title': t, **v} for t, v in items_by_title.items()]

    def _is_quiz_submitted(self, status: Dict) -> bool:
        """Quiz gilt als abgegeben wenn Status nicht explizit 'nicht eingereicht'"""
        if not status:
            return False
        s = status.get('status', '')
        return s not in ('Nicht eingereicht', 'Nicht abgeschlossen', '')

    def _find_activity_ids_by_title(self, export_data: Dict, title: str, activity_type: str) -> List[str]:
        """Sucht in ALLEN Kategorien nach Aktivitäten mit passendem Titel.

        Fallback wenn die Kategorie zwischen Exporten wechselt (z.B. ZLN → Alle).
        """
        ids = []
        key = 'assignments' if activity_type == 'assignment' else 'quizzes'
        for cat in export_data.get('activities_by_category', []):
            for item in cat.get(key, []):
                if html.unescape(item.get('title', '')) == title:
                    ids.append(item['id'])
        return ids

    def _extract_student_grade(self, activities: Dict, lnw_item: Dict) -> Tuple[str, Optional[str]]:
        """Extrahiert (bewertung_display, submission_time_raw) für ein LNW-Item.

        Spiegelt die Logik aus _lnw_table() für Quiz- und Assignment-Typen.
        Returns ('—', None) wenn nicht abgegeben.
        """
        if lnw_item['type'] == 'quiz':
            all_quiz = {q['id']: q.get('status', {}) for q in activities.get('quizzes', [])}
            status = None
            for qid in lnw_item['ids']:
                if qid in all_quiz:
                    status = all_quiz[qid]
                    break
            if not self._is_quiz_submitted(status):
                return ('—', None)
            grade = status.get('grade', '-') or '-'
            bewertung = grade if grade != '-' else 'Bewertung offen'
            return (bewertung, status.get('submission_time'))
        else:  # assignment
            all_assign = {a['id']: a.get('status', {}) for a in activities.get('assignments', [])}
            status = None
            for aid in lnw_item['ids']:
                if aid in all_assign:
                    s = all_assign[aid]
                    if s.get('submission_time'):
                        status = s
                        break
                    status = status or s
            if not status or not status.get('submission_time'):
                return ('—', None)
            grade_val = status.get('grade', '')
            bewertung = grade_val if (status.get('status2') == 'Bewertet' and grade_val) else 'Bewertung offen'
            return (bewertung, status.get('submission_time'))

    def _get_klassen_from_export(self, export_data: Dict) -> Dict[str, List[Dict]]:
        """
        Gruppiert Schüler nach Klassen-Präfix, dedupliziert per user_id.

        Returns:
            {klasse: [user_dict, ...]}
        """
        klassen: Dict[str, Dict[str, Dict]] = {}

        for group in export_data.get('groups', []):
            group_name = group.get('name', '')
            if any(pat in group_name for pat in IGNORED_GROUP_PATTERNS):
                continue
            klasse = extract_group_prefix(group_name)
            if not klasse:
                continue
            klassen.setdefault(klasse, {})
            for user in group.get('users', []):
                uid = str(user.get('id', ''))
                if uid and uid not in klassen[klasse] and user.get('name', '') not in self.exclude_names:
                    klassen[klasse][uid] = user

        return {k: list(v.values()) for k, v in klassen.items()}

    # ------------------------------------------------------------------ #
    #  Hilfsfunktionen                                                     #
    # ------------------------------------------------------------------ #

    def _parse_name(self, full_name: str) -> Tuple[str, str]:
        """Vorname = erstes Wort, Nachname = Rest (mit Bindestrich verbunden)"""
        parts = full_name.strip().split()
        if not parts:
            return ('', '')
        if len(parts) == 1:
            return (parts[0], '')
        return (parts[0], '-'.join(parts[1:]))

    def _safe_filename(self, s: str) -> str:
        """Ersetzt Zeichen die in Dateinamen nicht erlaubt sind"""
        for ch in r'/\:*?"<>|':
            s = s.replace(ch, '_')
        return s

    def _make_filename(self, klasse: str, full_name: str) -> str:
        """Dateiname: Klasse_Nachname_Vorname_YYYYMMDD.pdf"""
        vorname, nachname = self._parse_name(full_name)
        return (
            f"{self._safe_filename(klasse)}_"
            f"{self._safe_filename(nachname)}_"
            f"{self._safe_filename(vorname)}_"
            f"{self.export_date}.pdf"
        )

    def _format_submission_time(self, submission_time: Optional[str]) -> str:
        """ISO-Datetime → TT.MM.YYYY"""
        if not submission_time:
            return ''
        try:
            return datetime.fromisoformat(submission_time).strftime('%d.%m.%Y')
        except (ValueError, TypeError):
            return submission_time

    # ------------------------------------------------------------------ #
    #  PDF-Generierung                                                     #
    # ------------------------------------------------------------------ #

    def _page_footer(self, canvas, doc):
        """Footer mit Exportdatum und Seitenzahl"""
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(COLOR_META)
        canvas.drawString(MARGIN, 0.7 * cm, f"Exportiert am {self.export_date_display}")
        canvas.drawRightString(
            PAGE_WIDTH - MARGIN, 0.7 * cm, f"Seite {doc.page}"
        )
        canvas.restoreState()

    def _make_styles(self) -> Dict[str, ParagraphStyle]:
        """Erstellt alle benötigten ParagraphStyles"""
        base = getSampleStyleSheet()['Normal']
        return {
            'title': ParagraphStyle('RTitle',
                fontSize=14, fontName='Helvetica-Bold',
                alignment=TA_CENTER, spaceAfter=2 * mm),
            'meta': ParagraphStyle('RMeta',
                fontSize=9.5, fontName='Helvetica',
                alignment=TA_CENTER, spaceAfter=5 * mm,
                textColor=COLOR_META),
            'section': ParagraphStyle('RSection',
                fontSize=10.5, fontName='Helvetica-Bold',
                spaceBefore=6 * mm, spaceAfter=2 * mm,
                textColor=COLOR_SECTION),
            'cell': ParagraphStyle('RCell',
                fontSize=8.5, fontName='Helvetica',
                leading=11, parent=base),
            'cell_missing': ParagraphStyle('RCellMissing',
                fontSize=8.5, fontName='Helvetica-Oblique',
                leading=11, textColor=COLOR_MISSING, parent=base),
        }

    def _lnw_table(self, lnw_items: List[Dict],
                   all_quiz_status_by_id: Dict[str, Dict],
                   all_assign_status_by_id: Dict[str, Dict],
                   styles: Dict) -> Table:
        """
        Erstellt die Leistungsnachweise-Tabelle.

        Quiz-Typen: Status + Note aus activities.quizzes (Export).
        Assignment-Typen: Abgabedatum + Bewertung aus activities.assignments (Export).
        """
        col_w = [CONTENT_WIDTH * 0.55, CONTENT_WIDTH * 0.23, CONTENT_WIDTH * 0.22]
        rows = [['Leistungsnachweis', 'Abgabedatum', 'Note']]

        for item in lnw_items:
            title = item['title']

            if item['type'] == 'quiz':
                # Suche Quiz-Status nach ID (erster Treffer mit Submission gewinnt)
                status = None
                for qid in item['ids']:
                    if qid in all_quiz_status_by_id:
                        status = all_quiz_status_by_id[qid]
                        break

                if not self._is_quiz_submitted(status):
                    rows.append([
                        Paragraph(title, styles['cell']),
                        Paragraph('nicht abgegeben', styles['cell_missing']), '—',
                    ])
                else:
                    sub_time = self._format_submission_time(status.get('submission_time')) or '—'
                    grade = status.get('grade', '-') or '-'
                    note = grade if grade != '-' else 'Bewertung offen'
                    rows.append([Paragraph(title, styles['cell']), sub_time, note])

            else:  # assignment
                status = None
                for aid in item['ids']:
                    if aid in all_assign_status_by_id:
                        s = all_assign_status_by_id[aid]
                        if s.get('submission_time'):
                            status = s
                            break
                        status = status or s

                if not status or not status.get('submission_time'):
                    rows.append([
                        Paragraph(title, styles['cell']),
                        Paragraph('nicht abgegeben', styles['cell_missing']), '—',
                    ])
                else:
                    sub_time = self._format_submission_time(status['submission_time'])
                    grade_val = status.get('grade', '')
                    note = grade_val if (status.get('status2') == 'Bewertet' and grade_val) else 'Bewertung offen'
                    rows.append([Paragraph(title, styles['cell']), sub_time, note])

        if len(rows) == 1:
            rows.append([Paragraph('Keine Leistungsnachweise vorhanden', styles['cell_missing']), '', ''])

        return self._styled_table(rows, col_w)

    def _pflicht_table(self, pflichtaufgaben_items: Dict[str, Dict],
                       all_assign_status_by_id: Dict[str, Dict],
                       all_quiz_status_by_id: Dict[str, Dict],
                       styles: Dict) -> Table:
        """Erstellt die Pflichtaufgaben-Tabelle (A→Z nach Titel sortiert)"""
        col_w = [CONTENT_WIDTH * 0.50, CONTENT_WIDTH * 0.17, CONTENT_WIDTH * 0.33]
        rows = [['Aufgabe', 'Abgabedatum', 'Bewertung']]

        sorted_items = sorted(pflichtaufgaben_items.items(), key=lambda x: x[1]['title'])

        for item_id, item in sorted_items:
            title = item['title']
            item_type = item['type']

            if item_type == 'quiz':
                status = all_quiz_status_by_id.get(item_id)
                if not self._is_quiz_submitted(status):
                    rows.append([
                        Paragraph(title, styles['cell']),
                        Paragraph('nicht abgegeben', styles['cell_missing']), '—',
                    ])
                else:
                    sub_time = self._format_submission_time(status.get('submission_time')) or '—'
                    grade = status.get('grade', '-') or '-'
                    bewertung = grade if grade != '-' else 'Bewertung offen'
                    rows.append([Paragraph(title, styles['cell']), sub_time, bewertung])

            else:  # assignment
                status = all_assign_status_by_id.get(item_id)
                if not status:
                    rows.append([
                        Paragraph(title, styles['cell']),
                        Paragraph('nicht abgegeben', styles['cell_missing']), '—',
                    ])
                    continue
                sub_time = self._format_submission_time(status.get('submission_time'))
                if not sub_time:
                    rows.append([
                        Paragraph(title, styles['cell']),
                        Paragraph('nicht abgegeben', styles['cell_missing']), '—',
                    ])
                else:
                    grade_val = status.get('grade', '')
                    bewertung = grade_val if (status.get('status2') == 'Bewertet' and grade_val) else 'Bewertung offen'
                    rows.append([Paragraph(title, styles['cell']), sub_time, bewertung])

        return self._styled_table(rows, col_w)

    def _styled_table(self, rows: List, col_widths: List[float]) -> Table:
        """Einheitliches Tabellen-Styling"""
        table = Table(rows, colWidths=col_widths, repeatRows=1)

        style_cmds = [
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), COLOR_HEADER),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            # Inhalt
            ('FONTSIZE', (0, 1), (-1, -1), 8.5),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            # Alternating rows
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COLOR_ROW_ALT]),
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.4, COLOR_GRID),
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]
        table.setStyle(TableStyle(style_cmds))
        return table

    def _generate_pdf(self, student: Dict, klasse: str,
                      pflichtaufgaben_items: Dict[str, Dict],
                      lnw_items: List[Dict]) -> bytes:
        """Generiert den PDF-Inhalt für einen Schüler"""
        buffer = io.BytesIO()
        user_name = student.get('name', 'Unbekannt')
        vorname, nachname = self._parse_name(user_name)

        # Status-Dicts nach ID (Assignments + Quizzes getrennt)
        activities = student.get('activities', {})
        all_assign_status = {a['id']: a.get('status', {}) for a in activities.get('assignments', [])}
        all_quiz_status = {q['id']: q.get('status', {}) for q in activities.get('quizzes', [])}

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=1.0 * cm,
            bottomMargin=1.0 * cm,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            title=f"Übersicht {user_name}",
            author="Mebis Statistics",
        )

        styles = self._make_styles()
        elements = []

        # --- Header ---
        display_name = f"{nachname}, {vorname}" if nachname else vorname
        elements.append(Paragraph("Fortschritts-Übersicht", styles['title']))
        elements.append(Paragraph(
            f"{display_name}&nbsp;&nbsp;|&nbsp;&nbsp;{klasse}&nbsp;&nbsp;|&nbsp;&nbsp;Stand: {self.export_date_display}",
            styles['meta']
        ))

        # Trennlinie
        separator = Table([['']], colWidths=[CONTENT_WIDTH],
                          style=TableStyle([
                              ('LINEABOVE', (0, 0), (-1, -1), 1.2, COLOR_SECTION),
                          ]))
        elements.append(separator)
        elements.append(Spacer(1, 1 * mm))

        # --- Pflichtaufgaben ---
        elements.append(Paragraph("Pflichtaufgaben", styles['section']))
        elements.append(self._pflicht_table(pflichtaufgaben_items, all_assign_status, all_quiz_status, styles))

        # --- Leistungsnachweise ---
        elements.append(Paragraph("Leistungsnachweise", styles['section']))
        elements.append(self._lnw_table(lnw_items, all_quiz_status, all_assign_status, styles))

        doc.build(
            elements,
            onFirstPage=self._page_footer,
            onLaterPages=self._page_footer,
        )
        return buffer.getvalue()

    # ------------------------------------------------------------------ #
    #  Pflichtaufgaben-Übersicht (alle Schüler pro Aufgabe)               #
    # ------------------------------------------------------------------ #

    def _get_all_students(self, export_data: Dict) -> List[Dict]:
        """
        Alle Schüler (dedupliziert nach user_id) mit Klassen-Info,
        sortiert nach Name A→Z.

        Returns:
            [{'user': user_dict, 'klasse': str}, ...]
        """
        seen: Dict[str, Dict] = {}
        for group in export_data.get('groups', []):
            group_name = group.get('name', '')
            if any(pat in group_name for pat in IGNORED_GROUP_PATTERNS):
                continue
            klasse = extract_group_prefix(group_name)
            if not klasse:
                continue
            for user in group.get('users', []):
                uid = str(user.get('id', ''))
                if uid and uid not in seen and user.get('name', '') not in self.exclude_names:
                    seen[uid] = {'user': user, 'klasse': klasse}
        def sort_key(entry):
            vorname, nachname = self._parse_name(entry['user'].get('name', ''))
            return (nachname.lower().translate(_UMLAUT_TABLE),
                    vorname.lower().translate(_UMLAUT_TABLE))
        return sorted(seen.values(), key=sort_key)

    def _pflichtaufgabe_overview_table(self, item_id: str, item_type: str,
                                       students: List[Dict], styles: Dict) -> Table:
        """Tabelle aller Schüler für eine Pflichtaufgabe"""
        col_w = [CONTENT_WIDTH * 0.38, CONTENT_WIDTH * 0.28,
                 CONTENT_WIDTH * 0.20, CONTENT_WIDTH * 0.14]
        rows = [['Name', 'Bewertung', 'Datum', 'Klasse']]

        for entry in students:
            user = entry['user']
            klasse = entry['klasse']
            vorname, nachname = self._parse_name(user.get('name', ''))
            display_name = f"{vorname} {nachname}".strip()
            activities = user.get('activities', {})

            if item_type == 'quiz':
                all_quiz = {q['id']: q.get('status', {}) for q in activities.get('quizzes', [])}
                status = all_quiz.get(item_id)
                if not self._is_quiz_submitted(status):
                    rows.append([
                        Paragraph(display_name, styles['cell']), '—',
                        Paragraph('nicht abgegeben', styles['cell_missing']), klasse,
                    ])
                else:
                    sub_time = self._format_submission_time(status.get('submission_time')) or '—'
                    grade = status.get('grade', '-') or '-'
                    bewertung = grade if grade != '-' else 'Bewertung offen'
                    rows.append([Paragraph(display_name, styles['cell']), bewertung, sub_time, klasse])

            else:  # assignment
                all_assign = {a['id']: a.get('status', {}) for a in activities.get('assignments', [])}
                status = all_assign.get(item_id)
                if not status or not status.get('submission_time'):
                    rows.append([
                        Paragraph(display_name, styles['cell']), '—',
                        Paragraph('nicht abgegeben', styles['cell_missing']), klasse,
                    ])
                else:
                    sub_time = self._format_submission_time(status['submission_time'])
                    grade_val = status.get('grade', '')
                    bewertung = grade_val if (status.get('status2') == 'Bewertet' and grade_val) else 'Bewertung offen'
                    rows.append([Paragraph(display_name, styles['cell']), bewertung, sub_time, klasse])

        return self._styled_table(rows, col_w)

    def run_pflichtaufgaben(self, pflichtaufgaben_items: Dict[str, Dict],
                            all_students: List[Dict]):
        """Generiert pro Pflichtaufgabe einen Bericht mit allen Schülern (A→Z)"""

        output_dir = os.path.join(self.output_base, 'pflichtaufgaben')
        os.makedirs(output_dir, exist_ok=True)

        total_pdfs = 0
        total_errors = 0

        for item_id, item in sorted(pflichtaufgaben_items.items(), key=lambda x: x[1]['title']):
            title = item['title']
            item_type = item['type']
            filename = f"{self._safe_filename(title)}_{self.export_date}.pdf"
            filepath = os.path.join(output_dir, filename)

            try:
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(
                    buffer,
                    pagesize=A4,
                    topMargin=1.0 * cm,
                    bottomMargin=1.0 * cm,
                    leftMargin=MARGIN,
                    rightMargin=MARGIN,
                    title=f"Pflichtaufgabe: {title}",
                    author="Mebis Statistics",
                )
                styles = self._make_styles()
                elements = []

                elements.append(Paragraph("Pflichtaufgaben-Übersicht", styles['title']))
                elements.append(Paragraph(
                    f"{title}&nbsp;&nbsp;|&nbsp;&nbsp;Stand: {self.export_date_display}",
                    styles['meta']
                ))
                separator = Table([['']], colWidths=[CONTENT_WIDTH],
                                  style=TableStyle([('LINEABOVE', (0, 0), (-1, -1), 1.2, COLOR_SECTION)]))
                elements.append(separator)
                elements.append(Spacer(1, 1 * mm))
                elements.append(self._pflichtaufgabe_overview_table(item_id, item_type, all_students, styles))

                doc.build(elements, onFirstPage=self._page_footer, onLaterPages=self._page_footer)
                with open(filepath, 'wb') as f:
                    f.write(buffer.getvalue())
                total_pdfs += 1
                logger.info(f"  OK  {filename}")
            except Exception as e:
                total_errors += 1
                logger.error(f"  ERR {title}: {e}", exc_info=True)

        logger.info(f"\n{'='*50}")
        logger.info(f"Fertig: {total_pdfs} PDFs erstellt, {total_errors} Fehler")
        logger.info(f"Ausgabe: {output_dir}")

    # ------------------------------------------------------------------ #
    #  LNW Änderungsbericht (aktuell vs. vorherig)                        #
    # ------------------------------------------------------------------ #

    def _lnw_diff_section_table(self, rows: List, styles: Dict) -> Table:
        """Tabelle für einen LNW-Abschnitt im Diff-Report.

        Spalten: Name | Klasse | Bewertung jetzt | Bewertung alt | Datum jetzt | Datum alt
        """
        col_w = [
            CONTENT_WIDTH * 0.28, CONTENT_WIDTH * 0.10,
            CONTENT_WIDTH * 0.16, CONTENT_WIDTH * 0.16,
            CONTENT_WIDTH * 0.15, CONTENT_WIDTH * 0.15,
        ]
        return self._styled_table(rows, col_w)

    def run_lnw_diff(self, export_data: Dict, lnw_items: List[Dict], all_students: List[Dict]):
        """Generiert den LNW Änderungsbericht (aktuell vs. vorheriger Export)."""
        result = self._load_second_export()
        if result is None:
            logger.info("Kein vorheriger Export gefunden, Diff übersprungen.")
            return
        prev_data, prev_date_raw, prev_date_display = result
        logger.info(f"Vergleiche mit: {prev_date_display}")

        # LNW-Items aus vorherigem Export — IDs können sich geändert haben,
        # daher Titel-basierter Abgleich zwischen aktuellem und vorherigem Export.
        prev_lnw_by_title: Dict[str, Dict] = {
            item['title']: item for item in self._get_lnw_items(prev_data)
        }

        # Testgruppe im Diff-Report ausblenden
        diff_students = [e for e in all_students if e['klasse'] != 'Testgruppe']

        # Lookup: uid → user_dict aus dem vorherigen Export
        prev_user_map: Dict[str, Dict] = {}
        for group in prev_data.get('groups', []):
            group_name = group.get('name', '')
            if any(pat in group_name for pat in IGNORED_GROUP_PATTERNS):
                continue
            if extract_group_prefix(group_name) == 'Testgruppe':
                continue
            if not extract_group_prefix(group_name):
                continue
            for user in group.get('users', []):
                uid = str(user.get('id', ''))
                if uid and uid not in prev_user_map and user.get('name', '') not in self.exclude_names:
                    prev_user_map[uid] = user

        # LNW-Items aus aktuellem Export (kann leer sein wenn Kategorie umbenannt wurde)
        cur_lnw_by_title: Dict[str, Dict] = {
            item['title']: item for item in self._get_lnw_items(export_data)
        }

        # Diff-Daten aufbauen — Basis: vorheriger Export (korrekt kategorisiert)
        # Für aktuellen Export: zuerst cur_lnw_by_title, Fallback: titelweite Suche in allen Kategorien
        lnw_sections: List[Tuple[str, List]] = []
        total_changes = 0
        styles = self._make_styles()

        logger.info(f"  LNW aktuell: {len(cur_lnw_by_title)}, LNW vorher: {len(prev_lnw_by_title)}")

        for prev_lnw_item in prev_lnw_by_title.values():
            lnw_title = prev_lnw_item['title']
            item_type = prev_lnw_item['type']

            # Aktuelle IDs: erst aus korrekt kategorisierten Items, dann titelweite Suche
            if lnw_title in cur_lnw_by_title:
                cur_ids = cur_lnw_by_title[lnw_title]['ids']
            else:
                cur_ids = self._find_activity_ids_by_title(export_data, lnw_title, item_type)
                if cur_ids:
                    logger.info(f"  Titelsuche: '{lnw_title}' → {cur_ids}")
            cur_lnw_item = {'title': lnw_title, 'type': item_type, 'ids': cur_ids}

            header = ['Name', 'Klasse', 'Bewertung jetzt', 'Bewertung alt', 'Datum jetzt', 'Datum alt']
            section_rows = [header]

            for entry in diff_students:
                user = entry['user']
                klasse = entry['klasse']
                uid = str(user.get('id', ''))
                vorname, nachname = self._parse_name(user.get('name', ''))
                display_name = f"{vorname} {nachname}".strip()

                cur_activities = user.get('activities', {})
                grade_cur, dt_cur = self._extract_student_grade(cur_activities, cur_lnw_item)

                prev_user = prev_user_map.get(uid)
                if prev_user:
                    prev_activities = prev_user.get('activities', {})
                    grade_prev, dt_prev = self._extract_student_grade(prev_activities, prev_lnw_item)
                else:
                    grade_prev, dt_prev = '—', None

                if grade_cur == grade_prev:
                    continue

                dt_cur_fmt = self._format_submission_time(dt_cur) if dt_cur else '—'
                dt_prev_fmt = self._format_submission_time(dt_prev) if dt_prev else '—'

                name_cell = Paragraph(display_name, styles['cell'])
                section_rows.append([name_cell, klasse, grade_cur, grade_prev, dt_cur_fmt, dt_prev_fmt])

            if len(section_rows) > 1:
                lnw_sections.append((lnw_title, section_rows))
                total_changes += len(section_rows) - 1
                logger.info(f"  {lnw_title}: {len(section_rows) - 1} Änderungen")

        logger.info(f"  LNW: {total_changes} Änderungen in {len(lnw_sections)} Items")

        # --- Pflichtaufgaben-Diff ---
        prev_pflicht = self._get_pflichtaufgaben_items(prev_data)
        cur_pflicht = self._get_pflichtaufgaben_items(export_data)

        # Titel → {type, ids} für beide Exporte
        def _pflicht_by_title(items: Dict) -> Dict[str, Dict]:
            result: Dict[str, Dict] = {}
            for pid, pitem in items.items():
                t = pitem['title']
                result.setdefault(t, {'type': pitem['type'], 'ids': []})
                result[t]['ids'].append(pid)
            return result

        prev_pflicht_by_title = _pflicht_by_title(prev_pflicht)
        cur_pflicht_by_title_diff = _pflicht_by_title(cur_pflicht)

        pflicht_sections: List[Tuple[str, List]] = []
        total_pflicht_changes = 0

        for title in sorted(prev_pflicht_by_title.keys()):
            prev_pflicht_item = prev_pflicht_by_title[title]
            cur_pflicht_item = cur_pflicht_by_title_diff.get(
                title, {'type': prev_pflicht_item['type'], 'ids': []}
            )
            section_rows = [['Name', 'Klasse', 'Bewertung jetzt', 'Bewertung alt', 'Datum jetzt', 'Datum alt']]

            for entry in diff_students:
                user = entry['user']
                klasse = entry['klasse']
                uid = str(user.get('id', ''))
                vorname, nachname = self._parse_name(user.get('name', ''))
                display_name = f"{vorname} {nachname}".strip()

                cur_activities = user.get('activities', {})
                grade_cur, dt_cur = self._extract_student_grade(cur_activities, cur_pflicht_item)

                prev_user = prev_user_map.get(uid)
                if prev_user:
                    grade_prev, dt_prev = self._extract_student_grade(
                        prev_user.get('activities', {}), prev_pflicht_item
                    )
                else:
                    grade_prev, dt_prev = '—', None

                if grade_cur == grade_prev:
                    continue

                dt_cur_fmt = self._format_submission_time(dt_cur) if dt_cur else '—'
                dt_prev_fmt = self._format_submission_time(dt_prev) if dt_prev else '—'
                section_rows.append([Paragraph(display_name, styles['cell']),
                                      klasse, grade_cur, grade_prev, dt_cur_fmt, dt_prev_fmt])

            if len(section_rows) > 1:
                pflicht_sections.append((title, section_rows))
                total_pflicht_changes += len(section_rows) - 1
                logger.info(f"  {title}: {len(section_rows) - 1} Änderungen")

        logger.info(f"  Pflichtaufgaben: {total_pflicht_changes} Änderungen in {len(pflicht_sections)} Items")

        # PDF bauen
        output_dir = os.path.join(self.output_base, 'diff')
        os.makedirs(output_dir, exist_ok=True)
        filename = f"diff_{self.export_date}_{prev_date_raw}.pdf"
        filepath = os.path.join(output_dir, filename)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=1.0 * cm,
            bottomMargin=1.0 * cm,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            title="Änderungsbericht",
            author="Mebis Statistics",
        )
        elements = []

        elements.append(Paragraph("Änderungsbericht", styles['title']))
        elements.append(Paragraph(
            f"Stand: {self.export_date_display}&nbsp;&nbsp;|&nbsp;&nbsp;Vorheriger Export: {prev_date_display}",
            styles['meta']
        ))
        separator = Table([['']], colWidths=[CONTENT_WIDTH],
                          style=TableStyle([('LINEABOVE', (0, 0), (-1, -1), 1.2, COLOR_SECTION)]))
        elements.append(separator)
        elements.append(Spacer(1, 1 * mm))

        has_any = lnw_sections or pflicht_sections
        if not has_any:
            elements.append(Paragraph("Keine Änderungen gefunden.", styles['cell_missing']))
        else:
            if lnw_sections:
                elements.append(Paragraph("Leistungsnachweise", styles['section']))
                elements.append(Spacer(1, 1 * mm))
                for lnw_title, section_rows in lnw_sections:
                    elements.append(Paragraph(lnw_title, styles['meta']))
                    elements.append(self._lnw_diff_section_table(section_rows, styles))
                    elements.append(Spacer(1, 3 * mm))
            if pflicht_sections:
                elements.append(Paragraph("Pflichtaufgaben", styles['section']))
                elements.append(Spacer(1, 1 * mm))
                for title, section_rows in pflicht_sections:
                    elements.append(Paragraph(title, styles['meta']))
                    elements.append(self._lnw_diff_section_table(section_rows, styles))
                    elements.append(Spacer(1, 3 * mm))

        doc.build(elements, onFirstPage=self._page_footer, onLaterPages=self._page_footer)
        with open(filepath, 'wb') as f:
            f.write(buffer.getvalue())
        logger.info(f"  OK  {filename}")

        # ID-Matching-Datei: vollständige Zuordnung alter → neuer IDs
        # Leistungsnachweise-Sektion (Basis: vorheriger Export; current_ids per Titelsuche)
        lnw_section: Dict[str, Dict] = {}
        for prev_item in prev_lnw_by_title.values():
            title = prev_item['title']
            cur_ids = (cur_lnw_by_title[title]['ids'] if title in cur_lnw_by_title
                       else self._find_activity_ids_by_title(export_data, title, prev_item['type']))
            lnw_section[title] = {
                'type': prev_item['type'],
                'current_ids': cur_ids,
                'prev_ids': prev_item['ids'],
            }

        # Pflichtaufgaben-Sektion für Mapping (nutzt bereits berechnete Dicts)
        pflicht_mapping_section: Dict[str, Dict] = {}
        for title, prev_item in prev_pflicht_by_title.items():
            cur_item = cur_pflicht_by_title_diff.get(title, {'ids': []})
            pflicht_mapping_section[title] = {
                'type': prev_item['type'],
                'current_ids': cur_item['ids'],
                'prev_ids': prev_item['ids'],
            }

        # Flacher Lookup: prev_id → current_id (alle Aktivitäten)
        id_mapping: Dict[str, str] = {}
        for entry in list(lnw_section.values()) + list(pflicht_mapping_section.values()):
            for prev_id, cur_id in zip(entry['prev_ids'], entry['current_ids']):
                id_mapping[prev_id] = cur_id

        mapping_doc = {
            'meta': {
                'current_export': self.export_date,
                'prev_export': prev_date_raw,
                'generated': self.export_date_display,
            },
            'leistungsnachweise': lnw_section,
            'pflichtaufgaben': pflicht_mapping_section,
            'id_mapping': id_mapping,
        }
        mapping_filename = f"lnw_id_mapping_{self.export_date}_{prev_date_raw}.json"
        mapping_filepath = os.path.join(output_dir, mapping_filename)
        with open(mapping_filepath, 'w', encoding='utf-8') as f:
            json.dump(mapping_doc, f, ensure_ascii=False, indent=2)
        logger.info(f"  OK  {mapping_filename}")
        logger.info(f"  Ausgabe: {output_dir}")

    # ------------------------------------------------------------------ #
    #  Hauptmethode                                                        #
    # ------------------------------------------------------------------ #

    def run(self):
        """Generiert alle Berichte (Schüler-Übersichten + Pflichtaufgaben-Reports)"""
        export_data = self._load_latest_export()

        pflichtaufgaben_items = self._get_pflichtaufgaben_items(export_data)
        logger.info(f"{len(pflichtaufgaben_items)} Pflichtaufgaben gefunden")

        lnw_items = self._get_lnw_items(export_data)
        logger.info(f"{len(lnw_items)} Leistungsnachweise gefunden (Export)")

        klassen = self._get_klassen_from_export(export_data)
        logger.info(f"{len(klassen)} Klassen: {', '.join(sorted(klassen.keys()))}")

        total_pdfs = 0
        total_errors = 0

        for klasse in sorted(klassen.keys()):
            students = klassen[klasse]
            output_dir = os.path.join(self.output_base, klasse)
            os.makedirs(output_dir, exist_ok=True)

            logger.info(f"\n{klasse}: {len(students)} Schüler")

            for student in sorted(students, key=lambda s: s.get('name', '')):
                user_name = student.get('name', '')
                if not user_name:
                    continue
                try:
                    filename = self._make_filename(klasse, user_name)
                    filepath = os.path.join(output_dir, filename)
                    pdf_bytes = self._generate_pdf(
                        student, klasse,
                        pflichtaufgaben_items,
                        lnw_items,
                    )
                    with open(filepath, 'wb') as f:
                        f.write(pdf_bytes)
                    total_pdfs += 1
                    logger.info(f"  OK  {filename}")
                except Exception as e:
                    total_errors += 1
                    logger.error(f"  ERR {user_name}: {e}", exc_info=True)

        logger.info(f"\n{'='*50}")
        logger.info(f"Schüler-Berichte: {total_pdfs} PDFs, {total_errors} Fehler")

        # --- Pflichtaufgaben-Reports ---
        logger.info("\n--- Pflichtaufgaben-Reports ---")
        all_students = self._get_all_students(export_data)
        logger.info(f"{len(all_students)} Schüler gesamt")
        self.run_pflichtaufgaben(pflichtaufgaben_items, all_students)

        # --- LNW Änderungsbericht ---
        logger.info("\n--- LNW Änderungsbericht ---")
        self.run_lnw_diff(export_data, lnw_items, all_students)


def main():
    ReportGenerator().run()


if __name__ == '__main__':
    main()
