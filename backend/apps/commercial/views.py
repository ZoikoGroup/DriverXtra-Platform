"""Commercial control plane API (Master Architecture §21 minimum APIs, adapted to /api/v1/commercial/...).

Admin endpoints require platform staff with a commercial permission; approvals additionally require
commercial.approve and gate transitions require country_gate.manage. Public plan display only shows
APPROVED, non-regulated SKUs with APPROVED effective rates in markets whose DISCOVERY gate is ENABLED.
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status, views
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.organisations.models import Organisation
from platform_core.events.models import OutboxEvent

from .choices import CatalogueStatusChoices, GateCapabilityChoices, GateStatusChoices, RoleProfileStatusChoices
from .errors import CommercialRuleViolation
from .models import CommercialSku, CountryGate, PartyRoleProfile, QuoteSnapshot, RateSchedule
from .money import CURRENCY_EXPONENTS
from .permissions import (
    COMMERCIAL_APPROVE,
    COMMERCIAL_MANAGE,
    COUNTRY_GATE_MANAGE,
    IsCommercialStaff,
    user_has,
)
from .serializers import (
    CommercialSkuSerializer,
    CommercialSkuWriteSerializer,
    CountryGateConfigSerializer,
    CountryGateCreateSerializer,
    CountryGateDetailSerializer,
    CountryGateSerializer,
    GateTransitionRequestSerializer,
    OutboxEventSerializer,
    PartyRoleProfileSerializer,
    PartyRoleProfileWriteSerializer,
    QuoteAcceptSerializer,
    QuoteRequestSerializer,
    QuoteSnapshotSerializer,
    RateScheduleSerializer,
    RateScheduleWriteSerializer,
    StatusTransitionSerializer,
    TRANSITION_STATUS_CHOICES,
)
from .services import catalogue, gates, quotes, rates, roles
from .services.common import normalize_country
from .services.quotes import FeeItem, QuoteRequest


def require_permission(request, code: str):
    if not user_has(request.user, code):
        raise PermissionDenied(f"You do not have the required '{code}' permission.")


def transition_permission(to_status: str) -> str:
    return COMMERCIAL_APPROVE if to_status in ('APPROVED', 'RETIRED') else COMMERCIAL_MANAGE


def validated_transition(request, kind: str) -> dict:
    serializer = StatusTransitionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if data['to_status'] not in TRANSITION_STATUS_CHOICES[kind]:
        raise CommercialRuleViolation('INVALID_STATUS', f"'{data['to_status']}' is not a valid status.", 400)
    require_permission(request, transition_permission(data['to_status']))
    return data


CASE_SENSITIVE_FILTER_FIELDS = {'sku_id'}


def filter_params(queryset, request, mapping: dict):
    """Apply exact-match query filters; code-like values are matched in upper case."""
    for param, field in mapping.items():
        value = (request.query_params.get(param) or '').strip()
        if value:
            queryset = queryset.filter(**{field: value if field in CASE_SENSITIVE_FILTER_FIELDS else value.upper()})
    return queryset


# =================================================================================================
# Admin: SKU catalogue
# =================================================================================================

class AdminSkuListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsCommercialStaff]
    serializer_class = CommercialSkuSerializer

    def get_queryset(self):
        qs = CommercialSku.objects.select_related('created_by', 'approved_by')
        qs = filter_params(qs, self.request, {'status': 'status', 'vertical': 'vertical', 'family': 'family',
                                              'sku_code': 'sku_code'})
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(sku_code__icontains=search) | Q(name__icontains=search))
        return qs

    def create(self, request, *args, **kwargs):
        require_permission(request, COMMERCIAL_MANAGE)
        serializer = CommercialSkuWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sku = catalogue.create_sku(serializer.validated_data, request.user)
        return Response(CommercialSkuSerializer(sku).data, status=status.HTTP_201_CREATED)


class AdminSkuDetailView(views.APIView):
    permission_classes = [IsCommercialStaff]

    def get(self, request, id):
        return Response(CommercialSkuSerializer(get_object_or_404(CommercialSku, id=id)).data)

    def patch(self, request, id):
        require_permission(request, COMMERCIAL_MANAGE)
        sku = get_object_or_404(CommercialSku, id=id)
        serializer = CommercialSkuWriteSerializer(sku, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = {k: v for k, v in serializer.validated_data.items() if k != 'sku_code'}
        return Response(CommercialSkuSerializer(catalogue.update_sku(sku, data, request.user)).data)


class AdminSkuTransitionView(views.APIView):
    permission_classes = [IsCommercialStaff]

    def post(self, request, id):
        sku = get_object_or_404(CommercialSku, id=id)
        data = validated_transition(request, 'sku')
        sku = catalogue.transition_sku(sku, data['to_status'], request.user, data['reason'], data['approval_reference'])
        return Response(CommercialSkuSerializer(sku).data)


class AdminSkuNewVersionView(views.APIView):
    permission_classes = [IsCommercialStaff]

    def post(self, request, id):
        require_permission(request, COMMERCIAL_MANAGE)
        sku = catalogue.create_new_version(get_object_or_404(CommercialSku, id=id), request.user)
        return Response(CommercialSkuSerializer(sku).data, status=status.HTTP_201_CREATED)


# =================================================================================================
# Admin: rate schedules
# =================================================================================================

class AdminRateListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsCommercialStaff]
    serializer_class = RateScheduleSerializer

    def get_queryset(self):
        qs = RateSchedule.objects.select_related('sku', 'created_by', 'approved_by')
        return filter_params(qs, self.request, {'status': 'status', 'sku': 'sku_id', 'country_code': 'country_code',
                                                'currency': 'currency'})

    def create(self, request, *args, **kwargs):
        require_permission(request, COMMERCIAL_MANAGE)
        serializer = RateScheduleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        sku = data.pop('sku', None)
        if sku is None:
            raise CommercialRuleViolation('SKU_REQUIRED', 'sku is required.', 400)
        schedule = rates.create_rate(sku, data, request.user)
        return Response(RateScheduleSerializer(schedule).data, status=status.HTTP_201_CREATED)


class AdminRateDetailView(views.APIView):
    permission_classes = [IsCommercialStaff]

    def get(self, request, id):
        return Response(RateScheduleSerializer(get_object_or_404(RateSchedule.objects.select_related('sku'), id=id)).data)

    def patch(self, request, id):
        require_permission(request, COMMERCIAL_MANAGE)
        schedule = get_object_or_404(RateSchedule, id=id)
        serializer = RateScheduleWriteSerializer(schedule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = {k: v for k, v in serializer.validated_data.items() if k != 'sku'}
        return Response(RateScheduleSerializer(rates.update_rate(schedule, data, request.user)).data)


class AdminRateTransitionView(views.APIView):
    permission_classes = [IsCommercialStaff]

    def post(self, request, id):
        schedule = get_object_or_404(RateSchedule, id=id)
        data = validated_transition(request, 'rate')
        schedule = rates.transition_rate(schedule, data['to_status'], request.user, data['reason'],
                                         data['approval_reference'])
        return Response(RateScheduleSerializer(schedule).data)


# =================================================================================================
# Admin: party role profiles
# =================================================================================================

class AdminRoleProfileListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsCommercialStaff]
    serializer_class = PartyRoleProfileSerializer

    def get_queryset(self):
        qs = PartyRoleProfile.objects.select_related('created_by', 'approved_by')
        return filter_params(qs, self.request, {'status': 'status', 'country_code': 'country_code',
                                                'vertical': 'vertical'})

    def create(self, request, *args, **kwargs):
        require_permission(request, COMMERCIAL_MANAGE)
        serializer = PartyRoleProfileWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = roles.create_profile(serializer.validated_data, request.user)
        return Response(PartyRoleProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


class AdminRoleProfileDetailView(views.APIView):
    permission_classes = [IsCommercialStaff]

    def get(self, request, id):
        return Response(PartyRoleProfileSerializer(get_object_or_404(PartyRoleProfile, id=id)).data)

    def patch(self, request, id):
        require_permission(request, COMMERCIAL_MANAGE)
        profile = get_object_or_404(PartyRoleProfile, id=id)
        serializer = PartyRoleProfileWriteSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = {k: v for k, v in serializer.validated_data.items() if k != 'code'}
        return Response(PartyRoleProfileSerializer(roles.update_profile(profile, data, request.user)).data)


class AdminRoleProfileTransitionView(views.APIView):
    permission_classes = [IsCommercialStaff]

    def post(self, request, id):
        profile = get_object_or_404(PartyRoleProfile, id=id)
        data = validated_transition(request, 'profile')
        profile = roles.transition_profile(profile, data['to_status'], request.user, data['reason'],
                                           data['approval_reference'])
        return Response(PartyRoleProfileSerializer(profile).data)


class AdminRoleProfileNewVersionView(views.APIView):
    permission_classes = [IsCommercialStaff]

    def post(self, request, id):
        require_permission(request, COMMERCIAL_MANAGE)
        profile = roles.create_new_profile_version(get_object_or_404(PartyRoleProfile, id=id), request.user)
        return Response(PartyRoleProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


# =================================================================================================
# Admin: country gates
# =================================================================================================

class AdminGateListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsCommercialStaff]
    serializer_class = CountryGateSerializer

    def get_queryset(self):
        return filter_params(CountryGate.objects.all(), self.request,
                             {'status': 'status', 'country_code': 'country_code', 'vertical': 'vertical',
                              'capability': 'capability'})

    def create(self, request, *args, **kwargs):
        require_permission(request, COUNTRY_GATE_MANAGE)
        serializer = CountryGateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        gate = gates.create_gate(serializer.validated_data, request.user)
        return Response(CountryGateDetailSerializer(gate).data, status=status.HTTP_201_CREATED)


class AdminGateDetailView(views.APIView):
    permission_classes = [IsCommercialStaff]

    def get(self, request, id):
        gate = get_object_or_404(CountryGate.objects.prefetch_related('transitions__actor'), id=id)
        return Response(CountryGateDetailSerializer(gate).data)

    def patch(self, request, id):
        require_permission(request, COUNTRY_GATE_MANAGE)
        gate = get_object_or_404(CountryGate, id=id)
        serializer = CountryGateConfigSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        gate = gates.update_gate_config(gate, serializer.validated_data, request.user)
        return Response(CountryGateDetailSerializer(gate).data)


class AdminGateTransitionView(views.APIView):
    permission_classes = [IsCommercialStaff]

    def post(self, request, id):
        require_permission(request, COUNTRY_GATE_MANAGE)
        gate = get_object_or_404(CountryGate, id=id)
        serializer = GateTransitionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        gate = gates.transition_gate(gate, data['to_status'], request.user, data['reason'], data['evidence_reference'])
        return Response(CountryGateDetailSerializer(CountryGate.objects.prefetch_related('transitions__actor').get(pk=gate.pk)).data)


# =================================================================================================
# Admin: quote preview, quote list and outbox
# =================================================================================================

def build_quote_request(request, data) -> QuoteRequest:
    organisation = seller_organisation = None
    if data.get('organisation_id'):
        organisation = Organisation.objects.filter(id=data['organisation_id'], is_active=True).first()
        if organisation is None or organisation.get_member_role(request.user) not in ('OWNER', 'ADMIN'):
            raise CommercialRuleViolation(
                'ORGANISATION_NOT_AUTHORISED', 'You must be an OWNER or ADMIN of the organisation to request its quotes.', 403,
            )
    if data.get('seller_organisation_id'):
        seller_organisation = Organisation.objects.filter(id=data['seller_organisation_id'], is_active=True).first()
        if seller_organisation is None:
            raise CommercialRuleViolation('SELLER_ORGANISATION_NOT_FOUND', 'Seller organisation not found.', 404)
    return QuoteRequest(
        customer=request.user,
        customer_role=data['customer_role'],
        country_code=data['country_code'],
        vertical=data['vertical'],
        currency=data['currency'],
        role_profile_code=data['role_profile_code'],
        fee_items=[FeeItem(**item) for item in data['fee_items']],
        terms_version=data.get('terms_version', ''),
        tax_determination_reference=data.get('tax_determination_reference', ''),
        face_value_minor=data['face_value_minor'],
        discount_minor=data['discount_minor'],
        delivery_minor=data['delivery_minor'],
        tax_minor=data['tax_minor'],
        organisation=organisation,
        seller_organisation=seller_organisation,
    )


def serialize_computation(computation) -> dict:
    return {
        'binding': False,
        'pricing_label': 'NON_BINDING_PREVIEW',
        'country_code': computation.country_code,
        'vertical': computation.vertical,
        'currency': computation.currency,
        'currency_exponent': computation.exponent,
        'face_value_minor': computation.face_value_minor,
        'discount_minor': computation.discount_minor,
        'delivery_minor': computation.delivery_minor,
        'tax_minor': computation.tax_minor,
        'commissionable_base_minor': computation.commissionable_base_minor,
        'platform_fee_minor': computation.platform_fee_minor,
        'customer_total_minor': computation.customer_total_minor,
        'lines': [
            {
                'line_type': line.line_type,
                'description': line.description,
                'amount_minor': line.amount_minor,
                'is_customer_payable': line.is_customer_payable,
                'sku_code': line.sku.sku_code if line.sku else '',
                'sku_version': line.sku.version if line.sku else None,
                'sku_status': line.sku.status if line.sku else None,
                'rate_schedule_id': str(line.rate_schedule.id) if line.rate_schedule else None,
                'rate_status': line.rate_schedule.status if line.rate_schedule else None,
                'quantity': line.quantity,
                'payer_role': line.payer_role,
            }
            for line in computation.lines
        ],
        'parties': computation.parties,
        'blocking_reasons': computation.blocking_reasons,
        'would_be_binding': not computation.blocking_reasons,
    }


class AdminQuotePreviewView(views.APIView):
    """Non-binding calculation over draft/illustrative data. Never persisted, never a price offer."""
    permission_classes = [IsCommercialStaff]

    def post(self, request):
        require_permission(request, COMMERCIAL_MANAGE)
        serializer = QuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        computation = quotes.compute_quote(build_quote_request(request, serializer.validated_data), binding=False)
        return Response(serialize_computation(computation))


class AdminQuoteListView(generics.ListAPIView):
    permission_classes = [IsCommercialStaff]
    serializer_class = QuoteSnapshotSerializer

    def get_queryset(self):
        qs = QuoteSnapshot.objects.select_related('customer', 'role_snapshot').prefetch_related('lines')
        return filter_params(qs, self.request, {'status': 'status', 'country_code': 'country_code'})


class AdminOutboxListView(generics.ListAPIView):
    permission_classes = [IsCommercialStaff]
    serializer_class = OutboxEventSerializer

    def get_queryset(self):
        qs = OutboxEvent.objects.order_by('-occurred_at', '-id')
        topic = self.request.query_params.get('topic')
        if topic:
            qs = qs.filter(topic=topic)
        state = self.request.query_params.get('status')
        if state:
            qs = qs.filter(status=state.upper())
        return qs


# =================================================================================================
# Public plans and customer quotes
# =================================================================================================

class PublicPlansView(views.APIView):
    """GET /api/v1/commercial/plans/?market=XX[&vertical=...] — empty unless the market's DISCOVERY gate is ENABLED."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        market = request.query_params.get('market')
        if not market:
            raise CommercialRuleViolation('MARKET_REQUIRED', 'market (ISO 3166-1 alpha-2) is required; there is no default market.', 400)
        market = normalize_country(market)
        open_gates = CountryGate.objects.filter(
            country_code=market, capability=GateCapabilityChoices.DISCOVERY, status=GateStatusChoices.ENABLED,
        )
        vertical = request.query_params.get('vertical')
        if vertical:
            open_gates = open_gates.filter(vertical=vertical.strip().upper())

        now = timezone.now()
        plans = []
        for gate in open_gates:
            schedules = (
                RateSchedule.objects.select_related('sku')
                .filter(
                    country_code=market, vertical=gate.vertical, status=CatalogueStatusChoices.APPROVED,
                    currency__in=gate.allowed_currencies or [], sku__status=CatalogueStatusChoices.APPROVED,
                    sku__is_regulated=False, effective_from__lte=now,
                )
                .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=now))
                .order_by('sku__sku_code', '-priority')
            )
            by_sku = {}
            for schedule in schedules:
                sku = schedule.sku
                entry = by_sku.setdefault(sku.id, {
                    'sku_code': sku.sku_code, 'version': sku.version, 'name': sku.name, 'description': sku.description,
                    'family': sku.family, 'vertical': sku.vertical, 'fee_basis': sku.fee_basis,
                    'billing_interval': sku.billing_interval, 'entitlement_type': sku.entitlement_type, 'rates': [],
                })
                entry['rates'].append({
                    'currency': schedule.currency, 'currency_exponent': CURRENCY_EXPONENTS[schedule.currency],
                    'payer_role': schedule.payer_role, 'plan_code': schedule.plan_code,
                    'flat_amount_minor': schedule.flat_amount_minor, 'percentage_bps': schedule.percentage_bps,
                    'min_fee_minor': schedule.min_fee_minor, 'max_fee_minor': schedule.max_fee_minor,
                    'effective_from': schedule.effective_from, 'effective_to': schedule.effective_to,
                })
            plans.extend(by_sku.values())

        return Response({
            'market': market,
            'activated_verticals': sorted({gate.vertical for gate in open_gates}),
            'plans': plans,
            'disclosure': 'Prices are shown for information. Taxes, terms and the final payable total are confirmed in a quote before acceptance.',
        })


class QuoteCreateView(generics.ListCreateAPIView):
    """GET: the caller's quotes. POST: issue a binding quote (rejected unless every commercial control passes)."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = QuoteSnapshotSerializer

    def get_queryset(self):
        return (QuoteSnapshot.objects.filter(customer=self.request.user)
                .select_related('customer', 'role_snapshot').prefetch_related('lines'))

    def create(self, request, *args, **kwargs):
        serializer = QuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = quotes.issue_quote(build_quote_request(request, serializer.validated_data))
        return Response(QuoteSnapshotSerializer(quote).data, status=status.HTTP_201_CREATED)


def visible_quotes(user):
    qs = QuoteSnapshot.objects.select_related('customer', 'role_snapshot', 'gate').prefetch_related('lines')
    if user.is_platform_staff and any(user_has(user, c) for c in (COMMERCIAL_MANAGE, COMMERCIAL_APPROVE)):
        return qs
    return qs.filter(customer=user)


class QuoteDetailView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        return Response(QuoteSnapshotSerializer(get_object_or_404(visible_quotes(request.user), id=id)).data)


class QuoteAcceptView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        quote = get_object_or_404(QuoteSnapshot.objects.filter(customer=request.user), id=id)
        serializer = QuoteAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = quotes.accept_quote(quote, request.user, terms_hash=serializer.validated_data['terms_hash'],
                                    consent_notice_version=serializer.validated_data['consent_notice_version'])
        return Response(QuoteSnapshotSerializer(quote).data)
