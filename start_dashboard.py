#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Startskript für das Mebis Statistik Dashboard

Dieses Skript startet das Dashboard mit automatischer Erkennung
von Development/Production-Modi.
"""

import subprocess
import sys
import os
import webbrowser
import time
import threading
from pathlib import Path

# Sichere Konfiguration und Logging
from config.config_manager import config_manager
from config.logger_config import get_logger

# Logger für das Startskript
logger = get_logger('startup')

def check_environment():
    """
    Überprüft und bereitet die Umgebung vor

    Returns:
        bool: True wenn alles bereit ist
    """
    logger.info("Checking environment and dependencies...")

    # Prüfe ob .env Datei existiert
    if not Path('.env').exists():
        logger.warning(".env file not found. Using config/config.ini fallback.")
        if not Path('config/config.ini').exists():
            logger.error("Neither .env nor config/config.ini found!")
            logger.error("Please copy .env.template to .env and configure your credentials.")
            return False

    # Prüfe Export-Ordner
    export_folder = Path("export")
    if not export_folder.exists():
        logger.error("Export folder not found!")
        logger.error("Please ensure the 'export' folder with JSON files exists.")
        return False

    json_files = list(export_folder.glob("output_*.json"))
    if not json_files:
        logger.error("No export files found!")
        logger.error("Please run the data export first to generate JSON files.")
        return False

    latest_file = max(json_files, key=os.path.getctime)
    logger.info(f"Export data found: {latest_file.name}")

    return True

def install_requirements():
    """
    Installiert die benötigten Python-Pakete

    Returns:
        bool: True wenn erfolgreich
    """
    logger.info("Checking Python dependencies...")

    try:
        requirements_file = Path("requirements.txt")
        if requirements_file.exists():
            logger.info("Installing dependencies...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            logger.info("Dependencies installed successfully")
        else:
            logger.error("requirements.txt not found")
            return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install dependencies: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error installing dependencies: {e}")
        return False

    return True

def check_credentials():
    """
    Überprüft ob Login-Credentials verfügbar sind

    Returns:
        bool: True wenn Credentials verfügbar
    """
    try:
        credentials = config_manager.get_login_credentials()
        logger.info("Login credentials found")
        return True
    except ValueError as e:
        logger.error(f"Credential error: {e}")
        logger.error("Please set MEBIS_USERNAME and MEBIS_PASSWORD environment variables")
        logger.error("or configure them in config/config.ini")
        return False

def open_browser_delayed():
    """Öffnet den Browser nach kurzer Verzögerung"""
    flask_config = config_manager.get_flask_config()
    url = f"http://{flask_config['host']}:{flask_config['port']}"

    time.sleep(3)  # Warten bis der Server gestartet ist
    logger.info(f"Opening browser: {url}")
    webbrowser.open(url)

def start_secure_backend():
    """Startet das Backend"""
    try:
        logger.info("Starting dashboard backend...")
        from dashboard_backend import app

        flask_config = config_manager.get_flask_config()

        app.run(
            debug=flask_config['debug'],
            host=flask_config['host'],
            port=flask_config['port']
        )

    except ImportError as e:
        logger.error(f"Import error: {e}")
        logger.error("Make sure dashboard_backend.py is available.")
        return False
    except Exception as e:
        logger.error(f"Error starting dashboard: {e}")
        return False

    return True

def main():
    """Hauptfunktion mit verbesserter Fehlerbehandlung"""
    print("=" * 60)
    print("         MEBIS STATISTIK DASHBOARD")
    print("=" * 60)
    print()

    # Umgebung überprüfen
    if not check_environment():
        logger.error("Environment check failed.")
        input("Press Enter to exit...")
        return 1

    # Dependencies installieren
    if not install_requirements():
        logger.error("Dependency installation failed.")
        input("Press Enter to exit...")
        return 1

    # Credentials überprüfen
    if not check_credentials():
        logger.error("Credential check failed.")
        input("Press Enter to exit...")
        return 1

    # Flask-Konfiguration laden
    flask_config = config_manager.get_flask_config()

    # Browser-Thread starten (nur in Development)
    if flask_config['debug'] or flask_config['env'] == 'development':
        browser_thread = threading.Thread(target=open_browser_delayed)
        browser_thread.daemon = True
        browser_thread.start()
        logger.info("Browser will open automatically...")

    # Startup-Informationen
    logger.info("Dashboard starting...")
    logger.info(f"Mode: {flask_config['env'].upper()}")
    logger.info(f"Debug: {flask_config['debug']}")
    logger.info(f"Available at: http://{flask_config['host']}:{flask_config['port']}")
    logger.info("Press Ctrl+C to stop the dashboard")
    print("-" * 60)

    try:
        # Dashboard starten
        success = start_secure_backend()
        if not success:
            return 1

    except KeyboardInterrupt:
        logger.info("Dashboard stopped by user.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

    logger.info("Dashboard shutdown complete.")
    return 0

if __name__ == "__main__":
    sys.exit(main())