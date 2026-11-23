import io
import uuid
from unittest.mock import patch
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.models import User, RoleChoices
from apps.organisations.models import Organisation, OrganisationMembership, OrganisationRoleChoices, OrganisationTypeChoices
from apps.marketplace.models import (
    BulkUploadJob,
    BulkUploadRowError,
    BulkUploadTypeChoices,
    BulkUploadStatusChoices,
    BulkUploadDuplicatePolicy,
)


@pytest.fixture
def other_seller_user(db):
    user = User.objects.create_user(
        email='other_seller@driverxtra.com',
        password='SecurePassword123!',
        first_name='Oliver',
        last_name='Other',
        phone_number='+447000000009',
        is_email_verified=True,
    )
    user.add_role(RoleChoices.SELLER)
    return user


@pytest.fixture
def other_seller_auth_client(other_seller_user):
    client = APIClient()
    client.force_authenticate(user=other_seller_user)
    return client


@pytest.fixture
def sample_vehicle_csv_bytes():
    content = (
        "make,model,variant,year,price,currency,fuel_type,transmission,mileage,condition,vin,registration_number,body_type,location_city,location_postcode,description\n"
        "BMW,3 Series,320d M Sport,2022,24500,GBP,DIESEL,AUTOMATIC,28000,EXCELLENT,WBA3X11000K999999,AB22XYZ,Saloon,London,SW1A 1AA,Clean vehicle with full dealer history.\n"
    )
    return content.encode('utf-8')


@pytest.fixture
def sample_parts_csv_bytes():
    content = (
        "name,brand,mpn,oem_numbers,category,price,currency,stock_quantity,condition,hsn_code,gst_rate,description\n"
        "Front Brake Pads,Brembo,P85020,1K0698151,Braking Systems,45.00,GBP,25,NEW,8708,28.00,High quality front brake pads.\n"
    )
    return content.encode('utf-8')


@pytest.mark.django_db
class TestBulkUploadRESTAPI:
    """Comprehensive test suite for Phase 7.1 Dealer Bulk Upload REST APIs:

    - Upload submission (Vehicles & Spare Parts)
    - File validation (format, size, binary detection)
    - Permissions and Role-Based Access Control
    - Multi-tenant and Organisation Scoping
    - IDOR protection across all endpoints
    - Status reporting, error listing and error CSV export
    - Selective Retry mechanism
    - Downloadable templates
    """

    # -------------------------------------------------------------------------
    # 1. POST /api/v1/marketplace/bulk-upload/ (Upload Submission)
    # -------------------------------------------------------------------------

    def test_upload_valid_vehicle_csv(self, seller_auth_client, seller_user, sample_vehicle_csv_bytes):
        """Test submitting a valid vehicles CSV returns 201 and dispatches background task."""
        file = SimpleUploadedFile("vehicles_import.csv", sample_vehicle_csv_bytes, content_type="text/csv")
        data = {
            "file": file,
            "upload_type": BulkUploadTypeChoices.VEHICLES,
            "duplicate_policy": BulkUploadDuplicatePolicy.SKIP.value,
        }

        with patch("apps.marketplace.views.dispatch_bulk_upload_job") as mock_dispatch:
            response = seller_auth_client.post("/api/v1/marketplace/bulk-upload/", data, format="multipart")

        assert response.status_code == 201
        res_data = response.data
        assert "id" in res_data
        assert res_data["upload_type"] == BulkUploadTypeChoices.VEHICLES
        assert res_data["status"] == BulkUploadStatusChoices.PENDING
        assert res_data["duplicate_policy"] == BulkUploadDuplicatePolicy.SKIP.value
        assert res_data["filename"] == "vehicles_import.csv"
        assert res_data["progress_percentage"] == 0
        assert res_data["is_finished"] is False

        # Verify database record
        job = BulkUploadJob.objects.get(id=res_data["id"])
        assert job.seller == seller_user
        assert job.upload_type == BulkUploadTypeChoices.VEHICLES
        mock_dispatch.assert_called_once_with(job.id)

    def test_upload_valid_spare_parts_csv(self, seller_auth_client, seller_user, sample_parts_csv_bytes):
        """Test submitting a valid spare parts CSV returns 201."""
        file = SimpleUploadedFile("parts_catalog.csv", sample_parts_csv_bytes, content_type="text/csv")
        data = {
            "file": file,
            "upload_type": BulkUploadTypeChoices.SPARE_PARTS,
            "duplicate_policy": BulkUploadDuplicatePolicy.FAIL_ROW.value,
        }

        with patch("apps.marketplace.views.dispatch_bulk_upload_job") as mock_dispatch:
            response = seller_auth_client.post("/api/v1/marketplace/bulk-upload/", data, format="multipart")

        assert response.status_code == 201
        assert response.data["upload_type"] == BulkUploadTypeChoices.SPARE_PARTS
        assert response.data["duplicate_policy"] == BulkUploadDuplicatePolicy.FAIL_ROW.value
        mock_dispatch.assert_called_once()

    def test_upload_with_organisation_success(
        self, seller_auth_client, seller_user, test_organisation, sample_vehicle_csv_bytes
    ):
        """Seller who is OWNER of organisation may upload on behalf of the organisation."""
        file = SimpleUploadedFile("dealer_stock.csv", sample_vehicle_csv_bytes, content_type="text/csv")
        data = {
            "file": file,
            "upload_type": BulkUploadTypeChoices.VEHICLES,
            "organisation": str(test_organisation.id),
        }

        with patch("apps.marketplace.views.dispatch_bulk_upload_job"):
            response = seller_auth_client.post("/api/v1/marketplace/bulk-upload/", data, format="multipart")

        assert response.status_code == 201
        assert response.data["organisation"] == test_organisation.id
        assert response.data["organisation_name"] == test_organisation.name

        job = BulkUploadJob.objects.get(id=response.data["id"])
        assert job.organisation == test_organisation

    def test_upload_with_organisation_forbidden_for_non_admin_member(
        self, test_organisation, sample_vehicle_csv_bytes
    ):
        """Organisation member without OWNER or ADMIN role cannot submit bulk imports."""
        # Create non-admin member
        staff_member = User.objects.create_user(
            email='tech@apexmotors.com',
            password='SecurePassword123!',
            first_name='Tom',
            last_name='Tech',
            is_email_verified=True,
        )
        staff_member.add_role(RoleChoices.SELLER)
        OrganisationMembership.objects.create(
            organisation=test_organisation,
            user=staff_member,
            role=OrganisationRoleChoices.MEMBER,
            is_active=True,
        )

        client = APIClient()
        client.force_authenticate(user=staff_member)

        file = SimpleUploadedFile("dealer_stock.csv", sample_vehicle_csv_bytes, content_type="text/csv")
        data = {
            "file": file,
            "upload_type": BulkUploadTypeChoices.VEHICLES,
            "organisation": str(test_organisation.id),
        }

        response = client.post("/api/v1/marketplace/bulk-upload/", data, format="multipart")
        assert response.status_code == 403
        error_text = response.data.get("message") or str(response.data)
        assert "Only organisation OWNER or ADMIN" in error_text

    # -------------------------------------------------------------------------
    # 2. File Validation Rejections
    # -------------------------------------------------------------------------

    def test_upload_invalid_file_extension_rejected(self, seller_auth_client):
        """Rejects non-CSV files such as Excel spreadsheets or PDFs."""
        file = SimpleUploadedFile("inventory.xlsx", b"PK\x03\x04fakexlsx", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        data = {
            "file": file,
            "upload_type": BulkUploadTypeChoices.VEHICLES,
        }

        response = seller_auth_client.post("/api/v1/marketplace/bulk-upload/", data, format="multipart")
        assert response.status_code == 400
        error_text = response.data.get("message") or str(response.data)
        assert "Only CSV text files (.csv) are accepted" in error_text

    def test_upload_binary_file_rejected(self, seller_auth_client):
        """Rejects files containing binary null bytes."""
        binary_content = b"make,model,year\x00\x01\x02binarypayload\n"
        file = SimpleUploadedFile("bad_file.csv", binary_content, content_type="text/csv")
        data = {
            "file": file,
            "upload_type": BulkUploadTypeChoices.VEHICLES,
        }

        response = seller_auth_client.post("/api/v1/marketplace/bulk-upload/", data, format="multipart")
        assert response.status_code == 400
        error_text = response.data.get("message") or str(response.data)
        assert "binary" in error_text.lower()

    def test_upload_oversized_file_rejected(self, seller_auth_client):
        """Rejects files exceeding the 15 MB limit."""
        from django.core.files.uploadedfile import UploadedFile

        file = SimpleUploadedFile("large.csv", b"make,model\nBMW,320d\n", content_type="text/csv")
        data = {
            "file": file,
            "upload_type": BulkUploadTypeChoices.VEHICLES,
        }

        def make_oversized_prop():
            return property(lambda self: 16 * 1024 * 1024, lambda self, val: None)

        with patch.object(UploadedFile, "size", make_oversized_prop()):
            response = seller_auth_client.post("/api/v1/marketplace/bulk-upload/", data, format="multipart")

        assert response.status_code == 400
        error_text = response.data.get("message") or str(response.data)
        assert "exceeds maximum allowed limit of 15 MB" in error_text

    # -------------------------------------------------------------------------
    # 3. Access Control and Roles
    # -------------------------------------------------------------------------

    def test_upload_unauthenticated_rejected(self, api_client, sample_vehicle_csv_bytes):
        """Unauthenticated requests are denied with 401."""
        file = SimpleUploadedFile("cars.csv", sample_vehicle_csv_bytes, content_type="text/csv")
        response = api_client.post("/api/v1/marketplace/bulk-upload/", {"file": file, "upload_type": "VEHICLES"}, format="multipart")
        assert response.status_code == 401

    def test_upload_buyer_without_seller_role_rejected(self, buyer_auth_client, sample_vehicle_csv_bytes):
        """Regular buyers cannot submit bulk imports."""
        file = SimpleUploadedFile("cars.csv", sample_vehicle_csv_bytes, content_type="text/csv")
        response = buyer_auth_client.post(
            "/api/v1/marketplace/bulk-upload/",
            {"file": file, "upload_type": "VEHICLES"},
            format="multipart",
        )
        assert response.status_code == 403

    # -------------------------------------------------------------------------
    # 4. GET /api/v1/marketplace/bulk-upload/ (Listing and Scoping)
    # -------------------------------------------------------------------------

    def test_list_jobs_seller_scoping_and_filters(
        self, seller_auth_client, seller_user, other_seller_user
    ):
        """Sellers can only list their own jobs; filters by upload_type and status work correctly."""
        # Seller's jobs
        j1 = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='my_cars.csv',
            status=BulkUploadStatusChoices.COMPLETED,
        )
        j2 = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.SPARE_PARTS,
            filename='my_parts.csv',
            status=BulkUploadStatusChoices.PENDING,
        )
        # Other seller's job
        BulkUploadJob.objects.create(
            seller=other_seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='other_cars.csv',
            status=BulkUploadStatusChoices.COMPLETED,
        )

        # Listing without filter
        response = seller_auth_client.get("/api/v1/marketplace/bulk-upload/")
        assert response.status_code == 200
        results = response.data["results"] if "results" in response.data else response.data
        assert len(results) == 2
        returned_ids = {r["id"] for r in results}
        assert str(j1.id) in returned_ids
        assert str(j2.id) in returned_ids

        # Filter by upload_type
        res_filtered = seller_auth_client.get("/api/v1/marketplace/bulk-upload/?upload_type=VEHICLES")
        assert res_filtered.status_code == 200
        filtered_results = res_filtered.data["results"] if "results" in res_filtered.data else res_filtered.data
        assert len(filtered_results) == 1
        assert filtered_results[0]["id"] == str(j1.id)

        # Filter by status
        res_status = seller_auth_client.get("/api/v1/marketplace/bulk-upload/?status=PENDING")
        assert res_status.status_code == 200
        status_results = res_status.data["results"] if "results" in res_status.data else res_status.data
        assert len(status_results) == 1
        assert status_results[0]["id"] == str(j2.id)

    def test_list_jobs_admin_can_view_all(self, admin_auth_client, seller_user, other_seller_user):
        """Platform administrators can view all bulk upload jobs across all sellers."""
        BulkUploadJob.objects.create(seller=seller_user, upload_type=BulkUploadTypeChoices.VEHICLES, filename='seller.csv')
        BulkUploadJob.objects.create(seller=other_seller_user, upload_type=BulkUploadTypeChoices.SPARE_PARTS, filename='other.csv')

        response = admin_auth_client.get("/api/v1/marketplace/bulk-upload/")
        assert response.status_code == 200
        results = response.data["results"] if "results" in response.data else response.data
        assert len(results) >= 2

    # -------------------------------------------------------------------------
    # 5. GET /api/v1/marketplace/bulk-upload/<id>/ (Detail & IDOR Protection)
    # -------------------------------------------------------------------------

    def test_get_job_detail_and_idor_protection(
        self, seller_auth_client, other_seller_auth_client, seller_user
    ):
        """A seller can view their own job details, but another seller receives 404 (IDOR protection)."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='fleet.csv',
            status=BulkUploadStatusChoices.COMPLETED,
            total_rows=10,
            processed_rows=10,
            successful_rows=9,
            failed_rows=1,
        )

        # Owner accesses
        res_owner = seller_auth_client.get(f"/api/v1/marketplace/bulk-upload/{job.id}/")
        assert res_owner.status_code == 200
        assert res_owner.data["id"] == str(job.id)
        assert res_owner.data["successful_rows"] == 9
        assert res_owner.data["failed_rows"] == 1
        assert res_owner.data["progress_percentage"] == 100

        # Non-owner receives 404 Not Found
        res_other = other_seller_auth_client.get(f"/api/v1/marketplace/bulk-upload/{job.id}/")
        assert res_other.status_code == 404

    # -------------------------------------------------------------------------
    # 6. GET /api/v1/marketplace/bulk-upload/<id>/errors/ (Row Errors & Filter)
    # -------------------------------------------------------------------------

    def test_get_job_errors_and_scoping(
        self, seller_auth_client, other_seller_auth_client, seller_user
    ):
        """Test retrieving paginated errors and ?is_resolved filtering."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='vehicles.csv',
            status=BulkUploadStatusChoices.PARTIALLY_FAILED,
        )
        err1 = BulkUploadRowError.objects.create(
            job=job,
            row_number=2,
            field_name='vin',
            error_code='DUPLICATE_VIN',
            error_message='VIN already exists.',
            raw_data={'vin': 'WBA3X11000K123456'},
            is_resolved=False,
        )
        err2 = BulkUploadRowError.objects.create(
            job=job,
            row_number=5,
            field_name='price',
            error_code='INVALID_NUMBER',
            error_message='Price must be positive.',
            raw_data={'price': '-100'},
            is_resolved=True,
        )

        # Owner gets all errors
        response = seller_auth_client.get(f"/api/v1/marketplace/bulk-upload/{job.id}/errors/")
        assert response.status_code == 200
        results = response.data["results"] if "results" in response.data else response.data
        assert len(results) == 2

        # Filter ?is_resolved=false
        res_unresolved = seller_auth_client.get(f"/api/v1/marketplace/bulk-upload/{job.id}/errors/?is_resolved=false")
        assert res_unresolved.status_code == 200
        unresolved_results = res_unresolved.data["results"] if "results" in res_unresolved.data else res_unresolved.data
        assert len(unresolved_results) == 1
        assert unresolved_results[0]["id"] == str(err1.id)

        # Other seller gets 404
        res_other = other_seller_auth_client.get(f"/api/v1/marketplace/bulk-upload/{job.id}/errors/")
        assert res_other.status_code == 404

    # -------------------------------------------------------------------------
    # 7. GET /api/v1/marketplace/bulk-upload/<id>/export-errors/ (CSV Download & Sanitization)
    # -------------------------------------------------------------------------

    def test_export_errors_csv_download_and_sanitization(
        self, seller_auth_client, other_seller_auth_client, seller_user
    ):
        """Test error CSV export returns text/csv with sanitized formula cells."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='batch.csv',
            status=BulkUploadStatusChoices.PARTIALLY_FAILED,
        )
        BulkUploadRowError.objects.create(
            job=job,
            row_number=3,
            field_name='description',
            error_code='INVALID_FORMAT',
            error_message='Suspicious formula.',
            raw_data={'description': '=cmd|/c calc.exe!A1', 'vin': '+44123456789'},
            is_resolved=False,
        )

        response = seller_auth_client.get(f"/api/v1/marketplace/bulk-upload/{job.id}/export-errors/")
        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
        assert f'bulk_upload_errors_{job.id}.csv' in response["Content-Disposition"]

        content = response.content.decode("utf-8")
        # Ensure formulas are neutralized with single quote
        assert "'=cmd|/c calc.exe!A1" in content
        assert "'+44123456789" in content

        # IDOR protection: other seller receives 404
        res_other = other_seller_auth_client.get(f"/api/v1/marketplace/bulk-upload/{job.id}/export-errors/")
        assert res_other.status_code == 404

    # -------------------------------------------------------------------------
    # 8. POST /api/v1/marketplace/bulk-upload/<id>/retry/ (Selective Retry)
    # -------------------------------------------------------------------------

    def test_retry_job_success(self, seller_auth_client, seller_user):
        """Test retrying a partially failed job with unresolved errors."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='import.csv',
            status=BulkUploadStatusChoices.PARTIALLY_FAILED,
        )
        BulkUploadRowError.objects.create(
            job=job,
            row_number=2,
            field_name='make',
            error_code='MAKE_NOT_FOUND',
            error_message='Unknown make.',
            raw_data={'make': 'UnknownBrand'},
            is_resolved=False,
        )

        with patch("apps.marketplace.views.dispatch_bulk_upload_retry") as mock_retry:
            response = seller_auth_client.post(f"/api/v1/marketplace/bulk-upload/{job.id}/retry/")

        assert response.status_code == 200
        assert "Retry dispatched for 1 unresolved row(s)" in response.data["detail"]
        mock_retry.assert_called_once_with(job.id)

    def test_retry_job_rejected_when_no_unresolved_errors(self, seller_auth_client, seller_user):
        """Cannot retry a job that has zero unresolved errors."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='import.csv',
            status=BulkUploadStatusChoices.COMPLETED,
        )
        # All errors resolved
        BulkUploadRowError.objects.create(
            job=job,
            row_number=2,
            field_name='make',
            error_code='MAKE_NOT_FOUND',
            error_message='Unknown make.',
            raw_data={'make': 'BMW'},
            is_resolved=True,
        )

        response = seller_auth_client.post(f"/api/v1/marketplace/bulk-upload/{job.id}/retry/")
        assert response.status_code == 400
        assert "No unresolved errors found to retry" in response.data["detail"]

    def test_retry_job_rejected_when_in_progress(self, seller_auth_client, seller_user):
        """Cannot retry a job that is currently PROCESSING."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='import.csv',
            status=BulkUploadStatusChoices.PROCESSING,
        )
        BulkUploadRowError.objects.create(
            job=job,
            row_number=2,
            field_name='vin',
            error_code='INVALID_VIN',
            error_message='Bad VIN',
            is_resolved=False,
        )

        response = seller_auth_client.post(f"/api/v1/marketplace/bulk-upload/{job.id}/retry/")
        assert response.status_code == 400
        assert "currently in progress" in response.data["detail"]

    def test_retry_job_idor_protection(self, other_seller_auth_client, seller_user):
        """Another seller cannot retry a job they do not own."""
        job = BulkUploadJob.objects.create(
            seller=seller_user,
            upload_type=BulkUploadTypeChoices.VEHICLES,
            filename='import.csv',
            status=BulkUploadStatusChoices.PARTIALLY_FAILED,
        )
        BulkUploadRowError.objects.create(
            job=job,
            row_number=2,
            field_name='vin',
            error_code='INVALID_VIN',
            error_message='Bad VIN',
            is_resolved=False,
        )

        response = other_seller_auth_client.post(f"/api/v1/marketplace/bulk-upload/{job.id}/retry/")
        assert response.status_code == 404

    # -------------------------------------------------------------------------
    # 9. GET /api/v1/marketplace/bulk-upload/templates/<upload_type>/
    # -------------------------------------------------------------------------

    def test_template_download_vehicles(self, seller_auth_client):
        """Test downloading the vehicle CSV template."""
        response = seller_auth_client.get("/api/v1/marketplace/bulk-upload/templates/vehicles/")
        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
        assert "vehicles_template.csv" in response["Content-Disposition"]

        content = response.content.decode("utf-8")
        assert "make,model,variant" in content
        assert "vin,registration_number" in content

    def test_template_download_spare_parts(self, seller_auth_client):
        """Test downloading the spare parts CSV template."""
        response = seller_auth_client.get("/api/v1/marketplace/bulk-upload/templates/spare_parts/")
        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
        assert "spare_parts_template.csv" in response["Content-Disposition"]

        content = response.content.decode("utf-8")
        assert "name,brand,mpn" in content
        assert "hsn_code,gst_rate" in content

    def test_template_download_invalid_type_rejected(self, seller_auth_client):
        """Requesting an invalid template type returns 400."""
        response = seller_auth_client.get("/api/v1/marketplace/bulk-upload/templates/unknown_type/")
        assert response.status_code == 400
        assert "valid_types" in response.data
