from django.urls import path
from apps.garage.views import (
    GarageVehicleListCreateView,
    GarageVehicleDetailView,
    GarageVehicleSetPrimaryView,
)

urlpatterns = [
    path('garage/vehicles/', GarageVehicleListCreateView.as_view(), name='garage-vehicles-list'),
    path('garage/vehicles/<uuid:id>/', GarageVehicleDetailView.as_view(), name='garage-vehicle-detail'),
    path('garage/vehicles/<uuid:id>/set-primary/', GarageVehicleSetPrimaryView.as_view(), name='garage-vehicle-set-primary'),
]
