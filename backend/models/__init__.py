"""
Data Models für Mebis Dashboard

Definiert die Kerngeschäftsobjekte und deren Validierung.
"""

from .user import User, UserProgress
from .assignment import Assignment, AssignmentStatus
from .group import Group, GroupStatistics
from .category import Category
from .grade import Grade, GradeCalculator

__all__ = [
    'User', 'UserProgress',
    'Assignment', 'AssignmentStatus',
    'Group', 'GroupStatistics',
    'Category',
    'Grade', 'GradeCalculator'
]