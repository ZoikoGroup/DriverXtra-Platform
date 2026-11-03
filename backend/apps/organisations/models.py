import uuid
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from common.models import BaseUUIDModel
from apps.identity.models import User
from platform_core.regional import (
    CountryCode,
    validate_country_code,
    validate_jurisdiction,
    derive_country_from_jurisdiction,
    get_default_jurisdiction_for_country,
    get_country_spec,
    is_supported_country,
)


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
    slug = models.SlugField(max_length=255, unique=True, db_index=True, blank=True)
    type = models.CharField(
        max_length=50,
        choices=OrganisationTypeChoices.choices,
        default=OrganisationTypeChoices.INDIVIDUAL,
    )
    country = models.CharField(
        max_length=2,
        choices=CountryCode.choices,
        default=CountryCode.GB,
        db_index=True,
        help_text="Authoritative ISO 3166-1 alpha-2 country code (e.g. IN, GB).",
    )
    jurisdiction = models.CharField(
        max_length=50,
        default='GB-ENG',
        blank=True,
        help_text="Authoritative ISO 3166-2 legal jurisdiction (e.g. IN-TG, GB-ENG).",
    )
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
        indexes = [
            models.Index(fields=['country', 'is_active']),
            models.Index(fields=['jurisdiction', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.type}) [{self.country}:{self.jurisdiction}]"

    def clean(self):
        super().clean()

        # 1. Populate slug candidate if not present
        if not self.slug and self.name:
            base_slug = slugify(self.name) or "org"
            candidate = base_slug
            counter = 1
            while Organisation.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = candidate

        # 2. Harmonize missing country from jurisdiction if jurisdiction is provided
        if self.jurisdiction and not self.country:
            derived = derive_country_from_jurisdiction(self.jurisdiction)
            if derived:
                self.country = derived
            else:
                self.country = CountryCode.GB.value

        # 3. Harmonize missing jurisdiction from country if country is provided
        if self.country and not self.jurisdiction:
            if is_supported_country(self.country):
                self.jurisdiction = get_default_jurisdiction_for_country(self.country)

        # 4. Validate country code strictly
        self.country = validate_country_code(self.country)

        # 5. Validate jurisdiction strictly and reject country/jurisdiction mismatch
        self.jurisdiction = validate_jurisdiction(self.country, self.jurisdiction)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "org"
            candidate = base_slug
            counter = 1
            while Organisation.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = candidate

        if self.jurisdiction and not self.country:
            derived = derive_country_from_jurisdiction(self.jurisdiction)
            if derived:
                self.country = derived

        if self.country and not self.jurisdiction:
            if is_supported_country(self.country):
                self.jurisdiction = get_default_jurisdiction_for_country(self.country)

        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def regional_specification(self):
        """Returns authoritative CountrySpecification for this organisation."""
        return get_country_spec(self.country)

    @property
    def subdivision_specification(self):
        """Returns SubdivisionSpecification for this organisation's jurisdiction."""
        spec = self.regional_specification
        return spec.get_subdivision(self.jurisdiction)

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
