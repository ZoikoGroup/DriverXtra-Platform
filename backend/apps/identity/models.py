import uuid
from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from common.models import BaseUUIDModel


class RoleChoices(models.TextChoices):
    BUYER = 'BUYER', 'Buyer / Customer'
    SELLER = 'SELLER', 'Seller / Dealer'
    WORKSHOP = 'WORKSHOP', 'Workshop / Service Provider'
    STAFF = 'STAFF', 'Staff / Operations'
    ADMIN = 'ADMIN', 'Marketplace Admin'

    @classmethod
    def normalize_role(cls, role_str: str) -> str:
        """Normalizes external or prototype role aliases to canonical platform role."""
        if not role_str:
            return cls.BUYER
        cleaned = role_str.strip().upper()
        alias_map = {
            'CONSUMER': cls.BUYER,
            'BUYER': cls.BUYER,
            'CUSTOMER': cls.BUYER,
            'SELLER': cls.SELLER,
            'DEALER': cls.SELLER,
            'INVENTORY_MANAGER': cls.SELLER,
            'WORKSHOP': cls.WORKSHOP,
            'WORKSHOP_MANAGER': cls.WORKSHOP,
            'SERVICE_PROVIDER': cls.WORKSHOP,
            'STAFF': cls.STAFF,
            'OPERATIONS': cls.STAFF,
            'DISPUTE_ANALYST': cls.STAFF,
            'FINANCE_OPS': cls.STAFF,
            'ADMIN': cls.ADMIN,
            'MARKETPLACE_ADMIN': cls.ADMIN,
        }
        return alias_map.get(cleaned, cleaned)


class AccountStatusChoices(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    PENDING = 'PENDING', 'Pending Verification'
    SUSPENDED = 'SUSPENDED', 'Suspended'
    DEACTIVATED = 'DEACTIVATED', 'Deactivated'


class UserManager(BaseUserManager):
    """Custom user manager using email as primary identifier."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set.')
        email = self.normalize_email(email).lower()
        extra_fields.setdefault('status', AccountStatusChoices.ACTIVE)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_email_verified', False)
        extra_fields.setdefault('email_verified_at', None)

        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('status', AccountStatusChoices.ACTIVE)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_email_verified', True)
        extra_fields.setdefault('email_verified_at', timezone.now())

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        user = self.create_user(email, password, **extra_fields)
        user.add_role(RoleChoices.ADMIN)
        return user


class User(AbstractBaseUser, PermissionsMixin, BaseUUIDModel):
    """Custom User model with UUID primary key, email authentication, and account lifecycle status."""

    email = models.EmailField(unique=True, db_index=True, max_length=255)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)

    status = models.CharField(
        max_length=20,
        choices=AccountStatusChoices.choices,
        default=AccountStatusChoices.ACTIVE,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    email_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the email address was verified.",
    )
    is_email_verified = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Designates whether the user has verified ownership of their email address.",
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']

    def __str__(self):
        return self.email

    @property
    def full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else self.email

    @property
    def roles(self) -> list[str]:
        """Returns a list of active role codes assigned to the user."""
        return list(self.user_roles.values_list('role', flat=True))

    def has_role(self, role_name: str) -> bool:
        normalized = RoleChoices.normalize_role(role_name)
        if self.is_superuser and normalized in (RoleChoices.ADMIN, RoleChoices.STAFF):
            return True
        return self.user_roles.filter(role=normalized).exists()

    def add_role(self, role_name: str, actor_id=None, correlation_id=""):
        from platform_core.audit.writer import record_audit_entry
        from common.middleware import get_current_correlation_id

        normalized = RoleChoices.normalize_role(role_name)
        role_obj, created = UserRole.objects.get_or_create(user=self, role=normalized)
        if created:
            record_audit_entry(
                event_type="user.role.granted",
                action="identity:role.grant",
                resource_type="UserRole",
                resource_id=str(role_obj.id),
                actor_id=actor_id or self.id,
                correlation_id=correlation_id or get_current_correlation_id(),
                metadata={"user_id": str(self.id), "role": normalized, "email": self.email},
            )
        return role_obj

    def remove_role(self, role_name: str, actor_id=None, correlation_id=""):
        from platform_core.audit.writer import record_audit_entry
        from common.middleware import get_current_correlation_id

        normalized = RoleChoices.normalize_role(role_name)
        deleted_count, _ = self.user_roles.filter(role=normalized).delete()
        if deleted_count > 0:
            record_audit_entry(
                event_type="user.role.revoked",
                action="identity:role.revoke",
                resource_type="UserRole",
                resource_id=str(self.id),
                actor_id=actor_id or self.id,
                correlation_id=correlation_id or get_current_correlation_id(),
                metadata={"user_id": str(self.id), "role": normalized, "email": self.email},
            )

    @property
    def is_platform_admin(self) -> bool:
        return self.is_superuser or self.has_role(RoleChoices.ADMIN)

    @property
    def is_platform_staff(self) -> bool:
        return self.is_staff or self.has_role(RoleChoices.STAFF) or self.is_platform_admin

    def get_default_role(self) -> str:
        """Returns the highest priority role held by the user."""
        priority = [
            RoleChoices.ADMIN,
            RoleChoices.STAFF,
            RoleChoices.SELLER,
            RoleChoices.WORKSHOP,
            RoleChoices.BUYER,
        ]
        if self.is_superuser:
            return RoleChoices.ADMIN
        user_roles = self.roles
        for r in priority:
            if r in user_roles:
                return r
        return RoleChoices.BUYER

    def has_permission(self, perm_code: str) -> bool:
        """Checks if user has a platform permission. Platform admins have all permissions."""
        if self.is_superuser or self.has_role(RoleChoices.ADMIN):
            return True
        try:
            profile = getattr(self, 'staff_profile', None)
            if profile and profile.staff_role:
                return profile.staff_role.role_permissions.filter(permission__code=perm_code).exists()
            elif self.is_staff or self.has_role(RoleChoices.STAFF):
                from apps.identity.models import StaffRole
                default_role = StaffRole.objects.filter(code='VERIFICATION_OFFICER').first()
                if default_role:
                    return default_role.role_permissions.filter(permission__code=perm_code).exists()
        except Exception:
            pass
        return False

    @property
    def has_mfa_enabled(self) -> bool:
        try:
            profile = getattr(self, 'staff_profile', None)
            return bool(profile and profile.totp_enabled)
        except Exception:
            return False


class UserRole(BaseUUIDModel):
    """Bridge model supporting multiple platform roles per user."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_roles')
    role = models.CharField(max_length=50, choices=RoleChoices.choices)
    assigned_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'User Role'
        verbose_name_plural = 'User Roles'
        unique_together = ('user', 'role')
        indexes = [
            models.Index(fields=['user', 'role']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.role}"


class EmailVerificationToken(BaseUUIDModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='email_verification_tokens',
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SHA-256 hash of the verification token.",
    )
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = 'Email Verification Token'
        verbose_name_plural = 'Email Verification Tokens'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'consumed_at', 'expires_at'], name='identity_em_user_id_a3831a_idx'),
        ]

    def __str__(self):
        return f"EmailVerificationToken({self.user.email})"


class PasswordResetToken(BaseUUIDModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='password_reset_tokens',
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SHA-256 hash of the password reset token.",
    )
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = 'Password Reset Token'
        verbose_name_plural = 'Password Reset Tokens'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'consumed_at', 'expires_at'], name='identity_pa_user_id_ebb33f_idx'),
        ]

    def __str__(self):
        return f"PasswordResetToken({self.user.email})"


class Permission(BaseUUIDModel):
    code = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Platform Permission'
        verbose_name_plural = 'Platform Permissions'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} ({self.name})"


class StaffRoleChoices(models.TextChoices):
    SUPPORT_AGENT = 'SUPPORT_AGENT', 'Support Agent'
    VERIFICATION_OFFICER = 'VERIFICATION_OFFICER', 'Verification Officer'
    DISPUTE_MANAGER = 'DISPUTE_MANAGER', 'Dispute Manager'
    FINANCE_OFFICER = 'FINANCE_OFFICER', 'Finance Officer'


class StaffRole(BaseUUIDModel):
    code = models.CharField(max_length=64, choices=StaffRoleChoices.choices, unique=True, db_index=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Staff Sub-Role'
        verbose_name_plural = 'Staff Sub-Roles'
        ordering = ['code']

    def __str__(self):
        return self.name


class StaffRolePermission(BaseUUIDModel):
    staff_role = models.ForeignKey(StaffRole, on_delete=models.CASCADE, related_name='role_permissions')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name='role_permissions')

    class Meta:
        verbose_name = 'Staff Role Permission'
        verbose_name_plural = 'Staff Role Permissions'
        unique_together = ('staff_role', 'permission')

    def __str__(self):
        return f"{self.staff_role.code} -> {self.permission.code}"


class StaffProfile(BaseUUIDModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='staff_profile',
    )
    staff_role = models.ForeignKey(
        StaffRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members',
    )
    department = models.CharField(max_length=128, blank=True, default='')
    totp_secret = models.TextField(blank=True, default='', help_text="Fernet encrypted base32 secret")
    totp_enabled = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Staff Profile'
        verbose_name_plural = 'Staff Profiles'

    def __str__(self):
        role_name = self.staff_role.name if self.staff_role else "Unassigned"
        return f"StaffProfile({self.user.email} - {role_name})"

    def set_totp_secret(self, plain_secret: str):
        from .security import encrypt_totp_secret
        self.totp_secret = encrypt_totp_secret(plain_secret)

    def get_totp_secret(self) -> str:
        from .security import decrypt_totp_secret
        if not self.totp_secret:
            return ""
        try:
            return decrypt_totp_secret(self.totp_secret)
        except Exception:
            return ""

    def verify_totp(self, code: str) -> bool:
        from .security import verify_totp_code
        secret = self.get_totp_secret()
        if not secret:
            return False
        return verify_totp_code(secret, code)


class StaffInviteToken(BaseUUIDModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='staff_invite_tokens',
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SHA-256 hash of single-use staff set-password token.",
    )
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = 'Staff Invite Token'
        verbose_name_plural = 'Staff Invite Tokens'
        ordering = ['-created_at']

    def __str__(self):
        return f"StaffInviteToken({self.user.email})"


class ApprovalStatusChoices(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    CANCELLED = 'CANCELLED', 'Cancelled'


class ApprovalRequest(BaseUUIDModel):
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='approval_requests_created',
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approval_requests_reviewed',
    )
    action_type = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, db_index=True)
    target_id = models.CharField(max_length=128, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=32,
        choices=ApprovalStatusChoices.choices,
        default=ApprovalStatusChoices.PENDING,
        db_index=True,
    )
    rejection_reason = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    requested_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Approval Request'
        verbose_name_plural = 'Approval Requests'
        ordering = ['-requested_at']

    def __str__(self):
        return f"ApprovalRequest({self.action_type} - {self.target_type}:{self.target_id} - {self.status})"

    def approve(self, approver, notes=''):
        if approver.id == self.requester_id:
            raise ValueError("Maker-checker violation: Requester cannot approve their own request.")
        self.approver = approver
        self.status = ApprovalStatusChoices.APPROVED
        self.notes = notes
        self.reviewed_at = timezone.now()
        self.save(update_fields=['approver', 'status', 'notes', 'reviewed_at', 'updated_at'])

    def reject(self, approver, reason, notes=''):
        if approver.id == self.requester_id:
            raise ValueError("Maker-checker violation: Requester cannot review their own request.")
        self.approver = approver
        self.status = ApprovalStatusChoices.REJECTED
        self.rejection_reason = reason
        self.notes = notes
        self.reviewed_at = timezone.now()
        self.save(update_fields=['approver', 'status', 'rejection_reason', 'notes', 'reviewed_at', 'updated_at'])
