#!/usr/bin/env python3
"""
Vergleicht zwei Exporte (Schema 3) — für den Parallelbetrieb von
Python-Export (scripts/export_data.py) und Browser-Export (bycs/export).

Beide direkt nacheinander erzeugen, sonst liegen echte Abgaben dazwischen.
Verglichen werden Kurse, Aktivitäten (Kategorie, Bewertungs-ID, Gruppe),
Gruppenmitglieder und je Person und Aktivität Status, Bewertung,
Abgabezeit und "unbekannt". Ausgegeben werden IDs, keine Namen.

    python -X utf8 tests/vergleiche_exporte.py python.json browser.json
    python -X utf8 tests/vergleiche_exporte.py a.json b.json --max 50

Exit-Code 0 = keine Abweichung, 1 = Abweichungen.
"""
import argparse
import json
import re
import sys
from collections import Counter


def _norm(wert):
    """Leerraum vereinheitlichen: Selenium (.text) und DOMParser (textContent)
    unterscheiden sich darin, nicht im Inhalt."""
    if isinstance(wert, str):
        return re.sub(r'\s+', ' ', wert).strip()
    return wert


def _zeige(wert):
    """Wert fuer die Ausgabe. Laengere Texte werden maskiert: Eine Bewertung
    ist kurz ("80,00", "*** Solide Umsetzung"); ein langer Text ist ein
    Lesefehler und kann Namen enthalten (so geschehen mit dem versteckten
    Hilfstext der Bewerterübersicht)."""
    if isinstance(wert, str) and len(wert.split()) > 3:
        return f'<Text, {len(wert.split())} Wörter>'
    return repr(wert)


def _aktivitaeten(export):
    erg = {}
    for kid, kurs in export.get('kurse', {}).items():
        for kat in kurs.get('activities_by_category', []):
            for typ in ('assignments', 'quizzes'):
                for a in kat.get(typ, []):
                    erg[(kid, str(a['id']))] = {
                        'typ': typ,
                        'kategorie': a.get('category_id'),
                        'bewertungs_id': a.get('grade_item_id'),
                        'gruppen': a.get('groups'),
                    }
    return erg


def _personen(export):
    """{(gruppe, user_id): {(typ, cmid): status}}"""
    erg = {}
    for g in export.get('groups', []):
        for u in g.get('users', []):
            eintraege = {}
            for typ in ('assignments', 'quizzes'):
                for a in u.get('activities', {}).get(typ, []):
                    s = a.get('status') or {}
                    eintraege[(typ, str(a['id']))] = {
                        'status': _norm(s.get('status')),
                        'status2': _norm(s.get('status2')),
                        'grade': _norm(s.get('grade')),
                        'submission_time': s.get('submission_time'),
                        'unbekannt': bool(s.get('unbekannt')),
                    }
            erg[(g.get('name'), str(u.get('id')))] = eintraege
    return erg


def vergleiche(a, b):
    """Liefert (Abweichungen, Zusammenfassung)."""
    abw = []
    for name, ex in (('A', a), ('B', b)):
        if ex.get('schema') != 3:
            abw.append(('schema', f"{name} hat Schema {ex.get('schema')!r}, erwartet 3"))

    ka, kb = set(a.get('kurse', {})), set(b.get('kurse', {}))
    for k in sorted(ka ^ kb):
        abw.append(('kurs', f"Kurs {k} nur in {'A' if k in ka else 'B'}"))

    aa, ab = _aktivitaeten(a), _aktivitaeten(b)
    for key in sorted(set(aa) | set(ab)):
        if key not in aa or key not in ab:
            abw.append(('aktivität', f"Kurs {key[0]} cmid {key[1]} nur in {'A' if key in aa else 'B'}"))
            continue
        for feld in ('kategorie', 'bewertungs_id', 'gruppen'):
            if aa[key][feld] != ab[key][feld]:
                abw.append(('aktivität', f"cmid {key[1]} {feld}: A={aa[key][feld]!r} B={ab[key][feld]!r}"))

    pa, pb = _personen(a), _personen(b)
    for key in sorted(set(pa) | set(pb)):
        if key not in pa or key not in pb:
            abw.append(('person', f"Gruppe {key[0]!r} Person {key[1]} nur in {'A' if key in pa else 'B'}"))
            continue
        ea, eb = pa[key], pb[key]
        for akt in sorted(set(ea) | set(eb)):
            if akt not in ea or akt not in eb:
                abw.append(('eintrag', f"Person {key[1]} {akt[0]} {akt[1]} nur in {'A' if akt in ea else 'B'}"))
                continue
            for feld, wa in ea[akt].items():
                if wa != eb[akt][feld]:
                    abw.append((f'feld:{feld}', f"Person {key[1]} {akt[0]} {akt[1]} {feld}: "
                                                f"A={_zeige(wa)} B={_zeige(eb[akt][feld])}"))

    zusammenfassung = {
        'personen': (len(pa), len(pb)),
        'aktivitäten': (len(aa), len(ab)),
        'einträge': (sum(len(e) for e in pa.values()), sum(len(e) for e in pb.values())),
        'lücken': (len((a.get('pruefbericht') or {}).get('luecken', [])),
                   len((b.get('pruefbericht') or {}).get('luecken', []))),
    }
    return abw, zusammenfassung


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('a', help='erster Export (z.B. Python)')
    ap.add_argument('b', help='zweiter Export (z.B. Browser)')
    ap.add_argument('--max', type=int, default=30, help='höchstens so viele Einzelabweichungen zeigen')
    args = ap.parse_args()

    with open(args.a, encoding='utf-8') as f:
        a = json.load(f)
    with open(args.b, encoding='utf-8') as f:
        b = json.load(f)

    abw, zus = vergleiche(a, b)
    print(f"A: {args.a}\nB: {args.b}\n")
    for k, (x, y) in zus.items():
        print(f"  {k:12} A={x:<6} B={y:<6}{'' if x == y else '  ≠'}")
    print()
    if not abw:
        print("Keine Abweichungen.")
        return 0
    print(f"{len(abw)} Abweichung(en) nach Art:")
    for art, n in Counter(art for art, _ in abw).most_common():
        print(f"  {art:24} {n}")
    print(f"\nErste {min(args.max, len(abw))}:")
    for _, text in abw[:args.max]:
        print(f"  {text}")
    return 1


if __name__ == '__main__':
    sys.exit(main())
