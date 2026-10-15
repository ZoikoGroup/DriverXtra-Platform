from django.contrib import admin
from apps.garage.models import GarageVehicle


@admin.register(GarageVehicle)
class GarageVehicleAdmin(admin.ModelAdmin):
    list_display = ('user', 'year', 'make', 'model', 'registration_plate', 'is_primary', 'mot_status')
    list_filter = ('is_primary', 'make', 'mot_status')
    search_fields = ('user__email', 'registration_plate', 'vin', 'make', 'model')
