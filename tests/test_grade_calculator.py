"""
Unit Tests für Grade Calculator

Testet die Noten-Konvertierung und Berechnungen.
"""

import unittest
from backend.models.grade import GradeCalculator

class TestGradeCalculator(unittest.TestCase):
    """Test-Klasse für GradeCalculator"""

    def test_star_grade_conversion(self):
        """Test Sterne-basierte Noten-Konvertierung"""
        test_cases = [
            ("**** Exzellent", 1.0),
            ("*** Solide Umsetzung", 2.5),
            ("** Verbesserungsbedarf", 4.0),
            ("* Nicht akzeptabel", 5.5),
        ]

        for input_grade, expected in test_cases:
            with self.subTest(input_grade=input_grade):
                result = GradeCalculator.convert_to_ihk(input_grade)
                self.assertEqual(result, expected)

    def test_points_grade_conversion(self):
        """Test Punkte-basierte Noten-Konvertierung"""
        test_cases = [
            ("80 / 100", 3.0),  # 80% = Befriedigend
            ("95/100", 1.0),    # 95% = Sehr gut
            ("60 / 100", 4.0),  # 60% = Ausreichend
            ("40/100", 5.0),    # 40% = Mangelhaft
        ]

        for input_grade, expected in test_cases:
            with self.subTest(input_grade=input_grade):
                result = GradeCalculator.convert_to_ihk(input_grade)
                self.assertEqual(result, expected)

    def test_ihk_grade_passthrough(self):
        """Test direkte IHK-Noten"""
        test_cases = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]

        for grade in test_cases:
            with self.subTest(grade=grade):
                result = GradeCalculator.convert_to_ihk(grade)
                self.assertEqual(result, grade)

    def test_invalid_grades(self):
        """Test ungültige Noten"""
        invalid_grades = [
            None, "", "-", "Nicht bewertet", "Keine Bewertung",
            "abc", "7.0", "-1.0", "invalid"
        ]

        for invalid_grade in invalid_grades:
            with self.subTest(grade=invalid_grade):
                result = GradeCalculator.convert_to_ihk(invalid_grade)
                self.assertIsNone(result)

    def test_points_to_ihk_grade(self):
        """Test Punkte zu IHK-Note Konvertierung"""
        test_cases = [
            (95, 1.0),   # Sehr gut
            (85, 2.0),   # Gut
            (75, 3.0),   # Befriedigend
            (55, 4.0),   # Ausreichend
            (35, 5.0),   # Mangelhaft
            (15, 6.0),   # Ungenügend
        ]

        for points, expected in test_cases:
            with self.subTest(points=points):
                result = GradeCalculator.points_to_ihk(points)
                self.assertEqual(result, expected)

    def test_calculate_average(self):
        """Test Durchschnittsberechnung"""
        # Test mit gültigen Noten
        grades = [1.0, 2.0, 3.0, 4.0]
        result = GradeCalculator.calculate_average(grades)
        self.assertEqual(result, 2.5)

        # Test mit gemischten Formaten
        mixed_grades = ["**** Exzellent", "80/100", 2.0, "*** Solide Umsetzung"]
        result = GradeCalculator.calculate_average(mixed_grades)
        self.assertIsInstance(result, float)
        self.assertGreater(result, 0)
        self.assertLessEqual(result, 6)

        # Test mit leerer Liste
        result = GradeCalculator.calculate_average([])
        self.assertIsNone(result)

        # Test mit ungültigen Noten
        invalid_grades = [None, "", "invalid"]
        result = GradeCalculator.calculate_average(invalid_grades)
        self.assertIsNone(result)

    def test_round_grade_for_display(self):
        """Test Noten-Rundung für Anzeige"""
        test_cases = [
            ("1.4", "1"),
            ("1.5", "2"),
            ("2.6", "3"),
            ("3.3", "3"),
            ("Nicht bewertet", "Nicht bewertet"),
            ("-", "-"),
        ]

        for input_grade, expected in test_cases:
            with self.subTest(input_grade=input_grade):
                result = GradeCalculator.round_grade_for_display(input_grade)
                self.assertEqual(result, expected)

if __name__ == '__main__':
    unittest.main()