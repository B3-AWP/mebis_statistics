"""
Tests der Pruefschichten des Exports (src/export/pruefung.py) und der
Seiten-Nachladelogik im Exporter.

Kein Browser, kein Moodle: Seiten und Sitzung sind Attrappen, die
Seitenleisten im Moodle-Format liefern.

    python -X utf8 -m unittest tests.test_pruefung
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.export import pruefung  # noqa: E402
from src.export.pruefung import (  # noqa: E402
    NAMENSFILTER_PARAMETER, SeiteUnvollstaendig, erste_seite, fuehre_gruppen_zusammen,
    gilt_fuer_gruppe, ist_unbekannt, offene_seiten, ohne_namensfilter, pruefe_namensfilter,
    seiten_url, seitenwerte, unbekannter_status, vergleiche_zaehlwerte, zaehlwerte,
)
from urllib.parse import parse_qs, urlsplit  # noqa: E402

BASIS = 'https://lernplattform.bycs.de'


class TestSeitenwerte(unittest.TestCase):

    def test_page_und_start(self):
        werte = seitenwerte([
            f'{BASIS}/grade/report/grader/index.php?id=1&page=1',
            f'{BASIS}/grade/report/grader/index.php?id=1&page=2',
            f'{BASIS}/report/progress/index.php?course=1&start=25&sifirst=',
        ])
        self.assertEqual(werte, {'page': {1, 2}, 'start': {25}})

    def test_ohne_nummer_und_leer(self):
        self.assertEqual(seitenwerte([None, '', '#', f'{BASIS}/x.php?page=abc']), {})

    def test_relative_links(self):
        self.assertEqual(seitenwerte(['index.php?id=3&page=4']), {'page': {4}})

    def test_seiten_url_ersetzt_nur_den_parameter(self):
        url = seiten_url(f'{BASIS}/mod/quiz/report.php?id=5&tsort=timefinish&page=0', 'page', 3)
        self.assertIn('page=3', url)
        self.assertNotIn('page=0', url)
        self.assertIn('tsort=timefinish', url)

    def test_erste_seite(self):
        self.assertEqual(erste_seite(f'{BASIS}/a.php?id=1'), {'page': {0}, 'start': {0}})
        self.assertEqual(erste_seite(f'{BASIS}/a.php?id=1&page=2')['page'], {2})

    def test_offene_seiten(self):
        self.assertEqual(
            offene_seiten({'page': {0, 1, 2}}, {'page': {0}, 'start': {0}}),
            [('page', 1), ('page', 2)])


class TestNamensfilter(unittest.TestCase):
    """Ein in Moodle gespeicherter Buchstabenfilter darf den Export nicht kürzen."""

    URL = f'{BASIS}/mod/assign/view.php?id=94824799&action=grading&status&quickgrading=0&group=0'

    def _query(self, url):
        return parse_qs(urlsplit(url).query, keep_blank_values=True)

    def test_setzt_alle_filter_leer(self):
        q = self._query(ohne_namensfilter(self.URL))
        for p in NAMENSFILTER_PARAMETER:
            self.assertEqual(q[p], [''], p)
        # Uebrige Parameter bleiben, auch der leere Statusfilter
        self.assertEqual(q['id'], ['94824799'])
        self.assertEqual(q['status'], [''])
        self.assertEqual(q['group'], ['0'])

    def test_ersetzt_gesetzten_filter(self):
        q = self._query(ohne_namensfilter(f'{self.URL}&tifirst=B&silast=M'))
        self.assertEqual(q['tifirst'], [''])
        self.assertEqual(q['silast'], [''])

    def test_idempotent(self):
        einmal = ohne_namensfilter(self.URL)
        self.assertEqual(ohne_namensfilter(einmal), einmal)

    def test_seitennummer_ueberlebt(self):
        url = seiten_url(ohne_namensfilter(self.URL), 'page', 2)
        q = self._query(url)
        self.assertEqual(q['page'], ['2'])
        self.assertEqual(q['tifirst'], [''])

    def test_alle_ist_kein_filter(self):
        pruefe_namensfilter([])
        pruefe_namensfilter(['Alle', ' All ', '', None])

    def test_buchstabe_ist_filter(self):
        with self.assertRaises(SeiteUnvollstaendig) as ctx:
            pruefe_namensfilter(['B'])
        self.assertIn('Namensfilter aktiv (B)', str(ctx.exception))


class TestUnbekannt(unittest.TestCase):

    def test_status_zaehlt_nicht(self):
        s = unbekannter_status('7', 'Tabelle fehlt')
        self.assertTrue(ist_unbekannt(s))
        self.assertNotEqual(s['status'], 'Zur Bewertung abgegeben')
        self.assertNotEqual(s['status2'], 'Bewertet')
        self.assertIsNone(s['submission_time'])
        self.assertEqual(s['grade'], '-')

    def test_normaler_status_ist_nicht_unbekannt(self):
        self.assertFalse(ist_unbekannt({'status': 'Nicht eingereicht'}))
        self.assertFalse(ist_unbekannt(None))

    def test_zaehlt_als_abgabe(self):
        entwurf = dict(OFFEN, status=pruefung.STATUS_ENTWURF,
                       submission_time='2026-10-01T10:00:00')
        # Test mit offener Freitextbewertung: Datum, keine Note -> zaehlt
        test_offen = dict(OFFEN, submission_time='2026-10-01T10:00:00')
        self.assertFalse(pruefung.zaehlt_als_abgabe(entwurf))
        self.assertTrue(pruefung.zaehlt_als_abgabe(test_offen))
        self.assertTrue(pruefung.zaehlt_als_abgabe(ABGEGEBEN))
        self.assertFalse(pruefung.zaehlt_als_abgabe(OFFEN))
        self.assertFalse(pruefung.zaehlt_als_abgabe(unbekannter_status('1', 'x')))

    def test_gilt_fuer_gruppe(self):
        self.assertTrue(gilt_fuer_gruppe('all', 'K - IFA12A (6072)'))
        self.assertTrue(gilt_fuer_gruppe(None, 'IFA12A'))
        self.assertTrue(gilt_fuer_gruppe('IFA12A - Team 3', 'K - IFA12A (6072)'))
        self.assertFalse(gilt_fuer_gruppe('IFA12B', 'K - IFA12A (6072)'))


def _export(statusliste):
    """Mini-Export: ein Kurs, eine Aufgabe, eine Klasse."""
    return {
        'kurse': {'100': {'activities_by_category': [
            {'assignments': [{'id': '9', 'title': 'Aufgabe Neun'}], 'quizzes': []}]}},
        'groups': [{'name': 'K - IFA12A (6072)', 'users': [
            {'id': str(i), 'activities': {'assignments': [{'id': '9', 'status': s}], 'quizzes': []}}
            for i, s in enumerate(statusliste)
        ]}],
    }


ABGEGEBEN = {'status': 'Zur Bewertung abgegeben', 'status2': 'Nicht bewertet',
             'submission_time': '2026-10-01T10:00:00', 'grade': '-'}
BEWERTET = {'status': 'Zur Bewertung abgegeben', 'status2': 'Bewertet',
            'submission_time': '2026-10-01T10:00:00', 'grade': '80,00'}
OFFEN = {'status': 'Nicht eingereicht', 'status2': 'Nicht bewertet',
         'submission_time': None, 'grade': '-'}


class TestVerlauf(unittest.TestCase):

    def test_zaehlwerte(self):
        z = zaehlwerte(_export([ABGEGEBEN, BEWERTET, OFFEN, unbekannter_status('3', 'x')]))
        self.assertEqual(z['100/9']['IFA12A'], {'abgegeben': 2, 'bewertet': 1, 'unbekannt': 1})

    def test_rueckgang_wird_gemeldet(self):
        alt = zaehlwerte(_export([ABGEGEBEN, BEWERTET, OFFEN]))
        neu = zaehlwerte(_export([OFFEN, BEWERTET, OFFEN]))
        meldungen = vergleiche_zaehlwerte(alt, neu, {'9': 'Aufgabe Neun'})
        self.assertEqual(len(meldungen), 1)
        self.assertIn('Aufgabe Neun, IFA12A: abgegeben 2 → 1', meldungen[0])

    def test_zuwachs_ist_still(self):
        alt = zaehlwerte(_export([OFFEN, OFFEN]))
        neu = zaehlwerte(_export([ABGEGEBEN, BEWERTET]))
        self.assertEqual(vergleiche_zaehlwerte(alt, neu), [])

    def test_unbekannt_ueberspringt_rueckgang(self):
        # Die Luecke ist bereits als "unbekannt" gemeldet — kein Doppel.
        alt = zaehlwerte(_export([ABGEGEBEN, ABGEGEBEN]))
        neu = zaehlwerte(_export([unbekannter_status('0', 'x'), unbekannter_status('1', 'x')]))
        self.assertEqual(vergleiche_zaehlwerte(alt, neu), [])

    def test_fehlende_aufgabe(self):
        alt = zaehlwerte(_export([ABGEGEBEN]))
        meldungen = vergleiche_zaehlwerte(alt, {})
        self.assertEqual(len(meldungen), 1)
        self.assertIn('fehlt im neuen Export', meldungen[0])


class TestGruppenZusammenfuehren(unittest.TestCase):
    """Regression: Abgaben des zweiten Kurses gingen verloren."""

    def test_aktivitaeten_beider_kurse_bleiben(self):
        kurs1 = [{'name': 'IFA12A', 'users': [
            {'id': '1', 'name': 'Anna', 'activities': {'assignments': [{'id': 'a1'}], 'quizzes': []}}]}]
        kurs2 = [{'name': 'IFA12A', 'users': [
            {'id': '1', 'name': 'Anna', 'activities': {'assignments': [{'id': 'b1'}], 'quizzes': [{'id': 'q2'}]}},
            {'id': '2', 'name': 'Bernd', 'activities': {'assignments': [{'id': 'b1'}]}}]},
            {'name': 'IFA12B', 'users': []}]

        gesamt = []
        fuehre_gruppen_zusammen(gesamt, kurs1)
        fuehre_gruppen_zusammen(gesamt, kurs2)

        self.assertEqual([g['name'] for g in gesamt], ['IFA12A', 'IFA12B'])
        anna = gesamt[0]['users'][0]
        self.assertEqual([a['id'] for a in anna['activities']['assignments']], ['a1', 'b1'])
        self.assertEqual([q['id'] for q in anna['activities']['quizzes']], ['q2'])
        self.assertEqual([u['name'] for u in gesamt[0]['users']], ['Anna', 'Bernd'])

    def test_doppelte_aktivitaet_nur_einmal(self):
        g = [{'name': 'A', 'users': [{'id': '1', 'activities': {'assignments': [{'id': 'x'}]}}]}]
        fuehre_gruppen_zusammen(g, [{'name': 'A', 'users': [
            {'id': '1', 'activities': {'assignments': [{'id': 'x'}]}}]}])
        self.assertEqual(len(g[0]['users'][0]['activities']['assignments']), 1)


# ---------------------------------------------------------------------------
# Exporter: Nachladen aufgeteilter Seiten (mit Attrappen)
# ---------------------------------------------------------------------------

try:
    from src.export import exporter
except ImportError as e:  # Selenium/requests fehlen
    exporter = None
    _IMPORT_FEHLER = e


def _ohne_filterparameter(url):
    """URL ohne die Namensfilter-Parameter — für den Seitenvergleich der Attrappe."""
    teile = url.split('?', 1)
    if len(teile) < 2:
        return url
    rest = [p for p in teile[1].split('&') if p.split('=', 1)[0] not in NAMENSFILTER_PARAMETER]
    return f"{teile[0]}?{'&'.join(rest)}"


class FakeDriver:
    """Liefert je URL eine Seite: (Ergebnis, Seitenlinks[, aktive Buchstaben])."""

    def __init__(self, seiten, login_bei=None):
        self.seiten = seiten
        self.login_bei = login_bei
        self.current_url = ''
        self.aufrufe = []

    def get(self, url):
        self.aufrufe.append(url)
        self.current_url = (f'{BASIS}/login/index.php'
                            if self.login_bei and self.login_bei in url else url)

    def seite(self):
        url = _ohne_filterparameter(self.current_url)
        for schluessel, inhalt in self.seiten.items():
            if url.endswith(schluessel):
                return inhalt
        raise AssertionError(f'unerwartete URL {self.current_url}')

    def execute_script(self, skript):
        if skript is exporter._JS_SEITENLINKS:
            return self.seite()[1]
        if skript is exporter._JS_NAMENSFILTER:
            inhalt = self.seite()
            return inhalt[2] if len(inhalt) > 2 else []
        raise AssertionError('unerwartetes Skript')


@unittest.skipIf(exporter is None, 'exporter nicht importierbar')
class TestLadeAlleSeiten(unittest.TestCase):

    URL = f'{BASIS}/grade/report/grader/index.php?id=1&group=0'

    def test_folgt_allen_seiten_auch_spaet_sichtbaren(self):
        # Seite 0 zeigt nur 1; erst Seite 1 verraet die 2 (lange Leiste).
        drv = FakeDriver({
            'group=0': (['A'], [f'{self.URL}&page=1']),
            'page=1': (['B'], [f'{self.URL}&page=0', f'{self.URL}&page=2']),
            'page=2': (['C'], [f'{self.URL}&page=1']),
        })
        ergebnisse = exporter.lade_alle_seiten(drv, self.URL, lambda d: d.seite()[0])
        self.assertEqual(ergebnisse, [['A'], ['B'], ['C']])
        self.assertEqual(len(drv.aufrufe), 3)

    def test_ohne_seitenleiste_eine_seite(self):
        drv = FakeDriver({'group=0': (['A'], [])})
        self.assertEqual(exporter.lade_alle_seiten(drv, self.URL, lambda d: d.seite()[0]), [['A']])

    def test_anmeldeseite_bricht_ab(self):
        drv = FakeDriver({'group=0': (['A'], [f'{self.URL}&page=1'])}, login_bei='page=1')
        with self.assertRaises(SeiteUnvollstaendig):
            exporter.lade_alle_seiten(drv, self.URL, lambda d: d.seite()[0])

    def test_jeder_abruf_setzt_namensfilter_zurueck(self):
        drv = FakeDriver({
            'group=0': (['A'], [f'{self.URL}&page=1']),
            'page=1': (['B'], []),
        })
        exporter.lade_alle_seiten(drv, self.URL, lambda d: d.seite()[0])
        for url in drv.aufrufe:
            q = parse_qs(urlsplit(url).query, keep_blank_values=True)
            for p in NAMENSFILTER_PARAMETER:
                self.assertEqual(q.get(p), [''], f'{p} fehlt in {url}')

    def test_verbliebener_namensfilter_bricht_ab(self):
        # Greift das Zuruecksetzen nicht, waere die Tabelle still gekuerzt.
        drv = FakeDriver({'group=0': (['A'], [], ['B'])})
        with self.assertRaises(SeiteUnvollstaendig) as ctx:
            exporter.lade_alle_seiten(drv, self.URL, lambda d: d.seite()[0])
        self.assertIn('Namensfilter', str(ctx.exception))

    def test_lesefehler_laeuft_durch(self):
        def lese(_):
            raise SeiteUnvollstaendig('Tabelle fehlt')
        drv = FakeDriver({'group=0': (['A'], [])})
        with self.assertRaises(SeiteUnvollstaendig):
            exporter.lade_alle_seiten(drv, self.URL, lese)

    def test_obergrenze(self):
        class Endlos(FakeDriver):
            def execute_script(self, skript):
                if skript is exporter._JS_NAMENSFILTER:
                    return []
                n = int(self.current_url.rsplit('=', 1)[-1]) if 'page=' in self.current_url else 0
                return [f'{BASIS}/x.php?page={n + 1}']

            def seite(self):
                return ('x', [])
        drv = Endlos({})
        with self.assertRaises(SeiteUnvollstaendig):
            exporter.lade_alle_seiten(drv, self.URL, lambda d: 'x')
        self.assertEqual(len(drv.aufrufe), pruefung.MAX_SEITEN)


class FakeAntwort:
    def __init__(self, url, text):
        self.url = url
        self.text = text

    def raise_for_status(self):
        pass


def _fortschrittsseite(ids, starts):
    zeilen = ''.join(
        f'<tr><th scope="row"><a href="{BASIS}/user/view.php?id={i}&course=1">P{i}</a></th></tr>'
        for i in ids)
    leiste = ''.join(f'<a href="index.php?course=1&group=5&start={s}&sifirst=">{s}</a>' for s in starts)
    initial = '<nav class="initialbar"><ul class="pagination"><a href="index.php?sifirst=A&start=999">A</a></ul></nav>'
    return (f'<select name="group"></select>{initial}<div class="paging">{leiste}</div>'
            f'<table id="completion-progress"><tbody>{zeilen}</tbody></table>')


class FakeSession:
    def __init__(self, seiten, login=False):
        self.seiten = seiten
        self.login = login
        self.aufrufe = []

    def get(self, url, timeout=None):
        self.aufrufe.append(url)
        if self.login:
            return FakeAntwort(f'{BASIS}/login/index.php', '')
        start = 0
        if 'start=' in url:
            start = int(url.split('start=')[1].split('&')[0])
        return FakeAntwort(url, self.seiten[start])


@unittest.skipIf(exporter is None, 'exporter nicht importierbar')
class TestGruppenmitglieder(unittest.TestCase):
    """Der Fortschrittsbericht zeigt nur 25 Personen je Seite."""

    BASIS_URL = f'{BASIS}/report/progress/index.php'

    def test_alle_seiten_werden_geladen(self):
        session = FakeSession({
            0: _fortschrittsseite(range(1, 26), [25, 50]),
            25: _fortschrittsseite(range(26, 51), [0, 50]),
            50: _fortschrittsseite(range(51, 54), [0, 25]),
        })
        users = exporter.get_user_ids_from_group_fast(session, '5', self.BASIS_URL, '1')
        self.assertEqual(len(users), 53)
        self.assertEqual(users[-1]['id'], '53')
        # Die Buchstabenleiste (start=999) wurde nicht verfolgt
        self.assertFalse(any('999' in u for u in session.aufrufe))
        self.assertFalse(any('sifirst=A' in u for u in session.aufrufe))

    def test_namensfilter_wird_zurueckgesetzt(self):
        session = FakeSession({0: _fortschrittsseite(range(1, 4), [])})
        exporter.get_user_ids_from_group_fast(session, '5', self.BASIS_URL, '1')
        q = parse_qs(urlsplit(session.aufrufe[0]).query, keep_blank_values=True)
        for p in NAMENSFILTER_PARAMETER:
            self.assertEqual(q.get(p), [''], p)

    def test_verbliebener_namensfilter_wirft(self):
        # Moodle-Markup der Buchstabenleiste mit ausgewähltem „B“
        leiste = ('<div class="initialbar firstinitial"><nav><ul class="pagination">'
                  '<li class="initialbarall page-item"><a class="page-link" href="#">Alle</a></li>'
                  '<li class="page-item A"><a class="page-link" href="#">A</a></li>'
                  '<li class="page-item B active"><a class="page-link">B</a></li>'
                  '</ul></nav></div>')
        session = FakeSession({0: leiste + _fortschrittsseite(range(1, 4), [])})
        with self.assertRaises(SeiteUnvollstaendig):
            exporter.get_user_ids_from_group_fast(session, '5', self.BASIS_URL, '1')

    def test_alle_ausgewaehlt_ist_kein_filter(self):
        leiste = ('<div class="initialbar firstinitial"><nav><ul class="pagination">'
                  '<li class="initialbarall page-item active"><a class="page-link">Alle</a></li>'
                  '<li class="page-item B"><a class="page-link" href="#">B</a></li>'
                  '</ul></nav></div>')
        session = FakeSession({0: leiste + _fortschrittsseite(range(1, 4), [])})
        self.assertEqual(len(exporter.get_user_ids_from_group_fast(session, '5', self.BASIS_URL, '1')), 3)

    def test_leere_gruppe(self):
        session = FakeSession({0: '<select name="group"></select><p>Keine Teilnehmer</p>'})
        self.assertEqual(exporter.get_user_ids_from_group_fast(session, '5', self.BASIS_URL, '1'), [])

    def test_fremde_seite_wirft(self):
        session = FakeSession({0: '<html><body>Wartungsarbeiten</body></html>'})
        with self.assertRaises(SeiteUnvollstaendig):
            exporter.get_user_ids_from_group_fast(session, '5', self.BASIS_URL, '1')

    def test_anmeldeseite_wirft(self):
        with self.assertRaises(SeiteUnvollstaendig):
            exporter.get_user_ids_from_group_fast(FakeSession({}, login=True), '5', self.BASIS_URL, '1')


@unittest.skipIf(exporter is None, 'exporter nicht importierbar')
class TestBewertungszeilen(unittest.TestCase):

    def test_doppelte_zeile_ueber_seitengrenze(self):
        zeile = {'cls': 'user42 unselectedrow', 'status': None, 'status2': None,
                 'submission': None, 'grade': '-', 'time': None}
        ergebnis = exporter._bewertungszeilen_auswerten([zeile, dict(zeile)])
        self.assertEqual(len(ergebnis), 1)
        self.assertEqual(ergebnis[0]['status'], 'Nicht eingereicht')

    def test_entwurf_wird_erkannt(self):
        # Moodle: div.submissionstatusdraft statt ...submitted, aber mit Datum
        zeile = {'cls': 'user8', 'status': None, 'entwurf': True, 'status2': None,
                 'submission': None, 'grade': '-', 'time': '17.11.2026 14:31'}
        ergebnis = exporter._bewertungszeilen_auswerten([zeile])
        self.assertEqual(ergebnis[0]['status'], pruefung.STATUS_ENTWURF)
        self.assertIsNotNone(ergebnis[0]['submission_time'])
        self.assertFalse(pruefung.zaehlt_als_abgabe(ergebnis[0]))

    def test_bewerteter_entwurf_zaehlt(self):
        zeile = {'cls': 'user9', 'status': None, 'entwurf': True, 'status2': None,
                 'submission': None, 'grade': '70,00', 'time': '17.11.2026 14:31'}
        ergebnis = exporter._bewertungszeilen_auswerten([zeile])
        self.assertEqual(ergebnis[0]['status'], 'Zur Bewertung abgegeben')
        self.assertTrue(pruefung.zaehlt_als_abgabe(ergebnis[0]))

    def test_note_ohne_abgabe_zaehlt_als_abgegeben(self):
        zeile = {'cls': 'user7', 'status': None, 'status2': None,
                 'submission': None, 'grade': '85,00', 'time': None}
        ergebnis = exporter._bewertungszeilen_auswerten([zeile])
        self.assertEqual(ergebnis[0]['status'], 'Zur Bewertung abgegeben')
        self.assertEqual(ergebnis[0]['status2'], 'Bewertet')


class TestParallelvergleich(unittest.TestCase):
    """tests/vergleiche_exporte.py — Python- gegen Browser-Export."""

    def test_gleich_und_leerraum(self):
        import copy
        from tests.vergleiche_exporte import vergleiche
        a = _export([ABGEGEBEN, BEWERTET])
        a['schema'] = 3
        b = copy.deepcopy(a)
        b['groups'][0]['users'][1]['activities']['assignments'][0]['status']['grade'] = ' 80,00  '
        self.assertEqual(vergleiche(a, b)[0], [])

    def test_echte_abweichung(self):
        import copy
        from tests.vergleiche_exporte import vergleiche
        a = _export([ABGEGEBEN, BEWERTET])
        a['schema'] = 3
        b = copy.deepcopy(a)
        b['groups'][0]['users'][0]['activities']['assignments'][0]['status'] = unbekannter_status('0', 'x')
        b['groups'][0]['users'].pop()
        arten = {art for art, _ in vergleiche(a, b)[0]}
        self.assertIn('person', arten)
        self.assertIn('feld:unbekannt', arten)

    def test_lange_texte_werden_maskiert(self):
        import copy
        from tests.vergleiche_exporte import vergleiche
        a = _export([ABGEGEBEN])
        a['schema'] = 3
        b = copy.deepcopy(a)
        b['groups'][0]['users'][0]['activities']['assignments'][0]['status']['grade'] = \
            'Erika Mustermann Quiz HTML Bewertung'
        texte = ' '.join(t for _, t in vergleiche(a, b)[0])
        self.assertNotIn('Mustermann', texte)
        self.assertIn('<Text, 5 Wörter>', texte)


@unittest.skipIf(exporter is None, 'exporter nicht importierbar')
class TestVorlauf(unittest.TestCase):

    def test_vergleich_mit_letzter_datei(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as ordner:
            with open(os.path.join(ordner, 'output_20261001_080000.json'), 'w', encoding='utf-8') as f:
                json.dump(_export([ABGEGEBEN, ABGEGEBEN]), f)
            # Testexporte zaehlen nicht als Vorlauf
            with open(os.path.join(ordner, 'test_output_20261002_080000.json'), 'w', encoding='utf-8') as f:
                json.dump(_export([OFFEN, OFFEN]), f)
            datei, meldungen = exporter._vergleiche_mit_vorlauf(ordner, _export([ABGEGEBEN, OFFEN]))
        self.assertEqual(datei, 'output_20261001_080000.json')
        self.assertEqual(meldungen, ['Aufgabe Neun, IFA12A: abgegeben 2 → 1'])

    def test_ohne_vorlauf(self):
        import tempfile
        with tempfile.TemporaryDirectory() as ordner:
            self.assertEqual(exporter._vergleiche_mit_vorlauf(ordner, _export([])), (None, []))


@unittest.skipIf(exporter is None, 'exporter nicht importierbar')
class TestExportCourseAbgleich(unittest.TestCase):
    """
    export_course mit simuliertem Kurs: alle Moodle-Zugriffe sind ersetzt.

    Szenario (cmids aus der echten plan.json, damit die Plan-Regeln greifen):
      A1  Aufgabe, gelesen — Person 3 fehlt in der Tabelle
      A2  Aufgabe, Bewertungsseite nicht lesbar
      Q1  Test in der Bewerterübersicht — Person 3 fehlt dort
      Q2  Test ohne Spalte in der Bewerterübersicht
      Testgruppe (nicht im Plan) mit Person 9 — wird nicht abgeglichen
    """

    @classmethod
    def setUpClass(cls):
        from src.common.plan_loader import PlanFehler, get_plan
        try:
            cls.plan = get_plan()
        except (PlanFehler, OSError) as e:
            raise unittest.SkipTest(f'plan.json nicht erreichbar: {e}')
        kurs = next(k for k in cls.plan.get_kurse() if not k['gesperrt'])
        cls.kurs_id = kurs['moodle_course_id']
        assigns = [a['cmid'] for a in kurs['aufgaben'] if a['typ'] == 'assign']
        quizze = [a['cmid'] for a in kurs['aufgaben'] if a['typ'] == 'quiz']
        if len(assigns) < 2 or len(quizze) < 2:
            raise unittest.SkipTest('Plan hat zu wenige Aufgaben fuer das Szenario')
        cls.A1, cls.A2 = assigns[:2]
        cls.Q1, cls.Q2 = quizze[:2]
        klasse = next(iter(cls.plan.klassen_zu_schiene))
        cls.gruppe = f'K - {klasse} (6072)'

    def _lauf(self, **abweichend):
        from unittest import mock
        A1, A2, Q1, Q2 = self.A1, self.A2, self.Q1, self.Q2

        def status(uid):
            return {'user_id': uid, 'status': 'Zur Bewertung abgegeben', 'status2': 'Bewertet',
                    'submission': '', 'submission_time': '2026-10-01T10:00:00',
                    'grade_options': [], 'grade': '80,00'}

        def assignment(a, *args):
            if a['id'] == A2:
                return a['id'], None, 'all', 'Bewertungstabelle nicht gefunden'
            return a['id'], [status('1'), status('2')], 'all', None

        gruppen = {'10': [{'id': '1', 'name': 'Anna'}, {'id': '2', 'name': 'Bernd'},
                          {'id': '3', 'name': 'Clara'}],
                   '20': [{'id': '9', 'name': 'Gast'}]}
        url = lambda typ, cmid: f'{BASIS}/mod/{typ}/view.php?id={cmid}'  # noqa: E731

        ersatz = {
            'get_select_options': lambda d, name, w: (
                [{'value': '0', 'name': 'Alle'}, {'value': '10', 'name': self.gruppe},
                 {'value': '20', 'name': 'Testgruppe'}] if name == 'group' else []),
            'get_activity_urls': lambda d, cid: {
                'assignments': [{'id': A1, 'title': 'A1', 'url': url('assign', A1)},
                                {'id': A2, 'title': 'A2', 'url': url('assign', A2)}],
                'quizzes': [{'id': Q1, 'title': 'Q1', 'url': url('quiz', Q1)},
                            {'id': Q2, 'title': 'Q2', 'url': url('quiz', Q2)}],
                'checklists': [], 'feedbacks': []},
            'get_all_activity_categories': lambda d, cid: {},
            'process_assignment_parallel': assignment,
            'process_quiz_parallel': lambda q, *a: (q['id'], {}, None),
            'create_requests_session_from_driver': lambda d: None,
            'get_user_ids_from_group_fast': lambda s, g, b, c: [dict(u) for u in gruppen[g]],
            'get_grader_report_data': lambda d, c, g, w: (
                {Q1: {'type': 'quiz', 'grades': {'1': '90,00', '2': '-'}}}, {'1', '2'}),
            'cleanup_thread_drivers': lambda: None,
        }
        ersatz.update(abweichend)
        with mock.patch.multiple(exporter, **ersatz):
            daten = exporter.export_course(
                driver=FakeDriver({'': (None, [])}), course_id=self.kurs_id, course_title='T',
                base_url=f'{BASIS}/report/progress/index.php', username='u', password='p',
                isheadless='True', waittime=1, test_mode=False, test_limit=5,
                timer=exporter.PhaseTimer())
        personen = {u['id']: u for g in daten['groups'] for u in g['users']}
        return daten, personen

    @staticmethod
    def _status(person, typ, cmid):
        return next((e['status'] for e in person['activities'][typ] if e['id'] == cmid), None)

    def test_ausgefallene_aufgabe_ist_fuer_alle_unbekannt(self):
        _, p = self._lauf()
        for uid in ('1', '2', '3'):
            self.assertTrue(ist_unbekannt(self._status(p[uid], 'assignments', self.A2)), uid)

    def test_fehlende_zeile_ist_nur_fuer_die_person_unbekannt(self):
        _, p = self._lauf()
        self.assertEqual(self._status(p['1'], 'assignments', self.A1)['status2'], 'Bewertet')
        self.assertTrue(ist_unbekannt(self._status(p['3'], 'assignments', self.A1)))

    def test_tests(self):
        _, p = self._lauf()
        self.assertEqual(self._status(p['1'], 'quizzes', self.Q1)['status2'], 'Bewertet')
        self.assertEqual(self._status(p['2'], 'quizzes', self.Q1)['status'], 'Nicht eingereicht')
        self.assertTrue(ist_unbekannt(self._status(p['3'], 'quizzes', self.Q1)))
        self.assertTrue(ist_unbekannt(self._status(p['1'], 'quizzes', self.Q2)))

    def test_gruppe_ausserhalb_des_plans_wird_nicht_abgeglichen(self):
        _, p = self._lauf()
        self.assertIsNone(self._status(p['9'], 'assignments', self.A1))
        self.assertIsNone(self._status(p['9'], 'quizzes', self.Q1))

    def test_pruefbericht(self):
        daten, _ = self._lauf()
        luecken = {(l['cmid'], str(l['personen'])) for l in daten['pruefbericht']['luecken']}
        self.assertEqual(luecken, {
            (self.A2, 'alle'), (self.Q2, 'alle'),
            (self.A1, "['3']"), (self.Q1, "['3']"),
        })

    def test_gruppe_nicht_ladbar_ist_kritisch(self):
        def kaputt(s, g, b, c):
            raise SeiteUnvollstaendig('Anmeldeseite statt Fortschrittsbericht')
        with self.assertRaises(exporter.ExportValidationError):
            self._lauf(get_user_ids_from_group_fast=kaputt)

    def test_fremde_gruppe_nicht_ladbar_ist_nur_hinweis(self):
        echte = {'10': [{'id': '1', 'name': 'Anna'}]}

        def nur_klasse(s, g, b, c):
            if g == '20':
                raise SeiteUnvollstaendig('Zeitüberschreitung')
            return [dict(u) for u in echte[g]]
        daten, _ = self._lauf(get_user_ids_from_group_fast=nur_klasse)
        self.assertTrue(any('Testgruppe' in h for h in daten['pruefbericht']['hinweise']))

    def test_bewerteruebersicht_nicht_lesbar(self):
        def kaputt(d, c, g, w):
            raise SeiteUnvollstaendig('Tabelle der Bewerterübersicht nicht gefunden')
        daten, p = self._lauf(get_grader_report_data=kaputt)
        # Alle Plan-Tests unbekannt, Aufgaben unberuehrt
        self.assertTrue(ist_unbekannt(self._status(p['1'], 'quizzes', self.Q1)))
        self.assertTrue(ist_unbekannt(self._status(p['1'], 'quizzes', self.Q2)))
        self.assertEqual(self._status(p['1'], 'assignments', self.A1)['status2'], 'Bewertet')


if __name__ == '__main__':
    unittest.main()
