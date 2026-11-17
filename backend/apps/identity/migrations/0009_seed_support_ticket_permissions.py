from django.db import migrations


def seed_support_ticket_permissions(apps, schema_editor):
    Permission = apps.get_model('identity', 'Permission')
    StaffRole = apps.get_model('identity', 'StaffRole')
    StaffRolePermission = apps.get_model('identity', 'StaffRolePermission')

    permissions_data = [
        (
            'support.ticket.manage',
            'Support Ticket Management',
            'Manage support queues, assign tickets, reply to customer inquiries, and update ticket lifecycle',
        ),
        (
            'support.ticket.lead',
            'Support Team Lead',
            'Advanced support operations, reassigning escalated tickets, and managing team workload distribution',
        ),
        (
            'support.ticket.confidential',
            'Confidential Ticket Access',
            'Access and handle confidential, sensitive, or security-restricted customer support tickets',
        ),
    ]

    perms_by_code = {}
    for code, name, desc in permissions_data:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={'name': name, 'description': desc},
        )
        perms_by_code[code] = perm

    # Grant support.ticket.manage to SUPPORT_AGENT role
    support_role = StaffRole.objects.filter(code='SUPPORT_AGENT').first()
    if support_role and 'support.ticket.manage' in perms_by_code:
        StaffRolePermission.objects.get_or_create(
            staff_role=support_role,
            permission=perms_by_code['support.ticket.manage'],
        )


def rollback_support_ticket_permissions(apps, schema_editor):
    Permission = apps.get_model('identity', 'Permission')
    StaffRolePermission = apps.get_model('identity', 'StaffRolePermission')

    codes = [
        'support.ticket.manage',
        'support.ticket.lead',
        'support.ticket.confidential',
    ]
    StaffRolePermission.objects.filter(permission__code__in=codes).delete()
    Permission.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0008_approvalrequest_lifecycle_and_financial_fields'),
    ]

    operations = [
        migrations.RunPython(
            seed_support_ticket_permissions,
            rollback_support_ticket_permissions,
        ),
    ]

