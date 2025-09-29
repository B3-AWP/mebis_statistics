"""
Data Service

Verantwortlich für das Laden, Validieren und Bereitstellen von Rohdaten.
Ersetzt die monolithischen Datenlade-Funktionen aus dashboard_backend.py.
"""

import os
import json
import glob
from typing import Dict, List, Any, Optional, Set
from pathlib import Path

from config_manager import config_manager
from logger_config import get_logger
from backend.models.user import User
from backend.models.group import Group
from backend.models.category import Category
from backend.models.assignment import Assignment, ActivityType

logger = get_logger('services.data')

class DataService:
    """
    Service für Datenoperationen
    """

    def __init__(self):
        self.config = config_manager
        self._cache = {}
        self._cache_timestamp = None

    def find_latest_export_file(self, directory: str = 'export') -> Optional[str]:
        """
        Findet die neueste JSON-Export-Datei

        Args:
            directory: Verzeichnis zum Durchsuchen

        Returns:
            Pfad zur neuesten Datei oder None

        Raises:
            FileNotFoundError: Wenn Export-Verzeichnis nicht existiert
        """
        logger.info(f"Searching for latest export file in '{directory}'")

        if not os.path.exists(directory):
            raise FileNotFoundError(f"Export directory '{directory}' does not exist")

        try:
            pattern = os.path.join(directory, 'output_*.json')
            files = glob.glob(pattern)

            if not files:
                logger.warning(f"No JSON export files found in '{directory}'")
                return None

            latest_file = max(files, key=os.path.getctime)
            logger.info(f"Latest export file: {os.path.basename(latest_file)}")
            return latest_file

        except Exception as e:
            logger.error(f"Error finding latest export file: {e}")
            raise

    def load_json_data(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Lädt JSON-Daten aus Datei mit Validierung

        Args:
            file_path: Pfad zur JSON-Datei

        Returns:
            Dictionary mit geladenen Daten oder None bei Fehler

        Raises:
            FileNotFoundError: Wenn Datei nicht existiert
            json.JSONDecodeError: Wenn JSON ungültig ist
        """
        logger.info(f"Loading JSON data from: {file_path}")

        if not file_path:
            raise ValueError("File path cannot be empty")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File does not exist: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)

            # Validiere Grundstruktur
            if not isinstance(data, dict):
                raise ValueError("JSON data must be a dictionary")

            # Prüfe erwartete Schlüssel
            required_keys = ['groups', 'activities_by_category']
            missing_keys = [key for key in required_keys if key not in data]
            if missing_keys:
                logger.warning(f"Missing expected keys in JSON: {missing_keys}")

            logger.info(f"Successfully loaded JSON data with keys: {list(data.keys())}")
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format in {file_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading JSON data: {e}")
            raise

    def load_excluded_names(self, file_path: str = 'exclude_names.txt') -> Set[str]:
        """
        Lädt Liste der ausgeschlossenen Benutzernamen

        Args:
            file_path: Pfad zur Datei mit ausgeschlossenen Namen

        Returns:
            Set mit ausgeschlossenen Namen
        """
        logger.debug(f"Loading excluded names from: {file_path}")

        try:
            if not os.path.exists(file_path):
                logger.info(f"Excluded names file not found: {file_path}")
                return set()

            with open(file_path, 'r', encoding='utf-8') as file:
                excluded_names = {
                    line.strip() for line in file.readlines()
                    if line.strip() and not line.strip().startswith('#')
                }

            logger.info(f"Loaded {len(excluded_names)} excluded names")
            return excluded_names

        except Exception as e:
            logger.error(f"Error loading excluded names from {file_path}: {e}")
            return set()

    def get_ignored_groups(self) -> Set[str]:
        """
        Holt Liste der ignorierten Gruppen aus Konfiguration

        Returns:
            Set mit ignorierten Gruppennamen
        """
        try:
            ignored_groups = self.config.get_ignored_groups()
            logger.debug(f"Loaded {len(ignored_groups)} ignored groups from configuration")
            return ignored_groups

        except Exception as e:
            logger.error(f"Error loading ignored groups: {e}")
            return set()

    def parse_users_from_json(
        self,
        groups_data: List[Dict[str, Any]],
        excluded_names: Optional[Set[str]] = None
    ) -> Dict[str, Group]:
        """
        Parst Benutzer und Gruppen aus JSON-Daten

        Args:
            groups_data: Liste mit Gruppen-Daten aus JSON
            excluded_names: Set mit ausgeschlossenen Benutzernamen

        Returns:
            Dictionary mit Group-Objekten, indexiert nach Gruppenname
        """
        logger.info("Parsing users and groups from JSON data")

        if excluded_names is None:
            excluded_names = set()

        ignored_groups = self.get_ignored_groups()
        groups = {}

        try:
            for group_data in groups_data:
                group_name = group_data.get('name', 'Unknown')

                # Überspringe ignorierte Gruppen
                if group_name in ignored_groups:
                    logger.debug(f"Skipping ignored group: {group_name}")
                    continue

                # Erstelle Group-Objekt
                group = Group(name=group_name)

                # Füge Benutzer hinzu
                for user_data in group_data.get('users', []):
                    user_name = user_data.get('name', '').strip()

                    # Überspringe ausgeschlossene Benutzer
                    if not user_name or user_name in excluded_names:
                        continue

                    try:
                        user = User(
                            id=user_data.get('id', ''),
                            name=user_name,
                            group=group_name,
                            activities=user_data.get('activities', {})
                        )
                        group.add_user(user)

                    except Exception as e:
                        logger.warning(f"Error creating user {user_name}: {e}")
                        continue

                # Nur Gruppen mit Benutzern speichern
                if group.get_user_count() > 0:
                    groups[group_name] = group
                    logger.debug(f"Group '{group_name}' created with {group.get_user_count()} users")

            logger.info(f"Parsed {len(groups)} groups with users")
            return groups

        except Exception as e:
            logger.error(f"Error parsing users from JSON: {e}")
            raise

    def parse_categories_from_json(
        self,
        activities_data: List[Dict[str, Any]]
    ) -> List[Category]:
        """
        Parst Kategorien und Aktivitäten aus JSON-Daten

        Args:
            activities_data: Liste mit Kategorien-Daten aus JSON

        Returns:
            Liste mit Category-Objekten
        """
        logger.info("Parsing categories and activities from JSON data")

        categories = []

        try:
            for category_data in activities_data:
                category_name = category_data.get('category_name', 'Unknown')
                category_id = category_data.get('id', '')

                # Erstelle Category-Objekt
                category = Category(
                    id=category_id,
                    category_name=category_name
                )

                # Parse verschiedene Aktivitätstypen
                activity_types = [
                    ('assignments', ActivityType.ASSIGNMENT),
                    ('quizzes', ActivityType.QUIZ),
                    ('checklists', ActivityType.CHECKLIST),
                    ('feedbacks', ActivityType.FEEDBACK)
                ]

                for activity_key, activity_type in activity_types:
                    for activity_data in category_data.get(activity_key, []):
                        try:
                            assignment = Assignment(
                                id=activity_data.get('id', ''),
                                title=activity_data.get('title', ''),
                                url=activity_data.get('url', '#'),
                                category_name=category_name,
                                activity_type=activity_type,
                                category_id=category_id,
                                user_status=activity_data.get('user_status', [])
                            )
                            category.add_assignment(assignment)

                        except Exception as e:
                            logger.warning(f"Error creating assignment {activity_data.get('id', 'unknown')}: {e}")
                            continue

                categories.append(category)
                logger.debug(f"Category '{category_name}' created with {category.get_activity_count()['total']} activities")

            logger.info(f"Parsed {len(categories)} categories")
            return categories

        except Exception as e:
            logger.error(f"Error parsing categories from JSON: {e}")
            raise

    def get_latest_data(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        Holt die neuesten Daten mit Caching

        Args:
            force_reload: Ob Cache ignoriert werden soll

        Returns:
            Dictionary mit allen geladenen Daten

        Raises:
            FileNotFoundError: Wenn keine Export-Datei gefunden wird
            ValueError: Wenn Daten ungültig sind
        """
        logger.info(f"Getting latest data (force_reload={force_reload})")

        # Prüfe Cache
        if not force_reload and self._cache and self._cache_timestamp:
            cache_age = (Path().stat().st_mtime - self._cache_timestamp)
            if cache_age < 300:  # Cache 5 Minuten gültig
                logger.debug("Returning cached data")
                return self._cache

        try:
            # Finde neueste Export-Datei
            latest_file = self.find_latest_export_file()
            if not latest_file:
                raise FileNotFoundError("No export files found")

            # Lade JSON-Daten
            json_data = self.load_json_data(latest_file)
            if not json_data:
                raise ValueError("Failed to load JSON data")

            # Lade Hilfsdaten
            excluded_names = self.load_excluded_names()

            # Parse Daten zu strukturierten Objekten
            groups = self.parse_users_from_json(
                json_data.get('groups', []),
                excluded_names
            )

            categories = self.parse_categories_from_json(
                json_data.get('activities_by_category', [])
            )

            # Erstelle strukturierte Response
            result = {
                'groups': groups,
                'categories': categories,
                'excluded_names': excluded_names,
                'ignored_groups': self.get_ignored_groups(),
                'raw_data': json_data,
                'last_updated': latest_file,
                'metadata': {
                    'total_groups': len(groups),
                    'total_categories': len(categories),
                    'total_users': sum(g.get_user_count() for g in groups.values()),
                    'total_activities': sum(c.get_activity_count()['total'] for c in categories)
                }
            }

            # Cache aktualisieren
            self._cache = result
            self._cache_timestamp = Path().stat().st_mtime

            logger.info(f"Data loaded successfully: {result['metadata']}")
            return result

        except Exception as e:
            logger.error(f"Error getting latest data: {e}")
            raise

    def validate_data_integrity(self, data: Dict[str, Any]) -> List[str]:
        """
        Validiert die Integrität der geladenen Daten

        Args:
            data: Daten-Dictionary zum Validieren

        Returns:
            Liste mit gefundenen Problemen (leer = keine Probleme)
        """
        logger.debug("Validating data integrity")

        issues = []

        try:
            # Prüfe Grundstruktur
            required_keys = ['groups', 'categories', 'metadata']
            for key in required_keys:
                if key not in data:
                    issues.append(f"Missing required key: {key}")

            # Prüfe Gruppen
            groups = data.get('groups', {})
            if not groups:
                issues.append("No groups found in data")

            for group_name, group in groups.items():
                if not isinstance(group, Group):
                    issues.append(f"Group {group_name} is not a Group instance")
                    continue

                if group.get_user_count() == 0:
                    issues.append(f"Group {group_name} has no users")

            # Prüfe Kategorien
            categories = data.get('categories', [])
            if not categories:
                issues.append("No categories found in data")

            for category in categories:
                if not isinstance(category, Category):
                    issues.append(f"Category {category.category_name if hasattr(category, 'category_name') else 'unknown'} is not a Category instance")
                    continue

                if category.get_activity_count()['total'] == 0:
                    issues.append(f"Category {category.category_name} has no activities")

            # Prüfe Pflichtaufgaben-Kategorie
            pflicht_categories = [c for c in categories if c.is_pflichtaufgaben()]
            if not pflicht_categories:
                issues.append("No Pflichtaufgaben category found")

            logger.debug(f"Data validation completed: {len(issues)} issues found")

        except Exception as e:
            logger.error(f"Error during data validation: {e}")
            issues.append(f"Validation error: {str(e)}")

        return issues

    def clear_cache(self) -> None:
        """Löscht den internen Cache"""
        self._cache = {}
        self._cache_timestamp = None
        logger.debug("Data cache cleared")