from django.db import migrations


def seed_permissions_and_staff_roles(apps, schema_editor):
    Permission = apps.get_model('identity', 'Permission')
    StaffRole = apps.get_model('identity', 'StaffRole')
    StaffRolePermission = apps.get_model('identity', 'StaffRolePermission')
    StaffProfile = apps.get_model('identity', 'StaffProfile')
    User = apps.get_model('identity', 'User')

    # 1. Seed Permissions
    permissions_data = [
        ('seller.verify', 'Seller Verification', 'Review and verify seller and workshop onboarding applications'),
        ('listing.review', 'Listing Review', 'Review and approve/reject marketplace vehicle and parts listings'),
        ('order.refund', 'Order Refund', 'Authorise buyer order refunds and cancellations'),
        ('dispute.manage', 'Dispute Management', 'Adjudicate marketplace disputes and chargebacks'),
        ('finance.payout', 'Finance Payout', 'Authorise and release dealer and seller payouts'),
        ('staff.manage', 'Staff Management', 'Invite, configure, and manage internal staff roles'),
    ]

    perms_by_code = {}
    for code, name, desc in permissions_data:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={'name': name, 'description': desc},
        )
        perms_by_code[code] = perm

    # 2. Seed Staff Roles
    roles_data = [
        ('SUPPORT_AGENT', 'Support Agent', 'First-line operations, inquiries, and customer dispute resolution', ['dispute.manage']),
        ('VERIFICATION_OFFICER', 'Verification Officer', 'Verifies sellers, workshops, and approves marketplace listings', ['seller.verify', 'listing.review']),
        ('DISPUTE_MANAGER', 'Dispute Manager', 'Resolves high-value trade disputes and issues order refunds', ['dispute.manage', 'order.refund']),
        ('FINANCE_OFFICER', 'Finance Officer', 'Manages settlements, seller escrow releases, and refunds', ['finance.payout', 'order.refund']),
    ]

    staff_roles_by_code = {}
    for code, name, desc, perm_codes in roles_data:
        role, _ = StaffRole.objects.get_or_create(
            code=code,
            defaults={'name': name, 'description': desc},
        )
        staff_roles_by_code[code] = role
        for pcode in perm_codes:
            if pcode in perms_by_code:
                StaffRolePermission.objects.get_or_create(
                    staff_role=role,
                    permission=perms_by_code[pcode],
                )

    # 3. Migrate existing STAFF users to default VERIFICATION_OFFICER staff role without losing access
    default_role = staff_roles_by_code.get('VERIFICATION_OFFICER')
    for user in User.objects.all():
        is_staff_user = user.is_staff or user.user_roles.filter(role='STAFF').exists()
        if is_staff_user:
            StaffProfile.objects.get_or_create(
                user=user,
                defaults={
                    'staff_role': default_role,
                    'department': 'Operations',
                    'totp_enabled': False,
                },
            )


def rollback_permissions_and_staff_roles(apps, schema_editor):
    Permission = apps.get_model('identity', 'Permission')
    StaffRole = apps.get_model('identity', 'StaffRole')
    Permission.objects.all().delete()
    StaffRole.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0004_permission_staffrole_approvalrequest_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_permissions_and_staff_roles, rollback_permissions_and_staff_roles),
    ]
