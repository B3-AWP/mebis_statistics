"""
Grade Utilities

Hilfsfunktionen für Noten-Berechnungen, als Wrapper um die Grade-Models.
Für Rückwärtskompatibilität mit bestehendem Code.
"""

from typing import List, Union, Optional
from backend.models.grade import GradeCalculator

def round_grade(grade_str: str) -> str:
    """
    Rundet eine Note für die Anzeige

    Wrapper um GradeCalculator.round_grade_for_display für Kompatibilität
    """
    return GradeCalculator.round_grade_for_display(grade_str)

def convert_grade_to_ihk(grade_input: Union[str, float, None]) -> Optional[float]:
    """
    Konvertiert Note zu IHK-Format

    Wrapper um GradeCalculator.convert_to_ihk für Kompatibilität
    """
    return GradeCalculator.convert_to_ihk(grade_input)

def calculate_ihk_average(grades: List[Union[str, float]]) -> Optional[float]:
    """
    Berechnet IHK-Durchschnitt

    Wrapper um GradeCalculator.calculate_average für Kompatibilität
    """
    return GradeCalculator.calculate_average(grades)

def points_to_ihk_grade(points: float) -> float:
    """
    Konvertiert Punkte zu IHK-Note

    Wrapper um GradeCalculator.points_to_ihk für Kompatibilität
    """
    return GradeCalculator.points_to_ihk(points)