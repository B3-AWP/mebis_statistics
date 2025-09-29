"""
User Model und User Progress Tracking

Definiert Benutzer-Datenstrukturen und Fortschritts-Berechnungen.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from logger_config import get_logger

logger = get_logger('models.user')

@dataclass
class User:
    """
    Repräsentiert einen Benutzer im System
    """
    id: str
    name: str
    group: str
    activities: Dict[str, List[Dict]] = field(default_factory=dict)

    def __post_init__(self):
        """Validierung nach Initialisierung"""
        if not self.name or not isinstance(self.name, str):
            raise ValueError(f"Invalid user name: {self.name}")

        if not self.group or not isinstance(self.group, str):
            raise ValueError(f"Invalid group: {self.group}")

        # Standardisiere activities structure
        if not self.activities:
            self.activities = {
                'assignments': [],
                'quizzes': [],
                'checklists': [],
                'feedbacks': []
            }

    def get_activities_by_type(self, activity_type: str) -> List[Dict]:
        """
        Holt Aktivitäten eines bestimmten Typs

        Args:
            activity_type: Art der Aktivität (assignments, quizzes, etc.)

        Returns:
            Liste der Aktivitäten
        """
        return self.activities.get(activity_type, [])

    def has_activity(self, activity_id: str) -> bool:
        """
        Prüft ob Benutzer eine bestimmte Aktivität hat

        Args:
            activity_id: ID der zu suchenden Aktivität

        Returns:
            True wenn Aktivität gefunden
        """
        for activity_type, activities in self.activities.items():
            for activity in activities:
                if activity.get('id') == activity_id:
                    return True
        return False

    def get_activity_status(self, activity_id: str) -> Optional[Dict]:
        """
        Holt den Status einer bestimmten Aktivität

        Args:
            activity_id: ID der Aktivität

        Returns:
            Status-Dictionary oder None
        """
        for activity_type, activities in self.activities.items():
            for activity in activities:
                if activity.get('id') == activity_id:
                    return activity.get('status', {})
        return None

@dataclass
class UserProgress:
    """
    Berechnet und speichert Benutzer-Fortschritt
    """
    user: User
    assignments: Dict[str, Any] = field(default_factory=dict)
    checklists: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialisiere Standard-Strukturen"""
        if not self.assignments:
            self.assignments = {
                "reviewed_count": 0,
                "submitted_count": 0,
                "grades": {},
                "percent_submitted": 0.0,
                "percent_submitted_timed": 0.0,
                "average_grade": None
            }

        if not self.checklists:
            self.checklists = {
                "required_100_count": 0,
                "avg_required_progress": 0.0,
                "avg_all_progress": 0.0,
                "avg_required_progress_timed": 0.0,
                "avg_all_progress_timed": 0.0,
                "individual_checklists": []
            }

    def calculate_assignment_progress(
        self,
        assignment_details: Dict[str, Dict],
        categories: List[Dict],
        current_week: int = 10,
        total_weeks: int = 40
    ) -> None:
        """
        Berechnet Fortschritt bei Pflichtaufgaben

        Args:
            assignment_details: Dictionary mit Assignment-Details
            categories: Liste der verfügbaren Kategorien
            current_week: Aktuelle Referenzwoche
            total_weeks: Gesamtanzahl Wochen
        """
        try:
            # Nur Pflichtaufgaben berücksichtigen
            pflicht_categories = [c for c in categories if c.get('category_name') == "🎯Pflichtaufgaben"]

            if not pflicht_categories:
                logger.warning(f"No Pflichtaufgaben category found for user {self.user.name}")
                return

            pflicht_category = pflicht_categories[0]
            pflicht_category_id = pflicht_category.get('id')

            # Sammle alle Pflichtaktivitäten des Benutzers
            all_pflicht_activities = []

            for activity_type in ['assignments', 'quizzes', 'checklists', 'feedbacks']:
                user_activities = self.user.get_activities_by_type(activity_type)
                pflicht_activities = [
                    a for a in user_activities
                    if a.get('category_id') == pflicht_category_id
                ]
                all_pflicht_activities.extend(pflicht_activities)

            # Gesamtanzahl aller Pflichtaufgaben in der Kategorie
            total_pflicht_activities = (
                len(pflicht_category.get('assignments', [])) +
                len(pflicht_category.get('quizzes', [])) +
                len(pflicht_category.get('checklists', [])) +
                len(pflicht_category.get('feedbacks', []))
            )

            # Bewertete und eingereichte Aktivitäten
            reviewed_activities = [
                a for a in all_pflicht_activities
                if a.get('status', {}).get('status2') == "Bewertet"
            ]
            submitted_activities = [
                a for a in all_pflicht_activities
                if a.get('status', {}).get('status') == "Zur Bewertung abgegeben"
            ]

            self.assignments['reviewed_count'] = len(reviewed_activities)
            self.assignments['submitted_count'] = len(submitted_activities)

            # Noten sammeln und verarbeiten
            grades = []
            grade_details = []

            for activity in submitted_activities:
                activity_id = activity.get('id')
                details = assignment_details.get(activity_id, {})
                status = activity.get('status', {})

                grade_detail = {
                    'title': details.get('title', 'N/A'),
                    'grade': self._round_grade(status.get('grade', 'Nicht bewertet')),
                    'url': details.get('url', '#'),
                    'type': details.get('type', 'unknown')
                }
                grade_details.append(grade_detail)

                # Konvertiere Note zu IHK-Format für Durchschnittsberechnung
                from backend.models.grade import GradeCalculator
                ihk_grade = GradeCalculator.convert_to_ihk(status.get('grade'))
                if ihk_grade is not None:
                    grades.append(ihk_grade)

            self.assignments['grades'] = {"Pflichtaufgaben": grade_details}

            # Durchschnittsnote berechnen
            if grades:
                self.assignments['average_grade'] = GradeCalculator.calculate_average(grades)

            # Prozentberechnung
            if total_pflicht_activities > 0:
                self.assignments['percent_submitted'] = round(
                    (len(submitted_activities) / total_pflicht_activities) * 100, 2
                )

            # Referenzwoche-basierte Berechnung
            expected_for_week = max(1, round((total_pflicht_activities / total_weeks) * current_week))
            if expected_for_week > 0:
                self.assignments['percent_submitted_timed'] = round(
                    (len(submitted_activities) / expected_for_week) * 100, 2
                )

            logger.debug(f"Assignment progress calculated for {self.user.name}: "
                        f"{len(submitted_activities)}/{total_pflicht_activities} completed")

        except Exception as e:
            logger.error(f"Error calculating assignment progress for {self.user.name}: {e}")

    def calculate_checklist_progress(
        self,
        current_week: int = 10,
        total_weeks: int = 40
    ) -> None:
        """
        Berechnet Fortschritt bei Checklisten

        Args:
            current_week: Aktuelle Referenzwoche
            total_weeks: Gesamtanzahl Wochen
        """
        try:
            checklists = self.user.get_activities_by_type('checklists')
            total_checklists = len(checklists)

            if total_checklists == 0:
                logger.debug(f"No checklists found for user {self.user.name}")
                return

            # 100% erledigte Checklisten zählen
            required_100 = [
                c for c in checklists
                if c.get('progress', {}).get('required_progress') == "100%"
            ]
            self.checklists['required_100_count'] = len(required_100)

            # Individuelle Checklisten-Details sammeln
            checklist_details = []
            for checklist in checklists:
                progress = checklist.get('progress', {})
                detail = {
                    'id': checklist.get('id'),
                    'title': checklist.get('title', 'Unbekannt'),
                    'url': checklist.get('url', '#'),
                    'required_progress': progress.get('required_progress', '0%'),
                    'all_progress': progress.get('all_progress', '0%')
                }
                checklist_details.append(detail)

            self.checklists['individual_checklists'] = checklist_details

            # Durchschnittliche Fortschritte berechnen
            def parse_percentage(percent_str):
                """Hilfsfunktion um Prozent-String zu Float zu konvertieren"""
                try:
                    return float(str(percent_str).replace('%', ''))
                except (ValueError, TypeError):
                    return 0.0

            required_progresses = [
                parse_percentage(c.get('progress', {}).get('required_progress', '0%'))
                for c in checklists
            ]
            all_progresses = [
                parse_percentage(c.get('progress', {}).get('all_progress', '0%'))
                for c in checklists
            ]

            self.checklists['avg_required_progress'] = round(
                sum(required_progresses) / total_checklists, 2
            ) if total_checklists > 0 else 0.0

            self.checklists['avg_all_progress'] = round(
                sum(all_progresses) / total_checklists, 2
            ) if total_checklists > 0 else 0.0

            # Zeitbasierte Fortschrittsprognose
            if current_week > 0:
                week_factor = total_weeks / current_week
                self.checklists['avg_required_progress_timed'] = round(
                    self.checklists['avg_required_progress'] * week_factor, 2
                )
                self.checklists['avg_all_progress_timed'] = round(
                    self.checklists['avg_all_progress'] * week_factor, 2
                )

            logger.debug(f"Checklist progress calculated for {self.user.name}: "
                        f"{len(required_100)}/{total_checklists} completed")

        except Exception as e:
            logger.error(f"Error calculating checklist progress for {self.user.name}: {e}")

    def _round_grade(self, grade_str: str) -> str:
        """
        Rundet eine Note für die Anzeige

        Args:
            grade_str: Note als String

        Returns:
            Gerundete Note
        """
        from backend.utils.grade_utils import round_grade
        return round_grade(grade_str)

    def to_dict(self) -> Dict[str, Any]:
        """
        Konvertiert UserProgress zu Dictionary für API-Response

        Returns:
            Dictionary-Repräsentation
        """
        return {
            "name": self.user.name,
            "group": self.user.group,
            "assignments": self.assignments,
            "checklists": self.checklists
        }