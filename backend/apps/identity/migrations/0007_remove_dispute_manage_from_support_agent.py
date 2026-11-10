from django.db import migrations


def remove_dispute_manage_from_support_agent(apps, schema_editor):
    StaffRole = apps.get_model('identity', 'StaffRole')
    Permission = apps.get_model('identity', 'Permission')
    StaffRolePermission = apps.get_model('identity', 'StaffRolePermission')

    support_role = StaffRole.objects.filter(code='SUPPORT_AGENT').first()
    dispute_perm = Permission.objects.filter(code='dispute.manage').first()

    if support_role and dispute_perm:
        StaffRolePermission.objects.filter(
            staff_role=support_role,
            permission=dispute_perm,
        ).delete()


def restore_dispute_manage_to_support_agent(apps, schema_editor):
    StaffRole = apps.get_model('identity', 'StaffRole')
    Permission = apps.get_model('identity', 'Permission')
    StaffRolePermission = apps.get_model('identity', 'StaffRolePermission')

    support_role = StaffRole.objects.filter(code='SUPPORT_AGENT').first()
    dispute_perm = Permission.objects.filter(code='dispute.manage').first()

    if support_role and dispute_perm:
        StaffRolePermission.objects.get_or_create(
            staff_role=support_role,
            permission=dispute_perm,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0006_add_catalogue_manage_permission'),
    ]

    operations = [
        migrations.RunPython(
            remove_dispute_manage_from_support_agent,
            restore_dispute_manage_to_support_agent,
        ),
    ]

