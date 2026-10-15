import uuid
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

    def add_role(self, role_name: str):
        normalized = RoleChoices.normalize_role(role_name)
        role_obj, _ = UserRole.objects.get_or_create(user=self, role=normalized)
        return role_obj

    def remove_role(self, role_name: str):
        normalized = RoleChoices.normalize_role(role_name)
        self.user_roles.filter(role=normalized).delete()

    @property
    def is_platform_admin(self) -> bool:
        return self.is_superuser or self.has_role(RoleChoices.ADMIN)

    @property
    def is_platform_staff(self) -> bool:
        return self.is_staff or self.has_role(RoleChoices.STAFF) or self.is_platform_admin


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
