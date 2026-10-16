from django.contrib import admin
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    PartCategory,
    Part,
    PartCompatibility,
)


@admin.register(VehicleMake)
class VehicleMakeAdmin(admin.ModelAdmin):
    list_display = ('name', 'country_of_origin', 'is_active')
    search_fields = ('name',)


@admin.register(VehicleModel)
class VehicleModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'make', 'year_start', 'year_end', 'is_active')
    list_filter = ('make', 'is_active')
    search_fields = ('name', 'make__name')


@admin.register(VehicleVariant)
class VehicleVariantAdmin(admin.ModelAdmin):
    list_display = ('name', 'model', 'year', 'fuel_type', 'transmission', 'is_active')
    list_filter = ('model__make', 'year', 'fuel_type', 'transmission')
    search_fields = ('name', 'model__name', 'engine_code')


@admin.register(PartCategory)
class PartCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'parent', 'is_active')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'mpn', 'category', 'is_universal', 'is_active')
    list_filter = ('category', 'brand', 'is_universal', 'is_active')
    search_fields = ('name', 'brand', 'mpn')


@admin.register(PartCompatibility)
class PartCompatibilityAdmin(admin.ModelAdmin):
    list_display = ('part', 'vehicle_variant', 'fitment_type')
    list_filter = ('fitment_type',)
    search_fields = ('part__name', 'part__mpn', 'vehicle_variant__name')
