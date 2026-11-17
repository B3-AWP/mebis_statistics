"""
Der Schülerbericht darf einen unbekannten Stand nicht als "nicht abgegeben"
ausweisen — die PDFs gehen an Lernende.

    python -X utf8 -m unittest tests.test_report_unbekannt
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.export.pruefung import unbekannter_status  # noqa: E402

try:
    from src.report.report_generator import ReportGenerator
except ImportError:  # ReportLab fehlt
    ReportGenerator = None


@unittest.skipIf(ReportGenerator is None, 'report_generator nicht importierbar')
class TestBerichtUnbekannt(unittest.TestCase):

    def setUp(self):
        # Nur die reinen Hilfsmethoden werden gebraucht — ohne __init__,
        # das Exportordner und Ausschlussliste liest.
        self.rg = ReportGenerator.__new__(ReportGenerator)
        self.unbekannt = unbekannter_status('4', 'Bewertungstabelle nicht gefunden')

    def test_schema_3_wird_gelesen(self):
        flach = self.rg._flatten_export({'schema': 3, 'kurse': {}, 'groups': []}, 'x.json')
        self.assertEqual(flach['groups'], [])

    def test_schema_2_wird_abgelehnt(self):
        with self.assertRaises(ValueError):
            self.rg._flatten_export({'schema': 2}, 'alt.json')

    def test_quiz_unbekannt_ist_nicht_abgegeben_aber_benannt(self):
        self.assertFalse(self.rg._is_quiz_submitted(self.unbekannt))
        self.assertEqual(self.rg._fehlt_text(self.unbekannt), 'Stand unbekannt')
        self.assertEqual(self.rg._fehlt_text(None), 'nicht abgegeben')
        self.assertEqual(self.rg._fehlt_text({'status': 'Nicht eingereicht'}), 'nicht abgegeben')

    def test_extract_student_grade(self):
        acts = {'quizzes': [{'id': 'q', 'status': self.unbekannt}],
                'assignments': [{'id': 'a', 'status': self.unbekannt}]}
        self.assertEqual(self.rg._extract_student_grade(acts, {'type': 'quiz', 'ids': ['q']}),
                         ('Stand unbekannt', None))
        self.assertEqual(self.rg._extract_student_grade(acts, {'type': 'assignment', 'ids': ['a']}),
                         ('Stand unbekannt', None))


if __name__ == '__main__':
    unittest.main()
