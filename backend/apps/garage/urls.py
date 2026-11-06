from django.urls import path
from apps.garage.views import (
    GarageVehicleListCreateView,
    GarageVehicleDetailView,
    GarageVehicleSetPrimaryView,
    VehicleServiceRecordListCreateView,
    VehicleServiceRecordDetailView,
    VehicleServicePassportPdfView,
)

urlpatterns = [
    path('garage/vehicles/', GarageVehicleListCreateView.as_view(), name='garage-vehicles-list'),
    path('garage/vehicles/<uuid:id>/', GarageVehicleDetailView.as_view(), name='garage-vehicle-detail'),
    path('garage/vehicles/<uuid:id>/set-primary/', GarageVehicleSetPrimaryView.as_view(), name='garage-vehicle-set-primary'),
    path('garage/vehicles/<uuid:vehicle_id>/service-history/', VehicleServiceRecordListCreateView.as_view(), name='garage-vehicle-service-history-list'),
    path('garage/vehicles/<uuid:vehicle_id>/passport/pdf/', VehicleServicePassportPdfView.as_view(), name='garage-vehicle-passport-pdf'),
    path('garage/service-history/<uuid:id>/', VehicleServiceRecordDetailView.as_view(), name='garage-service-history-detail'),
]
