#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Entry point für den Schüler-Übersichtsbericht Generator.

Generiert pro Schüler eine PDF-Übersicht mit Pflichtaufgaben und
Leistungsnachweisen nach data/report/{Klasse}/.

Verwendung:
    python scripts/generate_reports.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.report.report_generator import main

if __name__ == '__main__':
    main()
