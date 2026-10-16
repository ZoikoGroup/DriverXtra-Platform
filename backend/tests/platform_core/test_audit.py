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
