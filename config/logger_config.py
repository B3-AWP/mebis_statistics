#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Zentrales Logging-System für Mebis Statistik Dashboard

Ersetzt print-Statements und console.log durch professionelles Logging
mit konfigurierbaren Log-Levels und strukturierten Ausgaben.
"""

import logging
import logging.handlers
import os
import sys
from typing import Optional

class DashboardLogger:
    """
    Zentraler Logger für das Dashboard mit konfigurierbaren Ausgaben.
    """

    def __init__(self):
        self.logger = None
        self._setup_logging()

    def _setup_logging(self):
        """Konfiguriert das Logging-System basierend auf Environment/Config"""
        # Lazy import um zirkuläre Abhängigkeiten zu vermeiden
        from .config_manager import config_manager as cm
        config = cm.get_logging_config()

        # Root Logger konfigurieren
        self.logger = logging.getLogger('mebis_dashboard')
        self.logger.setLevel(config['level'])

        # Entferne existierende Handler
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        # Console Handler (immer aktiv)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(config['level'])

        # Formatter
        formatter = logging.Formatter(config['format'])
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File Handler (optional)
        if config.get('filename'):
            try:
                # Erstelle logs Verzeichnis falls nicht vorhanden
                log_dir = os.path.dirname(config['filename'])
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir)

                # Rotating File Handler für Log-Rotation
                file_handler = logging.handlers.RotatingFileHandler(
                    config['filename'],
                    maxBytes=config['max_bytes'],
                    backupCount=config['backup_count'],
                    encoding='utf-8'
                )
                file_handler.setLevel(config['level'])
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

                self.logger.info(f"File logging enabled: {config['filename']}")
            except Exception as e:
                self.logger.warning(f"Failed to setup file logging: {e}")

        # Verhindere Doppel-Logging
        self.logger.propagate = False

        self.logger.info("Logging system initialized")

    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """
        Holt einen Logger für ein spezifisches Modul.

        Args:
            name: Name des Moduls (z.B. 'dashboard_backend')

        Returns:
            Konfigurierter Logger
        """
        if name:
            return logging.getLogger(f'mebis_dashboard.{name}')
        return self.logger

# Globale Logger-Instanz
dashboard_logger = DashboardLogger()

# Convenience-Funktionen für einfache Nutzung
def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Holt einen konfigurierten Logger"""
    return dashboard_logger.get_logger(name)

# Standard-Logger für Backend
backend_logger = get_logger('backend')
api_logger = get_logger('api')
data_logger = get_logger('data_processing')

# Debug-Ersatz-Funktionen für graduellen Übergang
def debug_print(*args, **kwargs):
    """
    Ersatz für Debug-Print-Statements.
    Loggt nur in Development-Modus.
    """
    flask_env = os.getenv('FLASK_ENV', 'production')
    if flask_env == 'development':
        message = ' '.join(str(arg) for arg in args)
        backend_logger.debug(f"DEBUG: {message}")

def safe_print(*args, **kwargs):
    """
    Sicherer Ersatz für Print-Statements.
    Nutzt Logger statt direkter Print-Ausgabe.
    """
    message = ' '.join(str(arg) for arg in args)
    backend_logger.info(message)