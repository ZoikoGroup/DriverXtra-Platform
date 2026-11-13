"""Authorization matrix for refund, dispute and review-moderation endpoints (F1, F4, F5, F8).

Every actor is checked against every endpoint and must receive exactly the expected success
status or HTTP 403. Allowed sets follow the seeded permission matrix plus approved decisions:
  - refund mutations: 'order.refund'                  (U3)
  - refund list: 'order.refund' or 'finance.payout'   (U3)
  - dispute management: 'dispute.manage'              (U1: SUPPORT_AGENT keeps it)
  - dispute detail read: also 'order.refund'          (U4)
  - review moderation: 'review.moderate'              (U2: VERIFICATION_OFFICER; STAFF without a
                                                       sub-role falls back to VERIFICATION_OFFICER)
Platform ADMIN and superusers hold every permission. Buyer/seller party access is unchanged.
Workshop review moderation is covered per staff role in tests/test_workshop_reviews.py.
"""
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices, StaffRole, StaffProfile
from apps.marketplace.models import (
    ProductReview,
    ReviewReport,
    ReviewReportReasonChoices,
    ReviewReportStatusChoices,
    ReviewStatusChoices,
    DisputeCategoryChoices,
    RefundMethodChoices,
)
from apps.marketplace.returns.service import RefundService, DisputeService
from tests.test_returns_refunds_and_disputes import brake_category, sample_delivered_order  # noqa: F401  (fixtures)

ACTORS = [
    'buyer',
    'seller',
    'staff_no_profile',
    'SUPPORT_AGENT',
    'VERIFICATION_OFFICER',
    'DISPUTE_MANAGER',
    'FINANCE_OFFICER',
    'admin_role',
    'superuser',
]

ADMINS = {'admin_role', 'superuser'}
REFUND = {'DISPUTE_MANAGER', 'FINANCE_OFFICER'} | ADMINS
REFUND_LIST = REFUND  # FINANCE_OFFICER also holds finance.payout
DISPUTE_MANAGE = {'SUPPORT_AGENT', 'DISPUTE_MANAGER'} | ADMINS
DISPUTE_READ = DISPUTE_MANAGE | {'FINANCE_OFFICER', 'buyer', 'seller'}
DISPUTE_MESSAGE = DISPUTE_MANAGE | {'buyer', 'seller'}
REFUND_SUMMARY = REFUND | {'buyer', 'seller'}
REVIEW_MODERATE = {'VERIFICATION_OFFICER', 'staff_no_profile'} | ADMINS

# key: (method, url builder, payload builder, success status, allowed actors)
ENDPOINTS = {
    'refund_create': ('post', lambda c: f"/api/v1/marketplace/admin/orders/{c['order'].id}/refund/",
                      lambda c: {'amount': '10.00', 'reason': 'Matrix', 'refund_method': 'BANK_TRANSFER'},
                      status.HTTP_201_CREATED, REFUND),
    'refund_approve': ('post', lambda c: f"/api/v1/marketplace/admin/refunds/{c['refund'].refund_number}/approve/",
                       lambda c: {}, status.HTTP_200_OK, REFUND),
    'refund_process': ('post', lambda c: f"/api/v1/marketplace/admin/refunds/{c['refund'].refund_number}/process/",
                       lambda c: {}, status.HTTP_200_OK, REFUND),
    'refund_reject': ('post', lambda c: f"/api/v1/marketplace/admin/refunds/{c['refund'].refund_number}/reject/",
                      lambda c: {'reason': 'Matrix rejection'}, status.HTTP_200_OK, REFUND),
    'refund_list': ('get', lambda c: '/api/v1/marketplace/admin/refunds/', None, status.HTTP_200_OK, REFUND_LIST),
    'refund_summary': ('get', lambda c: f"/api/v1/marketplace/orders/{c['order'].id}/refund-summary/", None,
                       status.HTTP_200_OK, REFUND_SUMMARY),
    'dispute_admin_list': ('get', lambda c: '/api/v1/marketplace/admin/disputes/', None,
                           status.HTTP_200_OK, DISPUTE_MANAGE),
    'dispute_status_update': ('post', lambda c: f"/api/v1/marketplace/admin/disputes/{c['dispute'].dispute_number}/status/",
                              lambda c: {'status': 'UNDER_REVIEW', 'resolution_notes': 'Matrix'},
                              status.HTTP_200_OK, DISPUTE_MANAGE),
    'dispute_detail': ('get', lambda c: f"/api/v1/marketplace/disputes/{c['dispute'].dispute_number}/", None,
                       status.HTTP_200_OK, DISPUTE_READ),
    'dispute_message': ('post', lambda c: f"/api/v1/marketplace/disputes/{c['dispute'].dispute_number}/messages/",
                        lambda c: {'message': 'Matrix message'}, status.HTTP_201_CREATED, DISPUTE_MESSAGE),
    'review_admin_list': ('get', lambda c: '/api/v1/marketplace/admin/reviews/', None,
                          status.HTTP_200_OK, REVIEW_MODERATE),
    'review_moderate': ('post', lambda c: f"/api/v1/marketplace/admin/reviews/{c['review'].id}/moderate/",
                        lambda c: {'action': 'FLAG', 'admin_notes': 'Matrix'}, status.HTTP_200_OK, REVIEW_MODERATE),
    'review_reports_list': ('get', lambda c: '/api/v1/marketplace/admin/review-reports/', None,
                            status.HTTP_200_OK, REVIEW_MODERATE),
    'review_report_resolve': ('post', lambda c: f"/api/v1/marketplace/admin/review-reports/{c['report'].id}/resolve/",
                              lambda c: {'action': 'DISMISS', 'admin_notes': 'Matrix'},
                              status.HTTP_200_OK, REVIEW_MODERATE),
    # Removing a review: allowed for its author (the buyer) and for review moderators only.
    'review_delete': ('delete', lambda c: f"/api/v1/marketplace/reviews/{c['review'].id}/", None,
                      status.HTTP_200_OK, REVIEW_MODERATE | {'buyer'}),
}


def _staff(email, staff_role_code=None):
    user = User.objects.create_user(email=email, password='SecurePassword123!', is_staff=True, is_email_verified=True)
    user.add_role(RoleChoices.STAFF)
    if staff_role_code:
        profile, _ = StaffProfile.objects.get_or_create(user=user)
        profile.staff_role = StaffRole.objects.get(code=staff_role_code)
        profile.save()
    return user


def _actor(name, buyer_user, seller_user):
    if name == 'buyer':
        return buyer_user
    if name == 'seller':
        return seller_user
    if name == 'staff_no_profile':
        return _staff('matrix_staff@driverxtra.com')
    if name == 'admin_role':
        user = User.objects.create_user(email='matrix_admin@driverxtra.com', password='SecurePassword123!',
                                        is_email_verified=True)
        user.add_role(RoleChoices.ADMIN)
        return user
    if name == 'superuser':
        return User.objects.create_superuser(email='matrix_root@driverxtra.com', password='SecurePassword123!')
    return _staff(f'matrix_{name.lower()}@driverxtra.com', name)


@pytest.fixture
def matrix_context(sample_delivered_order, buyer_user, seller_user):
    order, item, _ = sample_delivered_order
    setup_admin = User.objects.create_superuser(email='matrix_setup@driverxtra.com', password='SecurePassword123!')
    refund = RefundService.create_refund(
        order=order, amount=Decimal('50.00'), reason='Matrix pending refund', actor=setup_admin,
        refund_method=RefundMethodChoices.BANK_TRANSFER,
    )
    dispute = DisputeService.create_dispute(
        order=order, buyer=buyer_user, category=DisputeCategoryChoices.DAMAGED_OR_DEFECTIVE, description='Matrix dispute',
    )
    reporter = User.objects.create_user(email='matrix_reporter@driverxtra.com', password='SecurePassword123!',
                                        is_email_verified=True)
    review = ProductReview.objects.create(
        order=order, order_item=item, listing=item.listing, buyer=buyer_user, seller=seller_user,
        rating=1, comment='Matrix review under moderation.', status=ReviewStatusChoices.FLAGGED,
    )
    report = ReviewReport.objects.create(product_review=review, reporter=reporter,
                                         reason=ReviewReportReasonChoices.OFFENSIVE,
                                         status=ReviewReportStatusChoices.PENDING)
    return {'order': order, 'refund': refund, 'dispute': dispute, 'review': review, 'report': report}


@pytest.mark.django_db
@pytest.mark.parametrize('endpoint', list(ENDPOINTS))
@pytest.mark.parametrize('actor_name', ACTORS)
def test_authorization_matrix(matrix_context, buyer_user, seller_user, endpoint, actor_name):
    method, url_fn, payload_fn, success_status, allowed = ENDPOINTS[endpoint]
    client = APIClient()
    client.force_authenticate(user=_actor(actor_name, buyer_user, seller_user))
    url = url_fn(matrix_context)
    kwargs = {'format': 'json'} if method != 'get' else {}
    payload = payload_fn(matrix_context) if payload_fn else None
    response = getattr(client, method)(url, payload, **kwargs) if payload is not None else getattr(client, method)(url, **kwargs)

    expected = success_status if actor_name in allowed else status.HTTP_403_FORBIDDEN
    assert response.status_code == expected, (
        f"{actor_name} -> {endpoint}: expected {expected}, got {response.status_code}: {getattr(response, 'data', '')}"
    )


@pytest.mark.django_db
def test_review_author_vs_non_author(matrix_context, buyer_user, seller_user):
    """Author-owned review paths are unchanged; non-authors without 'review.moderate' are refused.

    Status codes are the pre-existing ones: a refused edit returns 400 (the service error is mapped
    to 400 by the existing view) and a refused delete returns 403.
    """
    review = matrix_context['review']
    url = f'/api/v1/marketplace/reviews/{review.id}/'
    non_author_buyer = User.objects.create_user(email='matrix_other_buyer@driverxtra.com',
                                                password='SecurePassword123!', is_email_verified=True)
    non_author_buyer.add_role(RoleChoices.BUYER)

    def client_for(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    for outsider in (non_author_buyer, seller_user):
        c = client_for(outsider)
        assert c.get(url).status_code == status.HTTP_404_NOT_FOUND  # unpublished review hidden
        assert c.patch(url, {'rating': 5}, format='json').status_code == status.HTTP_400_BAD_REQUEST
        assert c.delete(url).status_code == status.HTTP_403_FORBIDDEN
    review.refresh_from_db()
    assert review.rating == 1

    author = client_for(buyer_user)
    assert author.get(url).status_code == status.HTTP_200_OK
    assert author.patch(url, {'rating': 2}, format='json').status_code == status.HTTP_200_OK
    review.refresh_from_db()
    assert review.rating == 2
    assert author.delete(url).status_code == status.HTTP_200_OK
    assert not ProductReview.objects.filter(id=review.id).exists()


# =============================================================================
# U3 strict verification: 'finance.payout' never authorises refund mutations
# =============================================================================

REFUND_MUTATION_ENDPOINTS = ['refund_create', 'refund_approve', 'refund_process', 'refund_reject']


def _payout_only_staff():
    """STAFF user whose sub-role grants ONLY 'finance.payout' (no 'order.refund')."""
    from apps.identity.models import Permission
    role = StaffRole.objects.create(code='PAYOUT_ONLY_TEST', name='Payout only (test)')
    role.role_permissions.create(permission=Permission.objects.get(code='finance.payout'))
    user = _staff('matrix_payout_only@driverxtra.com')
    profile, _ = StaffProfile.objects.get_or_create(user=user)
    profile.staff_role = role
    profile.save()
    assert user.has_permission('finance.payout') is True
    assert user.has_permission('order.refund') is False
    return user


@pytest.mark.django_db
@pytest.mark.parametrize('endpoint', REFUND_MUTATION_ENDPOINTS)
def test_finance_payout_only_gets_403_on_every_refund_mutation_endpoint(matrix_context, endpoint):
    from apps.marketplace.models import Refund, RefundStatusChoices
    method, url_fn, payload_fn, _, _ = ENDPOINTS[endpoint]
    client = APIClient()
    client.force_authenticate(user=_payout_only_staff())
    before = Refund.objects.count()
    response = getattr(client, method)(url_fn(matrix_context), payload_fn(matrix_context), format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN, response.data
    matrix_context['refund'].refresh_from_db()
    assert matrix_context['refund'].status == RefundStatusChoices.PENDING
    assert Refund.objects.count() == before


@pytest.mark.django_db
def test_finance_payout_only_can_list_refunds_but_not_mutate_via_service(matrix_context):
    from django.core.exceptions import ValidationError as DjangoValidationError
    from apps.marketplace.models import RefundStatusChoices
    user = _payout_only_staff()
    client = APIClient()
    client.force_authenticate(user=user)
    assert client.get('/api/v1/marketplace/admin/refunds/').status_code == status.HTTP_200_OK
    # Refund summary requires 'order.refund' (or being the buyer/seller), so payout-only is refused.
    assert client.get(f"/api/v1/marketplace/orders/{matrix_context['order'].id}/refund-summary/").status_code == status.HTTP_403_FORBIDDEN

    refund, order = matrix_context['refund'], matrix_context['order']
    calls = [
        lambda: RefundService.create_refund(order=order, amount=Decimal('5.00'), reason='x', actor=user),
        lambda: RefundService.create_refund(order=order, amount=Decimal('5.00'), reason='x', actor=user, auto_process=True),
        lambda: RefundService.approve_refund(refund, user),
        lambda: RefundService.process_refund(refund, user),
        lambda: RefundService.reject_refund(refund, user, reason='x'),
        lambda: RefundService.fail_refund(refund, user, failure_reason='x'),
        lambda: RefundService.dispatch_gateway_refund(refund, user),
    ]
    for call in calls:
        with pytest.raises(DjangoValidationError, match='Permission denied'):
            call()
    refund.refresh_from_db()
    assert refund.status == RefundStatusChoices.PENDING


@pytest.mark.django_db
def test_matrix_allowed_sets_match_seeded_permissions():
    """The allowed-actor sets above are derived from the seeded matrix, not assumed.

    FINANCE_OFFICER is in the refund-mutation set only because it is seeded with 'order.refund'
    (migration 0005); 'finance.payout' alone grants refund list access only.
    """
    def staff_roles_with(*codes):
        roles = set()
        for role in StaffRole.objects.all():
            held = set(role.role_permissions.values_list('permission__code', flat=True))
            if held & set(codes):
                roles.add(role.code)
        return roles

    fallback = 'staff_no_profile'  # STAFF without sub-role uses VERIFICATION_OFFICER permissions

    def with_fallback(roles):
        return roles | ({fallback} if 'VERIFICATION_OFFICER' in roles else set())

    assert REFUND - ADMINS == with_fallback(staff_roles_with('order.refund'))
    assert REFUND_LIST - ADMINS == with_fallback(staff_roles_with('order.refund', 'finance.payout'))
    assert DISPUTE_MANAGE - ADMINS == with_fallback(staff_roles_with('dispute.manage'))
    assert REVIEW_MODERATE - ADMINS == with_fallback(staff_roles_with('review.moderate'))
    # Explicit seeded facts relied on by the matrix.
    fin = set(StaffRole.objects.get(code='FINANCE_OFFICER').role_permissions.values_list('permission__code', flat=True))
    dm = set(StaffRole.objects.get(code='DISPUTE_MANAGER').role_permissions.values_list('permission__code', flat=True))
    assert fin == {'finance.payout', 'order.refund'}
    assert dm == {'dispute.manage', 'order.refund'}
