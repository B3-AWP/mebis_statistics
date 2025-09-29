"""
Assignment Model und Assignment Status

Definiert Assignments, Quizzes und deren Status-Tracking.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from logger_config import get_logger

logger = get_logger('models.assignment')

class ActivityType(Enum):
    """Enumeration für Aktivitäts-Typen"""
    ASSIGNMENT = "assignment"
    QUIZ = "quiz"
    CHECKLIST = "checklist"
    FEEDBACK = "feedback"

class SubmissionStatus(Enum):
    """Enumeration für Einreichungs-Status"""
    NOT_SUBMITTED = "Nicht eingereicht"
    SUBMITTED = "Zur Bewertung abgegeben"
    REVIEWED = "Bewertet"
    LATE = "Verspätet eingereicht"
    DRAFT = "Entwurf gespeichert"

@dataclass
class Assignment:
    """
    Repräsentiert eine Aufgabe/Quiz/Aktivität im System
    """
    id: str
    title: str
    url: str
    category_name: str
    activity_type: ActivityType
    category_id: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    max_points: Optional[float] = None
    user_status: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        """Validierung nach Initialisierung"""
        if not self.id or not isinstance(self.id, str):
            raise ValueError(f"Invalid assignment ID: {self.id}")

        if not self.title or not isinstance(self.title, str):
            raise ValueError(f"Invalid assignment title: {self.title}")

        if not isinstance(self.activity_type, ActivityType):
            # Versuche String zu ActivityType zu konvertieren
            try:
                self.activity_type = ActivityType(self.activity_type)
            except ValueError:
                raise ValueError(f"Invalid activity type: {self.activity_type}")

        # URL validieren/säubern
        if not self.url:
            self.url = "#"
        elif not self.url.startswith(('http://', 'https://', '#')):
            logger.warning(f"Assignment {self.id} has suspicious URL: {self.url}")

    def get_user_status(self, user_name: str) -> Optional[Dict[str, Any]]:
        """
        Holt den Status für einen bestimmten Benutzer

        Args:
            user_name: Name des Benutzers

        Returns:
            Status-Dictionary oder None
        """
        for status in self.user_status:
            if status.get('user_name') == user_name:
                return status
        return None

    def get_submission_count(self, status_filter: Optional[SubmissionStatus] = None) -> int:
        """
        Zählt Einreichungen basierend auf Status

        Args:
            status_filter: Nur diesen Status zählen (None = alle)

        Returns:
            Anzahl Einreichungen
        """
        if not status_filter:
            return len([s for s in self.user_status if s.get('status') != SubmissionStatus.NOT_SUBMITTED.value])

        return len([s for s in self.user_status if s.get('status') == status_filter.value])

    def get_average_grade(self) -> Optional[float]:
        """
        Berechnet Durchschnittsnote für diese Aktivität

        Returns:
            Durchschnittsnote oder None
        """
        from backend.models.grade import GradeCalculator

        grades = []
        for status in self.user_status:
            grade = status.get('grade')
            if grade and grade != '-':
                ihk_grade = GradeCalculator.convert_to_ihk(grade)
                if ihk_grade is not None:
                    grades.append(ihk_grade)

        return GradeCalculator.calculate_average(grades)

    def to_dict(self, include_user_status: bool = True) -> Dict[str, Any]:
        """
        Konvertiert Assignment zu Dictionary für API-Response

        Args:
            include_user_status: Ob User-Status inkludiert werden soll

        Returns:
            Dictionary-Repräsentation
        """
        result = {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'category_name': self.category_name,
            'activity_type': self.activity_type.value,
            'category_id': self.category_id,
            'description': self.description,
            'due_date': self.due_date,
            'max_points': self.max_points
        }

        if include_user_status:
            result['user_status'] = self.user_status
            result['submission_stats'] = {
                'total_submissions': self.get_submission_count(),
                'reviewed_submissions': self.get_submission_count(SubmissionStatus.REVIEWED),
                'average_grade': self.get_average_grade()
            }

        return result

@dataclass
class AssignmentStatus:
    """
    Repräsentiert den Status einer Aufgabe für einen Benutzer
    """
    user_name: str
    assignment_id: str
    status: SubmissionStatus = SubmissionStatus.NOT_SUBMITTED
    status2: Optional[str] = None  # Zusätzlicher Status aus dem System
    grade: Optional[str] = None
    submission_date: Optional[str] = None
    feedback: Optional[str] = None

    def __post_init__(self):
        """Validierung und Standardisierung"""
        if not self.user_name:
            raise ValueError("User name is required")

        if not self.assignment_id:
            raise ValueError("Assignment ID is required")

        if not isinstance(self.status, SubmissionStatus):
            # Versuche String zu SubmissionStatus zu konvertieren
            status_mapping = {
                "Nicht eingereicht": SubmissionStatus.NOT_SUBMITTED,
                "Zur Bewertung abgegeben": SubmissionStatus.SUBMITTED,
                "Bewertet": SubmissionStatus.REVIEWED,
                "Verspätet eingereicht": SubmissionStatus.LATE,
                "Entwurf gespeichert": SubmissionStatus.DRAFT
            }

            if isinstance(self.status, str) and self.status in status_mapping:
                self.status = status_mapping[self.status]
            else:
                logger.warning(f"Unknown status '{self.status}' for user {self.user_name}")
                self.status = SubmissionStatus.NOT_SUBMITTED

        # Grade normalisieren
        if self.grade and self.grade in ['-', 'Nicht bewertet', 'Keine Bewertung', '']:
            self.grade = None

    def is_submitted(self) -> bool:
        """Prüft ob die Aufgabe eingereicht wurde"""
        return self.status != SubmissionStatus.NOT_SUBMITTED

    def is_graded(self) -> bool:
        """Prüft ob die Aufgabe bewertet wurde"""
        return self.status == SubmissionStatus.REVIEWED and self.grade is not None

    def get_ihk_grade(self) -> Optional[float]:
        """
        Konvertiert die Note zu IHK-Format

        Returns:
            IHK-Note oder None
        """
        if not self.grade:
            return None

        from backend.models.grade import GradeCalculator
        return GradeCalculator.convert_to_ihk(self.grade)

    def to_dict(self) -> Dict[str, Any]:
        """
        Konvertiert AssignmentStatus zu Dictionary

        Returns:
            Dictionary-Repräsentation
        """
        return {
            'user_name': self.user_name,
            'assignment_id': self.assignment_id,
            'status': self.status.value,
            'status2': self.status2,
            'grade': self.grade,
            'submission_date': self.submission_date,
            'feedback': self.feedback,
            'is_submitted': self.is_submitted(),
            'is_graded': self.is_graded(),
            'ihk_grade': self.get_ihk_grade()
        }