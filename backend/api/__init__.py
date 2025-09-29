"""
API Layer für Mebis Dashboard

Enthält HTTP-Endpoints, Request-Validierung und Response-Formatierung.
Trennt API-Logik von Business Logic (Services).
"""

from .endpoints import create_api_blueprint
from .validators import validate_api_request, APIError
from .responses import format_success_response, format_error_response

__all__ = [
    'create_api_blueprint',
    'validate_api_request', 'APIError',
    'format_success_response', 'format_error_response'
]