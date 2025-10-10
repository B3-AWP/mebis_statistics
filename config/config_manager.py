#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sicheres Konfigurationsmanagement für Mebis Statistik Dashboard

Dieses Modul lädt Konfiguration ausschließlich aus Environment Variables (.env Datei).
"""

import os
import json
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import logging

# Logger für dieses Modul
logger = logging.getLogger(__name__)

class ConfigManager:
    """
    Zentrale Konfigurationsverwaltung basierend auf Environment Variables.

    Lädt Konfiguration aus .env Datei im config/ Ordner.
    """

    def __init__(self):
        """Initialisiert den Konfigurationsmanager und lädt .env"""
        self._load_config()

    def _load_config(self):
        """Lädt Environment Variables aus .env Datei"""
        # Bestimme den Pfad zur .env Datei im config Ordner
        current_dir = os.path.dirname(os.path.abspath(__file__))
        env_file = os.path.join(current_dir, '.env')

        # Lade .env Datei
        if os.path.exists(env_file):
            load_dotenv(env_file)
            print(f"Configuration loaded from {env_file}")
        else:
            print(f".env file not found at {env_file}. Using system environment variables only.")

    def get_login_credentials(self) -> Dict[str, str]:
        """
        Holt Login-Credentials aus Environment Variables.

        Returns:
            Dictionary mit username und password

        Raises:
            ValueError: Wenn Credentials nicht gefunden werden
        """
        username = os.getenv('MEBIS_USERNAME')
        password = os.getenv('MEBIS_PASSWORD')

        if not username or not password:
            raise ValueError(
                "Login credentials not found. Set MEBIS_USERNAME and MEBIS_PASSWORD in .env file."
            )

        return {
            'username': username,
            'password': password
        }

    def get_mode_settings(self) -> Dict[str, Any]:
        """
        Holt Modus-Einstellungen.

        Returns:
            Dictionary mit headless und waittime
        """
        return {
            'headless': self._get_bool('MODE_HEADLESS', True),
            'waittime': self._get_int('MODE_WAITTIME', 10)
        }

    def get_urls(self) -> Dict[str, str]:
        """
        Holt URL-Konfiguration.

        Returns:
            Dictionary mit URLs
        """
        return {
            'base_url': os.getenv(
                'MEBIS_BASE_URL',
                'https://lernplattform.mebis.bycs.de/report/progress/index.php'
            ),
            'common_params': os.getenv(
                'MEBIS_COMMON_PARAMS',
                '&sifirst=&activityorder=orderincourse&activitysection=-1'
            )
        }

    def get_courses(self) -> Dict[str, str]:
        """
        Holt Kurs-Konfiguration.

        Returns:
            Dictionary mit course_id
        """
        courses = {}
        course_id = os.getenv('MEBIS_COURSE_ID')
        if course_id:
            courses['course_ifa12'] = course_id
        return courses

    def get_ignored_groups(self) -> set:
        """
        Holt Liste der ignorierten Gruppen.

        Returns:
            Set mit ignorierten Gruppennamen
        """
        ignored_groups = set()

        # Environment Variable (kommasepariert)
        env_ignored = os.getenv('MEBIS_IGNORED_GROUPS')
        if env_ignored:
            ignored_groups.update(group.strip() for group in env_ignored.split(','))

        return ignored_groups

    def get_flask_config(self) -> Dict[str, Any]:
        """
        Holt Flask-spezifische Konfiguration.

        Returns:
            Dictionary mit Flask-Einstellungen
        """
        return {
            'debug': self._get_bool('FLASK_DEBUG', False),
            'host': os.getenv('FLASK_HOST', '0.0.0.0'),
            'port': self._get_int('FLASK_PORT', 5000),
            'secret_key': os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production'),
            'env': os.getenv('FLASK_ENV', 'production')
        }

    def get_logging_config(self) -> Dict[str, Any]:
        """
        Holt Logging-Konfiguration.

        Returns:
            Dictionary mit Logging-Einstellungen
        """
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

        return {
            'level': getattr(logging, log_level, logging.INFO),
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'filename': os.getenv('LOG_FILE'),  # None = Console nur
            'max_bytes': self._get_int('LOG_MAX_BYTES', 10485760),  # 10MB
            'backup_count': self._get_int('LOG_BACKUP_COUNT', 5)
        }

    def get_export_folder(self) -> str:
        """
        Holt Export-Ordner-Pfad aus Environment Variable.

        Returns:
            Pfad zum Export-Ordner (relativ oder absolut)
        """
        return os.getenv('EXPORT_FOLDER', 'export')

    def get_grade_mapping(self) -> Dict[int, str]:
        """
        Holt Grade Mapping aus Environment Variable.

        Returns:
            Dictionary mit Punkte -> Bewertung Mapping
        """
        grade_mapping_json = os.getenv('GRADE_MAPPING')
        if grade_mapping_json:
            try:
                # Parse JSON und konvertiere String-Keys zu Integer
                mapping = json.loads(grade_mapping_json)
                return {int(k): v for k, v in mapping.items()}
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Invalid GRADE_MAPPING format: {e}. Using defaults.")

        # Default Mapping
        return {
            0: "* Nicht akzeptabel",
            70: "** Verbesserungsbedarf",
            100: "*** Solide Umsetzung",
            130: "**** Exzellent"
        }

    def get_max_schoolweeks(self) -> int:
        """
        Holt maximale Anzahl der Schulwochen aus Environment Variable.

        Returns:
            Maximale Anzahl der Schulwochen (Standard: 9)
        """
        return self._get_int('MAX_SCHOOLWEEKS', 9)

    def _get_int(self, env_var: str, default: int) -> int:
        """Holt Integer-Wert aus Environment Variable"""
        value = os.getenv(env_var)
        if value:
            try:
                return int(value)
            except ValueError:
                logger.warning(f"Invalid integer value for {env_var}: {value}. Using default: {default}")
        return default

    def _get_bool(self, env_var: str, default: bool) -> bool:
        """Holt Boolean-Wert aus Environment Variable"""
        value = os.getenv(env_var)
        if value:
            return value.lower() in ('true', '1', 'yes', 'on')
        return default

# Globale Instanz für einfache Nutzung
config_manager = ConfigManager()

# Convenience-Funktionen für Rückwärtskompatibilität
def load_config():
    """Lädt Konfiguration (für Kompatibilität mit bestehendem Code)"""
    return config_manager

def get_login_credentials():
    """Holt Login-Credentials"""
    return config_manager.get_login_credentials()

def get_ignored_groups():
    """Holt ignorierte Gruppen"""
    return config_manager.get_ignored_groups()