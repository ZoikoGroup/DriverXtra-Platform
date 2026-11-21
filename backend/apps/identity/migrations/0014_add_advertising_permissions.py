from django.db import migrations

# Phase 7.2: Seeds 'advertising.manage' and 'advertising.review' permissions.
# Commercial advertising review is restricted to Platform Admins or explicit role assignment.
# Platform ADMIN / superusers already hold every permission via has_perm.

PERMISSIONS = [
    {
        'code': 'advertising.manage',
        'name': 'Advertising Management',
        'description': 'Create, edit, pause, and configure sponsored advertising campaigns and listings.',
    },
    {
        'code': 'advertising.review',
        'name': 'Advertising Review & Moderation',
        'description': 'Review, approve, reject with reason, or terminate sponsored advertising campaigns.',
    },
]

GRANTED_STAFF_ROLES = []


def add_advertising_permissions(apps, schema_editor):
    Permission = apps.get_model('identity', 'Permission')
    StaffRole = apps.get_model('identity', 'StaffRole')
    StaffRolePermission = apps.get_model('identity', 'StaffRolePermission')

    for p in PERMISSIONS:
        perm, _ = Permission.objects.get_or_create(
            code=p['code'],
            defaults={
                'name': p['name'],
                'description': p['description'],
            },
        )
        if p['code'] == 'advertising.review' and GRANTED_STAFF_ROLES:
            for role in StaffRole.objects.filter(code__in=GRANTED_STAFF_ROLES):
                StaffRolePermission.objects.get_or_create(staff_role=role, permission=perm)


def remove_advertising_permissions(apps, schema_editor):
    Permission = apps.get_model('identity', 'Permission')
    StaffRolePermission = apps.get_model('identity', 'StaffRolePermission')
    codes = [p['code'] for p in PERMISSIONS]
    StaffRolePermission.objects.filter(permission__code__in=codes).delete()
    Permission.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0013_staffprofile_staff_role_protect'),
    ]

    operations = [
        migrations.RunPython(add_advertising_permissions, remove_advertising_permissions),
    ]
