"""URL Configuration for DriverXtra backend."""

from django.contrib import admin
from django.urls import path, include
from common.views import HealthCheckView

urlpatterns = [
    # Administration
    path('admin/', admin.site.urls),

    # Health check
    path('api/health/', HealthCheckView.as_view(), name='health-check'),

    # Phase 1: Authentication, Users & RBAC
    path('api/v1/', include('apps.identity.urls')),

    # Phase 1: Organisations & Tenant Management
    path('api/v1/', include('apps.organisations.urls')),

    # Phase 2: Seller Onboarding & Verification
    path('api/v1/', include('apps.onboarding.urls')),

    # Phase 2: Vehicle & Parts Catalogue
    path('api/v1/', include('apps.catalogue.urls')),

    # Phase 2: Personal Vehicle Garage
    path('api/v1/', include('apps.garage.urls')),

    # Marketplace: Vehicle & Spare Parts Submissions, Approvals & Public Browse
    path('api/v1/marketplace/', include('apps.marketplace.urls')),
]

# Serve media files in development / test environments
from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
