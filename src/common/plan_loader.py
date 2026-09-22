#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
plan_loader — Laden und Validieren der Planungsdatei (plan.json)

Einzige Quelle der Stammdaten: Kurse, Pflichtaufgaben, geplante Stunden,
Schulwochenkalender je Schiene, Notenschlüssel. Kennt keinen Moodle-Status.

Gegenstück zu js/plan.js und js/bilanz.js des Schüler-Dashboards. Die
Rechenfunktionen (soll_anteil, aktuelle_woche, verteile_unterrichtsstunden)
sind bewusst 1:1 portiert — zwei divergierende Implementierungen derselben
Formel wären eine Fehlerquelle, die später niemand findet.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from src.common.group_utils import extract_group_prefix

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 4
AUFGABEN_TYPEN = ('assign', 'quiz')

# Wochentage, die ein Stundenraster tragen darf. Blockwochen laufen Mo–Fr.
RASTER_TAGE = ('mo', 'di', 'mi', 'do', 'fr')

# date.weekday(): 0 = Montag. Wochenenden tragen kein Raster.
_WOCHENTAG_SCHLUESSEL = {0: 'mo', 1: 'di', 2: 'mi', 3: 'do', 4: 'fr'}


class PlanFehler(Exception):
    """Fehler mit gesammelten Validierungsmeldungen."""

    def __init__(self, meldungen: List[str]):
        self.meldungen = meldungen
        super().__init__('Planungsdatei fehlerhaft:\n· ' + '\n· '.join(meldungen))


# ============================================================
# Datumshilfen
# ============================================================

def _parse_datum(wert: Any) -> Optional[date]:
    """Parst ein ISO-Datum (YYYY-MM-DD). Gibt None zurück wenn unparsbar."""
    if not wert:
        return None
    if isinstance(wert, date) and not isinstance(wert, datetime):
        return wert
    if isinstance(wert, datetime):
        return wert.date()
    try:
        return datetime.strptime(str(wert)[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


# ============================================================
# Laden und Validieren
# ============================================================

def lade_plan(pfad: str) -> 'Plan':
    """
    Lädt plan.json und gibt das validierte Modell zurück.

    Args:
        pfad: Pfad zur Planungsdatei

    Returns:
        Plan-Objekt

    Raises:
        PlanFehler: bei Schema- oder Konsistenzfehlern, fehlender Datei
    """
    if not pfad:
        raise PlanFehler(['Kein Pfad zur Planungsdatei angegeben (PLAN_JSON_PATH).'])

    if not os.path.exists(pfad):
        raise PlanFehler([f'Planungsdatei nicht gefunden: {pfad}'])

    try:
        with open(pfad, 'r', encoding='utf-8') as f:
            rohdaten = json.load(f)
    except json.JSONDecodeError as e:
        raise PlanFehler([f'{pfad} ist kein gültiges JSON: {e}'])
    except OSError as e:
        raise PlanFehler([f'{pfad} konnte nicht gelesen werden: {e}'])

    return pruefe_plan(rohdaten, quelle=pfad)


def pruefe_plan(rohdaten: Any, quelle: str = '<memory>') -> 'Plan':
    """
    Validiert die Rohdaten und reichert sie um berechnete Summen an.

    Getrennt von lade_plan, damit sie ohne Dateizugriff testbar ist.
    """
    fehler: List[str] = []

    if not isinstance(rohdaten, dict):
        raise PlanFehler(['Die Planungsdatei enthält kein Objekt.'])

    if rohdaten.get('schemaVersion') != SCHEMA_VERSION:
        fehler.append(
            f"schemaVersion ist {json.dumps(rohdaten.get('schemaVersion'))}, "
            f"erwartet wird {SCHEMA_VERSION}."
        )

    notenschluessel = _pruefe_notenschluessel(rohdaten.get('notenschluessel'), fehler)
    skalen = _pruefe_skalen(rohdaten.get('skalen'), fehler)
    schienen = _pruefe_schienen(rohdaten.get('schienen'), fehler)
    klassen_zu_schiene = _pruefe_klassenzuordnung(
        rohdaten.get('klassenZuSchiene'), schienen, fehler
    )
    stundenraster = _pruefe_stundenraster(rohdaten.get('stundenraster'), fehler)
    klassen_zu_raster = _pruefe_rasterzuordnung(
        rohdaten.get('klassenZuRaster'), stundenraster, fehler
    )
    kurse = _pruefe_kurse(rohdaten.get('kurse'), skalen, fehler)

    if fehler:
        raise PlanFehler(fehler)

    stunden_gesamt = sum(k['stundenGeplant'] for k in kurse)
    if stunden_gesamt <= 0:
        raise PlanFehler(['Die Summe der geplanten Stunden ist 0 — es gäbe nichts zu messen.'])

    return Plan(
        schema_version=rohdaten['schemaVersion'],
        schuljahr=rohdaten.get('schuljahr'),
        stand=rohdaten.get('stand'),
        notenschluessel=notenschluessel,
        skalen=skalen,
        schienen=schienen,
        klassen_zu_schiene=klassen_zu_schiene,
        stundenraster=stundenraster,
        klassen_zu_raster=klassen_zu_raster,
        kurse=kurse,
        stunden_gesamt=stunden_gesamt,
        quelle=quelle,
    )


def _pruefe_notenschluessel(roh: Any, fehler: List[str]) -> List[Dict]:
    if not isinstance(roh, list) or not roh:
        fehler.append('notenschluessel fehlt oder ist leer.')
        return []

    stufen = []
    for i, s in enumerate(roh):
        if not isinstance(s, dict):
            fehler.append(f'notenschluessel[{i}] ist kein Objekt.')
            continue
        if not isinstance(s.get('note'), (int, float)):
            fehler.append(f'notenschluessel[{i}].note muss eine Zahl sein.')
        if not isinstance(s.get('abProzent'), (int, float)):
            fehler.append(f'notenschluessel[{i}].abProzent muss eine Zahl sein.')
        stufen.append({
            'note': s.get('note'),
            'name': s.get('name'),
            'ab_prozent': s.get('abProzent'),
            'farbe': s.get('farbe'),
        })

    # Absteigend nach Schwelle — percent_to_grade verlässt sich darauf.
    stufen.sort(key=lambda s: s['ab_prozent'] if isinstance(s['ab_prozent'], (int, float)) else -1,
                reverse=True)
    return stufen


def _pruefe_skalen(roh: Any, fehler: List[str]) -> Dict[str, Dict]:
    if not isinstance(roh, dict) or not roh:
        fehler.append('skalen fehlt oder ist leer.')
        return {}

    skalen = {}
    for name, skala in roh.items():
        if not isinstance(skala, dict) or not isinstance(skala.get('stufen'), list):
            fehler.append(f'skalen.{name}.stufen muss eine Liste sein.')
            continue
        stufen = []
        for stufe in skala['stufen']:
            if not isinstance(stufe, dict):
                continue
            stufen.append({
                'wert': stufe.get('wert'),
                'name': stufe.get('name'),
                'prozent': stufe.get('prozent'),
            })
        skalen[name] = {'titel': skala.get('titel', name), 'stufen': stufen}
    return skalen


def _pruefe_schienen(roh: Any, fehler: List[str]) -> Dict[str, Dict]:
    if not isinstance(roh, dict) or not roh:
        fehler.append('schienen fehlt oder ist leer.')
        return {}

    schienen = {}
    for name, schiene in roh.items():
        wochen_roh = schiene.get('schulwochen') if isinstance(schiene, dict) else None
        if not isinstance(wochen_roh, list) or not wochen_roh:
            fehler.append(f'schienen.{name}.schulwochen fehlt oder ist leer.')
            continue

        wochen = []
        for i, w in enumerate(wochen_roh):
            if not isinstance(w, dict):
                fehler.append(f'schienen.{name}.schulwochen[{i}] ist kein Objekt.')
                continue
            start = _parse_datum(w.get('start'))
            if start is None:
                fehler.append(f'schienen.{name}.schulwochen[{i}].start ist kein gültiges Datum.')
            wochen.append({
                'woche': w.get('woche'),
                'start': start,
                'ende': _parse_datum(w.get('ende')),
                'stunden': w.get('stunden') or 0,
            })

        wochen.sort(key=lambda w: (w['start'] or date.min))
        schienen[name] = {'titel': schiene.get('titel', name), 'schulwochen': wochen}
    return schienen


def _pruefe_klassenzuordnung(roh: Any, schienen: Dict, fehler: List[str]) -> Dict[str, str]:
    if not isinstance(roh, dict) or not roh:
        fehler.append('klassenZuSchiene fehlt oder ist leer.')
        return {}

    for klasse, schiene in roh.items():
        if schiene not in schienen:
            fehler.append(
                f'klassenZuSchiene.{klasse} verweist auf unbekannte Schiene "{schiene}".'
            )
    return dict(roh)


def _pruefe_stundenraster(roh: Any, fehler: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Prüft die Stundenraster — Verteilung der Wochenstunden auf Mo–Fr.

    Das Raster gibt nur die Form der Verteilung; die Höhe bleibt die
    Wochensumme aus der Schiene. Es ist optional: ohne Raster zählt eine
    angebrochene Blockwoche wie bisher ganz.
    """
    if roh is None:
        return {}

    if not isinstance(roh, dict):
        fehler.append('stundenraster ist kein Objekt.')
        return {}

    geprueft: Dict[str, Dict[str, float]] = {}

    for name, tage in roh.items():
        if not isinstance(tage, dict):
            fehler.append(f'stundenraster.{name} ist kein Objekt.')
            continue

        eintrag: Dict[str, float] = {}
        summe = 0.0
        gueltig = True

        for tag in RASTER_TAGE:
            wert = tage.get(tag, 0)
            if isinstance(wert, bool) or not isinstance(wert, (int, float)) or wert < 0:
                fehler.append(f'stundenraster.{name}.{tag} ist keine Stundenzahl >= 0.')
                gueltig = False
                continue
            eintrag[tag] = float(wert)
            summe += wert

        if not gueltig:
            continue

        # Ein Raster ohne Stunden könnte das Soll auf null ziehen.
        if summe <= 0:
            fehler.append(f'stundenraster.{name} hat in Summe 0 Stunden.')
            continue

        geprueft[name] = eintrag

    return geprueft


def _pruefe_rasterzuordnung(roh: Any, stundenraster: Dict,
                            fehler: List[str]) -> Dict[str, str]:
    """Prüft die Zuordnung Klasse → Stundenraster."""
    if roh is None:
        return {}

    if not isinstance(roh, dict):
        fehler.append('klassenZuRaster ist kein Objekt.')
        return {}

    for klasse, name in roh.items():
        if name not in stundenraster:
            fehler.append(
                f'klassenZuRaster.{klasse} verweist auf unbekanntes Raster "{name}".'
            )
    return dict(roh)


def _pruefe_kurse(roh: Any, skalen: Dict, fehler: List[str]) -> List[Dict]:
    if not isinstance(roh, list) or not roh:
        fehler.append('kurse fehlt oder ist leer.')
        return []

    kurse = []
    gesehene_cmids = set()

    for i, kurs in enumerate(roh):
        ko = f'kurse[{i}]'
        if not isinstance(kurs, dict):
            fehler.append(f'{ko} ist kein Objekt.')
            continue

        if not kurs.get('id'):
            fehler.append(f'{ko}.id fehlt.')
        if not kurs.get('moodleCourseId'):
            fehler.append(f'{ko}.moodleCourseId fehlt.')
        if kurs.get('gesperrt') is not None and not isinstance(kurs.get('gesperrt'), bool):
            fehler.append(f'{ko}.gesperrt muss true oder false sein.')
        if kurs.get('anzeigen') is not None and not isinstance(kurs.get('anzeigen'), bool):
            fehler.append(f'{ko}.anzeigen muss true oder false sein, wenn angegeben.')

        aufgaben_roh = kurs.get('aufgaben')
        if not isinstance(aufgaben_roh, list) or not aufgaben_roh:
            fehler.append(f'{ko}.aufgaben fehlt oder ist leer.')
            aufgaben_roh = []

        aufgaben = []
        for j, a in enumerate(aufgaben_roh):
            ao = f'{ko}.aufgaben[{j}]'
            if not isinstance(a, dict):
                fehler.append(f'{ao} ist kein Objekt.')
                continue

            cmid = str(a.get('cmid') or '').strip()
            if not cmid:
                fehler.append(f'{ao}.cmid fehlt.')
            elif cmid in gesehene_cmids:
                fehler.append(f'{ao}.cmid {cmid} kommt mehrfach vor.')
            else:
                gesehene_cmids.add(cmid)

            typ = a.get('typ')
            if typ not in AUFGABEN_TYPEN:
                fehler.append(f'{ao}.typ muss einer von {AUFGABEN_TYPEN} sein, ist "{typ}".')

            try:
                stunden = float(a.get('stunden'))
            except (TypeError, ValueError):
                fehler.append(f'{ao}.stunden muss eine Zahl sein.')
                stunden = 0.0
            if stunden <= 0:
                fehler.append(f'{ao}.stunden muss größer als 0 sein.')

            skala = a.get('skala')
            if skala is not None and skala not in skalen:
                fehler.append(f'{ao}.skala verweist auf unbekannte Skala "{skala}".')

            aufgaben.append({
                'cmid': cmid,
                'typ': typ,
                'titel': a.get('titel', ''),
                'lektion': a.get('lektion', ''),
                'stunden': stunden,
                'skala': skala,
                'kurs_id': kurs.get('id'),
                'moodle_course_id': str(kurs.get('moodleCourseId') or ''),
            })

        kurse.append({
            'id': kurs.get('id'),
            'moodle_course_id': str(kurs.get('moodleCourseId') or ''),
            'titel': kurs.get('titel', kurs.get('id')),
            'gesperrt': kurs.get('gesperrt') is True,
            'anzeigen': kurs.get('anzeigen') is not False,
            'freischaltung': _parse_datum(kurs.get('freischaltung')),
            'aufgaben': aufgaben,
            'stundenGeplant': sum(a['stunden'] for a in aufgaben),
        })

    return kurse


# ============================================================
# Rechenfunktionen — portiert aus js/bilanz.js
# ============================================================

def aktuelle_woche(schulwochen: List[Dict], heute: Optional[date] = None) -> int:
    """
    Ermittelt die laufende Schulwoche zu einem Datum.

    Blockwochen liegen weit auseinander. Zwischen zwei Blöcken gilt der
    Stand des zuletzt abgeschlossenen Blocks; innerhalb eines Blocks
    zählt dieser bereits mit.

    Returns:
        Wochennummer, 0 vor Beginn der ersten Blockwoche
    """
    stichtag = heute or date.today()
    aktuell = 0
    for woche in schulwochen:
        if woche['start'] and woche['start'] <= stichtag:
            aktuell = woche['woche']
        else:
            break
    return aktuell


def ist_im_block(schulwochen: List[Dict], woche: int, heute: Optional[date] = None) -> bool:
    """Läuft der Block der Woche gerade, oder liegt er schon hinter uns?"""
    eintrag = next((w for w in schulwochen if w['woche'] == woche), None)
    if not eintrag or not eintrag['start']:
        return False

    stichtag = heute or date.today()
    if stichtag < eintrag['start']:
        return False
    if not eintrag['ende']:
        return True
    return stichtag <= eintrag['ende']


def soll_anteil(schulwochen: List[Dict], woche: int,
                raster: Optional[Dict[str, float]] = None,
                heute: Optional[date] = None) -> float:
    """
    Soll(w) — Anteil der bis einschließlich Woche w verstrichenen Stunden.

        Soll(w) = Σ Stunden Schulwoche 1..w / Σ Stunden gesamt

    Bewusst nicht w / anzahl_wochen: Woche 1 hat 10 Stunden, die übrigen 14.

    Mit Raster und Stichtag zählt die laufende Blockwoche nur anteilig: am
    Dienstag einer Blockwoche sind eben noch nicht alle 14 Stunden gehalten.
    Ohne Raster bleibt es beim alten Verhalten — die angebrochene Woche
    zählt ganz.

    Args:
        schulwochen: Wochenkalender der Schiene
        woche: laufende Wochennummer
        raster: {mo..fr: Stunden} der Klasse, oder None
        heute: Stichtag; ohne ihn greift das Raster nicht
    """
    gesamt = sum(w['stunden'] for w in schulwochen)
    if gesamt <= 0:
        return 0.0

    bisher = sum(
        w['stunden'] for w in schulwochen
        if w['woche'] is not None and w['woche'] < woche
    )

    laufende = next((w for w in schulwochen if w['woche'] == woche), None)
    if laufende is None:
        return bisher / gesamt

    return (bisher + _anteil_laufende_woche(laufende, raster, heute)) / gesamt


def _anteil_laufende_woche(woche: Dict, raster: Optional[Dict[str, float]],
                           heute: Optional[date]) -> float:
    """
    Stunden der laufenden Blockwoche, die bis zum Stichtag gehalten sind.

    Das Raster gibt die Form der Verteilung, die Wochensumme aus dem Plan
    die Höhe: gerechnet wird anteilig, damit eine verkürzte erste Woche
    (10 statt 14 Stunden) nicht mehr ausweist als sie hat. Tage außerhalb
    von start–ende zählen nicht mit — so fällt der fehlende Montag einer
    am Dienstag beginnenden Woche von selbst heraus.
    """
    stunden = woche['stunden'] or 0

    # Ohne Raster oder Stichtag bleibt es beim alten Verhalten.
    if not raster or heute is None:
        return stunden

    beginn = woche['start']
    ende = woche['ende']
    if beginn is None:
        return stunden
    if heute < beginn:
        return 0.0
    if ende and heute >= ende:
        return stunden

    summe_woche = 0.0
    summe_bis_heute = 0.0

    # Ohne Endedatum gilt die Woche als Mo–Fr ab Beginn.
    letzter = ende or (beginn + timedelta(days=4))

    tag = beginn
    schutz = 0
    while tag <= letzter and schutz < 7:
        wert = raster.get(_WOCHENTAG_SCHLUESSEL.get(tag.weekday(), ''), 0)
        summe_woche += wert
        if tag <= heute:
            summe_bis_heute += wert
        tag += timedelta(days=1)
        schutz += 1

    # Ein Raster, das für diese Woche nichts hergibt, darf das Soll nicht
    # auf null ziehen — dann lieber die volle Wochensumme.
    if summe_woche <= 0:
        return stunden

    return (summe_bis_heute / summe_woche) * stunden


def begrenze_schulwochen(schulwochen: List[Dict], kurse: List[Dict],
                         alle_kurse: List[Dict]) -> List[Dict]:
    """
    Beschneidet den Wochenkalender auf die angezeigten Kurse.

    Wird nur das 1. Halbjahr gezeigt, darf sich das Soll nicht auf
    Blockwochen stützen, die zum ausgeblendeten 2. Halbjahr gehören.
    Sind alle Kurse sichtbar, bleibt der Kalender ganz.
    """
    if not schulwochen or len(kurse) >= len(alle_kurse):
        return list(schulwochen)

    sichtbare_ids = {k['id'] for k in kurse}
    # Erster ausgeblendeter Kurs mit Freischaltdatum bildet die obere Grenze.
    grenze = None
    for kurs in alle_kurse:
        if kurs['id'] not in sichtbare_ids and kurs.get('freischaltung'):
            if grenze is None or kurs['freischaltung'] < grenze:
                grenze = kurs['freischaltung']

    if grenze is None:
        return list(schulwochen)

    return [w for w in schulwochen if w['start'] and w['start'] < grenze]


def verteile_unterrichtsstunden(kurse: List[Dict], schulwochen: List[Dict]) -> Dict[str, float]:
    """
    Ordnet jeder Schulwoche einen Kurs zu und summiert die Stunden je Kurs.

    Grenzen aus den Freischaltdaten: jeder Kurs mit Datum eröffnet einen
    neuen Zeitraum, der bis zum nächsten Datum reicht. Nur der erste Kurs
    darf ohne Datum auskommen — er beginnt mit dem Schuljahr.

    Returns:
        {kurs_id: stunden} oder {} wenn die Zuordnung nicht eindeutig ist
    """
    verteilung: Dict[str, float] = {}
    if not schulwochen or not kurse:
        return verteilung

    grenzen = [{'id': k['id'], 'ab': k.get('freischaltung')} for k in kurse]

    if any(g['ab'] is None for g in grenzen[1:]):
        logger.warning(
            'verteile_unterrichtsstunden: Kurs ohne freischaltung nach dem ersten — '
            'Zuordnung nicht eindeutig, Verteilung bleibt leer.'
        )
        return verteilung

    for g in grenzen:
        verteilung[g['id']] = 0.0

    for woche in schulwochen:
        if not woche['start']:
            continue
        treffer = grenzen[0]
        for g in grenzen:
            if g['ab'] and woche['start'] >= g['ab']:
                treffer = g
        verteilung[treffer['id']] += woche['stunden'] or 0

    return verteilung


# ============================================================
# Plan-Objekt
# ============================================================

class Plan:
    """Validierter Plan mit Zugriffshilfen."""

    def __init__(self, schema_version, schuljahr, stand, notenschluessel, skalen,
                 schienen, klassen_zu_schiene, kurse, stunden_gesamt, quelle,
                 stundenraster=None, klassen_zu_raster=None):
        self.schema_version = schema_version
        self.schuljahr = schuljahr
        self.stand = stand
        self.notenschluessel = notenschluessel
        self.skalen = skalen
        self.schienen = schienen
        self.klassen_zu_schiene = klassen_zu_schiene
        self.stundenraster = stundenraster or {}
        self.klassen_zu_raster = klassen_zu_raster or {}
        self.kurse = kurse
        self.stunden_gesamt = stunden_gesamt
        self.quelle = quelle

        # cmid → Aufgabe, über alle Kurse. Bestimmt, was Pflichtaufgabe ist.
        self._aufgaben_nach_cmid: Dict[str, Dict] = {}
        for kurs in kurse:
            for aufgabe in kurs['aufgaben']:
                self._aufgaben_nach_cmid[aufgabe['cmid']] = aufgabe

    # --- Kurse ---

    def get_kurse(self, nur_sichtbare: bool = False,
                  nur_offene: bool = False) -> List[Dict]:
        """
        Args:
            nur_sichtbare: nur Kurse mit anzeigen=true
            nur_offene: nur Kurse mit gesperrt=false (scrapebar)
        """
        kurse = self.kurse
        if nur_sichtbare:
            kurse = [k for k in kurse if k['anzeigen']]
        if nur_offene:
            kurse = [k for k in kurse if not k['gesperrt']]
        return list(kurse)

    def get_kurs(self, kurs_id: str) -> Optional[Dict]:
        return next((k for k in self.kurse if k['id'] == kurs_id), None)

    def get_kurs_by_moodle_id(self, moodle_course_id: str) -> Optional[Dict]:
        moodle_course_id = str(moodle_course_id)
        return next(
            (k for k in self.kurse if k['moodle_course_id'] == moodle_course_id), None
        )

    # --- Aufgaben ---

    def get_aufgabe(self, cmid: Any) -> Optional[Dict]:
        """Aufgabe zur cmid, oder None wenn sie nicht im Plan steht."""
        return self._aufgaben_nach_cmid.get(str(cmid).strip())

    def ist_pflichtaufgabe(self, cmid: Any) -> bool:
        """
        Eine Aktivität ist genau dann Pflichtaufgabe, wenn ihre cmid im Plan steht.

        Ersetzt die frühere Prüfung auf den Kategorienamen. Nur über den Plan
        kommt man an das stunden-Feld, das die Gewichtung trägt.
        """
        return str(cmid).strip() in self._aufgaben_nach_cmid

    def get_alle_aufgaben(self) -> List[Dict]:
        return [a for k in self.kurse for a in k['aufgaben']]

    def get_stunden(self, cmid: Any) -> float:
        aufgabe = self.get_aufgabe(cmid)
        return aufgabe['stunden'] if aufgabe else 0.0

    # --- Schienen und Klassen ---

    def get_track_for_class(self, klasse: str) -> Optional[str]:
        """
        Schiene zu einer Klasse.

        Nimmt den Gruppennamen in jeder Form entgegen: Moodle liefert
        "K - IFA12A (6072)", frühere Kurse "IFA12A - Team 1" oder
        schlicht "IFA12A". Das Klassenkürzel wird per Muster gezogen.

        Returns:
            Schienenname, oder None wenn die Klasse nicht im Plan steht
            (fremde Klassen im selben Kurs werden so ausgesteuert).
        """
        if not klasse:
            return None
        if klasse in self.klassen_zu_schiene:
            return self.klassen_zu_schiene[klasse]
        kuerzel = extract_group_prefix(klasse)
        return self.klassen_zu_schiene.get(kuerzel)

    def get_schulwochen(self, track: str) -> List[Dict]:
        schiene = self.schienen.get(track)
        return list(schiene['schulwochen']) if schiene else []

    def get_raster_for_class(self, klasse: str) -> Optional[Dict[str, float]]:
        """
        Stundenraster zu einer Klasse.

        Nimmt den Gruppennamen in jeder Form entgegen — wie
        get_track_for_class. Ohne Eintrag gibt es kein Raster; die
        laufende Blockwoche zählt dann wie bisher ganz.
        """
        if not klasse or not self.klassen_zu_raster:
            return None
        name = self.klassen_zu_raster.get(klasse)
        if name is None:
            name = self.klassen_zu_raster.get(extract_group_prefix(klasse))
        return self.stundenraster.get(name) if name else None

    # --- Noten ---

    def percent_to_grade(self, prozent: Optional[float]) -> Optional[int]:
        """Prozentwert → IHK-Note über den Notenschlüssel."""
        if prozent is None:
            return None
        for stufe in self.notenschluessel:  # absteigend sortiert
            if prozent >= stufe['ab_prozent']:
                return stufe['note']
        return self.notenschluessel[-1]['note'] if self.notenschluessel else None

    def skala_to_percent(self, skala_name: str, text: str) -> Optional[float]:
        """Bewertungstext einer Skala (z.B. "*** Solide Umsetzung") → Prozent."""
        skala = self.skalen.get(skala_name)
        if not skala or not text:
            return None
        normalisiert = text.strip().lstrip('*').strip().lower()
        for stufe in skala['stufen']:
            if stufe['name'] and stufe['name'].strip().lower() == normalisiert:
                return stufe['prozent']
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialisierbare Fassung für /api/data — was das Frontend braucht."""
        def _iso(d):
            return d.isoformat() if isinstance(d, date) else None

        return {
            'schema_version': self.schema_version,
            'schuljahr': self.schuljahr,
            'stand': self.stand,
            'stunden_gesamt': self.stunden_gesamt,
            'notenschluessel': self.notenschluessel,
            'skalen': self.skalen,
            'klassen_zu_schiene': self.klassen_zu_schiene,
            'stundenraster': self.stundenraster,
            'klassen_zu_raster': self.klassen_zu_raster,
            'schienen': {
                name: {
                    'titel': s['titel'],
                    'schulwochen': [
                        {
                            'woche': w['woche'],
                            'start': _iso(w['start']),
                            'ende': _iso(w['ende']),
                            'stunden': w['stunden'],
                        }
                        for w in s['schulwochen']
                    ],
                }
                for name, s in self.schienen.items()
            },
            'kurse': [
                {
                    'id': k['id'],
                    'moodle_course_id': k['moodle_course_id'],
                    'titel': k['titel'],
                    'gesperrt': k['gesperrt'],
                    'anzeigen': k['anzeigen'],
                    'freischaltung': _iso(k['freischaltung']),
                    'stunden_geplant': k['stundenGeplant'],
                    'aufgaben': [
                        {
                            'cmid': a['cmid'],
                            'typ': a['typ'],
                            'titel': a['titel'],
                            'lektion': a['lektion'],
                            'stunden': a['stunden'],
                            'skala': a['skala'],
                        }
                        for a in k['aufgaben']
                    ],
                }
                for k in self.kurse
            ],
        }


# ============================================================
# Modulweiter Zugriff
# ============================================================

_plan_cache: Optional[Plan] = None


def get_plan(pfad: Optional[str] = None, reload: bool = False) -> Plan:
    """
    Liefert den geladenen Plan (gecacht).

    Args:
        pfad: überschreibt PLAN_JSON_PATH
        reload: erzwingt Neuladen
    """
    global _plan_cache
    if _plan_cache is not None and not reload and pfad is None:
        return _plan_cache

    if pfad is None:
        from config.config_manager import config_manager
        pfad = config_manager.get_plan_json_path()

    plan = lade_plan(pfad)
    if pfad is not None:
        _plan_cache = plan
    logger.info(
        'Plan geladen: %s Kurse, %s Aufgaben, %.2f Stunden (%s)',
        len(plan.kurse), len(plan.get_alle_aufgaben()), plan.stunden_gesamt, plan.quelle
    )
    return plan
