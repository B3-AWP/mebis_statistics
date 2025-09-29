"""
Grade Model und Grade Calculator

Behandelt Noten-Konvertierung und IHK-konforme Berechnungen.
"""

from typing import List, Optional, Union
import re
import math
from dataclasses import dataclass
from logger_config import get_logger

logger = get_logger('models.grade')

@dataclass
class Grade:
    """
    Repräsentiert eine Note im System
    """
    value: Union[str, float]
    type: str = "unknown"  # star, percentage, ihk, points
    original: str = ""

    def __post_init__(self):
        if not self.original:
            self.original = str(self.value)

class GradeCalculator:
    """
    Statische Methoden für Noten-Berechnungen und Konvertierungen
    """

    # IHK-Noten-Mapping (Punkte zu Note)
    IHK_GRADE_MAPPING = {
        (92, 100): 1.0,  # Sehr gut
        (81, 91): 2.0,   # Gut
        (67, 80): 3.0,   # Befriedigend
        (50, 66): 4.0,   # Ausreichend
        (30, 49): 5.0,   # Mangelhaft
        (0, 29): 6.0     # Ungenügend
    }

    # Sterne-basierte Noten zu IHK-Noten
    STAR_MAPPING = {
        "**** Exzellent": 1.0,           # Sehr gut
        "*** Solide Umsetzung": 2.5,     # Gut-Befriedigend
        "** Verbesserungsbedarf": 4.0,   # Ausreichend
        "* Nicht akzeptabel": 5.5        # Mangelhaft
    }

    # Umgekehrtes Mapping für Anzeige
    IHK_TO_POINTS = {
        1.0: 96,   # Sehr gut (92-100)
        2.0: 86,   # Gut (81-91)
        3.0: 73.5, # Befriedigend (67-80)
        4.0: 58.5, # Ausreichend (50-66)
        5.0: 40,   # Mangelhaft (30-49)
        6.0: 15    # Ungenügend (0-29)
    }

    @staticmethod
    def convert_to_ihk(grade_input: Union[str, float, None]) -> Optional[float]:
        """
        Konvertiert verschiedene Notenformate zu IHK-Note (1-6)

        Args:
            grade_input: Note in verschiedenen Formaten

        Returns:
            IHK-Note (1.0-6.0) oder None wenn nicht konvertierbar
        """
        if not grade_input or grade_input in ['-', 'Nicht bewertet', 'Keine Bewertung']:
            return None

        grade_str = str(grade_input).strip()

        try:
            # 1. Sterne-basierte Noten
            if grade_str in GradeCalculator.STAR_MAPPING:
                result = GradeCalculator.STAR_MAPPING[grade_str]
                logger.debug(f"Converted star grade '{grade_str}' to IHK: {result}")
                return result

            # 2. Punkte-basierte Noten (z.B. "80 / 100", "15/20")
            if '/' in grade_str:
                try:
                    parts = grade_str.split('/')
                    points = float(parts[0].strip())
                    max_points = float(parts[1].strip())

                    if max_points <= 0:
                        logger.warning(f"Invalid max_points in grade: {grade_str}")
                        return None

                    percentage = (points / max_points) * 100
                    result = GradeCalculator.points_to_ihk(percentage)
                    logger.debug(f"Converted points grade '{grade_str}' ({percentage}%) to IHK: {result}")
                    return result

                except (ValueError, IndexError, ZeroDivisionError) as e:
                    logger.warning(f"Could not parse points grade '{grade_str}': {e}")

            # 3. Prozent-basierte Noten (z.B. "85%", "75.5%")
            percent_match = re.search(r'(\d+(?:[.,]\d+)?)\s*%', grade_str)
            if percent_match:
                try:
                    percentage = float(percent_match.group(1).replace(',', '.'))
                    result = GradeCalculator.points_to_ihk(percentage)
                    logger.debug(f"Converted percentage grade '{grade_str}' to IHK: {result}")
                    return result
                except ValueError as e:
                    logger.warning(f"Could not parse percentage grade '{grade_str}': {e}")

            # 4. Direkte numerische Noten (1-6)
            try:
                if isinstance(grade_input, str):
                    grade_num = float(grade_str.replace(',', '.'))
                else:
                    grade_num = float(grade_input)

                # Nur Noten zwischen 1 und 6 sind gültig
                if 1 <= grade_num <= 6:
                    result = round(grade_num, 1)
                    logger.debug(f"Accepted direct IHK grade: {result}")
                    return result
                else:
                    logger.debug(f"Grade {grade_num} outside valid IHK range (1-6)")

            except (ValueError, TypeError) as e:
                logger.debug(f"Could not convert '{grade_str}' to number: {e}")

            # 5. Andere numerische Werte als Prozentsätze behandeln
            number_match = re.search(r'(\d+(?:[.,]\d+)?)', grade_str)
            if number_match:
                try:
                    number = float(number_match.group(1).replace(',', '.'))

                    # Wenn Zahl zwischen 0-100, als Prozentsatz behandeln
                    if 0 <= number <= 100:
                        result = GradeCalculator.points_to_ihk(number)
                        logger.debug(f"Treated number '{grade_str}' as percentage, IHK: {result}")
                        return result

                except ValueError as e:
                    logger.debug(f"Could not parse number from '{grade_str}': {e}")

        except Exception as e:
            logger.error(f"Unexpected error converting grade '{grade_str}': {e}")

        logger.debug(f"Could not convert grade '{grade_str}' to IHK format")
        return None

    @staticmethod
    def points_to_ihk(points: float) -> float:
        """
        Konvertiert Punkte (0-100) zu IHK-Note (1-6)

        Args:
            points: Punkte zwischen 0 und 100

        Returns:
            IHK-Note zwischen 1.0 und 6.0
        """
        points = max(0, min(100, points))  # Clamp to 0-100

        for (min_points, max_points), grade in GradeCalculator.IHK_GRADE_MAPPING.items():
            if min_points <= points <= max_points:
                return grade

        # Fallback
        return 6.0

    @staticmethod
    def ihk_to_points(grade: float) -> float:
        """
        Konvertiert IHK-Note zu mittleren Punktwert für Berechnungen

        Args:
            grade: IHK-Note (1-6)

        Returns:
            Mittlerer Punktwert
        """
        return GradeCalculator.IHK_TO_POINTS.get(grade, 50)

    @staticmethod
    def calculate_average(grades: List[Union[str, float]]) -> Optional[float]:
        """
        Berechnet IHK-konformen Notendurchschnitt

        Args:
            grades: Liste von Noten in verschiedenen Formaten

        Returns:
            Durchschnittsnote oder None wenn keine gültigen Noten
        """
        if not grades:
            return None

        # Konvertiere alle Noten zu IHK-Format
        valid_grades = []
        for grade in grades:
            ihk_grade = GradeCalculator.convert_to_ihk(grade)
            if ihk_grade is not None:
                valid_grades.append(ihk_grade)

        if not valid_grades:
            logger.warning("No valid grades found for average calculation")
            return None

        # IHK-konforme Durchschnittsberechnung:
        # Arithmetisches Mittel der Noten, gerundet auf 0.1
        average = sum(valid_grades) / len(valid_grades)
        result = round(average, 1)

        logger.debug(f"Calculated grade average: {result} from {len(valid_grades)} grades")
        return result

    @staticmethod
    def round_grade_for_display(grade_str: str) -> str:
        """
        Rundet eine Note für die Anzeige: bis 0.5 ab, ab 0.5 auf

        Args:
            grade_str: Note als String

        Returns:
            Gerundete Note oder ursprünglicher Wert
        """
        if not grade_str or grade_str in ['-', 'Nicht bewertet', 'Keine Bewertung']:
            return grade_str

        try:
            # Versuche, eine Zahl aus dem Grade-String zu extrahieren
            grade_match = re.search(r'(\d+[.,]\d+|\d+)', grade_str)
            if grade_match:
                grade_text = grade_match.group(1).replace(',', '.')
                grade_float = float(grade_text)

                # Runde auf ganze Zahlen: bis 0.5 ab, ab 0.5 auf
                rounded_grade = math.floor(grade_float + 0.5)
                return str(int(rounded_grade))

        except Exception as e:
            logger.debug(f"Could not round grade '{grade_str}': {e}")

        return grade_str

    @staticmethod
    def validate_grade(grade_input: Union[str, float]) -> bool:
        """
        Validiert ob ein Eingabewert eine gültige Note ist

        Args:
            grade_input: Zu validierende Note

        Returns:
            True wenn Note gültig ist
        """
        return GradeCalculator.convert_to_ihk(grade_input) is not None

    @staticmethod
    def format_grade_for_api(grade_input: Union[str, float], include_ihk: bool = False) -> dict:
        """
        Formatiert eine Note für API-Response

        Args:
            grade_input: Original-Note
            include_ihk: Ob IHK-Äquivalent inkludiert werden soll

        Returns:
            Dictionary mit formatierter Note
        """
        result = {
            'original': str(grade_input),
            'display': GradeCalculator.round_grade_for_display(str(grade_input)),
            'valid': GradeCalculator.validate_grade(grade_input)
        }

        if include_ihk:
            ihk_grade = GradeCalculator.convert_to_ihk(grade_input)
            result['ihk_equivalent'] = ihk_grade

        return result