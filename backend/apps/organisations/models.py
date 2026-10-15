import uuid
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from common.models import BaseUUIDModel
from apps.identity.models import User


class OrganisationTypeChoices(models.TextChoices):
    INDIVIDUAL = 'INDIVIDUAL', 'Individual / Personal Garage'
    DEALER_GROUP = 'DEALER_GROUP', 'Dealer Group'
    WORKSHOP = 'WORKSHOP', 'Workshop'
    FLEET_OPERATOR = 'FLEET_OPERATOR', 'Fleet Operator'
    INTERNAL_OPS = 'INTERNAL_OPS', 'Internal Operations'


class OrganisationRoleChoices(models.TextChoices):
    OWNER = 'OWNER', 'Owner'
    ADMIN = 'ADMIN', 'Admin'
    MEMBER = 'MEMBER', 'Member'
    TECHNICIAN = 'TECHNICIAN', 'Technician'
    ANALYST = 'ANALYST', 'Analyst'


class Organisation(BaseUUIDModel):
    """Tenant / Business Entity model (e.g. Dealer Group, Workshop Bay, Fleet)."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    type = models.CharField(
        max_length=50,
        choices=OrganisationTypeChoices.choices,
        default=OrganisationTypeChoices.INDIVIDUAL,
    )
    jurisdiction = models.CharField(max_length=50, default='GB-ENG')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_organisations',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Organisation'
        verbose_name_plural = 'Organisations'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.type})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "org"
            candidate = base_slug
            counter = 1
            while Organisation.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def is_member(self, user: User) -> bool:
        if not (user and user.is_authenticated):
            return False
        return self.memberships.filter(user=user, is_active=True).exists()

    def get_member_role(self, user: User) -> str | None:
        if not (user and user.is_authenticated):
            return None
        membership = self.memberships.filter(user=user, is_active=True).first()
        return membership.role if membership else None

    def add_member(self, user: User, role: str = OrganisationRoleChoices.MEMBER) -> 'OrganisationMembership':
        membership, created = OrganisationMembership.objects.get_or_create(
            organisation=self,
            user=user,
            defaults={'role': role, 'is_active': True},
        )
        if not created and not membership.is_active:
            membership.is_active = True
            membership.role = role
            membership.save(update_fields=['is_active', 'role'])
        return membership


class OrganisationMembership(BaseUUIDModel):
    """Represents a user's role and membership inside a specific organisation."""

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='organisation_memberships',
    )
    role = models.CharField(
        max_length=50,
        choices=OrganisationRoleChoices.choices,
        default=OrganisationRoleChoices.MEMBER,
    )
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Organisation Membership'
        verbose_name_plural = 'Organisation Memberships'
        unique_together = ('organisation', 'user')
        indexes = [
            models.Index(fields=['organisation', 'user']),
            models.Index(fields=['organisation', 'role']),
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.organisation.name} ({self.role})"
