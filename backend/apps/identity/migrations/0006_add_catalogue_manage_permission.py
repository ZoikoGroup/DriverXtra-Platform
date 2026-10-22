from django.db import migrations


def add_catalogue_manage_permission(apps, schema_editor):
    Permission = apps.get_model('identity', 'Permission')
    Permission.objects.get_or_create(
        code='catalogue.manage',
        defaults={
            'name': 'Catalogue Management',
            'description': 'Create, update, deactivate, and delete vehicle and spare parts catalogue master records and compatibilities',
        },
    )


def remove_catalogue_manage_permission(apps, schema_editor):
    Permission = apps.get_model('identity', 'Permission')
    Permission.objects.filter(code='catalogue.manage').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0005_seed_permissions_and_staff_roles'),
    ]

    operations = [
        migrations.RunPython(add_catalogue_manage_permission, remove_catalogue_manage_permission),
    ]
