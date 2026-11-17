import pytest
from rest_framework import status
from django.utils import timezone
from apps.identity.models import (
    User,
    UserRole,
    RoleChoices,
    StaffRole,
    StaffProfile,
    AccountStatusChoices,
    ApprovalRequest,
    ApprovalStatusChoices,
)


@pytest.fixture
def base_staff_factory(db):
    def _create_staff(email, staff_role_code, is_admin=False):
        user = User.objects.create(
            email=email,
            first_name=staff_role_code.replace('_', ' ').title(),
            last_name="Officer",
            is_active=True,
            is_staff=True,
            is_email_verified=True,
            status=AccountStatusChoices.ACTIVE,
        )
        user.set_password("SecurePass123!")
        user.save()

        if is_admin:
            user.add_role(RoleChoices.ADMIN)
        else:
            user.add_role(RoleChoices.STAFF)

        if staff_role_code:
            staff_role = StaffRole.objects.get(code=staff_role_code)
            StaffProfile.objects.create(
                user=user,
                staff_role=staff_role,
                department="Operations",
                totp_enabled=False,
            )
        return user
    return _create_staff


@pytest.mark.django_db
class TestStaffRoleDashboardContract:
    """Verifies profile data contract and API access boundaries for each staff role."""

    def test_support_agent_contract_and_boundaries(self, api_client, base_staff_factory):
        agent = base_staff_factory("support.agent@example.com", "SUPPORT_AGENT")
        api_client.force_authenticate(user=agent)

        # 1. Profile Contract
        resp = api_client.get("/api/v1/users/me/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["active_role"] == "STAFF"
        assert data["staff_role"]["code"] == "SUPPORT_AGENT"
        assert data["permissions"] == ['support.ticket.manage']  # Only granted customer support ticket management

        # 2. Blocked from listing moderation
        resp_veh = api_client.get("/api/v1/marketplace/admin/vehicles/")
        assert resp_veh.status_code == status.HTTP_403_FORBIDDEN

        # 3. Blocked from seller compliance queue
        resp_sell = api_client.get("/api/v1/admin/seller-applications/")
        assert resp_sell.status_code == status.HTTP_403_FORBIDDEN

        # 4. Blocked from dispute adjudication
        resp_disp = api_client.get("/api/v1/marketplace/admin/disputes/")
        assert resp_disp.status_code == status.HTTP_403_FORBIDDEN

        # 5. Blocked from staff administration
        resp_staff = api_client.get("/api/v1/admin/staff/")
        assert resp_staff.status_code == status.HTTP_403_FORBIDDEN

    def test_verification_officer_contract_and_boundaries(self, api_client, base_staff_factory):
        officer = base_staff_factory("verif.officer@example.com", "VERIFICATION_OFFICER")
        api_client.force_authenticate(user=officer)

        # 1. Profile Contract
        resp = api_client.get("/api/v1/users/me/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["staff_role"]["code"] == "VERIFICATION_OFFICER"
        assert "seller.verify" in data["permissions"]
        assert "listing.review" in data["permissions"]

        # 2. Permitted: Listing moderation queues
        resp_veh = api_client.get("/api/v1/marketplace/admin/vehicles/")
        assert resp_veh.status_code == status.HTTP_200_OK

        resp_parts = api_client.get("/api/v1/marketplace/admin/parts/")
        assert resp_parts.status_code == status.HTTP_200_OK

        # 3. Permitted: Seller applications compliance queue
        resp_sell = api_client.get("/api/v1/admin/seller-applications/")
        assert resp_sell.status_code == status.HTTP_200_OK

        # 4. Blocked: Catalogue master record review (lacks catalogue.manage)
        import uuid
        resp_cat = api_client.post(f"/api/v1/catalogue/applications/{uuid.uuid4()}/review/", {"decision": "APPROVE"})
        assert resp_cat.status_code == status.HTTP_403_FORBIDDEN

        # 5. Blocked: Dispute adjudication
        resp_disp = api_client.get("/api/v1/marketplace/admin/disputes/")
        assert resp_disp.status_code == status.HTTP_403_FORBIDDEN

    def test_dispute_manager_contract_and_boundaries(self, api_client, base_staff_factory):
        manager = base_staff_factory("dispute.mgr@example.com", "DISPUTE_MANAGER")
        api_client.force_authenticate(user=manager)

        # 1. Profile Contract
        resp = api_client.get("/api/v1/users/me/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["staff_role"]["code"] == "DISPUTE_MANAGER"
        assert "dispute.manage" in data["permissions"]
        assert "order.refund" in data["permissions"]

        # 2. Permitted: Disputes queue
        resp_disp = api_client.get("/api/v1/marketplace/admin/disputes/")
        assert resp_disp.status_code == status.HTTP_200_OK

        # 3. Permitted: Returns and refunds list
        resp_ref = api_client.get("/api/v1/marketplace/admin/refunds/")
        assert resp_ref.status_code == status.HTTP_200_OK

        # 4. Blocked: Listing moderation
        resp_veh = api_client.get("/api/v1/marketplace/admin/vehicles/")
        assert resp_veh.status_code == status.HTTP_403_FORBIDDEN

        # 5. Blocked: Seller verification
        resp_sell = api_client.get("/api/v1/admin/seller-applications/")
        assert resp_sell.status_code == status.HTTP_403_FORBIDDEN

    def test_finance_officer_contract_and_boundaries(self, api_client, base_staff_factory):
        officer = base_staff_factory("finance.off@example.com", "FINANCE_OFFICER")
        api_client.force_authenticate(user=officer)

        # 1. Profile Contract
        resp = api_client.get("/api/v1/users/me/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["staff_role"]["code"] == "FINANCE_OFFICER"
        assert "finance.payout" in data["permissions"]
        assert "order.refund" in data["permissions"]

        # 2. Permitted: Approvals list
        resp_appr = api_client.get("/api/v1/admin/approvals/")
        assert resp_appr.status_code == status.HTTP_200_OK

        # 3. Permitted: Refunds list
        resp_ref = api_client.get("/api/v1/marketplace/admin/refunds/")
        assert resp_ref.status_code == status.HTTP_200_OK

        # 4. Blocked: Dispute adjudication
        resp_disp = api_client.get("/api/v1/marketplace/admin/disputes/")
        assert resp_disp.status_code == status.HTTP_403_FORBIDDEN

        # 5. Blocked: Listing moderation
        resp_veh = api_client.get("/api/v1/marketplace/admin/vehicles/")
        assert resp_veh.status_code == status.HTTP_403_FORBIDDEN

    def test_platform_admin_unrestricted_access(self, api_client, base_staff_factory):
        admin = base_staff_factory("admin.chief@example.com", "VERIFICATION_OFFICER", is_admin=True)
        api_client.force_authenticate(user=admin)

        # 1. Profile Contract
        resp = api_client.get("/api/v1/users/me/")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["active_role"] == "ADMIN"
        assert len(data["permissions"]) >= 7  # Holds all platform permissions

        # 2. Permitted across all operational queues
        assert api_client.get("/api/v1/marketplace/admin/vehicles/").status_code == status.HTTP_200_OK
        assert api_client.get("/api/v1/admin/seller-applications/").status_code == status.HTTP_200_OK
        assert api_client.get("/api/v1/marketplace/admin/disputes/").status_code == status.HTTP_200_OK
        assert api_client.get("/api/v1/admin/approvals/").status_code == status.HTTP_200_OK
        assert api_client.get("/api/v1/admin/staff/").status_code == status.HTTP_200_OK

    def test_maker_checker_self_review_prevention(self, api_client, base_staff_factory):
        maker = base_staff_factory("finance.maker@example.com", "FINANCE_OFFICER")
        checker = base_staff_factory("finance.checker@example.com", "FINANCE_OFFICER")

        # Create approval request by maker
        req = ApprovalRequest.objects.create(
            requester=maker,
            action_type="HIGH_VALUE_REFUND",
            target_type="Refund",
            target_id="REF-TEST-001",
            amount=1500.00,
            currency="GBP",
            reason="Customer high value cancellation",
            status=ApprovalStatusChoices.PENDING,
        )

        # Maker attempts to self-approve -> Forbidden by maker-checker policy
        api_client.force_authenticate(user=maker)
        resp_self = api_client.post(f"/api/v1/admin/approvals/{req.id}/approve/", {
            "notes": "Self approval attempt",
        })
        assert resp_self.status_code == status.HTTP_400_BAD_REQUEST

        # Independent checker approves -> Success
        api_client.force_authenticate(user=checker)
        resp_checker = api_client.post(f"/api/v1/admin/approvals/{req.id}/approve/", {
            "notes": "Verified and approved by independent checker",
        })
        assert resp_checker.status_code == status.HTTP_200_OK
        req.refresh_from_db()
        assert req.status == ApprovalStatusChoices.APPROVED
        assert req.approver == checker
