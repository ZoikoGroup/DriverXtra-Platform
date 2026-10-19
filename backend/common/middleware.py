import contextvars
import uuid

_correlation_id_ctx = contextvars.ContextVar("correlation_id", default="")


def get_current_correlation_id() -> str:
    """Retrieve the correlation ID of the current request context."""
    return _correlation_id_ctx.get()


class CorrelationIdMiddleware:
    """Middleware that sets a correlation ID (from X-Request-ID header or generated UUID)
    on each incoming HTTP request, makes it available in request.correlation_id,
    stores it in a contextvar for decoupled logging/audit access,
    and echoes it in the response header X-Request-ID.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        corr_id = (
            request.headers.get("X-Request-ID")
            or request.META.get("HTTP_X_REQUEST_ID")
            or str(uuid.uuid4())
        )
        request.correlation_id = corr_id
        token = _correlation_id_ctx.set(corr_id)

        try:
            response = self.get_response(request)
        finally:
            _correlation_id_ctx.reset(token)

        response["X-Request-ID"] = corr_id
        return response
