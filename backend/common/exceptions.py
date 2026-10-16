from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

def custom_exception_handler(exc, context):
    """Custom DRF exception handler providing consistent, clean error payloads."""
    response = exception_handler(exc, context)

    if response is not None:
        error_message = "Validation or execution error."
        if isinstance(response.data, dict):
            if 'detail' in response.data:
                error_message = str(response.data['detail'])
            elif response.data:
                field_errors = []
                for field, errs in response.data.items():
                    if isinstance(errs, list) and errs:
                        field_errors.append(f"{field}: {errs[0]}")
                    elif isinstance(errs, str):
                        field_errors.append(f"{field}: {errs}")
                    else:
                        field_errors.append(f"{field}: {errs}")
                if field_errors:
                    error_message = "; ".join(field_errors[:3])
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
