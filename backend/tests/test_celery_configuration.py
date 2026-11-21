import uuid
from unittest.mock import patch
import pytest
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from config.celery import app as celery_app
from apps.marketplace.models import (
    BulkUploadJob,
    BulkUploadTypeChoices,
    BulkUploadStatusChoices,
)
from apps.marketplace.tasks import (
    process_bulk_upload_job,
    retry_bulk_upload_job,
    dispatch_bulk_upload_job,
    dispatch_bulk_upload_retry,
    check_celery_redis_health,
)


@pytest.mark.django_db
class TestCeleryConfigurationAndTasks:
    """Verifies Celery 5.7+ configuration, task registration, transaction.on_commit

    dispatch, and worker-unavailable safety.
    """

    def test_celery_app_and_settings(self):
        """Verify Celery app initialization, namespace loading, and security settings."""
        assert celery_app.main == 'driverxtra'

        # Verify JSON-only task serialization
        assert celery_app.conf.task_serializer == 'json'
        assert celery_app.conf.result_serializer == 'json'
        assert celery_app.conf.accept_content == ['json']

        # Verify worker reliability & acknowledgement behavior
        assert celery_app.conf.task_acks_late is True
        assert celery_app.conf.task_reject_on_worker_lost is True
        assert celery_app.conf.worker_prefetch_multiplier == 1

        # Verify environment variable broker configuration
        expected_broker = getattr(settings, 'CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
        assert celery_app.conf.broker_url == expected_broker

    def test_tasks_registered(self):
        """Verify bulk upload tasks are properly registered with Celery."""
        registered_tasks = celery_app.tasks.keys()
        assert 'apps.marketplace.tasks.process_bulk_upload_job' in registered_tasks
        assert 'apps.marketplace.tasks.retry_bulk_upload_job' in registered_tasks

    def test_task_direct_execution(self, seller_user):
        """Verify tasks can be executed directly via .apply() returning structured result."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='test_cars.csv',
        )

        result = process_bulk_upload_job.apply(args=[str(job.id)])
        assert result.successful()
        data = result.result
        assert data['job_id'] == str(job.id)
        assert data['status'] in ('COMPLETED', 'PARTIALLY_FAILED', 'FAILED')

        retry_result = retry_bulk_upload_job.apply(args=[str(job.id)])
        assert retry_result.successful()
        retry_data = retry_result.result
        assert retry_data['job_id'] == str(job.id)
        assert retry_data['status'] in ('RETRY_QUEUED', 'NO_UNRESOLVED_ERRORS')

    def test_dispatch_after_database_commit(self, seller_user, django_capture_on_commit_callbacks):
        """Verify task dispatch is deferred until database transaction successfully commits."""
        dispatched_jobs = []

        def mock_delay(job_id_str):
            dispatched_jobs.append(job_id_str)
            class MockAsyncResult:
                id = str(uuid.uuid4())
            return MockAsyncResult()

        with patch.object(process_bulk_upload_job, 'delay', side_effect=mock_delay):
            with django_capture_on_commit_callbacks(execute=True):
                job = BulkUploadJob.objects.create(
                    seller=seller_user,
                    upload_type=BulkUploadTypeChoices.SPARE_PARTS,
                    filename='parts.csv',
                )
                dispatch_bulk_upload_job(job.id)

            # After commit callbacks are executed, on_commit hook dispatched task
            assert len(dispatched_jobs) == 1
            assert dispatched_jobs[0] == str(job.id)

    def test_dispatch_cancelled_on_transaction_rollback(self, seller_user):
        """Verify task dispatch is cancelled if transaction rolls back."""
        dispatched_jobs = []

        with patch.object(process_bulk_upload_job, 'delay', side_effect=lambda j: dispatched_jobs.append(j)):
            try:
                with transaction.atomic():
                    job = BulkUploadJob.objects.create(
                        seller=seller_user,
                        upload_type=BulkUploadTypeChoices.VEHICLES,
                        filename='rollback.csv',
                    )
                    dispatch_bulk_upload_job(job.id)
                    raise RuntimeError("Simulated transaction failure")
            except RuntimeError:
                pass

            # Task must NOT be dispatched on rollback
            assert len(dispatched_jobs) == 0

    def test_worker_unavailable_leaves_job_pending_without_crashing(self, seller_user):
        """Verify that when Celery broker/worker is unavailable, the job remains PENDING

        and NO synchronous execution occurs.
        """
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='unreachable_broker.csv',
            status=BulkUploadStatusChoices.PENDING,
        )

        # Simulate broker connection failure (e.g. redis offline)
        with patch.object(process_bulk_upload_job, 'delay', side_effect=ConnectionError("Cannot connect to Redis at 127.0.0.1:6379")):
            # Dispatch must succeed without raising exception to API caller
            success = dispatch_bulk_upload_job(job.id)
            assert success is True

            job.refresh_from_db()
            # Job must remain in safe PENDING state
            assert job.status == BulkUploadStatusChoices.PENDING
            # Counters must remain 0
            assert job.processed_rows == 0
            assert job.successful_rows == 0

    def test_retry_dispatch_after_commit(self, seller_user, django_capture_on_commit_callbacks):
        """Verify retry dispatch operates reliably after transaction commit."""
        dispatched_retries = []

        def mock_retry_delay(job_id_str):
            dispatched_retries.append(job_id_str)
            class MockAsyncResult:
                id = str(uuid.uuid4())
            return MockAsyncResult()

        with patch.object(retry_bulk_upload_job, 'delay', side_effect=mock_retry_delay):
            with django_capture_on_commit_callbacks(execute=True):
                job = BulkUploadJob.objects.create(
                    seller=seller_user,
                    upload_type=BulkUploadTypeChoices.SPARE_PARTS,
                    filename='parts.csv',
                    status=BulkUploadStatusChoices.PARTIALLY_FAILED,
                )
                dispatch_bulk_upload_retry(job.id)

            assert len(dispatched_retries) == 1
            assert dispatched_retries[0] == str(job.id)

    def test_health_check_structure(self):
        """Verify health check function returns all diagnostic fields without crashing."""
        health = check_celery_redis_health()

        assert 'broker_url' in health
        assert 'redis_connected' in health
        assert 'broker_connection_ok' in health
        assert 'worker_available' in health
        assert 'active_workers' in health
        assert 'errors' in health
        assert isinstance(health['errors'], list)

    def test_recover_pending_bulk_upload_jobs_beat_and_task(self, seller_user, test_organisation):
        """Verify bulk upload recovery task registration, Celery Beat configuration, and execution."""
        from apps.marketplace.tasks import recover_pending_bulk_upload_jobs_task
        from config.celery import app as celery_app
        from django.conf import settings

        # 1. Registered task
        assert 'apps.marketplace.tasks.recover_pending_bulk_upload_jobs_task' in celery_app.tasks.keys()

        # 2. Celery Beat schedule
        beat_schedule = getattr(settings, 'CELERY_BEAT_SCHEDULE', {})
        assert 'recover-pending-bulk-upload-jobs' in beat_schedule
        entry = beat_schedule['recover-pending-bulk-upload-jobs']
        assert entry['task'] == 'apps.marketplace.tasks.recover_pending_bulk_upload_jobs_task'
        assert entry['schedule'] == 600.0

        # 3. Create a stuck PROCESSING job and a PENDING job
        stuck_job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=test_organisation,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='stuck.csv',
            status=BulkUploadStatusChoices.PROCESSING,
            started_at=timezone.now() - timezone.timedelta(minutes=45),
            successful_rows=1,
        )
        pending_job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=test_organisation,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='pending.csv',
            status=BulkUploadStatusChoices.PENDING,
        )

        with patch('apps.marketplace.tasks.dispatch_bulk_upload_job') as mock_dispatch:
            result = recover_pending_bulk_upload_jobs_task()

        assert result['status'] == 'completed'
        assert result['stuck_recovered'] >= 1
        assert result['pending_dispatched'] >= 1

        stuck_job.refresh_from_db()
        assert stuck_job.status == BulkUploadStatusChoices.PARTIALLY_FAILED
        assert "interrupted" in stuck_job.error_summary
