"""
Calculation Service

Verantwortlich für alle Berechnungen von Fortschritt, Statistiken und Noten.
Ersetzt die komplexen Berechnungsfunktionen aus dashboard_backend.py.
"""

import math
from typing import Dict, List, Any, Optional, Tuple
from backend.models.user import User, UserProgress
from backend.models.group import Group, GroupStatistics
from backend.models.assignment import Assignment
from backend.models.category import Category
from backend.models.grade import GradeCalculator
from logger_config import get_logger

logger = get_logger('services.calculation')

class CalculationService:
    """
    Service für alle Berechnungen im Dashboard
    """

    def __init__(self):
        self.grade_calculator = GradeCalculator()

    def calculate_user_progress(
        self,
        user: User,
        categories: List[Category],
        current_week: int = 10,
        total_weeks: int = 40
    ) -> UserProgress:
        """
        Berechnet den kompletten Fortschritt eines Benutzers

        Args:
            user: User-Objekt
            categories: Liste der verfügbaren Kategorien
            current_week: Aktuelle Referenzwoche
            total_weeks: Gesamtanzahl Wochen

        Returns:
            UserProgress-Objekt mit berechneten Daten
        """
        logger.debug(f"Calculating progress for user: {user.name}")

        try:
            # Erstelle UserProgress-Objekt
            user_progress = UserProgress(user=user)

            # Erstelle Assignment-Details für Berechnungen
            assignment_details = self._create_assignment_details(categories)

            # Berechne Assignment-Fortschritt
            user_progress.calculate_assignment_progress(
                assignment_details=assignment_details,
                categories=categories,
                current_week=current_week,
                total_weeks=total_weeks
            )

            # Berechne Checklisten-Fortschritt
            user_progress.calculate_checklist_progress(
                current_week=current_week,
                total_weeks=total_weeks
            )

            logger.debug(f"Progress calculated for {user.name}: "
                        f"{user_progress.assignments['submitted_count']} assignments, "
                        f"{user_progress.checklists['required_100_count']} checklists completed")

            return user_progress

        except Exception as e:
            logger.error(f"Error calculating user progress for {user.name}: {e}")
            # Rückgabe eines leeren UserProgress bei Fehler
            return UserProgress(user=user)

    def calculate_group_statistics(
        self,
        group: Group,
        user_progresses: List[UserProgress]
    ) -> GroupStatistics:
        """
        Berechnet Statistiken für eine Gruppe

        Args:
            group: Group-Objekt
            user_progresses: Liste der UserProgress-Objekte für die Gruppe

        Returns:
            GroupStatistics-Objekt
        """
        logger.debug(f"Calculating statistics for group: {group.name}")

        try:
            group_stats = GroupStatistics(group=group)
            group_stats.calculate_from_user_progress(user_progresses)

            logger.debug(f"Statistics calculated for group {group.name}: "
                        f"avg_grade={group_stats.assignments.get('avg_grade')}, "
                        f"avg_submitted={group_stats.assignments.get('avg_percent_submitted')}%")

            return group_stats

        except Exception as e:
            logger.error(f"Error calculating group statistics for {group.name}: {e}")
            return GroupStatistics(group=group)

    def calculate_overall_statistics(
        self,
        all_user_progresses: List[UserProgress]
    ) -> Dict[str, Any]:
        """
        Berechnet Gesamtstatistiken über alle Gruppen

        Args:
            all_user_progresses: Liste aller UserProgress-Objekte

        Returns:
            Dictionary mit Gesamtstatistiken
        """
        logger.debug(f"Calculating overall statistics for {len(all_user_progresses)} users")

        if not all_user_progresses:
            return self._get_empty_statistics()

        try:
            total_users = len(all_user_progresses)

            # Assignment-Statistiken
            assignment_stats = {
                "avg_percent_submitted": 0.0,
                "avg_percent_submitted_timed": 0.0,
                "avg_grade": None
            }

            total_percent_submitted = sum(
                up.assignments.get('percent_submitted', 0) for up in all_user_progresses
            )
            total_percent_submitted_timed = sum(
                up.assignments.get('percent_submitted_timed', 0) for up in all_user_progresses
            )

            assignment_stats['avg_percent_submitted'] = round(
                total_percent_submitted / total_users, 2
            )
            assignment_stats['avg_percent_submitted_timed'] = round(
                total_percent_submitted_timed / total_users, 2
            )

            # Gesamtdurchschnittsnote
            grades = [
                up.assignments.get('average_grade')
                for up in all_user_progresses
                if up.assignments.get('average_grade') is not None
            ]

            if grades:
                assignment_stats['avg_grade'] = GradeCalculator.calculate_average(grades)

            # Checklisten-Statistiken
            checklist_stats = {
                "total_required_100": sum(
                    up.checklists.get('required_100_count', 0) for up in all_user_progresses
                ),
                "avg_required_progress": round(
                    sum(up.checklists.get('avg_required_progress', 0) for up in all_user_progresses) / total_users, 2
                ),
                "avg_all_progress": round(
                    sum(up.checklists.get('avg_all_progress', 0) for up in all_user_progresses) / total_users, 2
                ),
                "avg_required_progress_timed": 0.0,
                "avg_all_progress_timed": 0.0
            }

            # Zeitbasierte Werte (Frontend berechnet diese)
            checklist_stats['avg_required_progress_timed'] = checklist_stats['avg_required_progress']
            checklist_stats['avg_all_progress_timed'] = checklist_stats['avg_all_progress']

            result = {
                'assignments': assignment_stats,
                'checklists': checklist_stats,
                'metadata': {
                    'total_users': total_users,
                    'users_with_grades': len(grades)
                }
            }

            logger.debug(f"Overall statistics calculated: avg_grade={assignment_stats['avg_grade']}")
            return result

        except Exception as e:
            logger.error(f"Error calculating overall statistics: {e}")
            return self._get_empty_statistics()

    def calculate_actual_progress_for_week(
        self,
        user: User,
        selected_week: int,
        total_weeks: int,
        group_name: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Berechnet tatsächlichen Fortschritt für eine bestimmte Woche

        Args:
            user: User-Objekt
            selected_week: Gewählte Referenzwoche
            total_weeks: Gesamtanzahl Wochen
            group_name: Name der Gruppe (optional)

        Returns:
            Dictionary mit Fortschrittswerten
        """
        logger.debug(f"Calculating week progress for {user.name}, week {selected_week}")

        try:
            # Sammle Checklisten-Daten
            checklists = user.get_activities_by_type('checklists')
            total_checklists = len(checklists)

            if total_checklists == 0:
                return {'pflichtProgress': 0.0, 'gesamtProgress': 0.0}

            # Erwartete Anzahl Checklisten für die gewählte Woche
            expected_checklists_for_week = math.ceil((total_checklists / total_weeks) * selected_week)

            # Berechne Fortschritte
            total_pflicht_progress = 0.0
            total_gesamt_progress = 0.0

            for checklist in checklists:
                progress_data = checklist.get('progress', {})

                # Parse Prozent-Strings
                pflicht_percent = self._parse_percentage(progress_data.get('required_progress', '0%'))
                gesamt_percent = self._parse_percentage(progress_data.get('all_progress', '0%'))

                total_pflicht_progress += pflicht_percent
                total_gesamt_progress += gesamt_percent

            # Durchschnittlicher Fortschritt pro Checkliste
            avg_pflicht_per_checklist = total_pflicht_progress / total_checklists if total_checklists > 0 else 0
            avg_gesamt_per_checklist = total_gesamt_progress / total_checklists if total_checklists > 0 else 0

            # Erwarteter Gesamtfortschritt für die Woche
            expected_total_pflicht_points = expected_checklists_for_week * 100  # 100% pro Checkliste
            expected_total_gesamt_points = expected_checklists_for_week * 100

            # Tatsächlicher Fortschritt als Prozentsatz des Erwarteten
            pflicht_progress = (total_pflicht_progress / expected_total_pflicht_points * 100) if expected_total_pflicht_points > 0 else 0
            gesamt_progress = (total_gesamt_progress / expected_total_gesamt_points * 100) if expected_total_gesamt_points > 0 else 0

            # Begrenze auf 100%
            pflicht_progress = min(100, max(0, pflicht_progress))
            gesamt_progress = min(100, max(0, gesamt_progress))

            result = {
                'pflichtProgress': round(pflicht_progress, 1),
                'gesamtProgress': round(gesamt_progress, 1)
            }

            logger.debug(f"Week progress for {user.name}: {result}")
            return result

        except Exception as e:
            logger.error(f"Error calculating week progress for {user.name}: {e}")
            return {'pflichtProgress': 0.0, 'gesamtProgress': 0.0}

    def create_structured_tables(
        self,
        groups: Dict[str, Group],
        categories: List[Category]
    ) -> Dict[str, Any]:
        """
        Erstellt strukturierte Tabellendaten für das Frontend

        Args:
            groups: Dictionary mit Group-Objekten
            categories: Liste der Kategorien

        Returns:
            Dictionary mit strukturierten Tabellendaten
        """
        logger.debug(f"Creating structured tables for {len(groups)} groups")

        structured_tables = {}

        try:
            # Sammle alle relevanten Aktivitäten
            all_checklists = []
            pflicht_assignments = []
            zentrale_assignments = []

            for category in categories:
                # Checklisten sammeln
                all_checklists.extend(category.checklists)

                # Pflichtaufgaben sammeln
                if category.is_pflichtaufgaben():
                    pflicht_assignments.extend(category.assignments + category.quizzes)

                # Zentrale Leistungsnachweise sammeln
                if category.is_zentrale_leistungsnachweise():
                    zentrale_assignments.extend(category.assignments + category.quizzes)

            # Sortiere alphabetisch
            all_checklists.sort(key=lambda x: x.title)
            pflicht_assignments.sort(key=lambda x: x.title)
            zentrale_assignments.sort(key=lambda x: x.title)

            # Erstelle Tabellen für jede Gruppe
            for group_name, group in groups.items():
                group_tables = {
                    'checklists': self._create_checklist_table(group, all_checklists),
                    'pflichtaufgaben': self._create_assignment_table(group, pflicht_assignments),
                    'zentrale_leistungsnachweise': self._create_assignment_table(group, zentrale_assignments)
                }
                structured_tables[group_name] = group_tables

            logger.debug(f"Structured tables created for {len(structured_tables)} groups")
            return structured_tables

        except Exception as e:
            logger.error(f"Error creating structured tables: {e}")
            return {}

    def _create_assignment_details(self, categories: List[Category]) -> Dict[str, Dict[str, Any]]:
        """
        Erstellt Assignment-Details-Dictionary für Berechnungen

        Args:
            categories: Liste der Kategorien

        Returns:
            Dictionary mit Assignment-Details, indexiert nach ID
        """
        assignment_details = {}

        for category in categories:
            for assignment in category.get_all_activities():
                assignment_details[assignment.id] = {
                    'title': assignment.title,
                    'url': assignment.url,
                    'category_name': assignment.category_name,
                    'type': assignment.activity_type.value
                }

        return assignment_details

    def _create_checklist_table(self, group: Group, checklists: List[Assignment]) -> Dict[str, Any]:
        """Erstellt Checklisten-Tabelle für eine Gruppe"""
        table = {
            'headers': ['Checkliste'] + [user.name for user in group.users],
            'rows': []
        }

        for checklist in checklists:
            row = {
                'checklist_id': checklist.id,
                'checklist_title': checklist.title,
                'checklist_url': checklist.url,
                'checklist_category': checklist.category_name,
                'user_progress': []
            }

            for user in group.users:
                progress = self._find_user_checklist_progress(user, checklist.id)
                row['user_progress'].append(progress)

            table['rows'].append(row)

        return table

    def _create_assignment_table(self, group: Group, assignments: List[Assignment]) -> Dict[str, Any]:
        """Erstellt Assignment-Tabelle für eine Gruppe"""
        table = {
            'headers': ['Aufgabe'] + [user.name for user in group.users],
            'rows': []
        }

        for assignment in assignments:
            row = {
                'assignment_id': assignment.id,
                'assignment_title': assignment.title,
                'assignment_url': assignment.url,
                'assignment_type': assignment.activity_type.value,
                'user_status': []
            }

            for user in group.users:
                status = self._find_user_assignment_status(user, assignment.id)
                status['user_name'] = user.name
                row['user_status'].append(status)

            table['rows'].append(row)

        return table

    def _find_user_checklist_progress(self, user: User, checklist_id: str) -> Dict[str, str]:
        """Findet Checklisten-Fortschritt für einen Benutzer"""
        checklists = user.get_activities_by_type('checklists')

        for checklist in checklists:
            if checklist.get('id') == checklist_id:
                progress = checklist.get('progress', {})
                return {
                    'required_progress': progress.get('required_progress', '0%'),
                    'all_progress': progress.get('all_progress', '0%'),
                    'url': checklist.get('url', '#')
                }

        return {'required_progress': '0%', 'all_progress': '0%', 'url': '#'}

    def _find_user_assignment_status(self, user: User, assignment_id: str) -> Dict[str, str]:
        """Findet Assignment-Status für einen Benutzer"""
        for activity_type in ['assignments', 'quizzes', 'checklists', 'feedbacks']:
            activities = user.get_activities_by_type(activity_type)

            for activity in activities:
                if activity.get('id') == assignment_id:
                    status_info = activity.get('status', {})
                    return {
                        'status': status_info.get('status', 'Nicht eingereicht'),
                        'status2': status_info.get('status2', ''),
                        'grade': GradeCalculator.round_grade_for_display(
                            str(status_info.get('grade', '-'))
                        )
                    }

        return {'status': 'Nicht eingereicht', 'status2': '', 'grade': '-'}

    def _parse_percentage(self, percent_str: str) -> float:
        """Konvertiert Prozent-String zu Float"""
        try:
            return float(str(percent_str).replace('%', ''))
        except (ValueError, TypeError):
            return 0.0

    def _get_empty_statistics(self) -> Dict[str, Any]:
        """Gibt leere Statistik-Struktur zurück"""
        return {
            'assignments': {
                "avg_percent_submitted": 0.0,
                "avg_percent_submitted_timed": 0.0,
                "avg_grade": None
            },
            'checklists': {
                "total_required_100": 0,
                "avg_required_progress": 0.0,
                "avg_all_progress": 0.0,
                "avg_required_progress_timed": 0.0,
                "avg_all_progress_timed": 0.0
            }
        }