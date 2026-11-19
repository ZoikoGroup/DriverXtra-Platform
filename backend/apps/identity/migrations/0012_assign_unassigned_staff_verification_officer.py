from django.db import migrations
from django.db.models import Q

# Data-only, additive. Before this migration, staff without a StaffProfile sub-role implicitly
# received VERIFICATION_OFFICER permissions at runtime. That implicit fallback is removed in code
# (User._get_effective_staff_role), so every such existing staff member is given an EXPLICIT
# VERIFICATION_OFFICER sub-role here. Their effective permissions are unchanged, but they are now
# visible and editable in staff management, and no future account gains permissions implicitly.
#
# - Explicitly assigned sub-roles are never touched.
# - Existing profiles keep their TOTP/MFA secret, enrollment flag and department.
# - Superusers and ADMIN-role holders are skipped: they hold every permission regardless.
# - If the VERIFICATION_OFFICER role does not exist, the old fallback granted nothing either,
#   so nothing is assigned.

FALLBACK_ROLE_CODE = 'VERIFICATION_OFFICER'


def assign_unassigned_staff(apps, schema_editor):
    User = apps.get_model('identity', 'User')
    StaffRole = apps.get_model('identity', 'StaffRole')
    StaffProfile = apps.get_model('identity', 'StaffProfile')

    role = StaffRole.objects.filter(code=FALLBACK_ROLE_CODE).first()
    if role is None:
        return

    staff_users = (
        User.objects.filter(Q(is_staff=True) | Q(user_roles__role='STAFF'))
        .exclude(is_superuser=True)
        .exclude(user_roles__role='ADMIN')
        .distinct()
    )
    for user in staff_users.iterator():
        profile = StaffProfile.objects.filter(user=user).first()
        if profile is None:
            StaffProfile.objects.create(
                user=user,
                staff_role=role,
                department='Operations',
                totp_enabled=False,
            )
        elif profile.staff_role_id is None:
            profile.staff_role = role
            profile.save(update_fields=['staff_role', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0011_user_session_version'),
    ]

    operations = [
        # Irreversible in substance: after the fact, an explicit assignment made here cannot be
        # told apart from one made by an administrator, so reversing is a no-op.
        migrations.RunPython(assign_unassigned_staff, migrations.RunPython.noop),
    ]
