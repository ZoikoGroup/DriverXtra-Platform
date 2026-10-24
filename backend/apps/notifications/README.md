# Notifications

In-app notifications (with optional email) generated from existing `AuditLog` business events.

## How it works

1. Business views in other apps already call `record_audit_entry(...)`, which creates an `AuditLog` row.
2. `NotificationsConfig.ready()` connects a `post_save` receiver to `AuditLog`
   (`handlers.handle_audit_log_saved`). No business module calls this app directly.
3. For a mapped `event_type` with `status == ALLOWED`, the handler loads the audited resource
   (`resource_type` + `resource_id`), confirms the resource is in the expected state, and resolves the
   recipient from that row. Audit metadata is never trusted for the recipient.
4. One `Notification` is stored per `(source_audit_id, recipient)` (unique constraint), so re-processing
   an audit entry never duplicates notifications.
5. If email is enabled, delivery runs in `transaction.on_commit`, after the business transaction commits.
   A delivery failure marks the notification `FAILED`; it never raises into the request.

Handler errors are caught inside a savepoint and logged, so they cannot roll back or fail the business operation.

## Supported events

| Audit `event_type` | Resource | Recipient | Link |
|---|---|---|---|
| `seller.application.approved` / `.rejected` | `SellerApplication` | `application.user` | `/platform?tab=seller_onboarding` |
| `listing.approved` / `.rejected` / `.changes_requested` | `VehicleListing` or `SparePartListing` | `listing.seller` | `/platform?tab=seller_inventory` |
| `catalogue.application.approved` / `.rejected` / `.changes_requested` | `VehicleCatalogueApplication` | `application.seller` | `/platform?tab=catalogue` |
| `catalogue.photo_proposal.approved` / `.rejected` | `CataloguePhotoProposal` | `proposal.seller` | `/platform?tab=catalogue` |
| `marketplace.vehicle_enquiry.created` | `VehicleEnquiry` | `enquiry.seller` | `/platform?tab=seller_inventory` |
| `marketplace.vehicle_enquiry.updated` (new seller reply only) | `VehicleEnquiry` | `enquiry.buyer` | `/platform?tab=my_enquiries` |
| `org.member.added` | `OrganisationMembership` | `membership.user` (not when actor adds themself) | `/platform?tab=organisations` |

A seller reply is notified only when `metadata.has_reply` is true **and** the enquiry's `replied_at` was
stamped in the same operation (within 2 minutes of the audit entry) **and** the buyer has not already been
notified for that `replied_at`. Status-only or notes-only updates therefore never re-notify the buyer.

### Known limitations

- **Staff are not notified of new seller applications.** Submitting an application writes no audit event,
  and adding one would require changing `apps/onboarding`.
- Enquiries on organisation-owned listings notify the listing's `seller` only, not other org OWNER/ADMIN members.
- Identity emails (verification, password reset, staff invite) are unchanged and still sent directly by `apps/identity`.
- Denied audit entries are never notified. On PostgreSQL they are written with raw SQL and fire no signal at all.
- Links target tabs of the single-page `/platform` shell; the frontend drawer maps `?tab=` to the in-page tab.

## API (authenticated, recipient-scoped)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/notifications/` | Paginated list, newest first. `?unread=true` / `?unread=false` (other values → 400) |
| GET | `/api/v1/notifications/unread-count/` | `{"status": "success", "unread_count": n}` |
| POST | `/api/v1/notifications/<id>/read/` | Mark one read (idempotent). Another user's ID → 404 |
| POST | `/api/v1/notifications/read-all/` | Mark all of the caller's unread notifications read |

## Email configuration

Emails are **off by default**. Local development keeps the console backend; nothing is sent.

| Variable | Default | Notes |
|---|---|---|
| `NOTIFICATIONS_EMAIL_ENABLED` | `False` | `True` to email notifications in addition to the in-app record |
| `NOTIFICATIONS_EMAIL_MAX_ATTEMPTS` | `5` | Total attempts (first send + retries) per notification |
| `EMAIL_BACKEND` | console backend | Use `django.core.mail.backends.smtp.EmailBackend` for real SMTP |
| `EMAIL_HOST` / `EMAIL_PORT` | `localhost` / `25` | SMTP server |
| `EMAIL_USE_TLS` / `EMAIL_USE_SSL` | `False` / `False` | Set at most one to `True` |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | empty | Set in the environment or `backend/.env` only; never commit |
| `EMAIL_TIMEOUT` | `10` | Seconds; prevents a slow SMTP server from hanging a request |
| `DEFAULT_FROM_EMAIL` | `no-reply@driverxtra.com` | Sender address |
| `FRONTEND_URL` | `http://localhost:3000` | Used to build absolute links in emails |

To try emails safely in development, set `NOTIFICATIONS_EMAIL_ENABLED=True` and keep the console backend:
emails are printed to the `runserver` output.

Failed emails store the exception class and message in `email_error` (truncated to 500 characters).
Credentials are never logged.

### Retrying

```bash
python manage.py retry_notification_emails              # FAILED, plus PENDING older than 60s
python manage.py retry_notification_emails --dry-run    # count eligible only
python manage.py retry_notification_emails --limit 50 --min-age-seconds 120
```

Only notifications with `email_attempts < NOTIFICATIONS_EMAIL_MAX_ATTEMPTS` are retried. The command does nothing
while `NOTIFICATIONS_EMAIL_ENABLED` is `False`. Schedule it with cron or Windows Task Scheduler if needed;
no Celery or Redis is required.

## Tests

```bash
cd backend
pytest tests/test_notifications.py
```
