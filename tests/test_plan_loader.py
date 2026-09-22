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

from src.common.group_utils import extract_group_prefix  # noqa: E402
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
        'schemaVersion': 4,
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
            pruefe_plan(minimal_plan(schemaVersion=3))
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
    """
    Die Gruppennamen kommen je nach Kursanlage in sehr unterschiedlicher
    Form aus Moodle. Der Kurs 2026/27 liefert "K - IFA12A (6072)" — eine
    Praefix-Regel ergaebe dort "K" fuer jede Klasse.
    """

    def setUp(self):
        self.plan = pruefe_plan(minimal_plan())

    def test_exakter_treffer(self):
        self.assertEqual(self.plan.get_track_for_class('IFA12A'), 'Schiene1')

    def test_moodle_format_2026_27(self):
        self.assertEqual(self.plan.get_track_for_class('K - IFA12A (6072)'), 'Schiene1')

    def test_praefix_treffer_fuer_altnamen(self):
        self.assertEqual(self.plan.get_track_for_class('IFA12A - Team 1'), 'Schiene1')

    def test_unbekannte_klasse(self):
        self.assertIsNone(self.plan.get_track_for_class('IFA12Z'))
        self.assertIsNone(self.plan.get_track_for_class(''))

    def test_fremde_klassen_werden_ausgesteuert(self):
        """Im Kurs liegen auch Klassen, die nicht im Plan stehen."""
        for name in ['K - IF11J (6072)', 'K - IF10B (6072)', 'Testgruppe', 'IT_Lehrkraft']:
            with self.subTest(name=name):
                self.assertIsNone(self.plan.get_track_for_class(name))


class TestStundenraster(unittest.TestCase):
    """
    Das Raster teilt eine laufende Blockwoche tagesgenau. Es ist optional:
    ohne Eintrag zaehlt die angebrochene Woche wie bisher ganz.
    """

    RASTER = {'RasterAB': {'mo': 2, 'di': 5, 'mi': 2, 'do': 3, 'fr': 2}}

    def _plan(self, **overrides):
        basis = {
            'stundenraster': self.RASTER,
            'klassenZuRaster': {'IFA12A': 'RasterAB'},
        }
        basis.update(overrides)
        return pruefe_plan(minimal_plan(**basis))

    def test_raster_zu_klasse(self):
        plan = self._plan()
        self.assertEqual(plan.get_raster_for_class('IFA12A')['di'], 5)

    def test_raster_nimmt_moodle_gruppennamen(self):
        # Wie get_track_for_class: das Kuerzel wird per Muster gezogen.
        plan = self._plan()
        self.assertEqual(plan.get_raster_for_class('K - IFA12A (6072)')['di'], 5)

    def test_klasse_ohne_raster(self):
        self.assertIsNone(self._plan().get_raster_for_class('IFA12Z'))

    def test_raster_ist_optional(self):
        # Ein Plan ohne die Felder bleibt gueltig — nur ohne Tagesgenauigkeit.
        plan = pruefe_plan(minimal_plan())
        self.assertEqual(plan.stundenraster, {})
        self.assertIsNone(plan.get_raster_for_class('IFA12A'))

    def test_unbekanntes_raster_wird_abgelehnt(self):
        with self.assertRaises(PlanFehler) as ctx:
            self._plan(klassenZuRaster={'IFA12A': 'Tippfehler'})
        self.assertTrue(any('Tippfehler' in m for m in ctx.exception.meldungen))

    def test_negative_stunden_werden_abgelehnt(self):
        with self.assertRaises(PlanFehler) as ctx:
            self._plan(stundenraster={'RasterAB': {'mo': -1, 'di': 5}})
        self.assertTrue(any('mo' in m for m in ctx.exception.meldungen))

    def test_leeres_raster_wird_abgelehnt(self):
        # Summe 0 koennte das Soll auf null ziehen.
        with self.assertRaises(PlanFehler) as ctx:
            self._plan(stundenraster={'RasterAB': {'mo': 0, 'di': 0, 'mi': 0,
                                                   'do': 0, 'fr': 0}})
        self.assertTrue(any('0 Stunden' in m for m in ctx.exception.meldungen))

    def test_raster_wandert_ins_frontend(self):
        d = self._plan().to_dict()
        self.assertEqual(d['stundenraster']['RasterAB']['di'], 5)
        self.assertEqual(d['klassen_zu_raster']['IFA12A'], 'RasterAB')


class TestKlassenkuerzel(unittest.TestCase):
    """extract_group_prefix gegen die real vorkommenden Namensformen."""

    def test_moodle_2026_27(self):
        self.assertEqual(extract_group_prefix('K - IFA12A (6072)'), 'IFA12A')
        self.assertEqual(extract_group_prefix('K - IF11J (6072)'), 'IF11J')

    def test_altformat_mit_team(self):
        self.assertEqual(extract_group_prefix('IFA12A - Team 3'), 'IFA12A')

    def test_blanker_name(self):
        self.assertEqual(extract_group_prefix('IFA12A'), 'IFA12A')

    def test_ohne_klassenkuerzel(self):
        self.assertEqual(extract_group_prefix('Testgruppe'), 'Testgruppe')
        self.assertEqual(extract_group_prefix('IT_Lehrkraft'), 'IT_Lehrkraft')
        self.assertEqual(extract_group_prefix(''), '')


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

    def test_soll_anteil_ohne_raster_unveraendert(self):
        # Das Raster ist optional; ohne es bleibt jede Woche ganz gezaehlt,
        # auch wenn ein Stichtag mitten im Block liegt.
        for w in range(0, 3):
            self.assertAlmostEqual(
                soll_anteil(self.wochen, w),
                soll_anteil(self.wochen, w, None, date(2026, 10, 6)),
                places=9,
            )

    def test_soll_anteil_teilt_laufende_woche_tagesgenau(self):
        # Woche 2 (Mo 05.10.-Fr 09.10.) hat 14 Stunden, Raster 2/3/2/5/2.
        # Am Dienstag sind 5 von 14 gehalten: 10 + 5 = 15 von 24.
        raster = {'mo': 2, 'di': 3, 'mi': 2, 'do': 5, 'fr': 2}
        self.assertAlmostEqual(
            soll_anteil(self.wochen, 2, raster, date(2026, 10, 6)), 15 / 24, places=6
        )
        # Montag: nur 2 von 14 gehalten.
        self.assertAlmostEqual(
            soll_anteil(self.wochen, 2, raster, date(2026, 10, 5)), 12 / 24, places=6
        )
        # Am letzten Tag zaehlt die Woche wieder ganz.
        self.assertAlmostEqual(
            soll_anteil(self.wochen, 2, raster, date(2026, 10, 9)), 1.0, places=6
        )

    def test_soll_anteil_raster_skaliert_auf_wochensumme(self):
        # Woche 1 hat nur 10 statt 14 Stunden. Das Raster gibt die Form,
        # die Wochensumme die Hoehe — am Ende der Woche exakt 10 Stunden,
        # nie die 14 des Rasters.
        raster = {'mo': 2, 'di': 3, 'mi': 2, 'do': 5, 'fr': 2}
        gesamt = sum(w['stunden'] for w in self.wochen)
        self.assertAlmostEqual(
            soll_anteil(self.wochen, 1, raster, date(2026, 10, 2)) * gesamt, 10.0,
            places=6,
        )
        # Mittwoch: (2+3+2)/14 * 10 Stunden.
        self.assertAlmostEqual(
            soll_anteil(self.wochen, 1, raster, date(2026, 9, 30)) * gesamt,
            7 / 14 * 10, places=6,
        )

    def test_soll_anteil_vor_blockbeginn_zaehlt_woche_nicht(self):
        raster = {'mo': 2, 'di': 3, 'mi': 2, 'do': 5, 'fr': 2}
        # Stichtag vor Woche 2, aber Woche 2 abgefragt: nur Woche 1 zaehlt.
        self.assertAlmostEqual(
            soll_anteil(self.wochen, 2, raster, date(2026, 10, 1)), 10 / 24, places=6
        )

    def test_soll_anteil_leeres_raster_faellt_zurueck(self):
        # Ein Raster ohne Stunden in dieser Woche darf das Soll nicht auf
        # null ziehen — dann gilt die volle Wochensumme.
        self.assertAlmostEqual(
            soll_anteil(self.wochen, 2, {'mo': 0, 'di': 0, 'mi': 0, 'do': 0, 'fr': 0},
                        date(2026, 10, 6)),
            1.0, places=6,
        )

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
