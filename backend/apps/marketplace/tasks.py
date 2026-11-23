import logging
import uuid
from typing import Dict, Any, Optional
from celery import shared_task
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


# =============================================================================
# CELERY ASYNCHRONOUS TASKS (Phase 7.1)
# =============================================================================

@shared_task(
    bind=True,
    name='apps.marketplace.tasks.process_bulk_upload_job',
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_bulk_upload_job(self, job_id: str) -> Dict[str, Any]:
    """Asynchronously processes a bulk inventory import job under a row-level database lock.

    Guarantees:
    - Idempotency: aborts if already processing, completed, or failed.
    - Prevents concurrent worker collision via select_for_update(nowait=True).
    - Transitions job through PENDING -> PROCESSING -> COMPLETED/PARTIALLY_FAILED/FAILED.
    """
    from django.db import DatabaseError, OperationalError
    from django.utils import timezone
    from apps.marketplace.models import BulkUploadJob, BulkUploadStatusChoices
    from apps.marketplace.bulk_upload_service import BulkUploadProcessor

    logger.info("Celery worker executing process_bulk_upload_job for job_id=%s [task_id=%s]", job_id, self.request.id)

    # 1. Acquire row-level lock and check status idempotently
    try:
        with transaction.atomic():
            job = (
                BulkUploadJob.objects.select_for_update(nowait=True)
                .filter(id=job_id)
                .first()
            )
            if not job:
                logger.error("BulkUploadJob %s not found. Aborting task.", job_id)
                return {"job_id": str(job_id), "status": "NOT_FOUND"}

            # Idempotency check: only PENDING jobs may be processed
            if job.status != BulkUploadStatusChoices.PENDING:
                logger.warning(
                    "BulkUploadJob %s is in state '%s' (not PENDING). Aborting redundant execution.",
                    job_id,
                    job.status,
                )
                return {"job_id": str(job_id), "status": "ABORTED_NOT_PENDING", "current_status": job.status}

            # Transition to PROCESSING
            job.status = BulkUploadStatusChoices.PROCESSING
            job.started_at = timezone.now()
            job.save(update_fields=['status', 'started_at', 'updated_at'])

    except (DatabaseError, OperationalError) as lock_err:
        logger.warning(
            "BulkUploadJob %s is currently locked by another worker process. Aborting duplicate execution: %s",
            job_id,
            lock_err,
        )
        return {"job_id": str(job_id), "status": "CONCURRENT_LOCK_BLOCKED"}

    # 2. Execute CSV processing pipeline
    try:
        processor = BulkUploadProcessor(job)
        finished_job = processor.process()
        return {
            "job_id": str(finished_job.id),
            "status": finished_job.status,
            "total_rows": finished_job.total_rows,
            "successful_rows": finished_job.successful_rows,
            "failed_rows": finished_job.failed_rows,
            "duplicate_rows": finished_job.duplicate_rows,
        }
    except Exception as exc:
        logger.exception("Fatal unhandled exception in BulkUploadProcessor for job %s: %s", job_id, exc)
        BulkUploadJob.objects.filter(id=job_id).update(
            status=BulkUploadStatusChoices.FAILED,
            error_summary=f"Worker execution failure: {exc}",
            completed_at=timezone.now(),
        )
        raise self.retry(exc=exc)



@shared_task(
    bind=True,
    name='apps.marketplace.tasks.retry_bulk_upload_job',
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def retry_bulk_upload_job(self, job_id: str) -> Dict[str, Any]:
    """Asynchronously retries unresolved failed rows from a previous bulk import job under row lock."""
    from django.db import DatabaseError, OperationalError
    from apps.marketplace.models import BulkUploadJob, BulkUploadStatusChoices
    from apps.marketplace.bulk_upload_service import BulkUploadProcessor

    logger.info("Celery worker executing retry_bulk_upload_job for job_id=%s [task_id=%s]", job_id, self.request.id)

    try:
        with transaction.atomic():
            job = (
                BulkUploadJob.objects.select_for_update(nowait=True)
                .filter(id=job_id)
                .first()
            )
            if not job:
                logger.error("BulkUploadJob %s not found for retry. Aborting.", job_id)
                return {"job_id": str(job_id), "status": "NOT_FOUND"}

            if job.status not in (BulkUploadStatusChoices.PARTIALLY_FAILED, BulkUploadStatusChoices.FAILED):
                logger.warning("Job %s in state '%s' cannot be retried.", job_id, job.status)
                return {"job_id": str(job_id), "status": "INELIGIBLE_STATUS", "current_status": job.status}

            if not job.row_errors.filter(is_resolved=False).exists():
                logger.info("Job %s has no unresolved errors to retry.", job_id)
                return {"job_id": str(job_id), "status": "NO_UNRESOLVED_ERRORS"}

            job.status = BulkUploadStatusChoices.PROCESSING
            job.save(update_fields=['status', 'updated_at'])

    except (DatabaseError, OperationalError) as lock_err:
        logger.warning("Job %s is currently locked by another retry/worker process: %s", job_id, lock_err)
        return {"job_id": str(job_id), "status": "CONCURRENT_LOCK_BLOCKED"}

    processor = BulkUploadProcessor(job)
    finished_job = processor.retry_failed_rows()
    return {
        "job_id": str(finished_job.id),
        "status": finished_job.status,
        "successful_rows": finished_job.successful_rows,
        "failed_rows": finished_job.failed_rows,
    }


# =============================================================================
# RELIABLE TASK DISPATCH & TRANSACTION INTEGRATION
# =============================================================================

def dispatch_bulk_upload_job(job_id: str | uuid.UUID) -> bool:
    """Dispatches the bulk upload task reliably AFTER the database transaction commits.

    If Redis / Celery broker is unavailable:
    - Logs a diagnostic warning.
    - Leaves the job in PENDING status in PostgreSQL so it can be picked up once
      the worker or broker returns.
    - Strictly avoids dangerous synchronous row processing in the web thread.
    """
    str_job_id = str(job_id)

    def _on_commit_dispatch():
        try:
            async_result = process_bulk_upload_job.delay(str_job_id)
            logger.info(
                "Dispatched bulk upload job %s to Celery (task_id=%s)",
                str_job_id,
                async_result.id,
            )
        except Exception as exc:
            # Worker or Redis unavailable: keep job in PENDING status
            logger.warning(
                "Celery broker unavailable when dispatching bulk upload job %s: %s. "
                "The job safely remains PENDING in database.",
                str_job_id,
                exc,
            )

    transaction.on_commit(_on_commit_dispatch)
    return True


def dispatch_bulk_upload_retry(job_id: str | uuid.UUID) -> bool:
    """Dispatches the retry task reliably AFTER the database transaction commits."""
    str_job_id = str(job_id)

    def _on_commit_dispatch():
        try:
            async_result = retry_bulk_upload_job.delay(str_job_id)
            logger.info(
                "Dispatched retry for bulk upload job %s to Celery (task_id=%s)",
                str_job_id,
                async_result.id,
            )
        except Exception as exc:
            logger.warning(
                "Celery broker unavailable when dispatching retry for job %s: %s. "
                "The job safely remains PENDING.",
                str_job_id,
                exc,
            )

    transaction.on_commit(_on_commit_dispatch)
    return True


@shared_task(
    name='apps.marketplace.tasks.recover_pending_bulk_upload_jobs_task',
    acks_late=True,
)
def recover_pending_bulk_upload_jobs_task() -> Dict[str, Any]:
    """Periodic task executed via Celery Beat every 10 minutes (600s).

    1. Recovers jobs stuck in PROCESSING due to worker crashes or termination.
    2. Finds PENDING bulk upload jobs and re-dispatches them to Celery.
    """
    from apps.marketplace.bulk_upload_service import (
        recover_stuck_bulk_upload_jobs,
        recover_pending_bulk_upload_jobs,
    )

    logger.info("Starting recover_pending_bulk_upload_jobs_task...")
    stuck_count = recover_stuck_bulk_upload_jobs(stuck_threshold_minutes=30)
    pending_count = recover_pending_bulk_upload_jobs(max_age_minutes=120)

    logger.info(
        "Bulk upload recovery completed: %d stuck jobs recovered, %d pending jobs re-dispatched.",
        stuck_count,
        pending_count,
    )
    return {
        "status": "completed",
        "stuck_recovered": stuck_count,
        "pending_dispatched": pending_count,
    }


# =============================================================================
# HEALTH CHECKS & DIAGNOSTICS
# =============================================================================

def check_celery_redis_health() -> Dict[str, Any]:
    """Performs deep health check across Redis broker and Celery worker pool.

    Returns diagnostic metrics without throwing unhandled exceptions.
    """
    import redis
    from config.celery import app as celery_app

    broker_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
    health = {
        "broker_url": broker_url,
        "redis_connected": False,
        "redis_ping": None,
        "broker_connection_ok": False,
        "worker_available": False,
        "active_workers": [],
        "errors": [],
    }

    # 1. Direct Redis Ping Check
    try:
        r = redis.Redis.from_url(broker_url, socket_timeout=1.5, socket_connect_timeout=1.5)
        health["redis_ping"] = r.ping()
        health["redis_connected"] = True
    except Exception as exc:
        health["errors"].append(f"Redis connection failed: {exc}")

    # 2. Celery Broker Connectivity Check
    try:
        with celery_app.connection_for_read() as conn:
            conn.connect()
            health["broker_connection_ok"] = True
    except Exception as exc:
        health["errors"].append(f"Celery broker check failed: {exc}")

    # 3. Active Worker Ping Check
    try:
        replies = celery_app.control.ping(timeout=0.5)
        if replies:
            health["worker_available"] = True
            for reply in replies:
                health["active_workers"].extend(list(reply.keys()))
    except Exception as exc:
        health["errors"].append(f"Worker ping check failed: {exc}")

    return health


# =============================================================================
# CELERY ASYNCHRONOUS TASKS (Phase 7.2 - Sponsored Listings & Advertising)
# =============================================================================

import datetime


@shared_task(
    name='apps.marketplace.tasks.activate_scheduled_campaigns_task',
    acks_late=True,
)
def activate_scheduled_campaigns_task() -> Dict[str, Any]:
    """Periodic task activating SCHEDULED advertising campaigns whose start date has arrived."""
    from apps.marketplace.advertising_service import AdvertisingCampaignService
    logger.info("Starting activate_scheduled_campaigns_task...")
    activated_count = AdvertisingCampaignService.activate_scheduled_campaigns()
    logger.info("activate_scheduled_campaigns_task completed: %d campaigns activated.", activated_count)
    return {"activated_count": activated_count}


@shared_task(
    name='apps.marketplace.tasks.expire_completed_campaigns_task',
    acks_late=True,
)
def expire_completed_campaigns_task() -> Dict[str, Any]:
    """Periodic task transitioning expired ACTIVE campaigns to COMPLETED."""
    from apps.marketplace.advertising_service import AdvertisingCampaignService
    logger.info("Starting expire_completed_campaigns_task...")
    completed_count = AdvertisingCampaignService.complete_expired_campaigns()
    logger.info("expire_completed_campaigns_task completed: %d campaigns completed.", completed_count)
    return {"completed_count": completed_count}


@shared_task(
    name='apps.marketplace.tasks.recover_held_advertising_campaigns_task',
    acks_late=True,
)
def recover_held_advertising_campaigns_task() -> Dict[str, Any]:
    """Periodic task recovering PAID campaigns that were held in PAYMENT_PENDING during live gate freeze."""
    from apps.marketplace.advertising_service import AdvertisingCampaignService
    logger.info("Starting recover_held_advertising_campaigns_task...")
    recovered_count = AdvertisingCampaignService.recover_held_paid_campaigns()
    logger.info("recover_held_advertising_campaigns_task completed: %d campaigns recovered.", recovered_count)
    return {"recovered_count": recovered_count}


@shared_task(
    name='apps.marketplace.tasks.aggregate_campaign_daily_metrics_task',
    acks_late=True,
)
def aggregate_campaign_daily_metrics_task() -> Dict[str, Any]:
    """Aggregates impression and click counts into CampaignDailyMetric records."""
    from django.utils import timezone
    from django.db.models import Count
    from apps.marketplace.models import AdvertisingCampaign, CampaignImpression, CampaignClick, CampaignDailyMetric

    today = timezone.localdate()
    yesterday = today - datetime.timedelta(days=1)
    target_dates = [yesterday, today]

    logger.info("Starting aggregate_campaign_daily_metrics_task for dates %s...", target_dates)
    aggregated_count = 0

    for d in target_dates:
        impressions = CampaignImpression.objects.filter(
            created_at__date=d
        ).values('campaign_id').annotate(count=Count('id'))
        imp_map = {item['campaign_id']: item['count'] for item in impressions}

        clicks = CampaignClick.objects.filter(
            created_at__date=d
        ).values('campaign_id').annotate(count=Count('id'))
        click_map = {item['campaign_id']: item['count'] for item in clicks}

        all_campaign_ids = set(imp_map.keys()) | set(click_map.keys())

        for c_id in all_campaign_ids:
            c = AdvertisingCampaign.objects.filter(id=c_id).first()
            if not c:
                continue

            imp_count = imp_map.get(c_id, 0)
            clk_count = click_map.get(c_id, 0)
            daily_spend = c.daily_rate_minor if c.status == 'ACTIVE' else 0

            CampaignDailyMetric.objects.update_or_create(
                campaign=c,
                date=d,
                defaults={
                    "impressions": imp_count,
                    "clicks": clk_count,
                    "spend_minor": daily_spend,
                },
            )
            aggregated_count += 1

    return {"status": "completed", "aggregated_count": aggregated_count}
