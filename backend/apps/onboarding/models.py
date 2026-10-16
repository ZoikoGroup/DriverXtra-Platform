from django.db import models
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
        """Approves the application, records reviewer, and grants SELLER role to applicant."""
        if reviewer == self.user:
            raise ValidationError('Applicants cannot approve their own application.')

        if self.status != SellerApplicationStatusChoices.PENDING:
            raise ValidationError(f'Only applications in PENDING status can be approved (current: {self.status}).')

        self.status = SellerApplicationStatusChoices.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        if notes:
            self.admin_notes = notes
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'admin_notes', 'updated_at'])

        # Grant verified seller platform role to applicant
        self.user.add_role(RoleChoices.SELLER)

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
