#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Entry point for Exam Scraper
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exam.scraper import main

if __name__ == '__main__':
    main()
