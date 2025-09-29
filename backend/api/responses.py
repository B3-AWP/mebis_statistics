"""
Response Formatting

Standardisierte Response-Formatierung für alle API-Endpoints.
"""

from flask import jsonify
from typing import Any, Dict, Optional
import datetime

def format_success_response(
    data: Any,
    message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> tuple:
    """
    Formatiert eine erfolgreiche API-Response

    Args:
        data: Response-Daten
        message: Optionale Success-Message
        metadata: Optionale Metadaten

    Returns:
        Tuple mit (response, status_code)
    """
    response = {
        'success': True,
        'data': data,
        'timestamp': datetime.datetime.now().isoformat()
    }

    if message:
        response['message'] = message

    if metadata:
        response['metadata'] = metadata

    return jsonify(response), 200

def format_error_response(
    message: str,
    error_code: str,
    details: Optional[str] = None,
    status_code: int = 400
) -> tuple:
    """
    Formatiert eine Fehler-Response

    Args:
        message: Benutzerfreundliche Fehlermeldung
        error_code: Maschinenlesbarer Fehlercode
        details: Optionale zusätzliche Details
        status_code: HTTP-Status-Code

    Returns:
        Tuple mit (response, status_code)
    """
    response = {
        'success': False,
        'error': {
            'message': message,
            'code': error_code,
            'timestamp': datetime.datetime.now().isoformat()
        }
    }

    if details:
        response['error']['details'] = details

    return jsonify(response), status_code

def format_validation_error(
    field: str,
    message: str,
    value: Optional[Any] = None
) -> tuple:
    """
    Formatiert einen Validierungs-Fehler

    Args:
        field: Name des fehlerhaften Feldes
        message: Validierungs-Fehlermeldung
        value: Fehlerhafter Wert (optional)

    Returns:
        Tuple mit (response, status_code)
    """
    error_details = {
        'field': field,
        'message': message
    }

    if value is not None:
        error_details['value'] = value

    return format_error_response(
        message=f"Validierungsfehler in Feld '{field}': {message}",
        error_code="VALIDATION_ERROR",
        details=error_details,
        status_code=422
    )