"""
Prueft das Umschreiben der Aktivitaets-Titel auf die Planstunden.

Im Moodle-Titel steht die Bearbeitungszeit der Aktivitaet ("20 Min"),
gerechnet wird aber mit den in plan.json hinterlegten Unterrichtsstunden.
Die Anzeige soll die Zahl nennen, die auch die Quantitaet bestimmt.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.dashboard.backend import (  # noqa: E402
    titel_mit_planstunden,
    _titel_auf_planstunden_umstellen,
)


PLAN_STUNDEN = {'1': 3.0, '2': 2.5, '3': 10.0}


class TestTitelMitPlanstunden(unittest.TestCase):

    def test_minuten_am_ende_werden_ersetzt(self):
        self.assertEqual(
            titel_mit_planstunden('Quiz CSS Grundlagen (10 Min.)', '1', PLAN_STUNDEN),
            'Quiz CSS Grundlagen (3 Std.)')
        self.assertEqual(
            titel_mit_planstunden('Quiz HTML Grundlagen (20 Min)', '1', PLAN_STUNDEN),
            'Quiz HTML Grundlagen (3 Std.)')

    def test_stundenangabe_und_spanne_werden_ersetzt(self):
        self.assertEqual(
            titel_mit_planstunden('Situation Mitarbeiterverwaltung (2-3 Std)', '3', PLAN_STUNDEN),
            'Situation Mitarbeiterverwaltung (10 Std.)')

    def test_ungefaehre_angaben(self):
        for roh in ('Quiz (ca. 45 Minuten)', 'Quiz (~45 Min)', 'Quiz (etwa 45 min)'):
            self.assertEqual(titel_mit_planstunden(roh, '2', PLAN_STUNDEN),
                             'Quiz (2,5 Std.)', roh)

    def test_zeit_in_klammer_mit_weiterem_text(self):
        """Nur die Zeit faellt weg, der uebrige Klammerinhalt bleibt."""
        self.assertEqual(
            titel_mit_planstunden('OOP - SOLID (Lernzielkontrolle, ~25 Min)', '3', PLAN_STUNDEN),
            'OOP - SOLID (Lernzielkontrolle) (10 Std.)')

    def test_titel_ohne_zeitangabe_bekommt_planstunden(self):
        self.assertEqual(
            titel_mit_planstunden('SD Kontobewegung', '1', PLAN_STUNDEN),
            'SD Kontobewegung (3 Std.)')

    def test_klammer_ohne_zeit_bleibt_erhalten(self):
        self.assertEqual(
            titel_mit_planstunden('Aufgabe (Gruppenarbeit)', '1', PLAN_STUNDEN),
            'Aufgabe (Gruppenarbeit) (3 Std.)')

    def test_halbe_stunden_deutsch_geschrieben(self):
        self.assertEqual(titel_mit_planstunden('Quiz (20 Min)', '2', PLAN_STUNDEN),
                         'Quiz (2,5 Std.)')

    def test_aufgabe_ohne_planeintrag_bleibt_unveraendert(self):
        """Keine Pflichtaufgabe — dort gibt es keine Planstunden."""
        self.assertEqual(
            titel_mit_planstunden('Uebung Car Sharing (25 Min)', '999', PLAN_STUNDEN),
            'Uebung Car Sharing (25 Min)')

    def test_leerer_titel(self):
        self.assertIsNone(titel_mit_planstunden(None, '1', PLAN_STUNDEN))
        self.assertEqual(titel_mit_planstunden('', '1', PLAN_STUNDEN), '')

    def test_idempotent(self):
        """Mehrfaches Anwenden darf die Stundenzahl nicht anhaengen."""
        einmal = titel_mit_planstunden('Quiz CSS (10 Min.)', '1', PLAN_STUNDEN)
        zweimal = titel_mit_planstunden(einmal, '1', PLAN_STUNDEN)
        self.assertEqual(einmal, zweimal)


class TestKategorienUmstellen(unittest.TestCase):

    def test_alle_aktivitaetsarten_werden_umgestellt(self):
        kategorien = [{
            'category_name': 'Pflichtaufgaben',
            'assignments': [{'id': '1', 'title': 'Skizze (20 Min)'}],
            'quizzes': [{'id': '2', 'title': 'Quiz (10 Min)'}],
            'checklists': [{'id': '3', 'title': 'Liste (5 Min)'}],
            'feedbacks': [{'id': '999', 'title': 'Feedback (5 Min)'}],
        }]
        _titel_auf_planstunden_umstellen(kategorien, PLAN_STUNDEN)
        k = kategorien[0]
        self.assertEqual(k['assignments'][0]['title'], 'Skizze (3 Std.)')
        self.assertEqual(k['quizzes'][0]['title'], 'Quiz (2,5 Std.)')
        self.assertEqual(k['checklists'][0]['title'], 'Liste (10 Std.)')
        # Nicht im Plan: bleibt, wie Moodle es liefert
        self.assertEqual(k['feedbacks'][0]['title'], 'Feedback (5 Min)')

    def test_ohne_planstunden_bleibt_alles_stehen(self):
        kategorien = [{'assignments': [{'id': '1', 'title': 'Skizze (20 Min)'}]}]
        _titel_auf_planstunden_umstellen(kategorien, {})
        self.assertEqual(kategorien[0]['assignments'][0]['title'], 'Skizze (20 Min)')


if __name__ == '__main__':
    unittest.main(verbosity=2)
