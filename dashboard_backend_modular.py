#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mebis Statistik Dashboard - Modulares Backend
Version 2.0 - Vollständig refactored mit Service-Architektur

Ersetzt dashboard_backend.py mit einer sauberen, modularen Architektur:
- Models: Datenstrukturen und Validierung
- Services: Business Logic
- API: HTTP-Endpoints und Validierung
- Utils: Hilfsfunktionen
"""

from flask import Flask, send_from_directory
from flask_cors import CORS

# Sichere Konfiguration und Logging
from config_manager import config_manager
from logger_config import get_logger

# Modulares Backend
from backend.api import create_api_blueprint

# Logger für diese Anwendung
logger = get_logger('app')

def create_app() -> Flask:
    """
    Factory-Funktion zur Erstellung der Flask-App

    Returns:
        Konfigurierte Flask-Anwendung
    """
    logger.info("Creating Flask application")

    # Flask App erstellen
    app = Flask(__name__, static_folder='.')

    # CORS aktivieren
    CORS(app)

    # Flask Konfiguration aus Environment Variables
    flask_config = config_manager.get_flask_config()
    app.config.update({
        'DEBUG': flask_config['debug'],
        'SECRET_KEY': flask_config['secret_key'],
        'ENV': flask_config['env'],
        'TESTING': False
    })

    # API Blueprint registrieren
    api_blueprint = create_api_blueprint()
    app.register_blueprint(api_blueprint)

    # Statische Dateien
    @app.route('/')
    def index():
        """Serviert die Dashboard HTML-Datei"""
        return send_from_directory('.', 'dashboard.html')

    @app.route('/<path:filename>')
    def static_files(filename):
        """Serviert statische Dateien"""
        # Sicherheitscheck: Verhindere Directory Traversal
        if '..' in filename or filename.startswith('/'):
            logger.warning(f"Blocked suspicious file request: {filename}")
            return "Access denied", 403

        return send_from_directory('.', filename)

    # Globale Error Handler
    @app.errorhandler(404)
    def not_found(error):
        """Global 404 Handler"""
        logger.warning(f"404 Not Found: {error}")
        return {"error": "Resource not found"}, 404

    @app.errorhandler(500)
    def internal_error(error):
        """Global 500 Handler"""
        logger.error(f"Internal Server Error: {error}", exc_info=True)
        return {"error": "Internal server error"}, 500

    # Startup-Validierung
    try:
        # Teste Konfiguration
        config_manager.get_login_credentials()
        logger.info("Configuration validated successfully")

        # Teste Services (optional)
        from backend.services.data_service import DataService
        data_service = DataService()

        # Versuche Export-Datei zu finden (ohne zu laden)
        try:
            latest_file = data_service.find_latest_export_file()
            if latest_file:
                logger.info(f"Export data available: {latest_file}")
            else:
                logger.warning("No export data found - some features may not work")
        except Exception as e:
            logger.warning(f"Export data check failed: {e}")

    except Exception as e:
        logger.error(f"Startup validation failed: {e}")
        # App trotzdem starten, aber warnen
        logger.warning("Starting app despite validation issues")

    logger.info("Flask application created successfully")
    return app

# Globale App-Instanz
app = create_app()

def main():
    """
    Hauptfunktion für direkten Start

    Für Produktion sollte ein WSGI-Server verwendet werden.
    """
    flask_config = config_manager.get_flask_config()

    logger.info("=" * 60)
    logger.info("    MEBIS STATISTIK DASHBOARD - MODULAR BACKEND")
    logger.info("=" * 60)
    logger.info(f"Version: 2.0 (Modular Architecture)")
    logger.info(f"Environment: {flask_config['env'].upper()}")
    logger.info(f"Debug Mode: {flask_config['debug']}")
    logger.info(f"Host: {flask_config['host']}")
    logger.info(f"Port: {flask_config['port']}")
    logger.info("=" * 60)

    try:
        app.run(
            debug=flask_config['debug'],
            host=flask_config['host'],
            port=flask_config['port']
        )
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Application failed to start: {e}")
        raise

if __name__ == '__main__':
    main()