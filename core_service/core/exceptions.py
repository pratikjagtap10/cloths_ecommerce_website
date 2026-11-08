"""
Centralised error format for every API response:

    {"detail": "Human readable message", "errors": {...optional field errors...}}

The frontend always shows `detail`, so validation errors are flattened into one
readable sentence (e.g. "Password: This password is too common.").
"""
from rest_framework.views import exception_handler


def _first_message(data) -> str:
    if isinstance(data, list):
        return _first_message(data[0]) if data else "Invalid request."
    if isinstance(data, dict):
        if not data:
            return "Invalid request."
        key, value = next(iter(data.items()))
        message = _first_message(value)
        if key in ("non_field_errors", "detail"):
            return message
        return f"{key.replace('_', ' ').capitalize()}: {message}"
    return str(data)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None  # unhandled -> Django returns 500

    data = response.data
    if isinstance(data, dict) and "detail" in data:
        data["detail"] = str(data["detail"])  # keep extra keys such as "code"
    else:
        response.data = {"detail": _first_message(data), "errors": data}
    return response
