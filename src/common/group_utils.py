#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Common utilities for group handling
"""

import re

# Klassenkürzel wie IFA12A, IF11J, BFI10C: Buchstaben, zwei Ziffern,
# ein Buchstabe. Moodle liefert die Gruppen je nach Kursanlage in sehr
# unterschiedlicher Form ("K - IFA12A (6072)", "IFA12A - Team 3",
# "IFA12A"); das Kürzel selbst bleibt dabei gleich.
_KLASSEN_MUSTER = re.compile(r'\b([A-Z]{2,4}\d{2}[A-Z])\b')


def extract_group_prefix(group_name: str) -> str:
    """
    Extrahiert das Klassenkürzel aus einem Moodle-Gruppennamen.

    Gesucht wird das Kürzel als Muster irgendwo im Namen, nicht als
    Präfix bis zum ersten Trenner. Der Moodle-Kurs 2026/27 liefert
    "K - IFA12A (6072)"; eine Präfix-Regel ergäbe dort "K" für jede
    Klasse und damit keine Schienenzuordnung mehr.

    Args:
        group_name: Vollständiger Gruppenname

    Returns:
        str: Das Klassenkürzel, oder der bereinigte Name wenn keines
             gefunden wird (z.B. "Testgruppe", "IT_Lehrkraft")

    Beispiele:
        "K - IFA12A (6072)" -> "IFA12A"
        "IFA12A - Team 3"   -> "IFA12A"
        "IFA12A"            -> "IFA12A"
        "Testgruppe"        -> "Testgruppe"
    """
    if not group_name:
        return ''

    treffer = _KLASSEN_MUSTER.search(group_name)
    if treffer:
        return treffer.group(1)

    # Kein Klassenkürzel: Alt-Format mit " - " weiter unterstützen,
    # sonst den Namen unverändert zurückgeben.
    if ' - ' in group_name:
        return group_name.split(' - ')[0].strip()

    return group_name.strip()
