#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Entry point for Data Exporter

Usage:
    python scripts/export_data.py          # Normaler Export
    python scripts/export_data.py --test   # Testmodus (nur 5 Items pro Typ)
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.export.exporter import main

if __name__ == '__main__':
    test_mode = '--test' in sys.argv
    main(test_mode=test_mode)
