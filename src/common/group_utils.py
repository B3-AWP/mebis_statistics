#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Common utilities for group handling
"""


def extract_group_prefix(group_name: str) -> str:
    """
    Extrahiert den Präfix aus dem Gruppennamen

    Args:
        group_name: Vollständiger Gruppenname (z.B. "IFA12A - Team 3")

    Returns:
        str: Nur der Präfix (z.B. "IFA12A")

    Beispiele:
        "IFA12A - Team 3" -> "IFA12A"
        "IFA12A" -> "IFA12A"
        "IFA12B-Team1" -> "IFA12B-Team1" (kein " - " mit Leerzeichen)
    """
    if not group_name:
        return ''

    # Suche nach " - " (Leerzeichen-Minus-Leerzeichen)
    if ' - ' in group_name:
        return group_name.split(' - ')[0].strip()

    # Falls kein Präfix gefunden, gib vollständigen Namen zurück
    return group_name.strip()
