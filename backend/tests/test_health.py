import pytest
from rest_framework import status


@pytest.mark.django_db
def test_health_check_endpoint(api_client):
    """Verify health endpoint responds with healthy status and metadata."""
    response = api_client.get('/api/health/')
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data['service'] == 'driverxtra-backend'
    assert 'status' in data
    assert 'database' in data
    assert 'timestamp' in data
