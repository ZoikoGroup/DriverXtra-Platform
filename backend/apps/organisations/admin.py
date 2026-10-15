from django.contrib import admin
from .models import Organisation, OrganisationMembership


class OrganisationMembershipInline(admin.TabularInline):
    model = OrganisationMembership
    extra = 1
    autocomplete_fields = ['user']


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'type', 'jurisdiction', 'created_by', 'is_active', 'created_at')
    list_filter = ('type', 'jurisdiction', 'is_active')
    search_fields = ('name', 'slug', 'created_by__email')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [OrganisationMembershipInline]


@admin.register(OrganisationMembership)
class OrganisationMembershipAdmin(admin.ModelAdmin):
    list_display = ('organisation', 'user', 'role', 'is_active', 'joined_at')
    list_filter = ('role', 'is_active')
    search_fields = ('organisation__name', 'user__email')
