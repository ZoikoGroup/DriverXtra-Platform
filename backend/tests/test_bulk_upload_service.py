import io
from decimal import Decimal
from unittest.mock import patch
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction, DatabaseError
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    PartCategory,
    FuelTypeChoices,
    TransmissionChoices,
)
from apps.marketplace.models import (
    BulkUploadJob,
    BulkUploadRowError,
    BulkUploadTypeChoices,
    BulkUploadStatusChoices,
    BulkUploadDuplicatePolicy,
    VehicleListing,
    SparePartListing,
    ListingStatusChoices,
    StockMovement,
    StockMovementReasonChoices,
)
from apps.organisations.models import Organisation
from apps.marketplace.bulk_upload_service import (
    BulkUploadProcessor,
    sanitize_csv_formula,
    recover_pending_bulk_upload_jobs,
)
from apps.marketplace.tasks import process_bulk_upload_job


@pytest.fixture
def bmw_make(db):
    return VehicleMake.objects.create(name="BMW", country_of_origin="Germany", is_active=True)


@pytest.fixture
def bmw_3series(db, bmw_make):
    return VehicleModel.objects.create(make=bmw_make, name="3 Series", year_start=2019, is_active=True)


@pytest.fixture
def bmw_320d_variant(db, bmw_3series):
    return VehicleVariant.objects.create(model=bmw_3series, name="320d M Sport", year=2021, is_active=True)


@pytest.fixture
def brakes_category(db):
    return PartCategory.objects.create(name="Braking Systems", slug="braking-systems", is_active=True)


@pytest.mark.django_db
class TestVehicleBulkUpload:
    """Verifies complete vehicle CSV import pipeline, catalogue resolution, and validations."""

    def test_valid_vehicle_import(self, seller_user, test_organisation, bmw_make, bmw_3series, bmw_320d_variant):
        csv_data = (
            "make,model,variant,year,price,currency,fuel_type,transmission,mileage,condition,vin,registration_number\n"
            "BMW,3 Series,320d M Sport,2021,22500.00,GBP,DIESEL,AUTOMATIC,35000,EXCELLENT,WBA3X11000K123456,AB21CDE\n"
            "BMW,3 Series,,2020,18900.00,GBP,PETROL,MANUAL,48000,VERY_GOOD,WBA3X11000K654321,EF20GHI\n"
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("vehicles.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=test_organisation,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename="vehicles.csv",
            file=uploaded,
            file_size_bytes=len(csv_data),
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.COMPLETED
        assert finished_job.total_rows == 2
        assert finished_job.successful_rows == 2
        assert finished_job.failed_rows == 0
        assert finished_job.duplicate_rows == 0

        # Verify database listings created
        listings = VehicleListing.objects.filter(seller=seller_user, organisation=test_organisation)
        assert listings.count() == 2

        v1 = listings.get(vin="WBA3X11000K123456")
        assert v1.make == bmw_make
        assert v1.model == bmw_3series
        assert v1.variant == bmw_320d_variant
        assert v1.year == 2021
        assert v1.price == Decimal("22500.00")
        assert v1.fuel_type == FuelTypeChoices.DIESEL
        assert v1.transmission == TransmissionChoices.AUTOMATIC
        assert v1.status == ListingStatusChoices.PENDING_APPROVAL
        assert v1.is_active is True

        v2 = listings.get(vin="WBA3X11000K654321")
        assert v2.variant is None
        assert v2.fuel_type == FuelTypeChoices.PETROL
        assert v2.transmission == TransmissionChoices.MANUAL

    def test_missing_mandatory_columns(self, seller_user):
        # Missing 'price' column
        csv_data = (
            "make,model,year,vin\n"
            "BMW,3 Series,2021,WBA3X11000K123456\n"
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("bad_headers.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename="bad_headers.csv",
            file=uploaded,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.FAILED
        assert "Missing mandatory CSV column(s): price" in finished_job.error_summary
        assert VehicleListing.objects.count() == 0

    def test_invalid_price_and_year(self, seller_user, bmw_make, bmw_3series):
        csv_data = (
            "make,model,year,price,vin\n"
            "BMW,3 Series,1850,20000.00,VIN00001\n"  # Invalid year < 1900
            "BMW,3 Series,2020,-500.00,VIN00002\n"   # Invalid negative price
            "BMW,3 Series,2020,15000.00,VIN00003\n"  # Valid row
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("invalid_vals.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename="invalid_vals.csv",
            file=uploaded,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.PARTIALLY_FAILED
        assert finished_job.total_rows == 3
        assert finished_job.successful_rows == 1
        assert finished_job.failed_rows == 2

        # Check row error records
        errors = BulkUploadRowError.objects.filter(job=job).order_by('row_number')
        assert errors.count() == 2
        assert errors[0].row_number == 1
        assert errors[0].field_name == 'year'
        assert errors[0].error_code == 'INVALID_YEAR'
        assert errors[1].row_number == 2
        assert errors[1].field_name == 'price'
        assert errors[1].error_code == 'INVALID_PRICE'

        # Valid listing created
        assert VehicleListing.objects.filter(vin="VIN00003").exists()

    def test_invalid_catalogue_make_and_model(self, seller_user, bmw_make):
        csv_data = (
            "make,model,year,price\n"
            "Ferrari,F40,1990,1000000.00\n"  # Make not in catalogue
            "BMW,Camry,2020,15000.00\n"       # Model doesn't belong to BMW
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("bad_catalogue.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename="bad_catalogue.csv",
            file=uploaded,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.FAILED
        assert finished_job.successful_rows == 0
        assert finished_job.failed_rows == 2

        err1 = BulkUploadRowError.objects.get(job=job, row_number=1)
        assert err1.error_code == 'INVALID_MAKE'
        assert "Ferrari" in err1.error_message

        err2 = BulkUploadRowError.objects.get(job=job, row_number=2)
        assert err2.error_code == 'INVALID_MODEL'
        assert "Camry" in err2.error_message

    def test_duplicate_vin_intra_file_and_database(self, seller_user, bmw_make, bmw_3series):
        # 1. Pre-existing database listing with VIN_EXISTING
        VehicleListing.objects.create(
            seller=seller_user,
            title="Pre-existing car",
            make=bmw_make,
            model=bmw_3series,
            year=2020,
            price=Decimal("15000.00"),
            vin="VIN_EXISTING",
            is_active=True,
        )

        # CSV containing intra-file duplicate VIN_DUP and DB duplicate VIN_EXISTING
        csv_data = (
            "make,model,year,price,vin\n"
            "BMW,3 Series,2020,16000.00,VIN_DUP\n"
            "BMW,3 Series,2020,17000.00,VIN_DUP\n"       # Intra-file duplicate
            "BMW,3 Series,2020,18000.00,VIN_EXISTING\n"  # Database duplicate
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("dups.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename="dups.csv",
            file=uploaded,
            duplicate_policy=BulkUploadDuplicatePolicy.FAIL_ROW,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.PARTIALLY_FAILED
        assert finished_job.successful_rows == 1
        assert finished_job.failed_rows == 2

        err_intra = BulkUploadRowError.objects.get(job=job, row_number=2)
        assert err_intra.error_code == 'DUPLICATE_VIN_IN_FILE'

        err_db = BulkUploadRowError.objects.get(job=job, row_number=3)
        assert err_db.error_code == 'DUPLICATE_VIN_DATABASE'

    def test_duplicate_vin_skip_policy(self, seller_user, bmw_make, bmw_3series):
        csv_data = (
            "make,model,year,price,vin\n"
            "BMW,3 Series,2020,16000.00,VIN_SKIP\n"
            "BMW,3 Series,2020,17000.00,VIN_SKIP\n"  # Should be skipped without error
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("skip.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename="skip.csv",
            file=uploaded,
            duplicate_policy=BulkUploadDuplicatePolicy.SKIP,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.COMPLETED
        assert finished_job.successful_rows == 1
        assert finished_job.duplicate_rows == 1
        assert finished_job.failed_rows == 0
        assert BulkUploadRowError.objects.filter(job=job).count() == 0


@pytest.mark.django_db
class TestSparePartBulkUpload:
    """Verifies spare parts import pipeline, stock ledger integration, and GST classification."""

    def test_valid_spare_part_import_and_stock_ledger(self, seller_user, test_organisation, brakes_category):
        csv_data = (
            "name,brand,mpn,category,price,compare_at_price,stock_quantity,hsn_code,gst_rate\n"
            "Front Ceramic Brake Pad Set,Brembo,P85020,Braking Systems,45.00,60.00,25,8708,28.00\n"
            "Rear Brake Disc 300mm,Bosch,0986479001,braking-systems,55.00,,10,8708,28.00\n"
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("parts.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=test_organisation,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename="parts.csv",
            file=uploaded,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.COMPLETED
        assert finished_job.successful_rows == 2
        assert finished_job.failed_rows == 0

        # Verify listings
        p1 = SparePartListing.objects.get(mpn="P85020")
        assert p1.seller == seller_user
        assert p1.organisation == test_organisation
        assert p1.category == brakes_category
        assert p1.price == Decimal("45.00")
        assert p1.compare_at_price == Decimal("60.00")
        assert p1.stock_quantity == 25
        assert p1.hsn_code == ""  # UK dealership: no Indian HSN code
        assert p1.gst_rate == Decimal("28.00")
        assert p1.is_tax_verified is False  # UK dealership: tax classification separate from statutory verification

        # Verify initial StockMovement record exists
        movement1 = StockMovement.objects.get(listing=p1)
        assert movement1.delta == 25
        assert movement1.resulting_quantity == 25
        assert movement1.reason == StockMovementReasonChoices.INITIAL
        assert movement1.actor == seller_user

        p2 = SparePartListing.objects.get(mpn="0986479001")
        assert p2.stock_quantity == 10
        movement2 = StockMovement.objects.get(listing=p2)
        assert movement2.delta == 10

    def test_compare_at_price_less_than_price_fails(self, seller_user, test_organisation, brakes_category):
        csv_data = (
            "name,brand,mpn,category,price,compare_at_price\n"
            "Brake Pads,Brembo,P85099,Braking Systems,50.00,45.00\n"  # compare_at < price
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("bad_compare.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=test_organisation,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename="bad_compare.csv",
            file=uploaded,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.FAILED
        assert finished_job.failed_rows == 1
        err = BulkUploadRowError.objects.get(job=job, row_number=1)
        assert err.field_name == 'compare_at_price'
        assert err.error_code == 'INVALID_COMPARE_AT_PRICE'

    def test_invalid_gst_rate_classification(self, seller_user, brakes_category):
        india_org = Organisation.objects.create(
            name="Mumbai Auto Spares",
            country="IN",
            jurisdiction="IN-MH",
            created_by=seller_user,
        )
        csv_data = (
            "name,brand,mpn,category,price,hsn_code,gst_rate\n"
            "Brake Pads,Brembo,P85099,Braking Systems,50.00,8708,5.00\n"  # 5% is illegal for 8708
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("bad_tax.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=india_org,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename="bad_tax.csv",
            file=uploaded,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.FAILED
        err = BulkUploadRowError.objects.get(job=job, row_number=1)
        assert err.field_name == 'gst_rate'
        assert err.error_code == 'INVALID_GST_CLASSIFICATION'
        assert "not legally applicable" in err.error_message

    def test_duplicate_mpn_and_brand_isolation(self, seller_user, test_organisation, brakes_category):
        # Pre-existing part for seller_user
        SparePartListing.objects.create(
            seller=seller_user,
            organisation=test_organisation,
            name="Existing Pad",
            brand="Brembo",
            mpn="P85020",
            category=brakes_category,
            price=Decimal("40.00"),
            is_active=True,
        )

        csv_data = (
            "name,brand,mpn,category,price\n"
            "Duplicate Pad,Brembo,P85020,Braking Systems,45.00\n"
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("dup_part.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=test_organisation,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename="dup_part.csv",
            file=uploaded,
            duplicate_policy=BulkUploadDuplicatePolicy.FAIL_ROW,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.FAILED
        err = BulkUploadRowError.objects.get(job=job, row_number=1)
        assert err.error_code == 'DUPLICATE_MPN_DATABASE'

    def test_uk_spare_part_upload_applies_uk_vat(self, seller_user, test_organisation, brakes_category):
        """UK dealership receives standard UK VAT (20%), no Indian HSN code, and GBP currency."""
        csv_data = (
            "name,brand,mpn,category,price,stock_quantity\n"
            "Brembo Brake Caliper,Brembo,CAL-991,Braking Systems,120.00,5\n"
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("uk_parts.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=test_organisation,  # GB-ENG
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename="uk_parts.csv",
            file=uploaded,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.COMPLETED
        assert finished_job.successful_rows == 1

        part = SparePartListing.objects.get(mpn="CAL-991")
        assert part.hsn_code == ""  # Strictly no Indian HSN code for UK dealerships
        assert part.gst_rate == Decimal("20.00")  # Standard UK VAT rate
        assert part.currency == "GBP"
        assert part.is_tax_verified is False  # Application default VAT rate is separate from statutory tax authority verification

    def test_uk_spare_part_explicit_vat_rate_not_statutorily_verified(self, seller_user, test_organisation, brakes_category):
        """Explicit UK VAT rates do not set Indian HSN and remain unverified until formal authority check."""
        csv_data = (
            "name,brand,mpn,category,price,stock_quantity,gst_rate\n"
            "Brembo Brake Rotor,Brembo,ROTOR-992,Braking Systems,85.00,10,20.00\n"
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("uk_parts_vat.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=test_organisation,  # GB-ENG
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename="uk_parts_vat.csv",
            file=uploaded,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.COMPLETED
        assert finished_job.successful_rows == 1

        part = SparePartListing.objects.get(mpn="ROTOR-992")
        assert part.hsn_code == ""  # No Indian HSN
        assert part.gst_rate == Decimal("20.00")
        assert part.currency == "GBP"
        assert part.is_tax_verified is False

    def test_india_spare_part_upload_applies_indian_hsn_and_gst(self, seller_user, brakes_category):
        """India dealership applies Indian HSN code, CBIC GST validation, and INR currency."""
        india_org = Organisation.objects.create(
            name='Hyderabad Spare Hub',
            country='IN',
            jurisdiction='IN-TG',
            created_by=seller_user,
        )
        csv_data = (
            "name,brand,mpn,category,price,stock_quantity,hsn_code,gst_rate\n"
            "Bosch Brake Rotor,Bosch,ROT-882,Braking Systems,3500.00,8,8708,28.00\n"
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("in_parts.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=india_org,  # IN-TG
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename="in_parts.csv",
            file=uploaded,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.COMPLETED
        assert finished_job.successful_rows == 1

        part = SparePartListing.objects.get(mpn="ROT-882")
        assert part.hsn_code == "8708"
        assert part.gst_rate == Decimal("28.00")
        assert part.currency == "INR"
        assert part.is_tax_verified is True

    def test_missing_organisation_jurisdiction_rejected(self, seller_user, brakes_category):
        """Row rejected when dealership organisation has missing/empty jurisdiction."""
        no_jurisdiction_org = Organisation.objects.create(
            name='No Jurisdiction Dealership',
            country='GB',
            jurisdiction='GB-ENG',
            created_by=seller_user,
        )
        Organisation.objects.filter(id=no_jurisdiction_org.id).update(jurisdiction='')
        no_jurisdiction_org.refresh_from_db()

        csv_data = (
            "name,brand,mpn,category,price,stock_quantity\n"
            "Oil Filter,Mann,OF-100,Braking Systems,15.00,10\n"
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("missing_jur.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=no_jurisdiction_org,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename="missing_jur.csv",
            file=uploaded,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.FAILED
        err = BulkUploadRowError.objects.get(job=job, row_number=1)
        assert err.field_name == 'organisation'
        assert err.error_code == 'MISSING_JURISDICTION'

    def test_unsupported_organisation_jurisdiction_rejected(self, seller_user, brakes_category):
        """Row rejected when dealership organisation has unsupported jurisdiction (e.g. US-CA)."""
        us_org = Organisation.objects.create(
            name='California Auto',
            country='GB',
            jurisdiction='GB-ENG',
            created_by=seller_user,
        )
        Organisation.objects.filter(id=us_org.id).update(jurisdiction='US-CA')
        us_org.refresh_from_db()

        csv_data = (
            "name,brand,mpn,category,price,stock_quantity\n"
            "Oil Filter,Mann,OF-200,Braking Systems,15.00,10\n"
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("unsupported_jur.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            organisation=us_org,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename="unsupported_jur.csv",
            file=uploaded,
        )

        processor = BulkUploadProcessor(job)
        finished_job = processor.process()

        assert finished_job.status == BulkUploadStatusChoices.FAILED
        err = BulkUploadRowError.objects.get(job=job, row_number=1)
        assert err.field_name == 'organisation'
        assert err.error_code == 'UNSUPPORTED_JURISDICTION'


@pytest.mark.django_db
class TestCeleryWorkerReliabilityAndLocking:
    """Verifies Celery worker idempotency, database locking, and recovery behavior."""

    def test_celery_task_execution_end_to_end(self, seller_user, bmw_make, bmw_3series):
        csv_data = (
            "make,model,year,price\n"
            "BMW,3 Series,2022,25000.00\n"
        ).encode('utf-8')

        uploaded = SimpleUploadedFile("celery_cars.csv", csv_data, content_type="text/csv")
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename="celery_cars.csv",
            file=uploaded,
            status=BulkUploadStatusChoices.PENDING,
        )

        res = process_bulk_upload_job.apply(args=[str(job.id)])
        assert res.successful()
        assert res.result['status'] == BulkUploadStatusChoices.COMPLETED
        assert res.result['successful_rows'] == 1

        job.refresh_from_db()
        assert job.status == BulkUploadStatusChoices.COMPLETED
        assert job.completed_at is not None

    def test_completed_job_not_processed_again(self, seller_user):
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename="already_done.csv",
            status=BulkUploadStatusChoices.COMPLETED,
        )

        res = process_bulk_upload_job.apply(args=[str(job.id)])
        assert res.successful()
        assert res.result['status'] == 'ABORTED_NOT_PENDING'

    def test_csv_formula_injection_sanitization(self):
        assert sanitize_csv_formula("=SUM(A1:A10)") == "'=SUM(A1:A10)"
        assert sanitize_csv_formula("+12345") == "'+12345"
        assert sanitize_csv_formula("-cmd|' /C calc'!A0") == "'-cmd|' /C calc'!A0"
        assert sanitize_csv_formula("@malicious") == "'@malicious"
        assert sanitize_csv_formula("Normal Text") == "Normal Text"

    def test_recover_pending_bulk_upload_jobs(self, seller_user, django_capture_on_commit_callbacks):
        # Create a pending job
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename="stuck.csv",
            status=BulkUploadStatusChoices.PENDING,
        )

        dispatched = []
        with patch("apps.marketplace.tasks.process_bulk_upload_job.delay", side_effect=lambda j: dispatched.append(j)):
            with django_capture_on_commit_callbacks(execute=True):
                count = recover_pending_bulk_upload_jobs(max_age_minutes=60)
            assert count >= 1
            assert str(job.id) in dispatched
