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

from apps.garage.models import VehicleServiceRecord
from apps.garage.serializers import (
    VehicleServiceRecordSerializer,
    BuyerServiceRecordCreateSerializer,
    BuyerServiceRecordUpdateSerializer,
)
from apps.garage.services import VehicleServiceHistoryService


class VehicleServiceRecordListCreateView(generics.ListCreateAPIView):
    """
    List chronological service history records for a buyer's vehicle or
    create a new manual buyer-entered historical service record.

    GET /api/v1/garage/vehicles/<vehicle_id>/service-history/
    POST /api/v1/garage/vehicles/<vehicle_id>/service-history/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        vehicle_id = self.kwargs['vehicle_id']
        vehicle = generics.get_object_or_404(
            GarageVehicle,
            id=vehicle_id,
            user=self.request.user,
            is_archived=False,
        )
        return (
            VehicleServiceRecord.objects.filter(vehicle=vehicle)
            .select_related('workshop', 'work_order')
            .prefetch_related('work_order__tasks', 'work_order__parts_used')
            .order_by('-service_date', '-created_at')
        )

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return BuyerServiceRecordCreateSerializer
        return VehicleServiceRecordSerializer

    def create(self, request, *args, **kwargs):
        vehicle_id = self.kwargs['vehicle_id']
        vehicle = generics.get_object_or_404(
            GarageVehicle,
            id=vehicle_id,
            user=request.user,
            is_archived=False,
        )
        serializer = BuyerServiceRecordCreateSerializer(
            data=request.data,
            context={'vehicle': vehicle, 'request': request},
        )
        serializer.is_valid(raise_exception=True)
        record = VehicleServiceHistoryService.create_buyer_record(
            vehicle=vehicle,
            data=serializer.validated_data,
            buyer=request.user,
        )
        return Response(
            VehicleServiceRecordSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )


class VehicleServiceRecordDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a vehicle service record.
    Update and delete are strictly restricted to unverified buyer-entered records.
    Platform-verified records reject modifications with 403 Forbidden.

    GET /api/v1/garage/service-history/<id>/
    PATCH /api/v1/garage/service-history/<id>/
    DELETE /api/v1/garage/service-history/<id>/
    """
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        return (
            VehicleServiceRecord.objects.filter(
                vehicle__user=self.request.user,
                vehicle__is_archived=False,
            )
            .select_related('workshop', 'work_order')
            .prefetch_related('work_order__tasks', 'work_order__parts_used')
        )

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return BuyerServiceRecordUpdateSerializer
        return VehicleServiceRecordSerializer

    def update(self, request, *args, **kwargs):
        record = self.get_object()
        serializer = BuyerServiceRecordUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_record = VehicleServiceHistoryService.update_buyer_record(
            record=record,
            data=serializer.validated_data,
            buyer=request.user,
        )
        return Response(
            VehicleServiceRecordSerializer(updated_record).data,
            status=status.HTTP_200_OK,
        )

    def perform_destroy(self, instance):
        VehicleServiceHistoryService.delete_buyer_record(
            record=instance,
            buyer=self.request.user,
        )
