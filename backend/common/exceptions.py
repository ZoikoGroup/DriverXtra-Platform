from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def custom_exception_handler(exc, context):
    """Custom DRF exception handler providing consistent, clean error payloads."""
    response = exception_handler(exc, context)

    if response is not None:
        error_message = "Validation or execution error."
        if isinstance(response.data, dict) and 'detail' in response.data:
            error_message = str(response.data['detail'])
        elif isinstance(response.data, list) and len(response.data) > 0:
            error_message = str(response.data[0])

        formatted_payload = {
            'status': 'error',
            'code': response.status_code,
            'message': error_message,
            'details': response.data,
        }
        response.data = formatted_payload

    return response
