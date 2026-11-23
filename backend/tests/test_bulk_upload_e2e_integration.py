import csv
import io
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    PartCategory,
    FuelTypeChoices,
    TransmissionChoices,
)
from apps.identity.models import User, RoleChoices
from apps.marketplace.models import (
    BulkUploadJob,
    BulkUploadRowError,
    BulkUploadTypeChoices,
    BulkUploadStatusChoices,
    BulkUploadDuplicatePolicy,
    VehicleListing,
    SparePartListing,
    ListingStatusChoices,
    VehicleListingAvailabilityChoices,
    StockMovement,
    StockMovementReasonChoices,
)
from apps.marketplace.tasks import (
    process_bulk_upload_job,
    retry_bulk_upload_job,
    dispatch_bulk_upload_job,
    check_celery_redis_health,
)
from apps.marketplace.bulk_upload_service import (
    BulkUploadProcessor,
    sanitize_csv_formula,
    recover_pending_bulk_upload_jobs,
)
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationRoleChoices,
    OrganisationTypeChoices,
)


@pytest.fixture
def vehicle_catalogue(db):
    """Creates catalogue makes and models required for 10-record vehicle E2E tests."""
    ford = VehicleMake.objects.create(name='Ford', is_active=True)
    bmw = VehicleMake.objects.create(name='BMW', is_active=True)
    toyota = VehicleMake.objects.create(name='Toyota', is_active=True)
    vw = VehicleMake.objects.create(name='Volkswagen', is_active=True)

    transit = VehicleModel.objects.create(make=ford, name='Transit', year_start=2014, is_active=True)
    focus = VehicleModel.objects.create(make=ford, name='Focus', year_start=2011, is_active=True)
    series3 = VehicleModel.objects.create(make=bmw, name='3 Series', year_start=2012, is_active=True)
    hilux = VehicleModel.objects.create(make=toyota, name='Hilux', year_start=2015, is_active=True)
    golf = VehicleModel.objects.create(make=vw, name='Golf', year_start=2013, is_active=True)

    return {
        'ford': ford,
        'bmw': bmw,
        'toyota': toyota,
        'vw': vw,
        'transit': transit,
        'focus': focus,
        'series3': series3,
        'hilux': hilux,
        'golf': golf,
    }


@pytest.fixture
def spare_part_catalogue(db):
    """Creates taxonomy categories required for 10-record spare parts E2E tests."""
    brakes = PartCategory.objects.create(name='Braking Systems', slug='braking-systems', is_active=True)
    filters = PartCategory.objects.create(name='Filters', slug='filters', is_active=True)
    lighting = PartCategory.objects.create(name='Lighting & Signaling', slug='lighting', is_active=True)
    suspension = PartCategory.objects.create(name='Suspension & Steering', slug='suspension', is_active=True)
    ignition = PartCategory.objects.create(name='Ignition Parts', slug='ignition', is_active=True)

    return {
        'brakes': brakes,
        'filters': filters,
        'lighting': lighting,
        'suspension': suspension,
        'ignition': ignition,
    }


# =============================================================================
# 1. MIGRATION VERIFICATION
# =============================================================================

@pytest.mark.django_db
class TestBulkUploadMigrationVerification:
    """Verifies migration 0022 integrity, constraints, indexes, and reversibility."""

    def test_migration_0022_metadata_and_dependencies(self):
        """Verify migration dependencies, operations, models, and constraints."""
        import importlib
        migration_0022 = importlib.import_module(
            'apps.marketplace.migrations.0022_bulkuploadjob_bulkuploadrowerror_and_more'
        )
        migration = migration_0022.Migration('0022_bulkuploadjob_bulkuploadrowerror_and_more', 'marketplace')

        expected_dependencies = {
            ('marketplace', '0021_vehicle_purchase_documents'),
            ('organisations', '0003_alter_organisation_jurisdiction_and_more'),
        }
        actual_deps = {dep for dep in migration.dependencies if dep[0] in ('marketplace', 'organisations')}
        assert expected_dependencies.issubset(actual_deps)

        operation_types = [type(op).__name__ for op in migration.operations]
        assert 'CreateModel' in operation_types
        assert 'AddIndex' in operation_types
        assert 'AddConstraint' in operation_types

    def test_database_table_indexes_and_constraints(self):
        """Verify created models BulkUploadJob and BulkUploadRowError exist with unique constraints."""
        assert BulkUploadJob._meta.db_table == 'marketplace_bulkuploadjob'
        assert BulkUploadRowError._meta.db_table == 'marketplace_bulkuploadrowerror'

        # Check unique constraint on (job, row_number)
        constraint_names = [c.name for c in BulkUploadRowError._meta.constraints]
        assert 'unique_bulk_upload_job_row_error' in constraint_names

        # Check index configurations
        job_indexes = [list(idx.fields) for idx in BulkUploadJob._meta.indexes]
        assert ['seller', 'status'] in job_indexes
        assert ['organisation', 'status'] in job_indexes
        assert ['status', 'created_at'] in job_indexes
        assert ['upload_type', 'status'] in job_indexes

        error_indexes = [list(idx.fields) for idx in BulkUploadRowError._meta.indexes]
        assert ['job', 'row_number'] in error_indexes
        assert ['job', 'is_resolved'] in error_indexes

    def test_migration_reversibility_plan(self):
        """Verify migration reversibility: plan backwards to 0021 and forwards to 0022."""
        executor = MigrationExecutor(connection)

        # Test backward plan to 0021
        backward_plan = executor.migration_plan([('marketplace', '0021_vehicle_purchase_documents')])
        assert len(backward_plan) >= 1
        # The backward plan unapplies migrations down to 0021 (including 0022)
        unapply_names = [target.name for target, is_backward in backward_plan if is_backward]
        assert '0022_bulkuploadjob_bulkuploadrowerror_and_more' in unapply_names
        assert backward_plan[0][1] is True  # True indicates backwards unapply

        # Test forward plan to 0022
        forward_plan = executor.migration_plan([('marketplace', '0022_bulkuploadjob_bulkuploadrowerror_and_more')])
        # If already at 0022 in test db, forward plan is empty; otherwise it applies 0022
        assert isinstance(forward_plan, list)


# =============================================================================
# 2. REAL BACKEND INTEGRATION & CELERY VERIFICATION
# =============================================================================

@pytest.mark.django_db
class TestRealBackendAndCeleryTaskLifecycle:
    """Verifies Celery worker discovery, task registration, and health check diagnostics."""

    def test_celery_task_registration_and_worker_loader(self):
        """Verify Celery registers process_bulk_upload_job and retry_bulk_upload_job."""
        from config.celery import app as celery_app
        celery_app.loader.import_default_modules()
        tasks = celery_app.tasks.keys()

        assert 'apps.marketplace.tasks.process_bulk_upload_job' in tasks
        assert 'apps.marketplace.tasks.retry_bulk_upload_job' in tasks

    def test_health_check_diagnostics_without_unhandled_crash(self):
        """Verify check_celery_redis_health returns comprehensive metrics gracefully."""
        health = check_celery_redis_health()
        assert 'broker_url' in health
        assert 'redis_connected' in health
        assert 'broker_connection_ok' in health
        assert 'worker_available' in health
        assert isinstance(health['errors'], list)

    def test_transaction_on_commit_dispatch_deferred(self, seller_user, django_capture_on_commit_callbacks):
        """Verify task dispatch hooks into transaction.on_commit."""
        dispatched = []

        def mock_delay(job_id_str):
            dispatched.append(job_id_str)
            class MockAsync:
                id = str(uuid.uuid4())
            return MockAsync()

        with patch.object(process_bulk_upload_job, 'delay', side_effect=mock_delay):
            with django_capture_on_commit_callbacks(execute=True):
                job = BulkUploadJob.objects.create(
                    seller=seller_user,
                    upload_type=BulkUploadTypeChoices.VEHICLES,
                    filename='cars.csv',
                )
                dispatch_bulk_upload_job(job.id)

            assert len(dispatched) == 1
            assert dispatched[0] == str(job.id)


# =============================================================================
# 3. VEHICLE IMPORT END-TO-END TEST (10 RECORDS)
# =============================================================================

@pytest.mark.django_db
class TestVehicleImportEndToEnd10Records:
    """Full end-to-end integration test of a 10-record vehicle bulk import."""

    def test_vehicle_import_10_records_complete_lifecycle(
        self, seller_auth_client, seller_user, vehicle_catalogue
    ):
        """
        Processes a realistic 10-record Vehicle CSV:
        - Rows 1-5: Valid vehicles across Ford, BMW, Toyota, VW
        - Row 6: Duplicate VIN of Row 1 (intra-file duplicate)
        - Row 7: Invalid Year (2055)
        - Row 8: Invalid Asking Price (-500)
        - Row 9: Missing mandatory Make
        - Row 10: Unknown Model ('PhantomX')
        """
        csv_rows = [
            "title,make,model,variant,year,vin,registration_number,mileage,fuel_type,transmission,price,currency,condition,description",
            "Ford Transit 350,Ford,Transit,Leader,2022,1FTNE3Y86NKA12345,AB22CDE,32000,DIESEL,MANUAL,18500.00,GBP,VERY_GOOD,Well maintained fleet van",
            "BMW 3 Series 320d,BMW,3 Series,M Sport,2021,WBA3A5C58MF098765,BC21FGH,28000,DIESEL,AUTOMATIC,24000.00,GBP,EXCELLENT,Full service history",
            "Toyota Hilux Invincible,Toyota,Hilux,Invincible,2023,MROER32G900112233,CD23IJK,15000,DIESEL,AUTOMATIC,31000.00,GBP,EXCELLENT,4x4 commercial pickup",
            "Volkswagen Golf 2.0 TDI,Volkswagen,Golf,Life,2020,WVWZZZAUZLW445566,DE20LMN,45000,DIESEL,MANUAL,14500.00,GBP,GOOD,Reliable hatchback",
            "Ford Focus 1.0 EcoBoost,Ford,Focus,Titanium,2021,WF0KXXGCRK8899001,EF21OPQ,21000,PETROL,MANUAL,13200.00,GBP,VERY_GOOD,Economical family car",
            "Duplicate Transit,Ford,Transit,Leader,2022,1FTNE3Y86NKA12345,FG22RST,35000,DIESEL,MANUAL,18000.00,GBP,GOOD,Duplicate VIN of row 1",
            "Future Car,Ford,Focus,,2055,WF0KXXGCRK9999999,GH55UVW,100,PETROL,AUTOMATIC,20000.00,GBP,NEW,Year in far future",
            "Negative Price Car,BMW,3 Series,,2021,WBA3A5C58MF111111,HI21XYZ,30000,DIESEL,AUTOMATIC,-500.00,GBP,GOOD,Negative price",
            "Missing Make Car,,Golf,,2020,WVWZZZAUZLW222222,IJ20ABC,40000,PETROL,MANUAL,12000.00,GBP,GOOD,Missing manufacturer make",
            "Invalid Model Car,Ford,PhantomX,,2021,WF0KXXGCRK3333333,JK21DEF,25000,PETROL,MANUAL,15000.00,GBP,GOOD,Model not in catalogue",
        ]
        csv_content = "\n".join(csv_rows).encode('utf-8')
        uploaded_file = SimpleUploadedFile("vehicles_batch_10.csv", csv_content, content_type="text/csv")

        # 1. Upload via REST API
        url = '/api/v1/marketplace/bulk-upload/'
        response = seller_auth_client.post(
            url,
            {
                'file': uploaded_file,
                'upload_type': 'VEHICLES',
                'duplicate_policy': 'SKIP',
            },
            format='multipart',
        )
        assert response.status_code == 201, response.data
        job_id = response.data['id']

        # 2. Process via Celery Task
        task_result = process_bulk_upload_job.apply(args=[job_id])
        assert task_result.successful()
        result_payload = task_result.result

        # 3. Verify Job Counters and Final Status
        job = BulkUploadJob.objects.get(id=job_id)
        assert job.status == BulkUploadStatusChoices.PARTIALLY_FAILED
        assert job.total_rows == 10
        assert job.processed_rows == 10
        assert job.successful_rows == 5
        assert job.failed_rows == 4
        assert job.duplicate_rows == 1

        # 4. Verify 5 VehicleListing records created
        listings = VehicleListing.objects.filter(seller=seller_user)
        assert listings.count() == 5
        for listing in listings:
            assert listing.status == ListingStatusChoices.PENDING_APPROVAL
            assert listing.is_active is True
            assert listing.availability_status == VehicleListingAvailabilityChoices.AVAILABLE
            assert listing.submitted_at is not None

        # Verify specific listing data
        transit_listing = listings.get(vin='1FTNE3Y86NKA12345')
        assert transit_listing.price == Decimal('18500.00')
        assert transit_listing.year == 2022
        assert transit_listing.mileage == 32000
        assert transit_listing.fuel_type == FuelTypeChoices.DIESEL
        assert transit_listing.transmission == TransmissionChoices.MANUAL

        bmw_listing = listings.get(vin='WBA3A5C58MF098765')
        assert bmw_listing.price == Decimal('24000.00')
        assert bmw_listing.transmission == TransmissionChoices.AUTOMATIC

        # 5. Verify Row Errors
        errors = BulkUploadRowError.objects.filter(job=job).order_by('row_number')
        assert errors.count() == 4
        error_map = {e.row_number: e for e in errors}

        # Row 7: Invalid Year
        assert 7 in error_map
        assert error_map[7].field_name == 'year'
        assert error_map[7].error_code == 'INVALID_YEAR'
        assert error_map[7].is_resolved is False

        # Row 8: Invalid Price
        assert 8 in error_map
        assert error_map[8].field_name == 'price'
        assert error_map[8].error_code == 'INVALID_PRICE'

        # Row 9: Missing Make
        assert 9 in error_map
        assert error_map[9].field_name == 'make'
        assert error_map[9].error_code == 'MISSING_MAKE'

        # Row 10: Invalid Model
        assert 10 in error_map
        assert error_map[10].field_name == 'model'
        assert error_map[10].error_code == 'INVALID_MODEL'


# =============================================================================
# 4. SPARE PARTS IMPORT END-TO-END TEST (10 RECORDS)
# =============================================================================

@pytest.mark.django_db
class TestSparePartsImportEndToEnd10Records:
    """Full end-to-end integration test of a 10-record spare parts bulk import."""

    def test_spare_parts_import_10_records_complete_lifecycle(
        self, seller_auth_client, seller_user, spare_part_catalogue
    ):
        """
        Processes a realistic 10-record Spare Parts CSV:
        - Rows 1-5: Valid spare parts across Brakes, Filters, Lighting, Suspension, Ignition
        - Row 6: Duplicate MPN + Brand of Row 1 (intra-file duplicate)
        - Row 7: Compare-at price lower than retail price
        - Row 8: Invalid GST rate (15.00%)
        - Row 9: Negative stock quantity (-10)
        - Row 10: Missing MPN
        """
        csv_rows = [
            "name,brand,mpn,category,price,compare_at_price,stock_quantity,hsn_code,gst_rate,condition,description",
            "Front Ceramic Brake Pads,TRW,BP-TRW-9011,Braking Systems,45.00,55.00,20,87083000,18.00,NEW,Premium low-dust ceramic pads",
            "High Efficiency Oil Filter,Bosch,OF-BOSCH-3300,Filters,12.50,15.00,50,84212300,18.00,NEW,Spin-on oil filter with synthetic media",
            "LED Headlight Assembly,Valeo,HL-VALEO-7721,Lighting & Signaling,180.00,210.00,8,85122010,28.00,NEW,Bi-LED adaptive front headlamp",
            "Gas-Matic Shock Absorber,Monroe,SA-MONROE-5510,Suspension & Steering,85.00,99.00,15,87088000,18.00,NEW,Twin-tube gas-charged shock",
            "Iridium Spark Plug 4-Pack,NGK,SP-NGK-6644,Ignition Parts,22.00,28.00,40,85111000,18.00,NEW,Laser iridium long life plugs",
            "Duplicate Brake Pads,TRW,BP-TRW-9011,Braking Systems,42.00,,10,87083000,18.00,NEW,Duplicate MPN of row 1",
            "Bad Compare Price,Bosch,OF-BOSCH-4400,Filters,50.00,30.00,10,84212300,18.00,NEW,Compare at lower than price",
            "Bad GST Rate,Valeo,HL-VALEO-8800,Lighting & Signaling,120.00,,5,85122010,15.00,NEW,Invalid 15% GST rate",
            "Negative Stock,Monroe,SA-MONROE-6600,Suspension & Steering,70.00,80.00,-10,87088000,18.00,NEW,Negative quantity",
            "Missing MPN Part,NGK,,Ignition Parts,20.00,,25,85111000,18.00,NEW,Missing manufacturer part number",
        ]
        csv_content = "\n".join(csv_rows).encode('utf-8')
        uploaded_file = SimpleUploadedFile("spare_parts_batch_10.csv", csv_content, content_type="text/csv")

        # Ensure seller user has an India dealership organisation for Indian HSN & GST routing
        india_org = Organisation.objects.create(
            name='Speed Spares India',
            type=OrganisationTypeChoices.DEALER_GROUP,
            country='IN',
            jurisdiction='IN-TG',
            created_by=seller_user,
        )
        OrganisationMembership.objects.create(
            organisation=india_org,
            user=seller_user,
            role=OrganisationRoleChoices.OWNER,
            is_active=True,
        )

        # 1. Upload via REST API
        url = '/api/v1/marketplace/bulk-upload/'
        response = seller_auth_client.post(
            url,
            {
                'file': uploaded_file,
                'upload_type': 'SPARE_PARTS',
                'duplicate_policy': 'SKIP',
                'organisation': str(india_org.id),
            },
            format='multipart',
        )
        assert response.status_code == 201, response.data
        job_id = response.data['id']

        # 2. Process via Celery Task
        task_result = process_bulk_upload_job.apply(args=[job_id])
        assert task_result.successful()

        # 3. Verify Job Status and Row Counts
        job = BulkUploadJob.objects.get(id=job_id)
        assert job.status == BulkUploadStatusChoices.PARTIALLY_FAILED
        assert job.total_rows == 10
        assert job.processed_rows == 10
        assert job.successful_rows == 5
        assert job.failed_rows == 4
        assert job.duplicate_rows == 1

        # 4. Verify 5 SparePartListing records created
        listings = SparePartListing.objects.filter(seller=seller_user)
        assert listings.count() == 5
        for listing in listings:
            assert listing.status == ListingStatusChoices.PENDING_APPROVAL
            assert listing.is_active is True
            assert listing.submitted_at is not None

        # Verify StockMovement entries for each listing
        for listing in listings:
            movement = StockMovement.objects.filter(listing=listing).first()
            assert movement is not None
            assert movement.reason == StockMovementReasonChoices.INITIAL
            assert movement.delta == listing.stock_quantity
            assert movement.actor == seller_user

        # Verify GST Tax Classification
        led_headlight = listings.get(mpn='HL-VALEO-7721')
        assert led_headlight.gst_rate == Decimal('28.00')
        assert led_headlight.hsn_code == '85122010'
        assert led_headlight.is_tax_verified is True
        assert led_headlight.compare_at_price == Decimal('210.00')
        assert led_headlight.stock_quantity == 8

        brake_pads = listings.get(mpn='BP-TRW-9011')
        assert brake_pads.gst_rate == Decimal('18.00')
        assert brake_pads.hsn_code == '87083000'
        assert brake_pads.is_tax_verified is True
        assert brake_pads.stock_quantity == 20

        # 5. Verify Row Errors
        errors = BulkUploadRowError.objects.filter(job=job).order_by('row_number')
        assert errors.count() == 4
        error_map = {e.row_number: e for e in errors}

        # Row 7: Invalid compare_at_price
        assert 7 in error_map
        assert error_map[7].field_name == 'compare_at_price'
        assert error_map[7].error_code == 'INVALID_COMPARE_AT_PRICE'

        # Row 8: Invalid GST rate classification
        assert 8 in error_map
        assert error_map[8].field_name == 'gst_rate'
        assert error_map[8].error_code == 'INVALID_GST_CLASSIFICATION'

        # Row 9: Negative stock
        assert 9 in error_map
        assert error_map[9].field_name == 'stock_quantity'
        assert error_map[9].error_code == 'INVALID_STOCK'

        # Row 10: Missing MPN
        assert 10 in error_map
        assert error_map[10].field_name == 'mpn'
        assert error_map[10].error_code == 'MISSING_MPN'


# =============================================================================
# 5. FAILURE AND RECOVERY TESTING
# =============================================================================

@pytest.mark.django_db
class TestFailureAndRecoveryWorkflows:
    """Verifies crash resilience, idempotency, duplicate prevention, and retries."""

    def test_idempotent_task_execution_aborts_non_pending_jobs(self, seller_user):
        """Completed jobs cannot be re-executed by duplicate task delivery."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='completed.csv',
            status=BulkUploadStatusChoices.COMPLETED,
        )

        res = process_bulk_upload_job.apply(args=[str(job.id)])
        assert res.successful()
        assert res.result['status'] == 'ABORTED_NOT_PENDING'

    def test_worker_lock_contention_blocks_concurrent_processing(self, seller_user):
        """When row lock is held by another worker, second worker exits cleanly."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='locked.csv',
            status=BulkUploadStatusChoices.PENDING,
        )

        from django.db import OperationalError
        with patch.object(BulkUploadJob.objects, 'select_for_update', side_effect=OperationalError("could not obtain lock")):
            res = process_bulk_upload_job.apply(args=[str(job.id)])
            assert res.successful()
            assert res.result['status'] == 'CONCURRENT_LOCK_BLOCKED'

    def test_redis_unavailable_preserves_job_pending_without_crash(self, seller_user):
        """When broker fails during dispatch, job remains safely in PENDING state."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename='pending.csv',
            status=BulkUploadStatusChoices.PENDING,
        )

        with patch.object(process_bulk_upload_job, 'delay', side_effect=Exception("Redis down")):
            # Simulate transaction commit callback
            def trigger_callback():
                from apps.marketplace.tasks import dispatch_bulk_upload_job
                dispatch_bulk_upload_job(job.id)

            trigger_callback()

            # Job is intact and still PENDING
            job.refresh_from_db()
            assert job.status == BulkUploadStatusChoices.PENDING

    def test_pending_job_recovery_service(self, seller_user, django_capture_on_commit_callbacks):
        """Orphaned pending jobs older than grace period are re-queued."""
        from django.utils import timezone
        import datetime

        old_job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='orphaned.csv',
            status=BulkUploadStatusChoices.PENDING,
        )
        # Backdate created_at
        BulkUploadJob.objects.filter(id=old_job.id).update(
            created_at=timezone.now() - datetime.timedelta(minutes=15)
        )

        dispatched = []
        with patch.object(process_bulk_upload_job, 'delay', side_effect=lambda j: dispatched.append(j)):
            with django_capture_on_commit_callbacks(execute=True):
                recovered_count = recover_pending_bulk_upload_jobs(max_age_minutes=30)
            assert recovered_count == 1
            assert len(dispatched) == 1
            assert dispatched[0] == str(old_job.id)

    def test_retry_failed_rows_workflow(self, seller_user, spare_part_catalogue):
        """Failed rows can be corrected and retried, updating status to COMPLETED."""
        test_org = Organisation.objects.create(
            name='Apex Spares Ltd',
            type=OrganisationTypeChoices.DEALER_GROUP,
            country='GB',
            jurisdiction='GB-ENG',
            created_by=seller_user,
        )
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=test_org,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename='retry_parts.csv',
            status=BulkUploadStatusChoices.PARTIALLY_FAILED,
            total_rows=1,
            successful_rows=0,
            failed_rows=1,
        )

        # Create row error with invalid price
        error = BulkUploadRowError.objects.create(
            job=job,
            row_number=1,
            field_name='price',
            error_code='INVALID_PRICE',
            error_message="Price must be greater than £0.00.",
            raw_data={
                'name': 'Wiper Blade Set',
                'brand': 'Bosch',
                'mpn': 'WB-BOSCH-99',
                'category': 'Braking Systems',  # valid category
                'price': '-15.00',
                'stock_quantity': '10',
            },
            is_resolved=False,
        )

        # Simulate user correcting the raw data before retry
        error.raw_data['price'] = '15.00'
        error.save()

        # Run retry task
        retry_result = retry_bulk_upload_job.apply(args=[str(job.id)])
        assert retry_result.successful()

        job.refresh_from_db()
        assert job.status == BulkUploadStatusChoices.COMPLETED
        assert job.successful_rows == 1
        assert job.failed_rows == 0

        # Verify error marked resolved
        error.refresh_from_db()
        assert error.is_resolved is True

        # Verify listing created
        part = SparePartListing.objects.get(mpn='WB-BOSCH-99')
        assert part.price == Decimal('15.00')
        assert part.stock_quantity == 10


# =============================================================================
# 6. SECURITY AND PERMISSION ENFORCEMENT
# =============================================================================

@pytest.mark.django_db
class TestSecurityAndPermissionEnforcement:
    """Verifies IDOR protection, organisation boundary checks, buyer rejection, and formula injection."""

    def test_seller_idor_isolation(self, seller_auth_client, seller_user, db):
        """Seller B cannot access Seller A's job details, errors, or trigger retry."""
        # Create seller B
        seller_b = User.objects.create_user(
            email='seller_b@example.com',
            password='Password123!',
            first_name='Bob',
            last_name='Seller',
            is_email_verified=True,
        )
        seller_b.add_role(RoleChoices.SELLER)

        job_a = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='seller_a.csv',
        )

        # Authenticate as seller B
        from rest_framework.test import APIClient
        client_b = APIClient()
        client_b.force_authenticate(user=seller_b)

        # Detail view
        detail_url = f'/api/v1/marketplace/bulk-upload/{job_a.id}/'
        res = client_b.get(detail_url)
        assert res.status_code == 404

        # Errors view
        errors_url = f'/api/v1/marketplace/bulk-upload/{job_a.id}/errors/'
        res = client_b.get(errors_url)
        assert res.status_code == 404

        # Export errors
        export_url = f'/api/v1/marketplace/bulk-upload/{job_a.id}/export-errors/'
        res = client_b.get(export_url)
        assert res.status_code == 404

        # Retry
        retry_url = f'/api/v1/marketplace/bulk-upload/{job_a.id}/retry/'
        res = client_b.post(retry_url)
        assert res.status_code == 404

    def test_organisation_permission_enforcement(self, seller_user, test_organisation, db):
        """Only OWNER and ADMIN organisation members can upload on behalf of dealership."""
        # Create member with MEMBER role (not OWNER/ADMIN)
        member_user = User.objects.create_user(
            email='regular_member@example.com',
            password='Password123!',
            first_name='Reg',
            last_name='Member',
            is_email_verified=True,
        )
        member_user.add_role(RoleChoices.SELLER)
        OrganisationMembership.objects.create(
            organisation=test_organisation,
            user=member_user,
            role=OrganisationRoleChoices.MEMBER,
            is_active=True,
        )

        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=member_user)

        csv_file = SimpleUploadedFile("org_upload.csv", b"title,make,model,year,price\n", content_type="text/csv")
        res = client.post(
            '/api/v1/marketplace/bulk-upload/',
            {
                'file': csv_file,
                'upload_type': 'VEHICLES',
                'organisation': str(test_organisation.id),
            },
            format='multipart',
        )
        assert res.status_code == 403
        assert 'OWNER or ADMIN' in str(res.data)

    def test_buyer_role_cannot_upload(self, buyer_auth_client):
        """Buyer accounts are forbidden from uploading bulk inventory."""
        csv_file = SimpleUploadedFile("buyer.csv", b"title,make\n", content_type="text/csv")
        res = buyer_auth_client.post(
            '/api/v1/marketplace/bulk-upload/',
            {
                'file': csv_file,
                'upload_type': 'VEHICLES',
            },
            format='multipart',
        )
        assert res.status_code == 403

    def test_csv_formula_injection_sanitization(self, seller_auth_client, seller_user):
        """CSV export formulas (=CMD, +SUM, @CALL, -DIFF) are sanitized with leading single quote."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='formula.csv',
            status=BulkUploadStatusChoices.FAILED,
        )
        BulkUploadRowError.objects.create(
            job=job,
            row_number=1,
            field_name='title',
            error_code='FORMULA_TEST',
            error_message="Formula test error message",
            raw_data={
                'title': '=cmd|"/C calc"!A0',
                'make': '+1+2',
                'model': '@calc',
            },
        )

        export_url = f'/api/v1/marketplace/bulk-upload/{job.id}/export-errors/'
        res = seller_auth_client.get(export_url)
        assert res.status_code == 200
        content = res.content.decode('utf-8')

        # Formulas must be escaped with single quotes
        assert "'=cmd|" in content
        assert "'+1+2" in content
        assert "'@calc" in content
