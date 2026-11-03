from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from common.models import BaseUUIDModel
from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation


class SellerApplicationStatusChoices(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    PENDING = 'PENDING', 'Pending Review'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class BusinessTypeChoices(models.TextChoices):
    # Sector categories
    DEALER = 'DEALER', 'Automotive Dealership'
    PARTS_MERCHANT = 'PARTS_MERCHANT', 'Parts Merchant / Distributor'
    INDIVIDUAL_TRADER = 'INDIVIDUAL_TRADER', 'Independent Vehicle Trader'
    WORKSHOP = 'WORKSHOP', 'Certified Workshop & Service Provider'
    # Legal business structures
    SOLE_TRADER = 'SOLE_TRADER', 'Sole Trader'
    PARTNERSHIP = 'PARTNERSHIP', 'Partnership'
    LTD = 'LTD', 'Limited Company (Ltd)'
    PLC = 'PLC', 'Public Limited Company (PLC)'
    LLP = 'LLP', 'Limited Liability Partnership (LLP)'


def grant_roles_for_application(user: User, business_type: str, requested_roles: list = None):
    """Grants canonical platform roles upon seller application approval."""
    if requested_roles:
        for role in requested_roles:
            user.add_role(role)
    else:
        # Backward compatibility for legacy applications without requested_roles
        user.add_role(RoleChoices.SELLER)
        if business_type == BusinessTypeChoices.WORKSHOP:
            user.add_role(RoleChoices.WORKSHOP)


class SellerApplication(BaseUUIDModel):
    """Workflow model for onboarding and vetting seller / dealer applicants."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='seller_applications',
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='seller_applications',
    )

    # Business Information
    business_name = models.CharField(max_length=255)
    business_type = models.CharField(
        max_length=50,
        choices=BusinessTypeChoices.choices,
        default=BusinessTypeChoices.DEALER,
    )
    requested_roles = models.JSONField(
        default=list,
        blank=True,
        help_text="Canonical roles requested: SELLER, WORKSHOP",
    )
    company_registration_number = models.CharField(max_length=100, blank=True)
    tax_id = models.CharField(max_length=100, blank=True)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=50)

    # Physical / Registered Address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=30, blank=True)
    country = models.CharField(max_length=100, default='United Kingdom')
    jurisdiction = models.CharField(
        max_length=50,
        blank=True,
        help_text="Authoritative ISO 3166-2 legal jurisdiction (e.g. IN-TG, GB-ENG).",
    )
    website_url = models.URLField(blank=True)
    description = models.TextField(blank=True)

    # Lifecycle & Review Tracking
    status = models.CharField(
        max_length=20,
        choices=SellerApplicationStatusChoices.choices,
        default=SellerApplicationStatusChoices.DRAFT,
        db_index=True,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_seller_applications',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    admin_notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Seller Application'
        verbose_name_plural = 'Seller Applications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', '-submitted_at']),
        ]

    def __str__(self):
        return f"{self.business_name} ({self.user.email}) - {self.status}"

    def clean(self):
        super().clean()
        if self.status == SellerApplicationStatusChoices.REJECTED and not self.rejection_reason:
            raise ValidationError({'rejection_reason': 'A rejection reason is required when rejecting an application.'})
        if self.requested_roles:
            if not isinstance(self.requested_roles, list):
                raise ValidationError({'requested_roles': 'Requested roles must be a list.'})
            allowed_roles = {RoleChoices.SELLER, RoleChoices.WORKSHOP}
            for r in self.requested_roles:
                if r not in allowed_roles:
                    raise ValidationError({'requested_roles': f"Role '{r}' is not supported for seller/workshop applicants."})
            if len(self.requested_roles) != len(set(self.requested_roles)):
                raise ValidationError({'requested_roles': 'Duplicate roles are not permitted.'})

        # Validate regional country and jurisdiction consistency
        if self.country:
            from platform_core.regional import (
                normalize_country_code,
                validate_country_code,
                validate_jurisdiction,
                derive_jurisdiction_from_tax_id,
                get_default_jurisdiction_for_country,
                is_supported_country,
            )
            norm_country = normalize_country_code(self.country)
            if not norm_country or not is_supported_country(norm_country):
                raise ValidationError({'country': f"Unsupported or invalid country: '{self.country}'. Supported countries are India (IN) and United Kingdom (GB)."})

            if norm_country in ('IN', 'INDIA', 'BHARAT') and self.tax_id and str(self.tax_id).strip():
                gst_jurisdiction = derive_jurisdiction_from_tax_id(self.tax_id, norm_country)
                if not gst_jurisdiction:
                    raise ValidationError({
                        'tax_id': f"Invalid GSTIN format '{self.tax_id}'. Indian GSTIN must be a 15-character statutory alphanumeric code starting with a valid state code."
                    })
                if self.jurisdiction and str(self.jurisdiction).strip():
                    clean_j = str(self.jurisdiction).strip().upper()
                    if clean_j != gst_jurisdiction:
                        raise ValidationError({
                            'jurisdiction': f"Jurisdiction mismatch: The provided GSTIN '{self.tax_id}' corresponds to jurisdiction '{gst_jurisdiction}', which does not match the submitted jurisdiction '{self.jurisdiction}'."
                        })
                else:
                    self.jurisdiction = gst_jurisdiction
            elif not self.jurisdiction and self.tax_id:
                derived = derive_jurisdiction_from_tax_id(self.tax_id, norm_country)
                if derived:
                    self.jurisdiction = derived

            if not self.jurisdiction:
                self.jurisdiction = get_default_jurisdiction_for_country(norm_country)

            try:
                valid_c = validate_country_code(norm_country)
                self.jurisdiction = validate_jurisdiction(valid_c, self.jurisdiction)
            except ValidationError as exc:
                raise ValidationError({'jurisdiction': str(exc.message if hasattr(exc, 'message') else exc)})

    def submit_for_review(self):
        """Transitions draft or rejected application into pending review state."""
        if self.status == SellerApplicationStatusChoices.APPROVED:
            raise ValidationError('This application has already been approved.')

        # Check for duplicate pending applications by the same user
        existing_pending = SellerApplication.objects.filter(
            user=self.user,
            status=SellerApplicationStatusChoices.PENDING,
        ).exclude(pk=self.pk).exists()
        if existing_pending:
            raise ValidationError('You already have an application currently pending review.')

        self.status = SellerApplicationStatusChoices.PENDING
        self.submitted_at = timezone.now()
        self.save(update_fields=['status', 'submitted_at', 'updated_at'])

    def approve(self, reviewer: User, notes: str = ''):
        """Approves the application, records reviewer, and grants requested roles to applicant."""
        if reviewer == self.user:
            raise ValidationError('Applicants cannot approve their own application.')

        if self.status != SellerApplicationStatusChoices.PENDING:
            raise ValidationError(f'Only applications in PENDING status can be approved (current: {self.status}).')

        with transaction.atomic():
            self.status = SellerApplicationStatusChoices.APPROVED
            self.reviewed_by = reviewer
            self.reviewed_at = timezone.now()
            if notes:
                self.admin_notes = notes
            self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'admin_notes', 'updated_at'])

            # Grant verified platform roles to applicant
            grant_roles_for_application(self.user, self.business_type, self.requested_roles)

            # Provision workshop organisation if workshop role requested or business type is WORKSHOP
            is_workshop = (
                self.business_type == BusinessTypeChoices.WORKSHOP
                or (self.requested_roles and RoleChoices.WORKSHOP in self.requested_roles)
            )
            if is_workshop:
                from apps.onboarding.services import provision_workshop_organisation
                provision_workshop_organisation(self)

    def reject(self, reviewer: User, reason: str, notes: str = ''):
        """Rejects the application with mandatory rejection reason."""
        if not reason or not reason.strip():
            raise ValidationError('A rejection reason is required when rejecting an application.')

        if reviewer == self.user:
            raise ValidationError('Applicants cannot review their own application.')

        if self.status != SellerApplicationStatusChoices.PENDING:
            raise ValidationError(f'Only applications in PENDING status can be rejected (current: {self.status}).')

        self.status = SellerApplicationStatusChoices.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason.strip()
        if notes:
            self.admin_notes = notes
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'admin_notes', 'updated_at'])
