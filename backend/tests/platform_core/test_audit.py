import uuid
import pytest
from django.db import connection, transaction, IntegrityError, InternalError, DatabaseError
from platform_core.audit.models import AuditLog
from platform_core.audit.writer import record_audit_entry, record_denied_audit_entry

@pytest.mark.django_db(transaction=True)
class TestAuditLedger:

    def test_audit_entry_creation(self):
        actor_id = uuid.uuid4()
        entry = record_audit_entry(
            event_type="user.role.granted",
            action="org:role.grant",
            resource_type="RoleBinding",
            resource_id="rb-123",
            actor_id=actor_id,
            status=AuditLog.STATUS_ALLOWED,
            correlation_id="corr-audit-001",
        )
        assert entry.id is not None
        assert entry.status == AuditLog.STATUS_ALLOWED
        assert AuditLog.objects.filter(id=entry.id).exists()

    def test_db_trigger_blocks_update(self):
        """Verifies PostgreSQL DB trigger blocks UPDATE statements on the audit ledger."""
        if connection.vendor != 'postgresql':
            pytest.skip("PostgreSQL DB trigger test.")

        entry = record_audit_entry(
            event_type="security.test",
            action="test:action",
            resource_type="TestResource",
        )

        with pytest.raises(DatabaseError) as exc_info:
            with connection.cursor() as cursor:
                cursor.execute(
                    'UPDATE "platform"."audit_log" SET action = %s WHERE id = %s;',
                    ["tampered_action", str(entry.id)]
                )
        assert "AuditLog is append-only" in str(exc_info.value)

    def test_db_trigger_blocks_delete(self):
        """Verifies PostgreSQL DB trigger blocks DELETE statements on the audit ledger."""
        if connection.vendor != 'postgresql':
            pytest.skip("PostgreSQL DB trigger test.")

        entry = record_audit_entry(
            event_type="security.test.delete",
            action="test:action",
            resource_type="TestResource",
        )

        with pytest.raises(DatabaseError) as exc_info:
            with connection.cursor() as cursor:
                cursor.execute(
                    'DELETE FROM "platform"."audit_log" WHERE id = %s;',
                    [str(entry.id)]
                )
        assert "AuditLog is append-only" in str(exc_info.value)

    def test_denied_audit_entry_survives_transaction_rollback(self):
        """Verifies denied audit entries survive business transaction rollback (written autonomously)."""
        if connection.vendor != 'postgresql':
            pytest.skip("Autonomous connection test on PostgreSQL.")

        denied_corr_id = f"corr-denied-survive-{uuid.uuid4().hex[:8]}"

        try:
            with transaction.atomic():
                # Write denied audit entry outside transaction
                record_denied_audit_entry(
                    action="payout:change",
                    resource_type="BankAccount",
                    resource_id="acc-999",
                    reason_code="CHALLENGE_FAILED",
                    correlation_id=denied_corr_id,
                )
                # Now raise exception to abort business transaction
                raise RuntimeError("Business transaction rolled back")
        except RuntimeError:
            pass

        # The denied audit entry MUST survive and exist in DB
        entry = AuditLog.objects.filter(correlation_id=denied_corr_id).first()
        assert entry is not None, "Denied audit entry was rolled back! It must survive."
        assert entry.status == AuditLog.STATUS_DENIED
        assert entry.action == "payout:change"

    def test_correlation_id_middleware(self, api_client):
        """Verifies correlation ID is set from header or generated and echoed in response."""
        custom_id = "req-corr-test-12345"
        res = api_client.get("/api/health/", HTTP_X_REQUEST_ID=custom_id)
        assert res.status_code == 200
        assert res.headers.get("X-Request-ID") == custom_id

        # Auto-generated when missing
        res_auto = api_client.get("/api/health/")
        assert res_auto.status_code == 200
        assert res_auto.headers.get("X-Request-ID") is not None
        assert len(res_auto.headers.get("X-Request-ID")) > 0

    def test_registration_audit_event(self, api_client):
        """Verifies user registration creates an audit log entry."""
        custom_corr = f"reg-audit-{uuid.uuid4().hex[:8]}"
        payload = {
            "email": f"audit_reg_{uuid.uuid4().hex[:6]}@driverxtra.com",
            "password": "SecurePassword123!",
            "first_name": "Audit",
            "last_name": "Tester",
        }
        res = api_client.post("/api/v1/auth/register/", payload, format="json", HTTP_X_REQUEST_ID=custom_corr)
        assert res.status_code == 201

        entry = AuditLog.objects.filter(
            event_type="auth.registration.success",
            correlation_id=custom_corr,
        ).first()
        assert entry is not None
        assert entry.status == AuditLog.STATUS_ALLOWED
        assert entry.resource_type == "User"
        assert entry.metadata.get("email") == payload["email"].lower()

    def test_login_success_and_failure_audit_events(self, api_client, buyer_user):
        """Verifies login failures and successes record audit log entries."""
        corr_fail = f"login-fail-{uuid.uuid4().hex[:8]}"
        res_fail = api_client.post(
            "/api/v1/auth/login/",
            {"email": buyer_user.email, "password": "WrongPassword123!"},
            format="json",
            HTTP_X_REQUEST_ID=corr_fail,
        )
        assert res_fail.status_code == 400
        denied_entry = AuditLog.objects.filter(
            action="auth:login",
            status=AuditLog.STATUS_DENIED,
            reason_code="LOGIN_FAILED",
            correlation_id=corr_fail,
        ).first()
        assert denied_entry is not None
        assert denied_entry.metadata.get("email") == buyer_user.email

        corr_success = f"login-succ-{uuid.uuid4().hex[:8]}"
        res_ok = api_client.post(
            "/api/v1/auth/login/",
            {"email": buyer_user.email, "password": "SecurePassword123!"},
            format="json",
            HTTP_X_REQUEST_ID=corr_success,
        )
        assert res_ok.status_code == 200
        allowed_entry = AuditLog.objects.filter(
            event_type="auth.login.success",
            status=AuditLog.STATUS_ALLOWED,
            correlation_id=corr_success,
        ).first()
        assert allowed_entry is not None
        assert str(allowed_entry.actor_id) == str(buyer_user.id)

    def test_role_grant_and_revoke_audit_events(self, buyer_user):
        """Verifies add_role and remove_role record audit log entries."""
        corr_grant = f"grant-{uuid.uuid4().hex[:8]}"
        buyer_user.add_role("SELLER", correlation_id=corr_grant)

        grant_entry = AuditLog.objects.filter(
            event_type="user.role.granted",
            correlation_id=corr_grant,
        ).first()
        assert grant_entry is not None
        assert grant_entry.metadata.get("role") == "SELLER"

        corr_revoke = f"revoke-{uuid.uuid4().hex[:8]}"
        buyer_user.remove_role("SELLER", correlation_id=corr_revoke)

        revoke_entry = AuditLog.objects.filter(
            event_type="user.role.revoked",
            correlation_id=corr_revoke,
        ).first()
        assert revoke_entry is not None
        assert revoke_entry.metadata.get("role") == "SELLER"

    def test_seller_application_approve_and_reject_audit(self, admin_auth_client, buyer_user):
        """Verifies seller application approval and rejection create audit records."""
        from apps.onboarding.models import SellerApplication, BusinessTypeChoices, SellerApplicationStatusChoices

        app1 = SellerApplication.objects.create(
            user=buyer_user,
            business_name="Audit Auto Corp",
            business_type=BusinessTypeChoices.INDIVIDUAL_TRADER,
            status=SellerApplicationStatusChoices.PENDING,
        )
        corr_app = f"app-approve-{uuid.uuid4().hex[:8]}"
        res = admin_auth_client.post(
            f"/api/v1/admin/seller-applications/{app1.id}/review/",
            {"action": "APPROVE", "admin_notes": "Good documents"},
            format="json",
            HTTP_X_REQUEST_ID=corr_app,
        )
        assert res.status_code == 200
        entry = AuditLog.objects.filter(
            event_type="seller.application.approved",
            resource_id=str(app1.id),
        ).first()
        assert entry is not None
        assert entry.metadata.get("business_name") == "Audit Auto Corp"

        # Create another user and application to reject
        from apps.identity.models import User
        user2 = User.objects.create_user(
            email=f"rej_{uuid.uuid4().hex[:6]}@driverxtra.com",
            password="SecurePassword123!",
            is_email_verified=True,
        )
        app2 = SellerApplication.objects.create(
            user=user2,
            business_name="Reject Motors",
            business_type=BusinessTypeChoices.DEALER,
            status=SellerApplicationStatusChoices.PENDING,
        )
        corr_rej = f"app-rej-{uuid.uuid4().hex[:8]}"
        res_rej = admin_auth_client.post(
            f"/api/v1/admin/seller-applications/{app2.id}/review/",
            {"action": "REJECT", "reason": "Missing proof of registration"},
            format="json",
            HTTP_X_REQUEST_ID=corr_rej,
        )
        assert res_rej.status_code == 200
        rej_entry = AuditLog.objects.filter(
            event_type="seller.application.rejected",
            resource_id=str(app2.id),
        ).first()
        assert rej_entry is not None
        assert rej_entry.metadata.get("reason") == "Missing proof of registration"

    def test_listing_review_audit_events(self, admin_auth_client, seller_user):
        """Verifies listing review actions (approve, request changes, reject) create audit records."""
        from apps.marketplace.models import VehicleListing, SparePartListing, ListingStatusChoices
        from apps.catalogue.models import VehicleMake, VehicleModel

        make = VehicleMake.objects.create(name=f"Make-{uuid.uuid4().hex[:4]}")
        model = VehicleModel.objects.create(make=make, name="Model-X", year_start=2020)

        vl = VehicleListing.objects.create(
            seller=seller_user,
            title="Audit Vehicle",
            make=make,
            model=model,
            year=2021,
            price=15000,
            status=ListingStatusChoices.PENDING_APPROVAL,
        )

        # Approve vehicle
        res = admin_auth_client.post(
            f"/api/v1/marketplace/admin/vehicles/{vl.id}/review/",
            {"action": "APPROVE"},
            format="json",
        )
        assert res.status_code == 200
        approve_entry = AuditLog.objects.filter(
            event_type="listing.approved",
            resource_id=str(vl.id),
            resource_type="VehicleListing",
        ).first()
        assert approve_entry is not None

        # Request changes on vehicle
        res_chg = admin_auth_client.post(
            f"/api/v1/marketplace/admin/vehicles/{vl.id}/review/",
            {"action": "REQUEST_CHANGES", "rejection_reason": "Provide better photos"},
            format="json",
        )
        assert res_chg.status_code == 200
        chg_entry = AuditLog.objects.filter(
            event_type="listing.changes_requested",
            resource_id=str(vl.id),
        ).first()
        assert chg_entry is not None

        # Reject spare part
        from apps.catalogue.models import PartCategory
        cat = PartCategory.objects.create(name="Braking", slug=f"braking-{uuid.uuid4().hex[:4]}")
        part = SparePartListing.objects.create(
            seller=seller_user,
            name="Brake Pads",
            brand="Bosch",
            mpn=f"BP-{uuid.uuid4().hex[:4]}",
            category=cat,
            price=50,
            condition="NEW",
            status=ListingStatusChoices.PENDING_APPROVAL,
        )
        res_part = admin_auth_client.post(
            f"/api/v1/marketplace/admin/parts/{part.id}/review/",
            {"action": "REJECT", "rejection_reason": "Counterfeit risk"},
            format="json",
        )
        assert res_part.status_code == 200
        part_rej_entry = AuditLog.objects.filter(
            event_type="listing.rejected",
            resource_id=str(part.id),
            resource_type="SparePartListing",
        ).first()
        assert part_rej_entry is not None
        assert part_rej_entry.metadata.get("reason") == "Counterfeit risk"

    def test_org_member_add_audit(self, seller_auth_client, test_organisation):
        """Verifies adding an org member writes an audit entry."""
        from apps.identity.models import User
        new_user = User.objects.create_user(
            email=f"member_{uuid.uuid4().hex[:6]}@driverxtra.com",
            password="SecurePassword123!",
            is_email_verified=True,
        )
        corr_mem = f"org-mem-{uuid.uuid4().hex[:8]}"
        res = seller_auth_client.post(
            f"/api/v1/organisations/{test_organisation.id}/members/",
            {"email": new_user.email, "role": "MEMBER"},
            format="json",
            HTTP_X_REQUEST_ID=corr_mem,
        )
        assert res.status_code == 201
        entry = AuditLog.objects.filter(
            event_type="org.member.added",
            operating_org_id=test_organisation.id,
            correlation_id=corr_mem,
        ).first()
        assert entry is not None
        assert entry.metadata.get("target_email") == new_user.email

    def test_password_reset_confirm_audit(self, api_client, buyer_user):
        """Verifies password reset confirmation writes an audit entry."""
        from apps.identity.services import create_and_send_password_reset
        raw_token = create_and_send_password_reset(buyer_user)

        corr_reset = f"reset-{uuid.uuid4().hex[:8]}"
        res = api_client.post(
            "/api/v1/auth/password-reset/confirm/",
            {"token": raw_token, "new_password": "NewBrandPassword999!"},
            format="json",
            HTTP_X_REQUEST_ID=corr_reset,
        )
        assert res.status_code == 200
        entry = AuditLog.objects.filter(
            event_type="auth.password_reset.success",
            correlation_id=corr_reset,
        ).first()
        assert entry is not None
        assert str(entry.actor_id) == str(buyer_user.id)

    def test_permission_denial_audit_event(self, buyer_auth_client):
        """Verifies 403 Forbidden responses record a denied audit entry."""
        corr_denied = f"denied-{uuid.uuid4().hex[:8]}"
        res = buyer_auth_client.get(
            "/api/v1/admin/seller-applications/",
            HTTP_X_REQUEST_ID=corr_denied,
        )
        assert res.status_code == 403
        entry = AuditLog.objects.filter(
            status=AuditLog.STATUS_DENIED,
            reason_code="PERMISSION_DENIED",
            correlation_id=corr_denied,
        ).first()
        assert entry is not None
        assert entry.resource_type == "APIEndpoint"
