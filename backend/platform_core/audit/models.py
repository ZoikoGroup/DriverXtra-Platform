import uuid

from django.db import models


class AuditLog(models.Model):
    STATUS_ALLOWED = "ALLOWED"
    STATUS_DENIED = "DENIED"

    STATUS_CHOICES = [
        (STATUS_ALLOWED, "Allowed"),
        (STATUS_DENIED, "Denied"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    event_type = models.CharField(max_length=150, db_index=True)
    action = models.CharField(max_length=150, db_index=True)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=255, blank=True, default="")
    actor_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor_kind = models.CharField(max_length=50, blank=True, default="USER")
    operating_org_id = models.UUIDField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, db_index=True)
    correlation_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    reason_code = models.CharField(max_length=100, blank=True, default="")
    metadata = models.JSONField(blank=True, default=dict)

    class Meta:
        db_table = '"platform"."audit_log"'
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["resource_type", "resource_id"]),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.status})"