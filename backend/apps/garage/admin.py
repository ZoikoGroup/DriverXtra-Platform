from django.contrib import admin
from apps.garage.models import GarageVehicle, VehicleServiceRecord


@admin.register(GarageVehicle)
class GarageVehicleAdmin(admin.ModelAdmin):
    list_display = ('user', 'year', 'make', 'model', 'registration_plate', 'is_primary', 'mot_status')
    list_filter = ('is_primary', 'make', 'mot_status')
    search_fields = ('user__email', 'registration_plate', 'vin', 'make', 'model')


@admin.register(VehicleServiceRecord)
class VehicleServiceRecordAdmin(admin.ModelAdmin):
    list_display = (
        'vehicle',
        'service_title',
        'service_date',
        'record_source',
        'is_verified',
        'workshop',
        'service_centre_name',
        'total_cost',
        'currency',
        'odometer_reading',
    )
    list_filter = ('record_source', 'is_verified', 'service_type', 'service_date')
    search_fields = (
        'service_title',
        'service_centre_name',
        'vehicle__registration_plate',
        'vehicle__user__email',
        'work_order__work_order_number',
    )
    raw_id_fields = ('vehicle', 'work_order', 'workshop', 'created_by')
