from django.utils import timezone
from rest_framework import serializers

from platform_core.events.models import OutboxEvent

from .choices import (
    CatalogueStatusChoices,
    GateStatusChoices,
    PayerRoleChoices,
    QuoteStatusChoices,
    RoleProfileStatusChoices,
    VerticalChoices,
)
from .models import (
    CommercialSku,
    CountryGate,
    CountryGateTransition,
    PartyRoleProfile,
    PartyRoleSnapshot,
    QuoteLine,
    QuoteSnapshot,
    RateSchedule,
)
from .money import CURRENCY_EXPONENTS


def _email(user):
    return user.email if user else None


class ApprovalReadMixin(serializers.Serializer):
    created_by_email = serializers.SerializerMethodField()
    approved_by_email = serializers.SerializerMethodField()

    def get_created_by_email(self, obj):
        return _email(obj.created_by)

    def get_approved_by_email(self, obj):
        return _email(obj.approved_by)


# --- SKUs ---------------------------------------------------------------------------------------

class CommercialSkuSerializer(ApprovalReadMixin, serializers.ModelSerializer):
    class Meta:
        model = CommercialSku
        fields = [
            'id', 'sku_code', 'version', 'name', 'description', 'family', 'revenue_code', 'vertical', 'fee_basis',
            'entitlement_type', 'billing_interval', 'tax_class', 'refund_policy_id', 'illustrative_band_note',
            'is_regulated', 'status', 'status_reason', 'approval_reference', 'approved_at',
            'created_by_email', 'approved_by_email', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class CommercialSkuWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommercialSku
        fields = [
            'sku_code', 'name', 'description', 'family', 'revenue_code', 'vertical', 'fee_basis', 'entitlement_type',
            'billing_interval', 'tax_class', 'refund_policy_id', 'illustrative_band_note',
        ]
        extra_kwargs = {'sku_code': {'validators': []}}


class StatusTransitionSerializer(serializers.Serializer):
    to_status = serializers.CharField()
    reason = serializers.CharField(allow_blank=True, required=False, default='')
    approval_reference = serializers.CharField(allow_blank=True, required=False, default='')


# --- Rate schedules -----------------------------------------------------------------------------

class RateScheduleSerializer(ApprovalReadMixin, serializers.ModelSerializer):
    sku_code = serializers.CharField(source='sku.sku_code', read_only=True)
    sku_version = serializers.IntegerField(source='sku.version', read_only=True)
    fee_basis = serializers.CharField(source='sku.fee_basis', read_only=True)
    currency_exponent = serializers.SerializerMethodField()

    class Meta:
        model = RateSchedule
        fields = [
            'id', 'name', 'sku', 'sku_code', 'sku_version', 'fee_basis', 'country_code', 'vertical', 'currency',
            'currency_exponent', 'payer_role', 'plan_code', 'priority', 'effective_from', 'effective_to',
            'flat_amount_minor', 'percentage_bps', 'min_fee_minor', 'max_fee_minor', 'status', 'status_reason',
            'approval_reference', 'approved_at', 'created_by_email', 'approved_by_email', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_currency_exponent(self, obj):
        return CURRENCY_EXPONENTS.get(obj.currency)


class RateScheduleWriteSerializer(serializers.ModelSerializer):
    sku = serializers.PrimaryKeyRelatedField(queryset=CommercialSku.objects.all(), required=False)

    class Meta:
        model = RateSchedule
        fields = [
            'sku', 'name', 'country_code', 'vertical', 'currency', 'payer_role', 'plan_code', 'priority',
            'effective_from', 'effective_to', 'flat_amount_minor', 'percentage_bps', 'min_fee_minor', 'max_fee_minor',
        ]
        extra_kwargs = {'vertical': {'required': False}}


# --- Party role profiles ------------------------------------------------------------------------

class PartyRoleProfileSerializer(ApprovalReadMixin, serializers.ModelSerializer):
    is_gated = serializers.BooleanField(read_only=True)

    class Meta:
        model = PartyRoleProfile
        fields = [
            'id', 'code', 'version', 'name', 'profile_type', 'country_code', 'vertical', 'seller_of_record',
            'service_performer', 'platform_role', 'payment_role', 'tax_party', 'invoice_issuer',
            'licensed_partner_required', 'legal_memo_reference', 'effective_from', 'effective_to', 'is_gated',
            'status', 'status_reason', 'approval_reference', 'approved_at', 'created_by_email', 'approved_by_email',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class PartyRoleProfileWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartyRoleProfile
        fields = [
            'code', 'name', 'profile_type', 'country_code', 'vertical', 'seller_of_record', 'service_performer',
            'platform_role', 'payment_role', 'tax_party', 'invoice_issuer', 'licensed_partner_required',
            'legal_memo_reference', 'effective_from', 'effective_to',
        ]


# --- Country gates ------------------------------------------------------------------------------

class CountryGateTransitionSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source='actor.email', read_only=True)

    class Meta:
        model = CountryGateTransition
        fields = ['id', 'from_status', 'to_status', 'version_after', 'actor_email', 'reason', 'evidence_reference',
                  'created_at']
        read_only_fields = fields


class CountryGateSerializer(serializers.ModelSerializer):
    is_open = serializers.BooleanField(read_only=True)
    is_regulated = serializers.BooleanField(read_only=True)
    allowed_next_statuses = serializers.SerializerMethodField()

    class Meta:
        model = CountryGate
        fields = [
            'id', 'country_code', 'vertical', 'capability', 'status', 'version', 'is_open', 'is_regulated',
            'allowed_currencies', 'tax_schedule_reference', 'notes', 'allowed_next_statuses', 'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_allowed_next_statuses(self, obj):
        from .services.gates import allowed_transitions
        return sorted(allowed_transitions(obj.status))


class CountryGateDetailSerializer(CountryGateSerializer):
    transitions = CountryGateTransitionSerializer(many=True, read_only=True)

    class Meta(CountryGateSerializer.Meta):
        fields = CountryGateSerializer.Meta.fields + ['transitions']
        read_only_fields = fields


class CountryGateCreateSerializer(serializers.ModelSerializer):
    allowed_currencies = serializers.ListField(child=serializers.CharField(), required=False)

    class Meta:
        model = CountryGate
        fields = ['country_code', 'vertical', 'capability', 'allowed_currencies', 'tax_schedule_reference', 'notes']
        extra_kwargs = {'country_code': {'validators': []}}
        validators = []


class CountryGateConfigSerializer(serializers.Serializer):
    allowed_currencies = serializers.ListField(child=serializers.CharField(), required=False)
    tax_schedule_reference = serializers.CharField(allow_blank=True, required=False)
    notes = serializers.CharField(allow_blank=True, required=False)


class GateTransitionRequestSerializer(serializers.Serializer):
    to_status = serializers.ChoiceField(choices=GateStatusChoices.choices)
    reason = serializers.CharField(allow_blank=True, required=False, default='')
    evidence_reference = serializers.CharField(allow_blank=True, required=False, default='')


# --- Quotes -------------------------------------------------------------------------------------

class FeeItemSerializer(serializers.Serializer):
    sku_code = serializers.CharField(max_length=64)
    payer_role = serializers.ChoiceField(choices=PayerRoleChoices.choices)
    quantity = serializers.IntegerField(min_value=1, default=1)
    plan_code = serializers.CharField(max_length=64, allow_blank=True, required=False, default='')


class QuoteRequestSerializer(serializers.Serializer):
    country_code = serializers.CharField(max_length=2)
    vertical = serializers.ChoiceField(choices=VerticalChoices.choices)
    currency = serializers.CharField(max_length=3)
    customer_role = serializers.ChoiceField(choices=PayerRoleChoices.choices)
    role_profile_code = serializers.CharField(max_length=64)
    fee_items = FeeItemSerializer(many=True)
    face_value_minor = serializers.IntegerField(min_value=0, default=0)
    discount_minor = serializers.IntegerField(min_value=0, default=0)
    delivery_minor = serializers.IntegerField(min_value=0, default=0)
    tax_minor = serializers.IntegerField(min_value=0, default=0)
    terms_version = serializers.CharField(max_length=64, allow_blank=True, required=False, default='')
    tax_determination_reference = serializers.CharField(max_length=255, allow_blank=True, required=False, default='')
    organisation_id = serializers.UUIDField(required=False, allow_null=True)
    seller_organisation_id = serializers.UUIDField(required=False, allow_null=True)


class QuoteLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuoteLine
        fields = ['position', 'line_type', 'description', 'sku_code', 'sku_version', 'rate_schedule', 'quantity',
                  'amount_minor', 'payer_role', 'is_customer_payable']
        read_only_fields = fields


class PartyRoleSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartyRoleSnapshot
        fields = ['profile_code', 'profile_version', 'profile_type', 'seller_of_record_party',
                  'service_performer_party', 'platform_role', 'payment_role', 'tax_party', 'invoice_issuer',
                  'licensed_partner_required', 'jurisdiction', 'snapshot_hash']
        read_only_fields = fields


class QuoteSnapshotSerializer(serializers.ModelSerializer):
    lines = QuoteLineSerializer(many=True, read_only=True)
    role_snapshot = PartyRoleSnapshotSerializer(read_only=True)
    effective_status = serializers.SerializerMethodField()
    customer_email = serializers.EmailField(source='customer.email', read_only=True)

    class Meta:
        model = QuoteSnapshot
        fields = [
            'id', 'quote_number', 'customer_email', 'organisation', 'customer_role', 'country_code', 'vertical',
            'currency', 'currency_exponent', 'face_value_minor', 'discount_minor', 'delivery_minor', 'tax_minor',
            'commissionable_base_minor', 'platform_fee_minor', 'customer_total_minor', 'fee_base_rule',
            'gate_version', 'tax_determination_reference', 'terms_version', 'terms_hash', 'expires_at', 'status',
            'effective_status', 'accepted_at', 'consent_notice_version', 'role_snapshot', 'lines', 'created_at',
        ]
        read_only_fields = fields

    def get_effective_status(self, obj):
        if obj.status == QuoteStatusChoices.ISSUED and timezone.now() >= obj.expires_at:
            return QuoteStatusChoices.EXPIRED
        return obj.status


class QuoteAcceptSerializer(serializers.Serializer):
    terms_hash = serializers.CharField(max_length=64)
    consent_notice_version = serializers.CharField(max_length=64, allow_blank=True)


# --- Outbox -------------------------------------------------------------------------------------

class OutboxEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutboxEvent
        fields = ['id', 'topic', 'schema_version', 'aggregate_type', 'aggregate_id', 'payload', 'correlation_id',
                  'actor_id', 'occurred_at', 'status', 'attempts', 'published_at', 'last_error']
        read_only_fields = fields


TRANSITION_STATUS_CHOICES = {
    'sku': {c for c, _ in CatalogueStatusChoices.choices},
    'rate': {c for c, _ in CatalogueStatusChoices.choices},
    'profile': {c for c, _ in RoleProfileStatusChoices.choices},
}
