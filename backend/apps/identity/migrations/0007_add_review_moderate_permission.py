from django.db import migrations

# Additive only: creates the 'review.moderate' permission and grants it to the
# VERIFICATION_OFFICER staff sub-role (approved decision U2). No existing rows are changed.
# Platform ADMIN / superusers already hold every permission.

PERMISSION_CODE = 'review.moderate'
GRANTED_STAFF_ROLES = ['VERIFICATION_OFFICER']


def add_review_moderate_permission(apps, schema_editor):
    Permission = apps.get_model('identity', 'Permission')
    StaffRole = apps.get_model('identity', 'StaffRole')
    StaffRolePermission = apps.get_model('identity', 'StaffRolePermission')

    perm, _ = Permission.objects.get_or_create(
        code=PERMISSION_CODE,
        defaults={
            'name': 'Review Moderation',
            'description': 'Moderate, hide, flag, approve and remove marketplace and workshop reviews and resolve review reports',
        },
    )
    for role in StaffRole.objects.filter(code__in=GRANTED_STAFF_ROLES):
        StaffRolePermission.objects.get_or_create(staff_role=role, permission=perm)


def remove_review_moderate_permission(apps, schema_editor):
    Permission = apps.get_model('identity', 'Permission')
    StaffRolePermission = apps.get_model('identity', 'StaffRolePermission')
    StaffRolePermission.objects.filter(permission__code=PERMISSION_CODE).delete()
    Permission.objects.filter(code=PERMISSION_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0006_add_catalogue_manage_permission'),
    ]

    operations = [
        migrations.RunPython(add_review_moderate_permission, remove_review_moderate_permission),
    ]
