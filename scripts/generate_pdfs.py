#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Entry point for PDF Generator
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.exam.pdf_generator import main

if __name__ == '__main__':
    main()
