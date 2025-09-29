"""
Group Model und Group Statistics

Definiert Gruppen und deren Statistik-Berechnungen.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from backend.models.user import User, UserProgress
from logger_config import get_logger

logger = get_logger('models.group')

@dataclass
class Group:
    """
    Repräsentiert eine Benutzergruppe
    """
    name: str
    users: List[User] = field(default_factory=list)
    ignored: bool = False

    def __post_init__(self):
        """Validierung nach Initialisierung"""
        if not self.name or not isinstance(self.name, str):
            raise ValueError(f"Invalid group name: {self.name}")

    def add_user(self, user: User) -> None:
        """
        Fügt einen Benutzer zur Gruppe hinzu

        Args:
            user: Benutzer-Objekt
        """
        if not isinstance(user, User):
            raise ValueError("user must be a User instance")

        if user not in self.users:
            user.group = self.name
            self.users.append(user)
            logger.debug(f"Added user {user.name} to group {self.name}")

    def remove_user(self, user_name: str) -> bool:
        """
        Entfernt einen Benutzer aus der Gruppe

        Args:
            user_name: Name des zu entfernenden Benutzers

        Returns:
            True wenn Benutzer entfernt wurde
        """
        for i, user in enumerate(self.users):
            if user.name == user_name:
                del self.users[i]
                logger.debug(f"Removed user {user_name} from group {self.name}")
                return True
        return False

    def get_user(self, user_name: str) -> Optional[User]:
        """
        Holt einen Benutzer aus der Gruppe

        Args:
            user_name: Name des Benutzers

        Returns:
            User-Objekt oder None
        """
        for user in self.users:
            if user.name == user_name:
                return user
        return None

    def get_user_count(self) -> int:
        """Gibt die Anzahl Benutzer in der Gruppe zurück"""
        return len(self.users)

    def to_dict(self, include_users: bool = True) -> Dict[str, Any]:
        """
        Konvertiert Group zu Dictionary

        Args:
            include_users: Ob Benutzer-Details inkludiert werden sollen

        Returns:
            Dictionary-Repräsentation
        """
        result = {
            'name': self.name,
            'user_count': self.get_user_count(),
            'ignored': self.ignored
        }

        if include_users:
            result['users'] = [user.name for user in self.users]

        return result

@dataclass
class GroupStatistics:
    """
    Berechnet und speichert Gruppen-Statistiken
    """
    group: Group
    assignments: Dict[str, Any] = field(default_factory=dict)
    checklists: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialisiere Standard-Strukturen"""
        if not self.assignments:
            self.assignments = {
                "avg_percent_submitted": 0.0,
                "avg_percent_submitted_timed": 0.0,
                "avg_grade": None
            }

        if not self.checklists:
            self.checklists = {
                "total_required_100": 0,
                "avg_required_progress": 0.0,
                "avg_all_progress": 0.0,
                "avg_required_progress_timed": 0.0,
                "avg_all_progress_timed": 0.0
            }

    def calculate_from_user_progress(self, user_progresses: List[UserProgress]) -> None:
        """
        Berechnet Gruppenstatistiken aus Benutzer-Fortschritten

        Args:
            user_progresses: Liste von UserProgress-Objekten
        """
        if not user_progresses:
            logger.warning(f"No user progresses provided for group {self.group.name}")
            return

        total_users = len(user_progresses)

        try:
            # Assignment-Statistiken
            total_percent_submitted = sum(
                up.assignments.get('percent_submitted', 0) for up in user_progresses
            )
            total_percent_submitted_timed = sum(
                up.assignments.get('percent_submitted_timed', 0) for up in user_progresses
            )

            self.assignments['avg_percent_submitted'] = round(
                total_percent_submitted / total_users, 2
            ) if total_users > 0 else 0.0

            self.assignments['avg_percent_submitted_timed'] = round(
                total_percent_submitted_timed / total_users, 2
            ) if total_users > 0 else 0.0

            # IHK-konforme Durchschnittsnote berechnen
            grades = [
                up.assignments.get('average_grade')
                for up in user_progresses
                if up.assignments.get('average_grade') is not None
            ]

            if grades:
                from backend.models.grade import GradeCalculator
                self.assignments['avg_grade'] = GradeCalculator.calculate_average(grades)

            # Checklisten-Statistiken
            total_required_100 = sum(
                up.checklists.get('required_100_count', 0) for up in user_progresses
            )
            total_required_progress = sum(
                up.checklists.get('avg_required_progress', 0) for up in user_progresses
            )
            total_all_progress = sum(
                up.checklists.get('avg_all_progress', 0) for up in user_progresses
            )

            self.checklists['total_required_100'] = total_required_100
            self.checklists['avg_required_progress'] = round(
                total_required_progress / total_users, 2
            ) if total_users > 0 else 0.0
            self.checklists['avg_all_progress'] = round(
                total_all_progress / total_users, 2
            ) if total_users > 0 else 0.0

            # Zeitbasierte Durchschnitte (werden vom Frontend berechnet, hier gleich setzen)
            self.checklists['avg_required_progress_timed'] = self.checklists['avg_required_progress']
            self.checklists['avg_all_progress_timed'] = self.checklists['avg_all_progress']

            logger.debug(f"Calculated statistics for group {self.group.name}: "
                        f"avg_grade={self.assignments['avg_grade']}, "
                        f"avg_submitted={self.assignments['avg_percent_submitted']}%")

        except Exception as e:
            logger.error(f"Error calculating group statistics for {self.group.name}: {e}")

    def get_top_performers(self, metric: str = 'percent_submitted', limit: int = 5) -> List[str]:
        """
        Holt die Top-Performer der Gruppe

        Args:
            metric: Metrik für Ranking (percent_submitted, average_grade, etc.)
            limit: Maximale Anzahl Ergebnisse

        Returns:
            Liste von Benutzernamen
        """
        # Placeholder - würde UserProgress-Objekte benötigen
        # Kann in Services implementiert werden
        return []

    def compare_to_overall(self, overall_stats: 'GroupStatistics') -> Dict[str, float]:
        """
        Vergleicht Gruppenstatistiken mit Gesamtstatistiken

        Args:
            overall_stats: Gesamtstatistiken zum Vergleich

        Returns:
            Dictionary mit Vergleichswerten (positiv = besser als Durchschnitt)
        """
        comparison = {}

        try:
            # Assignment-Vergleiche
            if overall_stats.assignments.get('avg_percent_submitted'):
                comparison['percent_submitted_diff'] = round(
                    self.assignments['avg_percent_submitted'] - overall_stats.assignments['avg_percent_submitted'], 2
                )

            if overall_stats.assignments.get('avg_grade') and self.assignments.get('avg_grade'):
                # Bei Noten ist niedriger besser (1.0 = sehr gut, 6.0 = ungenügend)
                comparison['grade_diff'] = round(
                    overall_stats.assignments['avg_grade'] - self.assignments['avg_grade'], 2
                )

            # Checklisten-Vergleiche
            if overall_stats.checklists.get('avg_required_progress'):
                comparison['checklist_progress_diff'] = round(
                    self.checklists['avg_required_progress'] - overall_stats.checklists['avg_required_progress'], 2
                )

        except Exception as e:
            logger.error(f"Error comparing group {self.group.name} to overall stats: {e}")

        return comparison

    def to_dict(self) -> Dict[str, Any]:
        """
        Konvertiert GroupStatistics zu Dictionary

        Returns:
            Dictionary-Repräsentation
        """
        return {
            'group_name': self.group.name,
            'user_count': self.group.get_user_count(),
            'assignments': self.assignments,
            'checklists': self.checklists
        }