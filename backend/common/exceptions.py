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

        # Phase 3 Audit: Record denied audit entries on 403 Forbidden
        if response.status_code == status.HTTP_403_FORBIDDEN:
            try:
                from platform_core.audit.writer import record_denied_audit_entry
                from common.middleware import get_current_correlation_id

                request = context.get('request') if context else None
                view = context.get('view') if context else None
                user = getattr(request, 'user', None) if request else None
                actor_id = getattr(user, 'id', None) if (user and user.is_authenticated) else None
                corr_id = getattr(request, 'correlation_id', '') if request else ''
                if not corr_id:
                    corr_id = get_current_correlation_id()

                path = getattr(request, 'path', '') if request else ''
                method = getattr(request, 'method', '') if request else ''
                view_name = view.__class__.__name__ if view else ''

                record_denied_audit_entry(
                    action=f"permission:{method.lower()}" if method else "permission:access",
                    resource_type="APIEndpoint",
                    resource_id=path,
                    reason_code="PERMISSION_DENIED",
                    correlation_id=corr_id,
                    actor_id=actor_id,
                    metadata={"view": view_name, "path": path, "method": method, "detail": error_message},
                )
            except Exception:
                pass

    return response
