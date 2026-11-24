"""
Prüfschichten für den Export.

Ersetzt den früheren Größenvergleich der Exportdatei. Die Bytezahl sagte
nichts darüber, *wo* etwas fehlt, und konnte einen Ausfall verdecken,
wenn anderswo genug Abgaben hinzukamen. Stattdessen drei Ebenen:

1. **Seite** — jede Moodle-Seite muss vollständig angekommen sein:
   keine Anmeldeseite, erwartete Tabelle vorhanden, aufgeteilte Seiten
   nachgeladen (``seitenwerte``, ``seiten_url``), kein Namensfilter
   (``ohne_namensfilter``, ``pruefe_namensfilter``). Schlägt das fehl, gilt
   der Status als **unbekannt** — nie als „nicht abgegeben".
2. **Abgleich** — wer laut Gruppen zum Kurs gehört, muss in jeder
   Bewertungstabelle stehen; fehlt jemand, ist der Status dieser Person
   unbekannt (``unbekannter_status``).
3. **Verlauf** — Zählwerte je Aufgabe und Klasse gegen den letzten Lauf
   (``zaehlwerte``, ``vergleiche_zaehlwerte``). Ein Rückgang ist eine
   Warnung, kein Abbruch: Abmeldungen oder zurückgesetzte Abgaben senken
   die Zahlen zu Recht.

Reine Funktionen ohne Selenium, damit sie ohne Browser testbar sind.
"""

import os
import sys
from typing import Dict, Iterable, List, Optional, Set
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.common.group_utils import extract_group_prefix  # noqa: E402

# Parameter, mit denen Moodle aufgeteilte Seiten adressiert: ``page`` bei
# Tabellen (Bewerterübersicht, Bewertungsseite, Testbericht), ``start``
# als Versatz beim Fortschrittsbericht.
SEITEN_PARAMETER = ('page', 'start')

# Obergrenze gegen Endlosschleifen bei unerwartetem Markup. 110 Personen
# bei 25 je Seite sind 5 Seiten; 50 lässt reichlich Luft.
MAX_SEITEN = 50

# Status-Text eines unbekannten Eintrags. Bewusst kein Wert, den ältere
# Auswertungen als "abgegeben" oder "bewertet" lesen könnten.
STATUS_UNBEKANNT = 'Unbekannt'


class SeiteUnvollstaendig(Exception):
    """Eine Moodle-Seite kam nicht vollständig oder nicht wie erwartet an."""


# ---------------------------------------------------------------------------
# Ebene 1: Seitenaufteilung
# ---------------------------------------------------------------------------

def seitenwerte(hrefs: Iterable[Optional[str]]) -> Dict[str, Set[int]]:
    """
    Liest aus den Links einer Seitenleiste, welche Seiten es gibt.

    Verwendet wird nur die *Seitennummer*, nie der Link selbst: Seitenlinks
    tragen je nach Bericht weitere Parameter, und Filterlinks (etwa die
    Buchstabenleiste ``sifirst``/``tifirst``) speichert Moodle in der
    Sitzung. Würde der Export einem solchen Link folgen, wären alle
    folgenden Abrufe gefiltert. Der Aufrufer baut die URL deshalb selbst
    aus seiner Basis-URL und der Nummer (``seiten_url``).

    Args:
        hrefs: href-Attribute der Links aus ``.pagination``/``.paging``

    Returns:
        {Parametername: {Werte}}, z.B. {'page': {1, 2}} oder {'start': {25, 50}}
    """
    werte: Dict[str, Set[int]] = {}
    for href in hrefs:
        if not href:
            continue
        query = dict(parse_qsl(urlsplit(href).query, keep_blank_values=True))
        for param in SEITEN_PARAMETER:
            wert = query.get(param, '')
            if wert.isdigit():
                werte.setdefault(param, set()).add(int(wert))
    return werte


def seiten_url(url: str, param: str, wert: int) -> str:
    """Setzt oder ersetzt einen Seitenparameter in der URL."""
    teile = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(teile.query, keep_blank_values=True) if k != param]
    query.append((param, str(wert)))
    return urlunsplit((teile.scheme, teile.netloc, teile.path, urlencode(query), teile.fragment))


def erste_seite(url: str) -> Dict[str, Set[int]]:
    """
    Welche Seitenwerte die Basis-URL selbst schon abdeckt.

    Ohne Parameter liefert Moodle Seite 0 bzw. Versatz 0. Steht ein Wert
    in der URL, gilt dieser als geladen.
    """
    query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
    geladen = {}
    for param in SEITEN_PARAMETER:
        wert = query.get(param, '0')
        geladen[param] = {int(wert) if wert.isdigit() else 0}
    return geladen


def offene_seiten(gefunden: Dict[str, Set[int]], geladen: Dict[str, Set[int]]) -> List[tuple]:
    """Seiten, die gefunden, aber noch nicht geladen wurden — sortiert."""
    offen = []
    for param, werte in gefunden.items():
        for wert in werte - geladen.get(param, set()):
            offen.append((param, wert))
    return sorted(offen)


# ---------------------------------------------------------------------------
# Ebene 1: Namensfilter
# ---------------------------------------------------------------------------

# Die Buchstabenleiste („Vorname: A B C …“) ist ein Filter, den Moodle im
# Konto bzw. in der Sitzung speichert. Wer auf der Bewertungsseite einmal
# „B“ angeklickt hat, sieht dort — und der Export liest dort — nur noch
# Personen mit B, bis jemand wieder „Alle“ wählt. Jeder Abruf einer
# Personentabelle setzt den Filter deshalb ausdrücklich leer. Zwei
# Parameterpaare, weil Moodle sie je Seite verschieden nennt: ``tifirst``/
# ``tilast`` (Bewertungsseite, Testbericht, Fortschrittsbericht ab Moodle 4)
# und ``sifirst``/``silast`` (Bewerterübersicht, Singleview, ältere
# Fortschrittsberichte). Parameter, die eine Seite nicht kennt, ignoriert
# Moodle.
NAMENSFILTER_PARAMETER = ('tifirst', 'tilast', 'sifirst', 'silast')

# Beschriftung der Schaltfläche ohne Filter in der Buchstabenleiste
_OHNE_FILTER = ('alle', 'all')


def ohne_namensfilter(url: str) -> str:
    """Setzt alle Namensfilter-Parameter der URL auf leer (= „Alle“)."""
    teile = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(teile.query, keep_blank_values=True)
             if k not in NAMENSFILTER_PARAMETER]
    query.extend((p, '') for p in NAMENSFILTER_PARAMETER)
    return urlunsplit((teile.scheme, teile.netloc, teile.path, urlencode(query), teile.fragment))


def pruefe_namensfilter(aktive: Iterable[Optional[str]]) -> None:
    """
    Bricht ab, wenn die geladene Seite trotzdem einen Namensfilter zeigt.

    Sicherheitsnetz zu ``ohne_namensfilter``: Greift das Zurücksetzen auf
    einer Seite nicht, wäre die Tabelle still unvollständig. Gemeldet wird
    nur bei eindeutigem Befund — ein ausgewählter Buchstabe in der
    Buchstabenleiste. Sieht das Markup anders aus, bleibt die Prüfung stumm;
    fehlende Personen fängt dann der Abgleich (Ebene 2).

    Args:
        aktive: Texte der ausgewählten Einträge der Buchstabenleiste(n)
            (``.initialbar li.active`` ohne ``.initialbarall``)

    Raises:
        SeiteUnvollstaendig: ein Buchstabe ist ausgewählt
    """
    buchstaben = [t.strip() for t in aktive
                  if t and t.strip() and t.strip().lower() not in _OHNE_FILTER]
    if buchstaben:
        raise SeiteUnvollstaendig(
            f"Namensfilter aktiv ({', '.join(buchstaben)}) — "
            "in Moodle in der Buchstabenleiste „Alle“ wählen")


# ---------------------------------------------------------------------------
# Ebene 2: Abgleich und unbekannter Status
# ---------------------------------------------------------------------------

def unbekannter_status(user_id: str, grund: str) -> Dict:
    """
    Status-Eintrag für eine Aufgabe, deren Stand nicht ermittelt werden konnte.

    Die Felder entsprechen einem normalen Eintrag, damit vorhandene
    Auswertungen nicht stolpern; ``unbekannt`` ist das maßgebliche
    Kennzeichen. Der Eintrag zählt weder als abgegeben noch als bewertet.
    """
    return {
        'user_id': user_id,
        'status': STATUS_UNBEKANNT,
        'status2': STATUS_UNBEKANNT,
        'submission': STATUS_UNBEKANNT,
        'submission_time': None,
        'grade_options': [],
        'grade': '-',
        'unbekannt': True,
        'grund': grund,
    }


def ist_unbekannt(status: Optional[Dict]) -> bool:
    """True, wenn ein Status-Eintrag als unbekannt markiert ist."""
    return bool(status) and bool(status.get('unbekannt'))


# Moodle-Status einer Aufgabe, die als Entwurf gespeichert, aber nicht
# eingereicht ist. Die Bewertungsseite traegt dafuer ein Datum
# ("Zuletzt geändert"), deshalb reicht submission_time allein nicht, um
# "abgegeben" zu erkennen.
STATUS_ENTWURF = 'Entwurf (nicht abgegeben)'


def ist_entwurf(status: Optional[Dict]) -> bool:
    """True, wenn ein Status-Eintrag ein nicht eingereichter Entwurf ist."""
    return bool(status) and status.get('status') == STATUS_ENTWURF


def zaehlt_als_abgabe(status: Optional[Dict]) -> bool:
    """
    Ist-Regel: abgegeben, bewertet oder mit Note — Entwurf und unbekannt nicht.

    Ein Test mit offener Freitextbewertung hat ein Datum, aber keine Note;
    er zaehlt. Ein Aufgaben-Entwurf hat ebenfalls ein Datum, zaehlt aber
    nicht, solange er nicht bewertet ist.
    """
    if not status or ist_unbekannt(status):
        return False
    hat_note = status.get('grade') not in (None, '', '-', 'Nicht bewertet',
                                           'Nicht eingereicht', 'Keine Bewertung')
    hat_abgabe = bool(status.get('submission_time')) and not ist_entwurf(status)
    return hat_abgabe or hat_note or status.get('status2') == 'Bewertet'


def gilt_fuer_gruppe(aufgaben_gruppen: Optional[str], gruppenname: str) -> bool:
    """
    Ob eine Aufgabe für eine Gruppe vorgesehen ist.

    ``aufgaben_gruppen`` ist der Wert aus ``get_assignment_groups``:
    "all" oder ein Gruppenname aus „Getrennte Gruppen (…)". Verglichen wird
    über das Klassenkürzel, weil Moodle Gruppennamen unterschiedlich
    schreibt (``K - IFA12A (6072)`` vs. ``IFA12A``).
    """
    if not aufgaben_gruppen or aufgaben_gruppen == 'all':
        return True
    return extract_group_prefix(aufgaben_gruppen) == extract_group_prefix(gruppenname)


# ---------------------------------------------------------------------------
# Ebene 3: Verlauf
# ---------------------------------------------------------------------------

def _hat_abgabe(status: Dict) -> bool:
    """Spiegelt die Ist-Regel des Backends: abgegeben, bewertet oder mit Note."""
    return zaehlt_als_abgabe(status)


def zaehlwerte(export: Dict) -> Dict[str, Dict[str, Dict[str, int]]]:
    """
    Verdichtet einen Export auf Zählwerte je Aufgabe und Klasse.

    Die Werte sind nicht personenbezogen und eignen sich deshalb auch als
    Vergleichsstand im Browser.

    Returns:
        {"<kurs>/<cmid>": {"IFA12A": {"abgegeben": n, "bewertet": n, "unbekannt": n}}}
    """
    ergebnis: Dict[str, Dict[str, Dict[str, int]]] = {}
    kurs_von_cmid = {}
    for kurs_id, kurs in (export.get('kurse') or {}).items():
        for kat in kurs.get('activities_by_category', []):
            for typ in ('assignments', 'quizzes'):
                for act in kat.get(typ, []):
                    kurs_von_cmid[str(act.get('id'))] = str(kurs_id)

    for gruppe in export.get('groups', []):
        klasse = extract_group_prefix(gruppe.get('name', ''))
        for user in gruppe.get('users', []):
            acts = user.get('activities', {})
            for act in acts.get('assignments', []) + acts.get('quizzes', []):
                cmid = str(act.get('id'))
                schluessel = f"{kurs_von_cmid.get(cmid, '?')}/{cmid}"
                zaehler = ergebnis.setdefault(schluessel, {}).setdefault(
                    klasse, {'abgegeben': 0, 'bewertet': 0, 'unbekannt': 0})
                status = act.get('status') or {}
                if ist_unbekannt(status):
                    zaehler['unbekannt'] += 1
                    continue
                if _hat_abgabe(status):
                    zaehler['abgegeben'] += 1
                if status.get('status2') == 'Bewertet':
                    zaehler['bewertet'] += 1
    return ergebnis


def vergleiche_zaehlwerte(alt: Dict, neu: Dict, titel: Optional[Dict[str, str]] = None) -> List[str]:
    """
    Meldet Rückgänge gegenüber dem letzten Lauf.

    Gemeldet wird je Aufgabe und Klasse, wenn weniger abgegeben oder
    bewertet ist als zuvor. Aufgaben mit unbekanntem Status werden
    übersprungen — dort ist der Rückgang schon als Lücke gemeldet.

    Args:
        alt, neu: Ergebnisse von ``zaehlwerte``
        titel: optional {cmid: Titel} für lesbare Meldungen

    Returns:
        Meldungen, leer wenn nichts zurückging
    """
    titel = titel or {}
    meldungen = []
    for schluessel in sorted(alt):
        cmid = schluessel.split('/', 1)[-1]
        name = titel.get(cmid, f'cmid {cmid}')
        if schluessel not in neu:
            meldungen.append(f"{name}: fehlt im neuen Export (war im letzten Lauf enthalten)")
            continue
        for klasse in sorted(alt[schluessel]):
            vorher = alt[schluessel][klasse]
            jetzt = neu[schluessel].get(klasse)
            if jetzt is None:
                meldungen.append(f"{name}, {klasse}: Klasse fehlt im neuen Export")
                continue
            if jetzt.get('unbekannt'):
                continue
            for feld in ('abgegeben', 'bewertet'):
                if jetzt[feld] < vorher[feld]:
                    meldungen.append(
                        f"{name}, {klasse}: {feld} {vorher[feld]} → {jetzt[feld]}"
                    )
    return meldungen


def fuehre_gruppen_zusammen(ziel: List[Dict], quelle: List[Dict]) -> None:
    """
    Führt die Gruppen eines weiteren Kurses in die Gesamtliste ein.

    Die Gruppen sind kursübergreifend dieselben Personen, ihre Aktivitäten
    aber je Kurs verschieden. Früher wurden die Gruppen nur vom ersten Kurs
    übernommen — damit fielen alle Abgaben späterer Kurse weg. Hier werden
    die Aktivitätslisten je Person (über die Moodle-ID) zusammengelegt;
    Personen und Gruppen, die nur im späteren Kurs vorkommen, kommen hinzu.

    Args:
        ziel: Gruppenliste des Exports, wird verändert
        quelle: Gruppenliste eines weiteren Kurses
    """
    gruppen = {g.get('name'): g for g in ziel}
    for gruppe in quelle:
        vorhanden = gruppen.get(gruppe.get('name'))
        if vorhanden is None:
            ziel.append(gruppe)
            gruppen[gruppe.get('name')] = gruppe
            continue
        personen = {u.get('id'): u for u in vorhanden.get('users', [])}
        for user in gruppe.get('users', []):
            bekannt = personen.get(user.get('id'))
            if bekannt is None:
                vorhanden.setdefault('users', []).append(user)
                personen[user.get('id')] = user
                continue
            ziel_acts = bekannt.setdefault('activities', {})
            for typ, eintraege in (user.get('activities') or {}).items():
                liste = ziel_acts.setdefault(typ, [])
                ids = {e.get('id') for e in liste}
                liste.extend(e for e in eintraege if e.get('id') not in ids)
