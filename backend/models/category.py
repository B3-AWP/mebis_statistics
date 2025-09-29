"""
Category Model

Definiert Kategorien für Assignments und Aktivitäten.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from backend.models.assignment import Assignment, ActivityType
from logger_config import get_logger

logger = get_logger('models.category')

@dataclass
class Category:
    """
    Repräsentiert eine Kategorie von Aktivitäten (z.B. Pflichtaufgaben, Zentrale Leistungsnachweise)
    """
    id: str
    category_name: str
    assignments: List[Assignment] = field(default_factory=list)
    quizzes: List[Assignment] = field(default_factory=list)
    checklists: List[Assignment] = field(default_factory=list)
    feedbacks: List[Assignment] = field(default_factory=list)

    def __post_init__(self):
        """Validierung und Standardisierung nach Initialisierung"""
        if not self.id:
            # Generiere ID aus Namen falls nicht vorhanden
            self.id = self._generate_id_from_name()

        if not self.category_name:
            raise ValueError("Category name is required")

        # Validiere dass alle Assignments korrekte Typen haben
        self._validate_activity_types()

    def _generate_id_from_name(self) -> str:
        """Generiert eine ID aus dem Kategorienamen"""
        if not self.category_name:
            return "unknown"

        # Entferne Sonderzeichen und konvertiere zu lowercase
        import re
        clean_name = re.sub(r'[^\w\s-]', '', self.category_name)
        return clean_name.replace(' ', '_').lower()

    def _validate_activity_types(self):
        """Validiert dass Aktivitäten in den richtigen Listen sind"""
        try:
            # Prüfe assignments
            for assignment in self.assignments:
                if assignment.activity_type != ActivityType.ASSIGNMENT:
                    logger.warning(f"Assignment {assignment.id} has wrong type {assignment.activity_type}")

            # Prüfe quizzes
            for quiz in self.quizzes:
                if quiz.activity_type != ActivityType.QUIZ:
                    logger.warning(f"Quiz {quiz.id} has wrong type {quiz.activity_type}")

            # Prüfe checklists
            for checklist in self.checklists:
                if checklist.activity_type != ActivityType.CHECKLIST:
                    logger.warning(f"Checklist {checklist.id} has wrong type {checklist.activity_type}")

            # Prüfe feedbacks
            for feedback in self.feedbacks:
                if feedback.activity_type != ActivityType.FEEDBACK:
                    logger.warning(f"Feedback {feedback.id} has wrong type {feedback.activity_type}")

        except Exception as e:
            logger.error(f"Error validating activity types for category {self.category_name}: {e}")

    def add_assignment(self, assignment: Assignment) -> None:
        """
        Fügt eine Aktivität zur entsprechenden Liste hinzu

        Args:
            assignment: Assignment-Objekt
        """
        if not isinstance(assignment, Assignment):
            raise ValueError("assignment must be an Assignment instance")

        # Setze category_id und category_name
        assignment.category_id = self.id
        assignment.category_name = self.category_name

        # Füge zur entsprechenden Liste hinzu
        if assignment.activity_type == ActivityType.ASSIGNMENT:
            if assignment not in self.assignments:
                self.assignments.append(assignment)
        elif assignment.activity_type == ActivityType.QUIZ:
            if assignment not in self.quizzes:
                self.quizzes.append(assignment)
        elif assignment.activity_type == ActivityType.CHECKLIST:
            if assignment not in self.checklists:
                self.checklists.append(assignment)
        elif assignment.activity_type == ActivityType.FEEDBACK:
            if assignment not in self.feedbacks:
                self.feedbacks.append(assignment)
        else:
            logger.warning(f"Unknown activity type {assignment.activity_type} for assignment {assignment.id}")

    def get_all_activities(self) -> List[Assignment]:
        """
        Holt alle Aktivitäten der Kategorie

        Returns:
            Liste aller Assignments/Aktivitäten
        """
        return self.assignments + self.quizzes + self.checklists + self.feedbacks

    def get_activity_by_id(self, activity_id: str) -> Optional[Assignment]:
        """
        Sucht eine Aktivität nach ID

        Args:
            activity_id: ID der gesuchten Aktivität

        Returns:
            Assignment-Objekt oder None
        """
        for activity in self.get_all_activities():
            if activity.id == activity_id:
                return activity
        return None

    def get_activity_count(self) -> Dict[str, int]:
        """
        Zählt Aktivitäten nach Typ

        Returns:
            Dictionary mit Anzahl pro Aktivitätstyp
        """
        return {
            'assignments': len(self.assignments),
            'quizzes': len(self.quizzes),
            'checklists': len(self.checklists),
            'feedbacks': len(self.feedbacks),
            'total': len(self.get_all_activities())
        }

    def is_pflichtaufgaben(self) -> bool:
        """Prüft ob dies eine Pflichtaufgaben-Kategorie ist"""
        return "Pflichtaufgaben" in self.category_name

    def is_zentrale_leistungsnachweise(self) -> bool:
        """Prüft ob dies eine Zentrale Leistungsnachweise-Kategorie ist"""
        name_lower = self.category_name.lower()
        return (
            'zentrale leistungsnachweise' in name_lower or
            'chart' in name_lower
        )

    def get_completion_stats(self) -> Dict[str, Any]:
        """
        Berechnet Completion-Statistiken für die Kategorie

        Returns:
            Dictionary mit Statistiken
        """
        all_activities = self.get_all_activities()
        if not all_activities:
            return {
                'total_activities': 0,
                'total_submissions': 0,
                'completion_rate': 0.0,
                'average_grade': None
            }

        total_submissions = 0
        all_grades = []

        for activity in all_activities:
            submissions = activity.get_submission_count()
            total_submissions += submissions

            avg_grade = activity.get_average_grade()
            if avg_grade is not None:
                all_grades.append(avg_grade)

        total_possible_submissions = sum(len(a.user_status) for a in all_activities)
        completion_rate = (total_submissions / total_possible_submissions * 100) if total_possible_submissions > 0 else 0.0

        from backend.models.grade import GradeCalculator
        average_grade = GradeCalculator.calculate_average(all_grades) if all_grades else None

        return {
            'total_activities': len(all_activities),
            'total_submissions': total_submissions,
            'completion_rate': round(completion_rate, 2),
            'average_grade': average_grade
        }

    def to_dict(self, include_activities: bool = True) -> Dict[str, Any]:
        """
        Konvertiert Category zu Dictionary für API-Response

        Args:
            include_activities: Ob Aktivitäts-Details inkludiert werden sollen

        Returns:
            Dictionary-Repräsentation
        """
        result = {
            'id': self.id,
            'category_name': self.category_name,
            'activity_counts': self.get_activity_count(),
            'is_pflichtaufgaben': self.is_pflichtaufgaben(),
            'is_zentrale_leistungsnachweise': self.is_zentrale_leistungsnachweise(),
            'completion_stats': self.get_completion_stats()
        }

        if include_activities:
            result.update({
                'assignments': [a.to_dict() for a in self.assignments],
                'quizzes': [q.to_dict() for q in self.quizzes],
                'checklists': [c.to_dict() for c in self.checklists],
                'feedbacks': [f.to_dict() for f in self.feedbacks]
            })

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Category':
        """
        Erstellt Category-Objekt aus Dictionary

        Args:
            data: Dictionary mit Kategorie-Daten

        Returns:
            Category-Objekt
        """
        category = cls(
            id=data.get('id', ''),
            category_name=data.get('category_name', '')
        )

        # Lade Aktivitäten
        for activity_data in data.get('assignments', []):
            assignment = Assignment(
                id=activity_data['id'],
                title=activity_data['title'],
                url=activity_data.get('url', '#'),
                category_name=category.category_name,
                activity_type=ActivityType.ASSIGNMENT,
                category_id=category.id,
                user_status=activity_data.get('user_status', [])
            )
            category.add_assignment(assignment)

        for quiz_data in data.get('quizzes', []):
            quiz = Assignment(
                id=quiz_data['id'],
                title=quiz_data['title'],
                url=quiz_data.get('url', '#'),
                category_name=category.category_name,
                activity_type=ActivityType.QUIZ,
                category_id=category.id,
                user_status=quiz_data.get('user_status', [])
            )
            category.add_assignment(quiz)

        for checklist_data in data.get('checklists', []):
            checklist = Assignment(
                id=checklist_data['id'],
                title=checklist_data['title'],
                url=checklist_data.get('url', '#'),
                category_name=category.category_name,
                activity_type=ActivityType.CHECKLIST,
                category_id=category.id,
                user_status=checklist_data.get('user_status', [])
            )
            category.add_assignment(checklist)

        for feedback_data in data.get('feedbacks', []):
            feedback = Assignment(
                id=feedback_data['id'],
                title=feedback_data['title'],
                url=feedback_data.get('url', '#'),
                category_name=category.category_name,
                activity_type=ActivityType.FEEDBACK,
                category_id=category.id,
                user_status=feedback_data.get('user_status', [])
            )
            category.add_assignment(feedback)

        return category