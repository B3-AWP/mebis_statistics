#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests für src/common/plan_loader.py

Die Sollwerte in TestGegenJsReferenz stammen aus einem Lauf der
JS-Implementierung des Schüler-Dashboards (js/bilanz.js) gegen dieselbe
plan.json. Sie sind die Absicherung dagegen, dass die beiden Dashboards
unbemerkt auseinanderlaufen — Python und JS müssen dieselbe Zahl liefern.
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.plan_loader import (  # noqa: E402
    PlanFehler,
    aktuelle_woche,
    begrenze_schulwochen,
    ist_im_block,
    pruefe_plan,
    soll_anteil,
    verteile_unterrichtsstunden,
)


def minimal_plan(**overrides):
    """Kleinster gültiger Plan, für Validierungstests."""
    plan = {
        'schemaVersion': 3,
        'schuljahr': '2026/27',
        'skalen': {
            'sterne4': {
                'titel': 'Bewertungsskala',
                'stufen': [
                    {'wert': 1, 'name': 'Nicht akzeptabel', 'prozent': 20},
                    {'wert': 4, 'name': 'Exzellent', 'prozent': 100},
                ],
            }
        },
        'notenschluessel': [
            {'note': 1, 'name': 'sehr gut', 'abProzent': 92},
            {'note': 4, 'name': 'ausreichend', 'abProzent': 50},
            {'note': 6, 'name': 'ungenügend', 'abProzent': 0},
        ],
        'klassenZuSchiene': {'IFA12A': 'Schiene1'},
        'schienen': {
            'Schiene1': {
                'titel': 'Schiene 1',
                'schulwochen': [
                    {'woche': 1, 'start': '2026-09-28', 'ende': '2026-10-02', 'stunden': 10},
                    {'woche': 2, 'start': '2026-10-05', 'ende': '2026-10-09', 'stunden': 14},
                ],
            }
        },
        'kurse': [
            {
                'id': 'halbjahr-1',
                'moodleCourseId': '2491549',
                'titel': '1. Halbjahr',
                'gesperrt': False,
                'anzeigen': True,
                'aufgaben': [
                    {'cmid': '111', 'typ': 'assign', 'titel': 'A', 'lektion': 'L',
                     'stunden': 10.0, 'skala': 'sterne4'},
                    {'cmid': '222', 'typ': 'quiz', 'titel': 'Q', 'lektion': 'L',
                     'stunden': 2.0},
                ],
            }
        ],
    }
    plan.update(overrides)
    return plan


class TestValidierung(unittest.TestCase):

    def test_gueltiger_plan(self):
        plan = pruefe_plan(minimal_plan())
        self.assertEqual(plan.schuljahr, '2026/27')
        self.assertEqual(plan.stunden_gesamt, 12.0)
        self.assertEqual(len(plan.kurse), 1)

    def test_falsche_schemaversion(self):
        with self.assertRaises(PlanFehler) as ctx:
            pruefe_plan(minimal_plan(schemaVersion=2))
        self.assertTrue(any('schemaVersion' in m for m in ctx.exception.meldungen))

    def test_doppelte_cmid(self):
        p = minimal_plan()
        p['kurse'][0]['aufgaben'][1]['cmid'] = '111'
        with self.assertRaises(PlanFehler) as ctx:
            pruefe_plan(p)
        self.assertTrue(any('mehrfach' in m for m in ctx.exception.meldungen))

    def test_unbekannter_typ(self):
        p = minimal_plan()
        p['kurse'][0]['aufgaben'][0]['typ'] = 'forum'
        with self.assertRaises(PlanFehler) as ctx:
            pruefe_plan(p)
        self.assertTrue(any('typ' in m for m in ctx.exception.meldungen))

    def test_stunden_null_ist_fehler(self):
        p = minimal_plan()
        p['kurse'][0]['aufgaben'][0]['stunden'] = 0
        with self.assertRaises(PlanFehler):
            pruefe_plan(p)

    def test_unbekannte_schiene_in_klassenzuordnung(self):
        p = minimal_plan(klassenZuSchiene={'IFA12A': 'SchieneX'})
        with self.assertRaises(PlanFehler) as ctx:
            pruefe_plan(p)
        self.assertTrue(any('SchieneX' in m for m in ctx.exception.meldungen))


class TestPflichtaufgaben(unittest.TestCase):
    """Der Plan bestimmt, was Pflichtaufgabe ist — nicht der Kategoriename."""

    def setUp(self):
        self.plan = pruefe_plan(minimal_plan())

    def test_cmid_im_plan_ist_pflichtaufgabe(self):
        self.assertTrue(self.plan.ist_pflichtaufgabe('111'))
        self.assertEqual(self.plan.get_stunden('111'), 10.0)

    def test_cmid_nicht_im_plan(self):
        self.assertFalse(self.plan.ist_pflichtaufgabe('999'))
        self.assertEqual(self.plan.get_stunden('999'), 0.0)

    def test_cmid_als_zahl_und_mit_leerzeichen(self):
        self.assertTrue(self.plan.ist_pflichtaufgabe(111))
        self.assertTrue(self.plan.ist_pflichtaufgabe(' 111 '))


class TestNoten(unittest.TestCase):

    def setUp(self):
        self.plan = pruefe_plan(minimal_plan())

    def test_percent_to_grade(self):
        self.assertEqual(self.plan.percent_to_grade(100), 1)
        self.assertEqual(self.plan.percent_to_grade(92), 1)
        self.assertEqual(self.plan.percent_to_grade(91), 4)
        self.assertEqual(self.plan.percent_to_grade(0), 6)
        self.assertIsNone(self.plan.percent_to_grade(None))

    def test_skala_to_percent(self):
        self.assertEqual(self.plan.skala_to_percent('sterne4', '**** Exzellent'), 100)
        self.assertEqual(self.plan.skala_to_percent('sterne4', 'Exzellent'), 100)
        self.assertIsNone(self.plan.skala_to_percent('sterne4', 'Unbekannt'))


class TestSchienen(unittest.TestCase):

    def setUp(self):
        self.plan = pruefe_plan(minimal_plan())

    def test_exakter_treffer(self):
        self.assertEqual(self.plan.get_track_for_class('IFA12A'), 'Schiene1')

    def test_praefix_treffer_fuer_altnamen(self):
        self.assertEqual(self.plan.get_track_for_class('IFA12A - Team 1'), 'Schiene1')

    def test_unbekannte_klasse(self):
        self.assertIsNone(self.plan.get_track_for_class('IFA12Z'))
        self.assertIsNone(self.plan.get_track_for_class(''))


class TestWochenrechnung(unittest.TestCase):

    def setUp(self):
        self.wochen = pruefe_plan(minimal_plan()).get_schulwochen('Schiene1')

    def test_vor_beginn_ist_woche_null(self):
        self.assertEqual(aktuelle_woche(self.wochen, date(2026, 9, 1)), 0)

    def test_innerhalb_block(self):
        self.assertEqual(aktuelle_woche(self.wochen, date(2026, 9, 30)), 1)

    def test_zwischen_bloecken_gilt_letzter(self):
        self.assertEqual(aktuelle_woche(self.wochen, date(2026, 10, 3)), 1)

    def test_nach_letztem_block(self):
        self.assertEqual(aktuelle_woche(self.wochen, date(2027, 6, 1)), 2)

    def test_soll_anteil_gewichtet_nach_stunden(self):
        # Woche 1 hat 10 von 24 Stunden — nicht 1/2.
        self.assertAlmostEqual(soll_anteil(self.wochen, 1), 10 / 24, places=6)
        self.assertAlmostEqual(soll_anteil(self.wochen, 2), 1.0, places=6)
        self.assertEqual(soll_anteil(self.wochen, 0), 0.0)

    def test_ist_im_block(self):
        self.assertTrue(ist_im_block(self.wochen, 1, date(2026, 9, 30)))
        self.assertFalse(ist_im_block(self.wochen, 1, date(2026, 10, 3)))


class TestGegenJsReferenz(unittest.TestCase):
    """
    Abgleich mit der echten plan.json und den Werten aus js/bilanz.js.

    Wird übersprungen, wenn die Planungsdatei nicht erreichbar ist (z.B. CI
    ohne das Nachbar-Repo).
    """

    @classmethod
    def setUpClass(cls):
        from config.config_manager import config_manager
        from src.common.plan_loader import lade_plan
        pfad = config_manager.get_plan_json_path()
        if not os.path.exists(pfad):
            raise unittest.SkipTest(f'plan.json nicht gefunden: {pfad}')
        cls.plan = lade_plan(pfad)
        cls.wochen = cls.plan.get_schulwochen('Schiene1')

    def test_stunden_gesamt(self):
        self.assertAlmostEqual(self.plan.stunden_gesamt, 93.75, places=2)

    def test_kursstunden(self):
        self.assertAlmostEqual(self.plan.get_kurs('halbjahr-1')['stundenGeplant'], 58.5, places=2)
        self.assertAlmostEqual(self.plan.get_kurs('halbjahr-2')['stundenGeplant'], 35.25, places=2)

    def test_aktuelle_woche(self):
        self.assertEqual(aktuelle_woche(self.wochen, date(2026, 9, 18)), 0)
        self.assertEqual(aktuelle_woche(self.wochen, date(2026, 10, 6)), 2)
        self.assertEqual(aktuelle_woche(self.wochen, date(2027, 4, 20)), 9)

    def test_soll_anteil(self):
        for woche, erwartet in [(0, 0.0), (1, 0.0820), (2, 0.1967),
                                (5, 0.5410), (9, 1.0)]:
            with self.subTest(woche=woche):
                self.assertAlmostEqual(soll_anteil(self.wochen, woche), erwartet, places=4)

    def test_verteile_unterrichtsstunden(self):
        verteilung = verteile_unterrichtsstunden(self.plan.kurse, self.wochen)
        self.assertAlmostEqual(verteilung['halbjahr-1'], 66.0, places=2)
        self.assertAlmostEqual(verteilung['halbjahr-2'], 56.0, places=2)

    def test_begrenze_schulwochen_auf_sichtbare_kurse(self):
        sichtbar = self.plan.get_kurse(nur_sichtbare=True)
        begrenzt = begrenze_schulwochen(self.wochen, sichtbar, self.plan.kurse)
        self.assertEqual(len(begrenzt), 5)
        self.assertAlmostEqual(sum(w['stunden'] for w in begrenzt), 66.0, places=2)

    def test_zweites_halbjahr_ist_gesperrt(self):
        """Solange das gilt, ist nur ein Kurs scrapebar — siehe Plan, AP 2."""
        offen = self.plan.get_kurse(nur_offene=True)
        self.assertEqual([k['id'] for k in offen], ['halbjahr-1'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
