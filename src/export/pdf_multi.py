#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PDF Generator für Code-Review Dokumente - Multi-Group Version
Erstellt ein PDF mit mehreren Seiten (eine pro Gruppe)
"""

import os
import tempfile
from datetime import datetime
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_BREAK
from docx2pdf import convert
import pythoncom
try:
    from pypdf import PdfWriter  # no longer used if merging disabled
except Exception:
    PdfWriter = None
from config.logger_config import get_logger
import json
import re

# Logger Setup
pdf_logger = get_logger('pdf_generator')


class ReviewPDFGeneratorMulti:
    """Generator für Code-Review PDFs mit Multi-Group Support"""

    def __init__(self, template_path='Templates/Code_Review_Vorlage.docx'):
        """
        Initialisiert den PDF Generator

        Args:
            template_path: Pfad zur Word-Vorlage
        """
        self.template_path = template_path
        self.logger = pdf_logger

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Word-Vorlage nicht gefunden: {template_path}")

        self.logger.info(f"PDF Generator Multi initialized with template: {template_path}")

    def generate_pdf(self, data, output_path=None):
        """
        Generiert ein PDF basierend auf der Vorlage und den übergebenen Daten

        Args:
            data: Dictionary mit Daten für das PDF
                - reviewNr: Review-Nummer
                - reviewDate: Datum des Reviews
                - grouping: Gruppierung
                - group: Gruppe (oder 'all')
                - isAllGroups: Boolean - ob alle Gruppen erstellt werden sollen
                - allGroups: Dictionary mit allen Gruppen (wenn isAllGroups=True)
                - groupData: Daten einer einzelnen Gruppe

        Returns:
            str: Pfad zum generierten PDF
        """
        self.logger.info(f"Starting PDF generation for Review {data.get('reviewNr')}")

        try:
            # Prüfe ob alle Gruppen oder nur eine Gruppe
            is_all_groups = data.get('isAllGroups', False)

            if is_all_groups:
                self.logger.info("Generating PDF for ALL groups")
                return self._generate_multi_group_pdf(data, output_path)
            else:
                self.logger.info(f"Generating PDF for single group: {data.get('group')}")
                return self._generate_single_group_pdf(data, output_path)

        except Exception as e:
            self.logger.error(f"Error generating PDF: {e}", exc_info=True)
            raise

    def _generate_multi_group_pdf(self, data, output_path=None):
        """Generiert pro Gruppe ein eigenes PDF und merged sie zu einem großen PDF."""
        self.logger.info("Generating multi-group PDFs with merge")

        all_groups = data.get('allGroups', {})
        disabled_groups = data.get('disabledGroups', [])

        self.logger.info(f"Total groups: {len(all_groups)}, Disabled groups: {disabled_groups}")

        # Filtere deaktivierte Gruppen aus
        group_names = sorted([name for name in all_groups.keys() if name not in disabled_groups and name != 'all'])

        self.logger.info(f"Processing {len(group_names)} active groups")

        if not group_names:
            self.logger.warning("No groups to process")
            return None

        # Ausgabe-Verzeichnis bestimmen
        if output_path:
            output_dir = os.path.dirname(output_path) or tempfile.gettempdir()
        else:
            output_dir = tempfile.gettempdir()

        # Hilfsfunktion für Dateinamen
        def safe_name(name: str) -> str:
            name = name or "group"
            return re.sub(r"[^A-Za-z0-9_\-]+", "_", name.strip())[:80]

        per_group_pdfs = []

        # COM für diesen Block initialisieren (einmal für alle Konvertierungen)
        pythoncom.CoInitialize()
        try:
            for group_name in group_names:
                self.logger.info(f"Creating PDF for group: {group_name}")
                group_doc = self._create_group_document(data, group_name, all_groups[group_name])

                # Speichern als DOCX (temporär) und als PDF (temporär)
                tmp_docx = os.path.join(tempfile.gettempdir(), f"code_review_{data.get('reviewNr')}_{safe_name(group_name)}.docx")
                tmp_pdf = os.path.join(tempfile.gettempdir(), f"code_review_{data.get('reviewNr')}_{safe_name(group_name)}.pdf")

                group_doc.save(tmp_docx)
                self.logger.info(f"Saved DOCX for group '{group_name}' to {tmp_docx}")

                self._convert_docx_to_pdf(tmp_docx, tmp_pdf)
                self.logger.info(f"Converted PDF for group '{group_name}' to {tmp_pdf}")

                per_group_pdfs.append(tmp_pdf)
        finally:
            pythoncom.CoUninitialize()

        # Merge alle PDFs zu einem großen PDF
        if len(per_group_pdfs) > 1:
            self.logger.info(f"Merging {len(per_group_pdfs)} PDFs into one")

            if not PdfWriter:
                self.logger.error("pypdf not available, cannot merge PDFs")
                # Fallback: gebe Liste zurück
                return per_group_pdfs

            merged_pdf_path = os.path.join(output_dir, f"Code_Review_{data.get('grouping', 'all')}_Review{data.get('reviewNr')}.pdf")

            try:
                merger = PdfWriter()

                for pdf_path in per_group_pdfs:
                    self.logger.info(f"Adding {pdf_path} to merger")
                    merger.append(pdf_path)

                # Schreibe merged PDF
                with open(merged_pdf_path, 'wb') as output_file:
                    merger.write(output_file)

                merger.close()
                self.logger.info(f"Successfully merged PDF saved to {merged_pdf_path}")

                # Lösche temporäre einzelne PDFs
                for pdf_path in per_group_pdfs:
                    try:
                        if os.path.exists(pdf_path):
                            os.remove(pdf_path)
                            self.logger.info(f"Deleted temporary PDF: {pdf_path}")
                    except Exception as e:
                        self.logger.warning(f"Could not delete temporary PDF {pdf_path}: {e}")

                return merged_pdf_path

            except Exception as e:
                self.logger.error(f"Error merging PDFs: {e}", exc_info=True)
                # Fallback: gebe Liste zurück
                return per_group_pdfs

        elif len(per_group_pdfs) == 1:
            # Nur ein PDF, gebe es direkt zurück
            single_pdf = per_group_pdfs[0]
            # Verschiebe zu finalem Pfad
            final_path = os.path.join(output_dir, f"Code_Review_{data.get('grouping', 'all')}_Review{data.get('reviewNr')}.pdf")
            if single_pdf != final_path:
                import shutil
                shutil.move(single_pdf, final_path)
                self.logger.info(f"Moved single PDF to {final_path}")
            return final_path

        else:
            self.logger.warning("No PDFs generated")
            return None

    def _cleanup_word_processes(self):
        """Beendet hängende Word-Prozesse (nur wenn nötig)."""
        try:
            import subprocess
            # Prüfe ob Word-Prozesse hängen
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq WINWORD.EXE'],
                                  capture_output=True, text=True, timeout=5)
            if 'WINWORD.EXE' in result.stdout:
                self.logger.warning("Found hanging WINWORD.EXE processes, cleaning up...")
                subprocess.run(['taskkill', '/F', '/IM', 'WINWORD.EXE'],
                             capture_output=True, timeout=5)
                import time
                time.sleep(1)
        except Exception as e:
            self.logger.warning(f"Could not cleanup Word processes: {e}")

    def _convert_docx_to_pdf(self, docx_path: str, pdf_path: str):
        """Konvertiert DOCX zu PDF mit docx2pdf/Word COM."""
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                self.logger.info(f"Converting DOCX to PDF (attempt {attempt + 1}/{max_retries}): {docx_path}")

                # Bei Wiederholungsversuchen: säubere Word-Prozesse
                if attempt > 0:
                    self._cleanup_word_processes()

                convert(docx_path, pdf_path)

                # Prüfe ob PDF erfolgreich erstellt wurde
                if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                    self.logger.info(f"PDF conversion successful: {pdf_path}")
                    return
                else:
                    raise Exception("PDF file not created or empty")

            except Exception as e:
                self.logger.warning(f"Conversion attempt {attempt + 1} failed: {e}")

                if attempt < max_retries - 1:
                    self.logger.info(f"Retrying in {retry_delay} seconds...")
                    import time
                    time.sleep(retry_delay)
                else:
                    self.logger.error(f"PDF conversion failed after {max_retries} attempts")
                    raise Exception(f"PDF-Konvertierung fehlgeschlagen nach {max_retries} Versuchen: {str(e)}")

    def _create_group_document(self, data, group_name, group_data):
        """
        Erstellt ein vollständig gefülltes Dokument für eine Gruppe

        Args:
            data: Basis-Daten
            group_name: Name der Gruppe
            group_data: Daten der Gruppe

        Returns:
            Document: Gefülltes Dokument
        """
        # Lade neues Template
        doc = Document(self.template_path)

        # Hole structured tables für diese Gruppe
        all_structured_tables = data.get('allStructuredTables', {})
        group_structured = all_structured_tables.get(group_name) if all_structured_tables else None

        group_specific_data = {
            'reviewNr': data.get('reviewNr'),
            'reviewDate': data.get('reviewDate'),
            'exportDate': data.get('exportDate', ''),
            'grouping': data.get('grouping'),
            'group': group_name,
            'groupData': group_data,
            'absentPersons': data.get('absentPersons', []),
            'week': data.get('week', 9),
            'maxWeeks': data.get('maxWeeks', 9),
            'structuredTables': group_structured
        }

        # Fülle das Dokument
        self._replace_placeholders_in_doc(doc, group_specific_data)
        self._fill_person_table_in_doc(doc, group_specific_data)

        return doc

    def _generate_single_group_pdf(self, data, output_path=None):
        """Generiert ein PDF für eine einzelne Gruppe"""
        self.logger.info("Generating single-group PDF")

        # Für Single-Group: structuredTables ist direkt in data
        # Erstelle ein vereinheitlichtes Data-Dict
        group_name = data.get('group')
        group_data = data.get('groupData')

        # Erstelle group_specific_data direkt hier
        group_specific_data = {
            'reviewNr': data.get('reviewNr'),
            'reviewDate': data.get('reviewDate'),
            'exportDate': data.get('exportDate', ''),
            'grouping': data.get('grouping'),
            'group': group_name,
            'groupData': group_data,
            'absentPersons': data.get('absentPersons', []),
            'week': data.get('week', 9),
            'maxWeeks': data.get('maxWeeks', 9),
            'structuredTables': data.get('structuredTables')  # Direkt aus data nehmen!
        }

        self.logger.info(f"Single-group PDF: structuredTables present: {group_specific_data['structuredTables'] is not None}")

        # Lade neues Template
        doc = Document(self.template_path)

        # Fülle das Dokument
        self._replace_placeholders_in_doc(doc, group_specific_data)
        self._fill_person_table_in_doc(doc, group_specific_data)

        # Speichere und konvertiere
        return self._save_and_convert(doc, data, output_path)

    def _save_and_convert(self, doc, data, output_path=None):
        """Speichert das Dokument und konvertiert es zu PDF (Word/docx2pdf)."""
        # Temporäre DOCX-Datei erstellen
        temp_dir = tempfile.gettempdir()
        temp_docx = os.path.join(temp_dir, f"code_review_{data.get('reviewNr')}.docx")
        doc.save(temp_docx)

        self.logger.info(f"Word document saved to: {temp_docx}")

        # PDF-Ausgabepfad
        if output_path is None:
            output_path = os.path.join(temp_dir, f"code_review_{data.get('reviewNr')}.pdf")

        # Konvertiere zu PDF via Word/docx2pdf mit COM-Init
        self.logger.info(f"Converting to PDF: {output_path}")
        pythoncom.CoInitialize()
        try:
            self._convert_docx_to_pdf(temp_docx, output_path)
        finally:
            pythoncom.CoUninitialize()

        self.logger.info(f"PDF generated successfully: {output_path}")
        return output_path

    def _extract_export_date_from_filename(self, export_date_path):
        """
        Extrahiert Datum und Uhrzeit aus dem Export-Dateinamen

        Args:
            export_date_path: Pfad zur Export-Datei (z.B. "output_20241014_150823.json")

        Returns:
            str: Formatiertes Datum (z.B. "14.10.2024 15:08") oder "Unbekannt"
        """
        if not export_date_path:
            return "Unbekannt"

        try:
            # Extrahiere Dateinamen aus dem Pfad
            filename = os.path.basename(export_date_path)

            # Regex-Pattern: output_YYYYMMDD_HHMMSS.json
            pattern = r'output_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})'
            match = re.search(pattern, filename)

            if match:
                year, month, day, hour, minute, second = match.groups()
                # Format: DD.MM.YYYY HH:MM
                formatted_date = f"{day}.{month}.{year} {hour}:{minute}"
                self.logger.info(f"Extracted export date from filename: {formatted_date}")
                return formatted_date
            else:
                self.logger.warning(f"Could not extract date from filename: {filename}")
                return "Unbekannt"

        except Exception as e:
            self.logger.error(f"Error extracting export date: {e}")
            return "Unbekannt"

    def _replace_placeholders_in_doc(self, doc, data):
        """
        Ersetzt Platzhalter im Word-Dokument mit Daten

        Args:
            doc: Document-Objekt
            data: Dictionary mit Daten
        """
        group_data = data.get('groupData')
        structured_tables = data.get('structuredTables')
        current_week = data.get('week', 9)

        # Extrahiere ExportDate aus Dateiname
        export_date_path = data.get('exportDate', '')
        formatted_export_date = self._extract_export_date_from_filename(export_date_path)

        # Berechne Gruppenprogress für diese Woche
        group_progress = 0.0
        if group_data and isinstance(group_data, dict):
            users = group_data.get('users', [])
            if users and structured_tables:
                total_progress = 0
                for user in users:
                    user_name = user.get('name')
                    user_progress = self._calculate_user_progress(user_name, structured_tables, current_week, data.get('maxWeeks', 9))
                    total_progress += user_progress

                if len(users) > 0:
                    group_progress = round((total_progress / len(users)) * 10) / 10

                self.logger.info(f"Group '{data.get('group')}': total_progress={total_progress:.1f}, users={len(users)}, avg={group_progress:.1f}%")

        # Erstelle Abwesend-Liste - NUR PERSONEN DIESER GRUPPE
        absent_persons = data.get('absentPersons', [])
        current_group = data.get('group', '')

        # Hole alle Personennamen dieser Gruppe
        group_user_names = []
        if group_data and isinstance(group_data, dict):
            users = group_data.get('users', [])
            group_user_names = [user.get('name') for user in users]

        # Filtere nur abwesende Personen, die auch in dieser Gruppe sind
        group_absent_persons = [name for name in absent_persons if name in group_user_names]

        absent_text = '\n'.join(group_absent_persons) if group_absent_persons else '-'

        # Prüfe ob Gruppierung bereits im Gruppennamen enthalten ist
        # Wenn ja, zeige Gruppierung nicht separat an
        display_grouping = ''
        grouping_name = data.get('grouping', '')
        group_name = data.get('group', '')
        if grouping_name and grouping_name != 'all':
            if grouping_name not in group_name:
                display_grouping = grouping_name

        # Platzhalter-Ersetzungen
        replacements = {
            '{Review-Nr}': str(data.get('reviewNr', '')),
            '{Datum}': data.get('reviewDate', ''),
            '{Gruppierung}': display_grouping,
            '{Gruppe}': data.get('group', ''),
            '{Abwesend}': absent_text,
            '{Durchschnitt}': f"{group_progress:.1f}%",
            '{ExportDate}': formatted_export_date,
            '{ReferenceWeek}': str(current_week)
        }

        # Robuste Ersetzung: funktioniert auch wenn Platzhalter über mehrere Runs verteilt ist
        total_replacements = 0

        def replace_in_paragraph(paragraph):
            nonlocal total_replacements
            original_text = paragraph.text or ''
            new_text = original_text
            replaced_something = False
            for placeholder, value in replacements.items():
                if placeholder in new_text:
                    new_text = new_text.replace(placeholder, value)
                    replaced_something = True
            if replaced_something and new_text != original_text:
                # Alle Runs leeren und gesamten Text in den ersten Run schreiben
                if paragraph.runs:
                    for run in paragraph.runs:
                        run.text = ''
                    paragraph.runs[0].text = new_text
                else:
                    paragraph.add_run(new_text)
                total_replacements += 1

        def replace_in_table(table):
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        replace_in_paragraph(p)
                    for nested_table in cell.tables:
                        replace_in_table(nested_table)

        # Ersetzen im Dokument-Körper
        for p in doc.paragraphs:
            replace_in_paragraph(p)
        for t in doc.tables:
            replace_in_table(t)

        # Ersetzen in Headern/Footern aller Sektionen
        for section in doc.sections:
            header = section.header
            if header:
                for p in header.paragraphs:
                    replace_in_paragraph(p)
                for t in header.tables:
                    replace_in_table(t)
            footer = section.footer
            if footer:
                for p in footer.paragraphs:
                    replace_in_paragraph(p)
                for t in footer.tables:
                    replace_in_table(t)

        self.logger.info(f"Placeholder replacement done. Paragraphs updated: {total_replacements}")

    def _calculate_user_progress(self, user_name, structured_tables, current_week, max_weeks):
        """
        Berechnet den Fortschritt eines Benutzers

        Args:
            user_name: Name des Benutzers
            structured_tables: Strukturierte Tabellendaten
            current_week: Aktuelle Woche
            max_weeks: Maximale Wochen

        Returns:
            float: Fortschritt in Prozent
        """
        if not structured_tables:
            self.logger.warning(f"No structured_tables provided for user '{user_name}'")
            return 0.0

        # Hole Checklisten-Tabelle
        checklists_data = structured_tables.get('checklists', {})
        rows = checklists_data.get('rows', [])

        if not rows:
            self.logger.warning(f"No checklist rows found for user '{user_name}'")
            return 0.0

        # Finde User-Index in den Headers
        headers = checklists_data.get('headers', [])
        self.logger.info(f"Checklist headers: {headers}")

        if 'Checkliste' in headers:
            headers = headers[1:]  # Überspringe erste Spalte ('Checkliste')
            self.logger.info(f"Headers after removing 'Checkliste': {headers}")

        if user_name not in headers:
            self.logger.warning(f"User '{user_name}' not found in headers: {headers}")
            return 0.0

        user_index = headers.index(user_name)
        self.logger.info(f"User '{user_name}' found at index {user_index}")

        # Berechne Fortschritt nur für Pflicht-Checklisten
        total_mandatory_checklists = sum(1 for row in rows if row.get('is_mandatory', False))

        if total_mandatory_checklists == 0:
            self.logger.warning("No mandatory checklists found")
            return 0.0

        total_pflicht_percent = 0

        for row in rows:
            # Überspringe nicht-Pflicht Checklisten
            if not row.get('is_mandatory', False):
                continue

            # Hole User-Progress (wie im Frontend!)
            user_progress_list = row.get('user_progress', [])
            # user_index ist der Header-Index, user_progress ist 0-basiert
            if user_index < len(user_progress_list):
                progress_data = user_progress_list[user_index]
                # Hole required_progress (als String mit %)
                progress_str = progress_data.get('required_progress', '0%')
                try:
                    # Entferne % und konvertiere
                    progress_val = float(progress_str.replace('%', '').strip())
                    total_pflicht_percent += progress_val
                except (ValueError, AttributeError):
                    pass

        # Berechne erwartete Punkte für diese Woche
        expected_pflicht_points = (total_mandatory_checklists * 100 / max_weeks) * current_week

        if expected_pflicht_points == 0:
            return 0.0

        # Berechne Prozent
        progress = (total_pflicht_percent / expected_pflicht_points) * 100
        progress = round(progress * 10) / 10  # Runde auf 1 Nachkommastelle

        self.logger.info(f"User '{user_name}': mandatory={total_mandatory_checklists}, total%={total_pflicht_percent}, expected={expected_pflicht_points:.1f}, progress={progress:.1f}%")

        return progress

    def _fill_person_table_in_doc(self, doc, data):
        """
        Füllt die Personentabelle mit Daten - verwendet Template-Zeile mit {Person} und {Progress %}

        Args:
            doc: Document-Objekt
            data: Dictionary mit Daten
        """
        group_data = data.get('groupData')
        structured_tables = data.get('structuredTables')
        current_week = data.get('week', 9)
        max_weeks = data.get('maxWeeks', 9)
        absent_persons = data.get('absentPersons', [])
        current_group = data.get('group', '')

        if not group_data:
            self.logger.warning("No group data available")
            return

        # Versuche users zu finden
        users = None
        if isinstance(group_data, dict):
            users = group_data.get('users')

        if not users:
            self.logger.warning("No users found in group data")
            return

        # Filtere abwesende Personen aus - NUR DIE, DIE ZUR AKTUELLEN GRUPPE GEHÖREN
        # Hole alle Personennamen dieser Gruppe
        group_user_names = [user.get('name') for user in users]

        # Filtere nur abwesende Personen, die auch in dieser Gruppe sind
        group_absent_persons = [name for name in absent_persons if name in group_user_names]

        # Filtere abwesende Personen aus der User-Liste
        present_users = [user for user in users if user.get('name') not in group_absent_persons]

        self.logger.info(f"Processing {len(present_users)} present users (total: {len(users)}, absent: {len(group_absent_persons)}) for group {current_group}, week={current_week}")

        # Finde die Tabelle mit der Template-Zeile
        if not doc.tables:
            self.logger.warning("No tables found in document")
            return

        # Suche nach Tabelle mit {Person} Platzhalter
        table = None
        template_row = None
        template_row_index = None

        for tbl in doc.tables:
            for idx, row in enumerate(tbl.rows):
                row_text = ''.join(cell.text for cell in row.cells)
                if '{Person}' in row_text or '{Progress %}' in row_text:
                    table = tbl
                    template_row = row
                    template_row_index = idx
                    self.logger.info(f"Found template row at index {idx}")
                    break
            if template_row:
                break

        if not template_row:
            self.logger.warning("No template row with {Person} or {Progress %} found")
            return

        # Erstelle Zeilen für anwesende Personen
        for user in present_users:
            person_name = user.get('name')

            # Berechne Progress
            progress = self._calculate_user_progress(person_name, structured_tables, current_week, max_weeks)

            # Füge neue Zeile hinzu
            new_row = table.add_row()
            new_row.height = Cm(2.5)

            # Kopiere Formatierung und ersetze Platzhalter
            for j, cell in enumerate(template_row.cells):
                cell_text = cell.text
                # Ersetze Platzhalter
                cell_text = cell_text.replace('{Person}', person_name)
                cell_text = cell_text.replace('{Progress %}', f'{progress:.1f}%')

                # Setze Text
                new_row.cells[j].text = cell_text

                # Kopiere Formatierung
                for paragraph_idx, src_paragraph in enumerate(cell.paragraphs):
                    if paragraph_idx < len(new_row.cells[j].paragraphs):
                        dest_paragraph = new_row.cells[j].paragraphs[paragraph_idx]
                        for src_run, dest_run in zip(src_paragraph.runs, dest_paragraph.runs):
                            dest_run.font.name = src_run.font.name
                            dest_run.font.size = src_run.font.size
                            dest_run.font.bold = src_run.font.bold
                            dest_run.font.italic = src_run.font.italic

        # Entferne Template-Zeile
        table._element.remove(template_row._element)
        self.logger.info(f"Removed template row, added {len(present_users)} person rows")
