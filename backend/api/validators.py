"""
Request Validators

Input-Validierung für API-Requests.
"""

from typing import Any, Dict, Optional
from flask import request

class APIError(Exception):
    """
    Exception für API-Validierungsfehler
    """

    def __init__(
        self,
        message: str,
        error_code: str = "VALIDATION_ERROR",
        details: Optional[str] = None,
        status_code: int = 400
    ):
        self.message = message
        self.error_code = error_code
        self.details = details
        self.status_code = status_code
        super().__init__(message)

def validate_api_request(required_params: Optional[Dict[str, type]] = None) -> Dict[str, Any]:
    """
    Validiert API-Request-Parameter

    Args:
        required_params: Dictionary mit erforderlichen Parametern und deren Typen

    Returns:
        Dictionary mit validierten Parametern

    Raises:
        APIError: Bei Validierungsfehlern
    """
    if required_params is None:
        required_params = {}

    validated_params = {}

    # JSON-Body validieren (falls vorhanden)
    if request.is_json:
        try:
            json_data = request.get_json()
            if json_data is not None:
                validated_params.update(json_data)
        except Exception as e:
            raise APIError(
                message="Ungültiges JSON-Format",
                error_code="INVALID_JSON",
                details=str(e),
                status_code=400
            )

    # Query-Parameter hinzufügen
    validated_params.update(request.args.to_dict())

    # Erforderliche Parameter prüfen
    for param_name, param_type in required_params.items():
        if param_name not in validated_params:
            raise APIError(
                message=f"Erforderlicher Parameter fehlt: {param_name}",
                error_code="MISSING_PARAMETER",
                details=param_name,
                status_code=422
            )

        # Typ-Validierung
        value = validated_params[param_name]
        try:
            if param_type == bool:
                validated_params[param_name] = str(value).lower() in ('true', '1', 'yes', 'on')
            elif param_type == int:
                validated_params[param_name] = int(value)
            elif param_type == float:
                validated_params[param_name] = float(value)
            elif param_type == str:
                validated_params[param_name] = str(value)
            else:
                # Für komplexere Typen
                if not isinstance(value, param_type):
                    raise ValueError(f"Expected {param_type.__name__}, got {type(value).__name__}")

        except (ValueError, TypeError) as e:
            raise APIError(
                message=f"Ungültiger Typ für Parameter '{param_name}': {str(e)}",
                error_code="INVALID_TYPE",
                details=f"Expected {param_type.__name__}, got {type(value).__name__}",
                status_code=422
            )

    return validated_params

def validate_group_name(group_name: str) -> None:
    """
    Validiert einen Gruppennamen

    Args:
        group_name: Zu validierender Gruppenname

    Raises:
        APIError: Wenn Gruppenname ungültig ist
    """
    if not group_name or not isinstance(group_name, str):
        raise APIError(
            message="Gruppenname ist erforderlich und muss ein String sein",
            error_code="INVALID_GROUP_NAME",
            status_code=422
        )

    if len(group_name.strip()) == 0:
        raise APIError(
            message="Gruppenname darf nicht leer sein",
            error_code="EMPTY_GROUP_NAME",
            status_code=422
        )

    # Weitere Validierungen könnten hier hinzugefügt werden
    # z.B. erlaubte Zeichen, Länge, etc.

def validate_week_parameter(week: Any) -> int:
    """
    Validiert Wochen-Parameter

    Args:
        week: Wochen-Wert

    Returns:
        Validierte Wochenzahl

    Raises:
        APIError: Wenn Wochenzahl ungültig ist
    """
    try:
        week_int = int(week)
    except (ValueError, TypeError):
        raise APIError(
            message="Wochenzahl muss eine ganze Zahl sein",
            error_code="INVALID_WEEK",
            details=f"Got: {week}",
            status_code=422
        )

    if week_int < 1 or week_int > 52:
        raise APIError(
            message="Wochenzahl muss zwischen 1 und 52 liegen",
            error_code="WEEK_OUT_OF_RANGE",
            details=f"Got: {week_int}",
            status_code=422
        )

    return week_int

def validate_user_name(user_name: str) -> None:
    """
    Validiert einen Benutzernamen

    Args:
        user_name: Zu validierender Benutzername

    Raises:
        APIError: Wenn Benutzername ungültig ist
    """
    if not user_name or not isinstance(user_name, str):
        raise APIError(
            message="Benutzername ist erforderlich und muss ein String sein",
            error_code="INVALID_USER_NAME",
            status_code=422
        )

    if len(user_name.strip()) == 0:
        raise APIError(
            message="Benutzername darf nicht leer sein",
            error_code="EMPTY_USER_NAME",
            status_code=422
        )

    # Sicherheitscheck: Keine HTML/Script-Tags
    dangerous_chars = ['<', '>', '&', '"', "'"]
    if any(char in user_name for char in dangerous_chars):
        raise APIError(
            message="Benutzername enthält ungültige Zeichen",
            error_code="INVALID_CHARACTERS",
            status_code=422
        )