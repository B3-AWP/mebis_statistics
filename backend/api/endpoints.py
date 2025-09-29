"""
API Endpoints

Definiert alle HTTP-Endpoints mit Input-Validierung und standardisierter Fehlerbehandlung.
"""

from flask import Blueprint, jsonify, request
from typing import Dict, Any

from logger_config import get_logger
from backend.services.data_service import DataService
from backend.services.calculation_service import CalculationService
from backend.api.validators import validate_api_request, APIError
from backend.api.responses import format_success_response, format_error_response

logger = get_logger('api.endpoints')

def create_api_blueprint() -> Blueprint:
    """
    Erstellt und konfiguriert das API Blueprint

    Returns:
        Konfiguriertes Flask Blueprint
    """
    api = Blueprint('api', __name__, url_prefix='/api')

    # Services initialisieren
    data_service = DataService()
    calculation_service = CalculationService()

    @api.route('/data', methods=['GET'])
    def get_dashboard_data():
        """
        Haupt-API-Endpoint für Dashboard-Daten

        Returns:
            JSON-Response mit Dashboard-Daten oder Fehler
        """
        logger.info("API endpoint /api/data called")

        try:
            # Parameter validieren
            force_reload = request.args.get('force_reload', 'false').lower() == 'true'

            # Daten laden
            data = data_service.get_latest_data(force_reload=force_reload)

            # Daten-Integrität prüfen
            integrity_issues = data_service.validate_data_integrity(data)
            if integrity_issues:
                logger.warning(f"Data integrity issues found: {integrity_issues}")

            # Benutzer-Fortschritte berechnen
            all_user_progresses = []
            groups_with_progress = {}

            for group_name, group in data['groups'].items():
                user_progresses = []

                for user in group.users:
                    user_progress = calculation_service.calculate_user_progress(
                        user=user,
                        categories=data['categories'],
                        current_week=10,  # TODO: Aus Request-Parameter holen
                        total_weeks=40
                    )
                    user_progresses.append(user_progress)
                    all_user_progresses.append(user_progress)

                # Gruppen-Statistiken berechnen
                group_stats = calculation_service.calculate_group_statistics(
                    group=group,
                    user_progresses=user_progresses
                )

                # Kombiniere Gruppendaten mit Statistiken
                groups_with_progress[group_name] = {
                    'name': group.name,
                    'users': [up.to_dict() for up in user_progresses],
                    'assignments': group_stats.assignments,
                    'checklists': group_stats.checklists
                }

            # Gesamtstatistiken berechnen
            overall_stats = calculation_service.calculate_overall_statistics(all_user_progresses)

            # Strukturierte Tabellen erstellen
            structured_tables = calculation_service.create_structured_tables(
                groups=data['groups'],
                categories=data['categories']
            )

            # Assignment-Details für Frontend
            assignment_details = calculation_service._create_assignment_details(data['categories'])

            # Response zusammenstellen
            response_data = {
                'groups': groups_with_progress,
                'overall_stats': overall_stats,
                'assignment_details': assignment_details,
                'activities_by_category': [cat.to_dict() for cat in data['categories']],
                'structured_tables': structured_tables,
                'ignored_groups': list(data['ignored_groups']),
                'last_updated': data['last_updated'],
                'metadata': data['metadata']
            }

            if integrity_issues:
                response_data['warnings'] = integrity_issues

            logger.info(f"API response created successfully: {data['metadata']}")
            return format_success_response(response_data)

        except FileNotFoundError as e:
            logger.error(f"No export file found: {e}")
            return format_error_response(
                message="Keine Export-Datei gefunden",
                error_code="NO_EXPORT_FILE",
                status_code=404
            )

        except ValueError as e:
            logger.error(f"Data validation error: {e}")
            return format_error_response(
                message="Fehler beim Laden der Daten",
                error_code="DATA_VALIDATION_ERROR",
                details=str(e),
                status_code=400
            )

        except Exception as e:
            logger.error(f"Unexpected error in get_dashboard_data: {e}", exc_info=True)
            return format_error_response(
                message="Unerwarteter Server-Fehler",
                error_code="INTERNAL_ERROR",
                status_code=500
            )

    @api.route('/groups', methods=['GET'])
    def get_groups():
        """
        API-Endpoint für Gruppen-Liste

        Returns:
            JSON-Response mit verfügbaren Gruppen
        """
        logger.info("API endpoint /api/groups called")

        try:
            # Daten laden (nur Metadaten benötigt)
            data = data_service.get_latest_data()

            # Einfache Gruppen-Liste erstellen
            groups = []
            for group_name, group in data['groups'].items():
                groups.append({
                    'name': group.name,
                    'user_count': group.get_user_count()
                })

            response_data = {
                'groups': groups,
                'total_groups': len(groups),
                'total_users': sum(g['user_count'] for g in groups)
            }

            logger.info(f"Groups list returned: {len(groups)} groups")
            return format_success_response(response_data)

        except Exception as e:
            logger.error(f"Error in get_groups: {e}")
            return format_error_response(
                message="Fehler beim Laden der Gruppen",
                error_code="GROUPS_ERROR",
                status_code=500
            )

    @api.route('/health', methods=['GET'])
    def health_check():
        """
        Health-Check-Endpoint für Monitoring

        Returns:
            JSON-Response mit System-Status
        """
        try:
            # Prüfe ob Export-Datei verfügbar ist
            latest_file = data_service.find_latest_export_file()
            has_data = latest_file is not None

            status = {
                'status': 'healthy' if has_data else 'degraded',
                'has_export_data': has_data,
                'last_export_file': latest_file,
                'services': {
                    'data_service': 'ok',
                    'calculation_service': 'ok'
                }
            }

            return format_success_response(status)

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return format_error_response(
                message="Health check failed",
                error_code="HEALTH_CHECK_ERROR",
                status_code=500
            )

    @api.route('/cache/clear', methods=['POST'])
    def clear_cache():
        """
        Endpoint zum Löschen des Daten-Caches

        Returns:
            JSON-Response mit Bestätigung
        """
        logger.info("Cache clear requested")

        try:
            data_service.clear_cache()

            return format_success_response({
                'message': 'Cache cleared successfully',
                'timestamp': data_service._cache_timestamp
            })

        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return format_error_response(
                message="Fehler beim Löschen des Caches",
                error_code="CACHE_CLEAR_ERROR",
                status_code=500
            )

    # Error Handler für API-spezifische Fehler
    @api.errorhandler(APIError)
    def handle_api_error(error):
        """Handler für API-Validierungsfehler"""
        logger.warning(f"API validation error: {error}")
        return format_error_response(
            message=error.message,
            error_code=error.error_code,
            details=error.details,
            status_code=error.status_code
        )

    @api.errorhandler(404)
    def handle_not_found(error):
        """Handler für 404-Fehler"""
        return format_error_response(
            message="Endpoint nicht gefunden",
            error_code="NOT_FOUND",
            status_code=404
        )

    @api.errorhandler(405)
    def handle_method_not_allowed(error):
        """Handler für 405-Fehler"""
        return format_error_response(
            message="HTTP-Methode nicht erlaubt",
            error_code="METHOD_NOT_ALLOWED",
            status_code=405
        )

    return api