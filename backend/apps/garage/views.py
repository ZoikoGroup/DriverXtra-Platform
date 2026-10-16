from rest_framework import generics, permissions, status, views
from rest_framework.response import Response
from apps.garage.models import GarageVehicle
from apps.garage.serializers import GarageVehicleSerializer


class GarageVehicleListCreateView(generics.ListCreateAPIView):
    """List or add personal vehicles to the authenticated user's digital garage.

    GET /api/v1/garage/vehicles/
    POST /api/v1/garage/vehicles/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = GarageVehicleSerializer

    def get_queryset(self):
        # Strict user-isolation & active vehicle filtering: only retrieve non-archived vehicles
        return GarageVehicle.objects.filter(
            user=self.request.user,
            is_archived=False,
        ).select_related('vehicle_variant', 'vehicle_variant__model', 'vehicle_variant__model__make')


class GarageVehicleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or archive a specific vehicle in the user's garage.

    GET /api/v1/garage/vehicles/<id>/
    PATCH /api/v1/garage/vehicles/<id>/
    DELETE /api/v1/garage/vehicles/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = GarageVehicleSerializer
    lookup_field = 'id'

    def get_queryset(self):
        # Strict user-isolation: User A cannot retrieve/update/archive User B's vehicle
        return GarageVehicle.objects.filter(
            user=self.request.user,
            is_archived=False,
        ).select_related('vehicle_variant')

    def perform_destroy(self, instance):
        # Soft-delete: Archive the vehicle while preserving historical records
        instance.archive()


class GarageVehicleSetPrimaryView(views.APIView):
    """Set a specific active garage vehicle as the user's primary vehicle.

    POST /api/v1/garage/vehicles/<id>/set-primary/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        vehicle = generics.get_object_or_404(GarageVehicle, id=id, user=request.user, is_archived=False)
        vehicle.set_as_primary()
        return Response(
            {
                "status": "success",
                "message": f"{vehicle.year} {vehicle.make} {vehicle.model} marked as primary vehicle.",
                "vehicle": GarageVehicleSerializer(vehicle).data,
            },
            status=status.HTTP_200_OK,
        )
