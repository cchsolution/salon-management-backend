import logging
from django.conf import settings
from django.http import JsonResponse
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Unified Django REST Framework exception handler.
    Ensures that ALL API responses (including unhandled 500 exceptions, validation
    errors, and permission issues) ALWAYS return clean, structured JSON.
    Never lets Django return HTML error pages to the frontend.
    """
    response = exception_handler(exc, context)

    view = context.get('view')
    view_name = view.__class__.__name__ if view else 'APIView'

    if response is not None:
        # Standardize known DRF exceptions (ValidationError, NotFound, PermissionDenied, etc.)
        data = response.data

        if isinstance(data, dict):
            # If 'detail' is present, also expose it as 'error'
            if 'detail' in data and 'error' not in data:
                data['error'] = str(data['detail'])

            # If it's a validation error dict like {'field': ['msg']}, build a human-readable top-level 'error'
            if 'error' not in data:
                error_parts = []
                for field, msgs in data.items():
                    if isinstance(msgs, list):
                        msg_str = " ".join(str(m) for m in msgs)
                    else:
                        msg_str = str(msgs)
                    if field in ['non_field_errors', 'detail']:
                        error_parts.append(msg_str)
                    else:
                        error_parts.append(f"{field}: {msg_str}")
                if error_parts:
                    data['error'] = " | ".join(error_parts)
                else:
                    data['error'] = 'A validation error occurred.'
        elif isinstance(data, list):
            data = {
                'error': " ".join(str(item) for item in data),
                'details': data
            }
            response.data = data

        return response

    # UNCAUGHT EXCEPTION (500 Internal Server Error)
    # Log the full exception and traceback with context
    logger.error(
        f"Unhandled Server Exception in {view_name}: {exc}",
        exc_info=True,
        extra={'context': str(context)}
    )

    err_str = str(exc)
    user_msg = (
        f"Server Error in {view_name}: {err_str}"
        if getattr(settings, 'DEBUG', False)
        else (err_str if len(err_str) > 0 and len(err_str) < 150 and not any(k in err_str.lower() for k in ['syntax', 'line', 'file', 'traceback']) else "An internal server error occurred. Please try again.")
    )

    return Response(
        {
            'error': user_msg,
            'detail': err_str,
            'view': view_name,
            'status': 500
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def server_error_500_handler(request):
    """
    Django root 500 handler for unhandled exceptions outside DRF (e.g., middleware).
    Always returns application/json.
    """
    return JsonResponse(
        {
            'error': 'Internal Server Error (500)',
            'detail': 'An unexpected server error occurred. Please check backend logs or retry.',
            'status': 500
        },
        status=500
    )


def not_found_404_handler(request, exception=None):
    """
    Django root 404 handler.
    Always returns application/json.
    """
    return JsonResponse(
        {
            'error': 'API Endpoint Not Found (404)',
            'detail': f"The requested URL '{request.path}' was not found on this server.",
            'status': 404
        },
        status=404
    )

