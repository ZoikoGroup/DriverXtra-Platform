from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.db import connection
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class HealthCheckView(APIView):
    """Health check endpoint to verify backend service and database connectivity.

    GET /api/health/
    """
    permission_classes = [AllowAny]

    def get(self, request):
        db_status = "connected"
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                row = cursor.fetchone()
                if not row or row[0] != 1:
                    db_status = "unhealthy"
        except Exception as e:
            logger.warning(f"Database health check warning: {e}")
            db_status = "unavailable"

        payload = {
            "status": "healthy" if db_status == "connected" else "degraded",
            "service": "driverxtra-backend",
            "version": "1.0.0",
            "timestamp": timezone.now().isoformat(),
            "database": db_status,
        }
        return Response(payload, status=status.HTTP_200_OK)
