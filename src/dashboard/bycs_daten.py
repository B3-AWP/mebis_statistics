"""
Daten für das Dashboard in ByCS (bycs/dashboard).

Dort gibt es keinen Flask-Server und keine config/.env. Was das Backend
zur Laufzeit aus Plan und Konfiguration liest, wird beim Bauen des ZIP
einmal mit Python erzeugt und als JSON beigelegt:

- ``plan_dashboard.json``: der validierte Plan in der Form von
  ``Plan.to_dict()`` — dieselbe Normalisierung wie im Backend, nicht in
  JavaScript nachgebaut.
- ``einstellungen.json``: Ausschlussliste, ignorierte Gruppen,
  Notenzuordnung, Mitarbeitsnoten-Konfiguration, Zeitfenster.

Die Ausschlussliste enthält Namen. Sie landet nur im ZIP für die
Lehrkräfte-Aktivität, die für Lernende verborgen ist.
"""
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config.config_manager import config_manager  # noqa: E402
from src.common.plan_loader import get_plan  # noqa: E402


def plan_fuer_browser(plan=None) -> dict:
    """Validierter Plan wie in /api/data (``Plan.to_dict()``)."""
    return (plan or get_plan()).to_dict()


def einstellungen_fuer_browser() -> dict:
    """Alles aus der Konfiguration, was die Aufbereitung braucht."""
    # Gleiche Quelle wie das Backend; der Import setzt dort das CWD auf
    # den Projekt-Root, damit config/exclude_names.txt gefunden wird.
    from src.dashboard.backend import load_excluded_names, load_ignored_groups

    return {
        'excluded_names': sorted(load_excluded_names()),
        'ignored_groups': sorted(load_ignored_groups()),
        # JSON kennt nur Text-Schluessel — wie in der Flask-Antwort
        'grade_mapping': {str(k): v for k, v in config_manager.get_grade_mapping().items()},
        'mitarbeitsnote_config': config_manager.get_mitarbeitsnote_config() or {},
        'recent_submission_days': config_manager.get_recent_submission_days(),
        'inactive_threshold_days': config_manager.get_inactive_threshold_days(),
        'environment': {
            'flask_env': os.getenv('FLASK_ENV', 'production'),
            'log_level': os.getenv('LOG_LEVEL', 'INFO'),
            'flask_debug': os.getenv('FLASK_DEBUG', 'False'),
        },
    }
