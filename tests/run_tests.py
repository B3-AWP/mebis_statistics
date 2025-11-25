#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test Runner für Mebis Dashboard

Führt alle Unit Tests aus und zeigt Ergebnisse an.
"""

import unittest
import sys
import os
from pathlib import Path

# Füge das Projekt-Root zum Python-Path hinzu
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from logger_config import get_logger

logger = get_logger('tests')

def run_all_tests():
    """
    Führt alle Tests aus

    Returns:
        bool: True wenn alle Tests erfolgreich
    """
    logger.info("Starting test suite execution")

    # Test-Discovery
    loader = unittest.TestLoader()
    start_dir = 'tests'

    try:
        suite = loader.discover(start_dir, pattern='test_*.py')
    except Exception as e:
        logger.error(f"Failed to discover tests: {e}")
        return False

    # Test-Runner mit detaillierter Ausgabe
    runner = unittest.TextTestRunner(
        verbosity=2,
        stream=sys.stdout,
        buffer=True
    )

    # Tests ausführen
    try:
        result = runner.run(suite)

        # Ergebnisse loggen
        tests_run = result.testsRun
        failures = len(result.failures)
        errors = len(result.errors)
        skipped = len(result.skipped)

        logger.info(f"Test results: {tests_run} tests run")
        logger.info(f"  Successful: {tests_run - failures - errors}")
        logger.info(f"  Failures: {failures}")
        logger.info(f"  Errors: {errors}")
        logger.info(f"  Skipped: {skipped}")

        # Zeige Fehler-Details
        if result.failures:
            logger.error("Test failures:")
            for test, traceback in result.failures:
                logger.error(f"  {test}: {traceback}")

        if result.errors:
            logger.error("Test errors:")
            for test, traceback in result.errors:
                logger.error(f"  {test}: {traceback}")

        # Success nur wenn keine Fehler oder Failures
        success = len(result.failures) == 0 and len(result.errors) == 0

        if success:
            logger.info("All tests passed successfully! ✅")
        else:
            logger.error("Some tests failed! ❌")

        return success

    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        return False

def run_specific_test(test_module: str):
    """
    Führt einen spezifischen Test aus

    Args:
        test_module: Name des Test-Moduls (z.B. 'test_grade_calculator')
    """
    logger.info(f"Running specific test: {test_module}")

    try:
        # Importiere und führe spezifischen Test aus
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName(f'tests.{test_module}')

        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)

        return len(result.failures) == 0 and len(result.errors) == 0

    except Exception as e:
        logger.error(f"Failed to run test {test_module}: {e}")
        return False

def main():
    """Hauptfunktion"""
    import argparse

    parser = argparse.ArgumentParser(description='Run Mebis Dashboard Tests')
    parser.add_argument(
        '--test',
        help='Run specific test module (e.g., test_grade_calculator)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Setup Logging für Tests
    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        if args.test:
            success = run_specific_test(args.test)
        else:
            success = run_all_tests()

        # Exit-Code setzen
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Test runner failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()