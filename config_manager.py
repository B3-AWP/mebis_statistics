#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sicheres Konfigurationsmanagement für Mebis Statistik Dashboard

Dieses Modul lädt Konfiguration aus Environment Variables oder config.ini,
wobei Environment Variables Vorrang haben (für bessere Sicherheit).
"""

import os
import configparser
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import logging

# Logger für dieses Modul
logger = logging.getLogger(__name__)

class ConfigManager:
    """
    Zentrale Konfigurationsverwaltung mit Sicherheitsfokus.

    Priorität:
    1. Environment Variables (höchste Sicherheit)
    2. config.ini (Fallback für lokale Entwicklung)
    3. Default-Werte (letzte Option)
    """

    def __init__(self, config_file: str = 'config.ini'):
        """
        Initialisiert den Konfigurationsmanager.

        Args:
            config_file: Pfad zur config.ini Datei
        """
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self._load_config()

    def _load_config(self):
        """Lädt Konfiguration aus .env und config.ini"""
        # 1. Lade Environment Variables aus .env Datei
        load_dotenv()

        # 2. Lade config.ini als Fallback
        if os.path.exists(self.config_file):
            try:
                self.config.read(self.config_file, encoding='utf-8')
                logger.info(f"Config loaded from {self.config_file}")
            except Exception as e:
                logger.warning(f"Failed to load {self.config_file}: {e}")
        else:
            logger.warning(f"Config file {self.config_file} not found. Using environment variables only.")

    def get_login_credentials(self) -> Dict[str, str]:
        """
        Holt Login-Credentials sicher aus Environment Variables.

        Returns:
            Dictionary mit username und password

        Raises:
            ValueError: Wenn Credentials nicht gefunden werden
        """
        username = os.getenv('MEBIS_USERNAME')
        password = os.getenv('MEBIS_PASSWORD')

        # Fallback auf config.ini (nur für Entwicklung!)
        if not username and self.config.has_section('login'):
            username = self.config.get('login', 'username', fallback=None)
            logger.warning("Username loaded from config.ini - use environment variables in production!")

        if not password and self.config.has_section('login'):
            password = self.config.get('login', 'password', fallback=None)
            logger.warning("Password loaded from config.ini - use environment variables in production!")

        if not username or not password:
            raise ValueError(
                "Login credentials not found. Set MEBIS_USERNAME and MEBIS_PASSWORD environment variables."
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
            'headless': self._get_bool('MODE_HEADLESS', 'mode', 'headless', True),
            'waittime': self._get_int('MODE_WAITTIME', 'mode', 'waittime', 10)
        }

    def get_urls(self) -> Dict[str, str]:
        """
        Holt URL-Konfiguration.

        Returns:
            Dictionary mit URLs
        """
        return {
            'base_url': self._get_string(
                'MEBIS_BASE_URL',
                'urls',
                'base_url',
                'https://lernplattform.mebis.bycs.de/report/progress/index.php'
            ),
            'common_params': self._get_string(
                'MEBIS_COMMON_PARAMS',
                'urls',
                'common_params',
                '&sifirst=&activityorder=orderincourse&activitysection=-1'
            )
        }

    def get_courses(self) -> Dict[str, str]:
        """Holt Kurs-Konfiguration"""
        courses = {}

        # Environment Variable für Hauptkurs
        course_id = os.getenv('MEBIS_COURSE_ID')
        if course_id:
            courses['course_ifa12'] = course_id
        elif self.config.has_section('courses'):
            courses.update(dict(self.config.items('courses')))

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

        # Fallback auf config.ini
        if self.config.has_section('IgnoreGroups'):
            for key, group_name in self.config.items('IgnoreGroups'):
                if not key.startswith(';'):  # Ignore comments
                    ignored_groups.add(group_name.strip())

        return ignored_groups

    def get_flask_config(self) -> Dict[str, Any]:
        """
        Holt Flask-spezifische Konfiguration.

        Returns:
            Dictionary mit Flask-Einstellungen
        """
        return {
            'debug': self._get_bool('FLASK_DEBUG', None, None, False),
            'host': self._get_string('FLASK_HOST', None, None, '0.0.0.0'),
            'port': self._get_int('FLASK_PORT', None, None, 5000),
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
            'max_bytes': self._get_int('LOG_MAX_BYTES', None, None, 10485760),  # 10MB
            'backup_count': self._get_int('LOG_BACKUP_COUNT', None, None, 5)
        }

    def _get_string(self, env_var: str, section: str, key: str, default: str) -> str:
        """Holt String-Wert aus Env Var oder config.ini"""
        value = os.getenv(env_var)
        if value:
            return value

        if section and self.config.has_section(section):
            return self.config.get(section, key, fallback=default)

        return default

    def _get_int(self, env_var: str, section: str, key: str, default: int) -> int:
        """Holt Integer-Wert aus Env Var oder config.ini"""
        value = os.getenv(env_var)
        if value:
            try:
                return int(value)
            except ValueError:
                logger.warning(f"Invalid integer value for {env_var}: {value}")

        if section and self.config.has_section(section):
            return self.config.getint(section, key, fallback=default)

        return default

    def _get_bool(self, env_var: str, section: str, key: str, default: bool) -> bool:
        """Holt Boolean-Wert aus Env Var oder config.ini"""
        value = os.getenv(env_var)
        if value:
            return value.lower() in ('true', '1', 'yes', 'on')

        if section and self.config.has_section(section):
            return self.config.getboolean(section, key, fallback=default)

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