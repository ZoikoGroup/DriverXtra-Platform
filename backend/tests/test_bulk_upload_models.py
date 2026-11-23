import uuid
import pytest
from django.db import IntegrityError
from django.utils import timezone
from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationTypeChoices
from apps.marketplace.models import (
    BulkUploadJob,
    BulkUploadRowError,
    BulkUploadTypeChoices,
    BulkUploadStatusChoices,
    BulkUploadDuplicatePolicy,
)


@pytest.mark.django_db
class TestBulkUploadJobModel:
    """Tests for BulkUploadJob model fields, choices, properties and deletion behaviour."""

    def test_job_creation_with_defaults(self, seller_user):
        """Verify that a job can be created with sensible defaults and auto-generated UUID."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='inventory_q4.csv',
            file_size_bytes=1048576,
        )

        assert isinstance(job.id, uuid.UUID)
        assert job.seller == seller_user
        assert job.organisation is None
        assert job.upload_type == BulkUploadTypeChoices.VEHICLES
        assert job.status == BulkUploadStatusChoices.PENDING
        assert job.duplicate_policy == BulkUploadDuplicatePolicy.SKIP
        assert job.filename == 'inventory_q4.csv'
        assert job.file_size_bytes == 1048576
        assert job.total_rows == 0
        assert job.processed_rows == 0
        assert job.successful_rows == 0
        assert job.failed_rows == 0
        assert job.duplicate_rows == 0
        assert job.started_at is None
        assert job.completed_at is None
        assert job.error_summary == ''
        assert job.created_at is not None
        assert job.updated_at is not None
        assert not job.is_finished
        assert job.progress_percentage == 0
        assert 'BulkUploadJob' in str(job)

    def test_valid_upload_types_and_statuses(self, seller_user):
        """Test all upload types and status transitions."""
        for upload_type in [BulkUploadTypeChoices.VEHICLES, BulkUploadTypeChoices.SPARE_PARTS]:
            job = BulkUploadJob.objects.create(
                seller=seller_user,
                upload_type=upload_type,
                filename=f'{upload_type.lower()}.csv',
            )
            assert job.upload_type == upload_type

        # Verify status transitions & is_finished property
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename='parts.csv',
            total_rows=100,
        )
        assert not job.is_finished

        job.status = BulkUploadStatusChoices.PARSING
        job.save()
        assert not job.is_finished

        job.status = BulkUploadStatusChoices.PROCESSING
        job.processed_rows = 50
        job.save()
        assert not job.is_finished
        assert job.progress_percentage == 50

        job.status = BulkUploadStatusChoices.PARTIALLY_FAILED
        job.completed_at = timezone.now()
        job.save()
        assert job.is_finished

        job.status = BulkUploadStatusChoices.COMPLETED
        job.processed_rows = 100
        job.save()
        assert job.is_finished
        assert job.progress_percentage == 100

        job.status = BulkUploadStatusChoices.FAILED
        job.save()
        assert job.is_finished

    def test_organisation_association_and_set_null_on_delete(self, seller_user, test_organisation):
        """Verify that jobs can be associated with an organisation and organisation deletion preserves job with NULL."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=test_organisation,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='apex_dealership_cars.csv',
        )

        assert job.organisation == test_organisation
        assert job in test_organisation.bulk_upload_jobs.all()

        # Delete organisation -> organisation FK should be set to NULL (SET_NULL)
        test_organisation.delete()
        job.refresh_from_db()
        assert job.organisation is None
        assert job.seller == seller_user

    def test_seller_deletion_sets_null_preserving_audit_history(self):
        """Verify that deleting a seller sets seller=NULL on the job, preserving historical auditability."""
        temp_seller = User.objects.create_user(
            email='temp_seller@driverxtra.com',
            password='TempPassword123!',
        )
        temp_seller.add_role(RoleChoices.SELLER)

        job = BulkUploadJob.objects.create(
            seller=temp_seller,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='temp_cars.csv',
        )
        job_id = job.id

        temp_seller.delete()
        job.refresh_from_db()
        assert job.seller is None
        assert BulkUploadJob.objects.filter(id=job_id).exists()


@pytest.mark.django_db
class TestBulkUploadRowErrorModel:
    """Tests for BulkUploadRowError model fields, constraints, and cascading."""

    def test_row_error_creation(self, seller_user):
        """Verify row error record creation and relationships."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='cars.csv',
            total_rows=10,
        )

        row_error = BulkUploadRowError.objects.create(
            job=job,
            row_number=3,
            field_name='price',
            error_code='INVALID_PRICE',
            error_message='Asking price must be a positive decimal greater than 0.00.',
            raw_data={'make': 'BMW', 'model': '3 Series', 'price': '-500'},
        )

        assert isinstance(row_error.id, uuid.UUID)
        assert row_error.job == job
        assert row_error.row_number == 3
        assert row_error.field_name == 'price'
        assert row_error.error_code == 'INVALID_PRICE'
        assert row_error.error_message == 'Asking price must be a positive decimal greater than 0.00.'
        assert row_error.raw_data == {'make': 'BMW', 'model': '3 Series', 'price': '-500'}
        assert not row_error.is_resolved
        assert 'RowError' in str(row_error)
        assert str(job.id) in str(row_error)

    def test_unique_constraint_on_job_and_row_number(self, seller_user):
        """Verify that duplicate row error records cannot be created for the same job and row."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename='parts.csv',
        )

        BulkUploadRowError.objects.create(
            job=job,
            row_number=5,
            field_name='mpn',
            error_code='MISSING_MPN',
            error_message='Manufacturer Part Number (MPN) is required.',
        )

        # Attempting to create another row error for row 5 on the same job must fail constraint
        with pytest.raises(IntegrityError):
            BulkUploadRowError.objects.create(
                job=job,
                row_number=5,
                field_name='price',
                error_code='INVALID_PRICE',
                error_message='Price cannot be blank.',
            )

    def test_different_jobs_can_have_same_row_number(self, seller_user):
        """Verify that different jobs can have error records for the same row number."""
        job1 = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='file1.csv',
        )
        job2 = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='file2.csv',
        )

        err1 = BulkUploadRowError.objects.create(
            job=job1,
            row_number=1,
            field_name='make',
            error_message='Invalid vehicle make.',
        )
        err2 = BulkUploadRowError.objects.create(
            job=job2,
            row_number=1,
            field_name='make',
            error_message='Invalid vehicle make.',
        )

        assert err1.id != err2.id
        assert err1.job == job1
        assert err2.job == job2

    def test_job_cascade_deletes_row_errors(self, seller_user):
        """Verify that deleting a BulkUploadJob cascades and deletes all associated row errors."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename='parts.csv',
        )

        err1 = BulkUploadRowError.objects.create(
            job=job,
            row_number=1,
            field_name='brand',
            error_message='Brand is required.',
        )
        err2 = BulkUploadRowError.objects.create(
            job=job,
            row_number=2,
            field_name='price',
            error_message='Price is required.',
        )

        err1_id = err1.id
        err2_id = err2.id

        job.delete()

        assert not BulkUploadRowError.objects.filter(id=err1_id).exists()
        assert not BulkUploadRowError.objects.filter(id=err2_id).exists()

    def test_resolution_status_toggle(self, seller_user):
        """Verify that is_resolved can be toggled when an error is resolved during retry."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename='parts.csv',
        )

        row_error = BulkUploadRowError.objects.create(
            job=job,
            row_number=4,
            field_name='category',
            error_message='Invalid category.',
        )

        assert not row_error.is_resolved
        row_error.is_resolved = True
        row_error.save()

        row_error.refresh_from_db()
        assert row_error.is_resolved
