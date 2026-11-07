"""Commercial control plane models (Master Architecture v1.0 §7, §9, §21, §22, Appendix C).

All money is stored as integer minor units with an ISO 4217 currency code.
Nothing here moves money: R1 defines what may be sold, where, by whom and at what
approved rate, and freezes the accepted commercial terms.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.models import BaseUUIDModel
from .choices import (
    BillingIntervalChoices,
    CatalogueStatusChoices,
    EntitlementTypeChoices,
    FeeBasisChoices,
    GATED_PAYMENT_ROLES,
    GATED_REVENUE_CODES,
    GATED_ROLE_PROFILE_TYPES,
    GateCapabilityChoices,
    GateStatusChoices,
    InvoiceIssuerChoices,
    PayerRoleChoices,
    PaymentRoleChoices,
    PlatformRoleChoices,
    QuoteLineTypeChoices,
    QuoteStatusChoices,
    REGULATED_CAPABILITIES,
    REGULATED_SKU_FAMILIES,
    REGULATED_VERTICALS,
    RevenueCodeChoices,
    RoleProfileStatusChoices,
    RoleProfileTypeChoices,
    SellerOfRecordChoices,
    ServicePerformerChoices,
    SkuFamilyChoices,
    TaxPartyChoices,
    VerticalChoices,
)
from .errors import ImmutableCommercialRecordError


# ---------------------------------------------------------------------------
# Append-only support
# ---------------------------------------------------------------------------

class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableCommercialRecordError(f"{self.model.__name__} records are append-only and cannot be updated.")

    def delete(self):
        raise ImmutableCommercialRecordError(f"{self.model.__name__} records are append-only and cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ImmutableCommercialRecordError(f"{self.model.__name__} records are append-only and cannot be updated.")


class AppendOnlyModel(BaseUUIDModel):
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableCommercialRecordError(f"{self.__class__.__name__} records are append-only and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableCommercialRecordError(f"{self.__class__.__name__} records are append-only and cannot be deleted.")


class ApprovalFieldsMixin(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_reference = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Executive/CFO/legal approval ticket or memo identifier.",
    )
    status_reason = models.TextField(blank=True, default='')

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Commercial SKU catalogue (§4, §6, §21 commercial_sku)
# ---------------------------------------------------------------------------

class CommercialSku(ApprovalFieldsMixin, BaseUUIDModel):
    sku_code = models.CharField(max_length=64, db_index=True, help_text="Stable SKU identifier, e.g. DX-DEAL-GROWTH.")
    version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    family = models.CharField(max_length=30, choices=SkuFamilyChoices.choices)
    revenue_code = models.CharField(max_length=10, choices=RevenueCodeChoices.choices)
    vertical = models.CharField(max_length=30, choices=VerticalChoices.choices)
    fee_basis = models.CharField(max_length=30, choices=FeeBasisChoices.choices)
    entitlement_type = models.CharField(
        max_length=30, choices=EntitlementTypeChoices.choices, default=EntitlementTypeChoices.NONE,
    )
    billing_interval = models.CharField(
        max_length=20, choices=BillingIntervalChoices.choices, default=BillingIntervalChoices.ONE_TIME,
    )
    tax_class = models.CharField(max_length=64, blank=True, default='', help_text="Tax classification key for the tax engine.")
    refund_policy_id = models.CharField(max_length=64, blank=True, default='')
    illustrative_band_note = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Planning-only price band text from the price book. Never used in calculations.",
    )
    is_regulated = models.BooleanField(default=False, editable=False)
    status = models.CharField(
        max_length=20, choices=CatalogueStatusChoices.choices, default=CatalogueStatusChoices.DRAFT, db_index=True,
    )

    class Meta:
        verbose_name = 'Commercial SKU'
        verbose_name_plural = 'Commercial SKUs'
        ordering = ['sku_code', '-version']
        constraints = [
            models.UniqueConstraint(fields=['sku_code', 'version'], name='unique_commercial_sku_version'),
        ]

    def __str__(self):
        return f"{self.sku_code} v{self.version} ({self.status})"

    @staticmethod
    def compute_is_regulated(family, revenue_code, vertical) -> bool:
        return (
            family in REGULATED_SKU_FAMILIES
            or revenue_code in GATED_REVENUE_CODES
            or vertical in REGULATED_VERTICALS
        )

    def save(self, *args, **kwargs):
        self.is_regulated = self.compute_is_regulated(self.family, self.revenue_code, self.vertical)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Country / market activation gates (§9, §22, §21 commercial_policy)
# ---------------------------------------------------------------------------

class CountryGate(BaseUUIDModel):
    country_code = models.CharField(max_length=2, help_text="ISO 3166-1 alpha-2 country code.")
    vertical = models.CharField(max_length=30, choices=VerticalChoices.choices)
    capability = models.CharField(max_length=30, choices=GateCapabilityChoices.choices)
    status = models.CharField(
        max_length=30, choices=GateStatusChoices.choices, default=GateStatusChoices.DESIGNED, db_index=True,
    )
    version = models.PositiveIntegerField(
        default=1, help_text="Country activation version; increments on every transition.",
    )
    allowed_currencies = models.JSONField(default=list, blank=True, help_text="ISO 4217 codes permitted in this market.")
    tax_schedule_reference = models.CharField(
        max_length=255, blank=True, default='', help_text="Signed tax/role schedule reference (required to enable).",
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Country Gate'
        verbose_name_plural = 'Country Gates'
        ordering = ['country_code', 'vertical', 'capability']
        constraints = [
            models.UniqueConstraint(fields=['country_code', 'vertical', 'capability'], name='unique_country_gate_scope'),
        ]

    def __str__(self):
        return f"{self.country_code}/{self.vertical}/{self.capability}: {self.status} (v{self.version})"

    @property
    def is_open(self) -> bool:
        return self.status == GateStatusChoices.ENABLED

    @property
    def is_regulated(self) -> bool:
        return self.vertical in REGULATED_VERTICALS or self.capability in REGULATED_CAPABILITIES


class CountryGateTransition(AppendOnlyModel):
    gate = models.ForeignKey(CountryGate, on_delete=models.PROTECT, related_name='transitions')
    from_status = models.CharField(max_length=30, choices=GateStatusChoices.choices)
    to_status = models.CharField(max_length=30, choices=GateStatusChoices.choices)
    version_after = models.PositiveIntegerField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    reason = models.TextField()
    evidence_reference = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        verbose_name = 'Country Gate Transition'
        verbose_name_plural = 'Country Gate Transitions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.gate_id}: {self.from_status} -> {self.to_status} (v{self.version_after})"


# ---------------------------------------------------------------------------
# Party role profiles (§2, §9, §21 commercial_agreement.role_profile / party_role_snapshot)
# ---------------------------------------------------------------------------

class PartyRoleProfile(ApprovalFieldsMixin, BaseUUIDModel):
    code = models.CharField(max_length=64, db_index=True)
    version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=255)
    profile_type = models.CharField(max_length=40, choices=RoleProfileTypeChoices.choices)
    country_code = models.CharField(max_length=2)
    vertical = models.CharField(max_length=30, choices=VerticalChoices.choices)
    seller_of_record = models.CharField(max_length=30, choices=SellerOfRecordChoices.choices)
    service_performer = models.CharField(max_length=30, choices=ServicePerformerChoices.choices)
    platform_role = models.CharField(max_length=30, choices=PlatformRoleChoices.choices)
    payment_role = models.CharField(max_length=30, choices=PaymentRoleChoices.choices)
    tax_party = models.CharField(max_length=30, choices=TaxPartyChoices.choices)
    invoice_issuer = models.CharField(max_length=20, choices=InvoiceIssuerChoices.choices)
    licensed_partner_required = models.BooleanField(default=False)
    legal_memo_reference = models.CharField(max_length=255, blank=True, default='')
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=RoleProfileStatusChoices.choices, default=RoleProfileStatusChoices.DRAFT, db_index=True,
    )

    class Meta:
        verbose_name = 'Party Role Profile'
        verbose_name_plural = 'Party Role Profiles'
        ordering = ['code', '-version']
        constraints = [
            models.UniqueConstraint(fields=['code', 'version'], name='unique_party_role_profile_version'),
        ]

    def __str__(self):
        return f"{self.code} v{self.version} {self.country_code}/{self.vertical} ({self.status})"

    @property
    def is_gated(self) -> bool:
        return (
            self.profile_type in GATED_ROLE_PROFILE_TYPES
            or self.payment_role in GATED_PAYMENT_ROLES
            or self.vertical in REGULATED_VERTICALS
        )


class PartyRoleSnapshot(AppendOnlyModel):
    """Immutable copy of the legal roles applied to one quote (Appendix C commercial_role_id / seller_of_record_id)."""

    profile = models.ForeignKey(PartyRoleProfile, on_delete=models.PROTECT, related_name='snapshots')
    profile_code = models.CharField(max_length=64)
    profile_version = models.PositiveIntegerField()
    profile_type = models.CharField(max_length=40, choices=RoleProfileTypeChoices.choices)
    seller_of_record_party = models.CharField(max_length=100, help_text="e.g. 'org:<uuid>' or 'platform'.")
    service_performer_party = models.CharField(max_length=100)
    platform_role = models.CharField(max_length=30, choices=PlatformRoleChoices.choices)
    payment_role = models.CharField(max_length=30, choices=PaymentRoleChoices.choices)
    tax_party = models.CharField(max_length=30, choices=TaxPartyChoices.choices)
    invoice_issuer = models.CharField(max_length=20, choices=InvoiceIssuerChoices.choices)
    licensed_partner_required = models.BooleanField(default=False)
    jurisdiction = models.CharField(max_length=2)
    snapshot_hash = models.CharField(max_length=64)

    class Meta:
        verbose_name = 'Party Role Snapshot'
        verbose_name_plural = 'Party Role Snapshots'
        ordering = ['-created_at']


# ---------------------------------------------------------------------------
# Effective-dated rate schedules (§7, §21 rate_schedule)
# ---------------------------------------------------------------------------

class RateSchedule(ApprovalFieldsMixin, BaseUUIDModel):
    name = models.CharField(max_length=255)
    sku = models.ForeignKey(CommercialSku, on_delete=models.PROTECT, related_name='rate_schedules')
    country_code = models.CharField(max_length=2)
    vertical = models.CharField(max_length=30, choices=VerticalChoices.choices)
    currency = models.CharField(max_length=3)
    payer_role = models.CharField(max_length=30, choices=PayerRoleChoices.choices)
    plan_code = models.CharField(max_length=64, blank=True, default='', help_text="Blank applies to any plan.")
    priority = models.PositiveIntegerField(default=100, help_text="Higher priority wins during resolution.")
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    flat_amount_minor = models.BigIntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    percentage_bps = models.PositiveIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(10_000)],
        help_text="Percentage in basis points (800 = 8%).",
    )
    min_fee_minor = models.BigIntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    max_fee_minor = models.BigIntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    status = models.CharField(
        max_length=20, choices=CatalogueStatusChoices.choices, default=CatalogueStatusChoices.DRAFT, db_index=True,
    )

    class Meta:
        verbose_name = 'Rate Schedule'
        verbose_name_plural = 'Rate Schedules'
        ordering = ['sku__sku_code', 'country_code', '-priority', '-effective_from']
        indexes = [
            models.Index(fields=['sku', 'country_code', 'vertical', 'currency', 'payer_role', 'status']),
        ]

    def __str__(self):
        return f"{self.name} [{self.sku.sku_code} {self.country_code} {self.currency}] ({self.status})"


# ---------------------------------------------------------------------------
# Immutable quote snapshots (§7, §21 quote_snapshot, Appendix C)
# ---------------------------------------------------------------------------

class QuoteSnapshotQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableCommercialRecordError("Quote snapshots can only change status through QuoteSnapshot.save().")

    def delete(self):
        raise ImmutableCommercialRecordError("Quote snapshots cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ImmutableCommercialRecordError("Quote snapshots can only change status through QuoteSnapshot.save().")


class QuoteSnapshot(BaseUUIDModel):
    MUTABLE_FIELDS = {
        'status', 'accepted_at', 'accepted_by', 'consent_notice_version', 'accept_gate_version', 'updated_at',
    }
    ALLOWED_STATUS_TRANSITIONS = {
        QuoteStatusChoices.ISSUED: {QuoteStatusChoices.ACCEPTED, QuoteStatusChoices.EXPIRED, QuoteStatusChoices.VOID},
    }

    quote_number = models.CharField(max_length=40, unique=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='commercial_quotes')
    organisation = models.ForeignKey(
        'organisations.Organisation', on_delete=models.PROTECT, null=True, blank=True, related_name='commercial_quotes',
    )
    customer_role = models.CharField(max_length=30, choices=PayerRoleChoices.choices)
    country_code = models.CharField(max_length=2)
    vertical = models.CharField(max_length=30, choices=VerticalChoices.choices)
    currency = models.CharField(max_length=3)
    currency_exponent = models.PositiveSmallIntegerField()

    face_value_minor = models.BigIntegerField(default=0)
    discount_minor = models.BigIntegerField(default=0)
    delivery_minor = models.BigIntegerField(default=0)
    tax_minor = models.BigIntegerField(default=0)
    commissionable_base_minor = models.BigIntegerField(default=0)
    platform_fee_minor = models.BigIntegerField(default=0)
    customer_total_minor = models.BigIntegerField(default=0)
    fee_base_rule = models.CharField(max_length=64)

    gate = models.ForeignKey(CountryGate, on_delete=models.PROTECT, related_name='quotes')
    gate_version = models.PositiveIntegerField(help_text="country_activation_version at issue time.")
    role_snapshot = models.OneToOneField(PartyRoleSnapshot, on_delete=models.PROTECT, related_name='quote')
    tax_determination_reference = models.CharField(max_length=255)
    terms_version = models.CharField(max_length=64)
    terms_hash = models.CharField(max_length=64, db_index=True)
    expires_at = models.DateTimeField()

    status = models.CharField(
        max_length=20, choices=QuoteStatusChoices.choices, default=QuoteStatusChoices.ISSUED, db_index=True,
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+',
    )
    consent_notice_version = models.CharField(max_length=64, blank=True, default='')
    accept_gate_version = models.PositiveIntegerField(null=True, blank=True)

    objects = QuoteSnapshotQuerySet.as_manager()

    class Meta:
        verbose_name = 'Quote Snapshot'
        verbose_name_plural = 'Quote Snapshots'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['customer', '-created_at'])]

    def __str__(self):
        return f"{self.quote_number} {self.currency} {self.customer_total_minor} ({self.status})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = QuoteSnapshot.objects.filter(pk=self.pk).first()
            if original is not None:
                self._guard_changes(original)
        super().save(*args, **kwargs)

    def _guard_changes(self, original):
        for field in self._meta.concrete_fields:
            if field.attname in self.MUTABLE_FIELDS or field.name in self.MUTABLE_FIELDS:
                continue
            if getattr(original, field.attname) != getattr(self, field.attname):
                raise ImmutableCommercialRecordError(
                    f"Quote {original.quote_number} is immutable; field '{field.name}' cannot change."
                )
        if original.status != self.status:
            allowed = self.ALLOWED_STATUS_TRANSITIONS.get(original.status, set())
            if self.status not in allowed:
                raise ImmutableCommercialRecordError(
                    f"Quote {original.quote_number} cannot move from {original.status} to {self.status}."
                )
        elif original.status != QuoteStatusChoices.ISSUED:
            raise ImmutableCommercialRecordError(f"Quote {original.quote_number} is {original.status} and frozen.")

    def delete(self, *args, **kwargs):
        raise ImmutableCommercialRecordError("Quote snapshots cannot be deleted.")


class QuoteLine(AppendOnlyModel):
    quote = models.ForeignKey(QuoteSnapshot, on_delete=models.PROTECT, related_name='lines')
    position = models.PositiveSmallIntegerField()
    line_type = models.CharField(max_length=20, choices=QuoteLineTypeChoices.choices)
    description = models.CharField(max_length=255)
    sku_code = models.CharField(max_length=64, blank=True, default='')
    sku_version = models.PositiveIntegerField(null=True, blank=True)
    rate_schedule = models.ForeignKey(
        RateSchedule, on_delete=models.PROTECT, null=True, blank=True, related_name='quote_lines',
    )
    quantity = models.PositiveIntegerField(default=1)
    amount_minor = models.BigIntegerField()
    payer_role = models.CharField(max_length=30, choices=PayerRoleChoices.choices, blank=True, default='')
    is_customer_payable = models.BooleanField()

    class Meta:
        verbose_name = 'Quote Line'
        verbose_name_plural = 'Quote Lines'
        ordering = ['quote', 'position']
        constraints = [
            models.UniqueConstraint(fields=['quote', 'position'], name='unique_quote_line_position'),
        ]
