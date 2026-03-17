#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Entry point für den Schüler-Übersichtsbericht Generator.

Generiert pro Schüler eine PDF-Übersicht mit Pflichtaufgaben und
Leistungsnachweisen nach data/report/{Klasse}/.

Verwendung:
    python scripts/generate_reports.py
    python scripts/generate_reports.py --cutoff-date 2025-12-10
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.report.report_generator import ReportGenerator


def main():
    parser = argparse.ArgumentParser(description='Schüler-Übersichtsberichte generieren')
    parser.add_argument(
        '--cutoff-date',
        metavar='YYYY-MM-DD',
        default=None,
        help='Referenztermin für Pflichtaufgaben-Filter (überschreibt CLASS_TO_TRACK). '
             'Nur Abgaben NACH diesem Datum werden angezeigt.'
    )
    args = parser.parse_args()

    ReportGenerator().run(cutoff_date_override=args.cutoff_date)


if __name__ == '__main__':
    main()
