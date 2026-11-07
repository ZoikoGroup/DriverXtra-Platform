from django.db import migrations

COMMERCIAL_PERMISSIONS = [
    (
        'commercial.manage',
        'Commercial Catalogue Management',
        'Create and edit draft/illustrative SKUs, rate schedules and party role profiles; run non-binding quote previews.',
    ),
    (
        'commercial.approve',
        'Commercial Approval',
        'Approve or retire SKUs, rate schedules and party role profiles (separation of duties enforced).',
    ),
    (
        'country_gate.manage',
        'Country Gate Management',
        'Create country/market gates and record activation transitions with evidence.',
    ),
]


def add_permissions(apps, schema_editor):
    Permission = apps.get_model('identity', 'Permission')
    for code, name, description in COMMERCIAL_PERMISSIONS:
        Permission.objects.get_or_create(code=code, defaults={'name': name, 'description': description})


def remove_permissions(apps, schema_editor):
    Permission = apps.get_model('identity', 'Permission')
    Permission.objects.filter(code__in=[code for code, _, _ in COMMERCIAL_PERMISSIONS]).delete()


class Migration(migrations.Migration):
    """Adds commercial control-plane permission codes. They are not assigned to any staff sub-role;
    platform ADMIN users hold all permissions by default."""

    dependencies = [
        ('commercial', '0001_initial'),
        ('identity', '0006_add_catalogue_manage_permission'),
    ]

    operations = [
        migrations.RunPython(add_permissions, remove_permissions),
    ]
