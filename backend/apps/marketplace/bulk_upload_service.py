import csv
import io
import logging
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Tuple, Set, Optional
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction, models
from django.db.models import F
from django.utils import timezone

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
    VehicleListingAvailabilityChoices,
    VehicleConditionChoices,
    PartConditionChoices,
    StockMovementReasonChoices,
)
from apps.marketplace.tax import (
    validate_gst_classification,
    resolve_default_hsn_for_category,
)
from apps.marketplace.services import (
    adjust_stock,
    record_audit_entry,
)
from apps.notifications.services import create_notification

logger = logging.getLogger(__name__)

# Maximum file size allowed for bulk uploads: 15 MB
MAX_BULK_UPLOAD_FILE_SIZE_BYTES = 15 * 1024 * 1024
# Maximum data rows permitted in a single bulk import
MAX_BULK_UPLOAD_DATA_ROWS = 5000


class RowValidationError(Exception):
    """Encapsulates a row-level validation error with machine code and readable message."""

    def __init__(self, field_name: str, error_code: str, message: str):
        super().__init__(message)
        self.field_name = field_name
        self.error_code = error_code
        self.message = message


def sanitize_csv_formula(val: Any) -> Any:
    """Neutralizes formula injection characters (=, +, -, @, \\t, \\r) by prefixing a single quote."""
    if val is None:
        return ""
    str_val = str(val)
    stripped = str_val.lstrip()
    if stripped.startswith(('=', '+', '-', '@', '\t', '\r')):
        return f"'{str_val}"
    return str_val


def normalize_header(header: str) -> str:
    """Normalizes CSV header to lower_snake_case for resilient matching."""
    cleaned = re.sub(r'[^\w\s]', '', str(header or '').strip())
    return re.sub(r'\s+', '_', cleaned).lower()


def resolve_tax_country_from_jurisdiction(jurisdiction: Optional[str]) -> Optional[str]:
    """Derives sovereign tax country ('GB' or 'IN') exclusively from authoritative jurisdiction string."""
    if not jurisdiction or not isinstance(jurisdiction, str):
        return None
    from platform_core.regional.validators import derive_country_from_jurisdiction, normalize_country_code
    clean = jurisdiction.strip().upper()
    country = derive_country_from_jurisdiction(clean)
    if country in ('GB', 'IN'):
        return country
    norm = normalize_country_code(clean)
    if norm in ('GB', 'IN'):
        return norm
    return None


# ---------------------------------------------------------------------------
# Column Aliases
# ---------------------------------------------------------------------------

VEHICLE_COLUMN_ALIASES: Dict[str, str] = {
    'title': 'title',
    'listing_title': 'title',
    'vehicle_title': 'title',
    'name': 'title',
    'heading': 'title',
    'make': 'make',
    'vehicle_make': 'make',
    'car_make': 'make',
    'manufacturer': 'make',
    'model': 'model',
    'vehicle_model': 'model',
    'car_model': 'model',
    'variant': 'variant',
    'trim': 'variant',
    'edition': 'variant',
    'submodel': 'variant',
    'year': 'year',
    'reg_year': 'year',
    'registration_year': 'year',
    'mfg_year': 'year',
    'vin': 'vin',
    'vin_number': 'vin',
    'chassis_number': 'vin',
    'chassis_no': 'vin',
    'registration_number': 'registration_number',
    'registration': 'registration_number',
    'reg': 'registration_number',
    'reg_no': 'registration_number',
    'license_plate': 'registration_number',
    'vrm': 'registration_number',
    'mileage': 'mileage',
    'odometer': 'mileage',
    'miles': 'mileage',
    'km': 'mileage',
    'fuel_type': 'fuel_type',
    'fuel': 'fuel_type',
    'transmission': 'transmission',
    'gearbox': 'transmission',
    'trans': 'transmission',
    'body_type': 'body_type',
    'body': 'body_type',
    'price': 'price',
    'asking_price': 'price',
    'cost': 'price',
    'currency': 'currency',
    'condition': 'condition',
    'description': 'description',
    'primary_image_url': 'primary_image_url',
    'image': 'primary_image_url',
    'primary_image': 'primary_image_url',
    'photo': 'primary_image_url',
    'images': 'images',
    'photos': 'images',
    'location_city': 'location_city',
    'city': 'location_city',
    'location_postcode': 'location_postcode',
    'postcode': 'location_postcode',
    'postal_code': 'location_postcode',
    'zip': 'location_postcode',
}

SPARE_PART_COLUMN_ALIASES: Dict[str, str] = {
    'name': 'name',
    'part_name': 'name',
    'title': 'name',
    'item_name': 'name',
    'brand': 'brand',
    'manufacturer': 'brand',
    'mfr': 'brand',
    'mpn': 'mpn',
    'part_number': 'mpn',
    'part_no': 'mpn',
    'manufacturer_part_number': 'mpn',
    'oem_numbers': 'oem_numbers',
    'oem': 'oem_numbers',
    'oem_no': 'oem_numbers',
    'category': 'category',
    'part_category': 'category',
    'taxonomy': 'category',
    'catalogue_part': 'catalogue_part',
    'price': 'price',
    'retail_price': 'price',
    'unit_price': 'price',
    'selling_price': 'price',
    'compare_at_price': 'compare_at_price',
    'msrp': 'compare_at_price',
    'rrp': 'compare_at_price',
    'list_price': 'compare_at_price',
    'currency': 'currency',
    'stock_quantity': 'stock_quantity',
    'stock': 'stock_quantity',
    'quantity': 'stock_quantity',
    'qty': 'stock_quantity',
    'low_stock_threshold': 'low_stock_threshold',
    'condition': 'condition',
    'hsn_code': 'hsn_code',
    'hsn': 'hsn_code',
    'gst_rate': 'gst_rate',
    'gst': 'gst_rate',
    'description': 'description',
    'primary_image_url': 'primary_image_url',
    'image': 'primary_image_url',
    'images': 'images',
    'compatibility_notes': 'compatibility_notes',
}


class BulkUploadProcessor:
    """Robust, concurrency-safe, transactional processing engine for CSV inventory imports."""

    def __init__(self, job: BulkUploadJob):
        self.job = job
        # In-memory caches to prevent N+1 queries during bulk lookups
        self._makes_cache: Dict[str, VehicleMake] = {}
        self._models_cache: Dict[Tuple[str, str], VehicleModel] = {}
        self._categories_cache: Dict[str, PartCategory] = {}
        # Intra-file duplicate trackers
        self._file_vins: Set[str] = set()
        self._file_registrations: Set[str] = set()
        self._file_parts: Set[Tuple[str, str]] = set()

    def process(self) -> BulkUploadJob:
        """Executes the complete processing lifecycle with row savepoints and atomic metrics."""
        logger.info("Starting processing for BulkUploadJob %s (%s)", self.job.id, self.job.upload_type)

        # 1. Inspect raw file and decode text stream
        try:
            content = self._read_and_validate_file()
        except Exception as exc:
            logger.error("Failed to read file for BulkUploadJob %s: %s", self.job.id, exc)
            self._fail_job(str(exc))
            return self.job

        # 2. Parse CSV rows
        try:
            rows, header_map = self._parse_csv_content(content)
        except Exception as exc:
            logger.error("CSV parse error in BulkUploadJob %s: %s", self.job.id, exc)
            self._fail_job(f"Malformed CSV file format: {exc}")
            return self.job

        total_rows = len(rows)
        if total_rows == 0:
            self._fail_job("The uploaded CSV file contains no data rows.")
            return self.job

        if total_rows > MAX_BULK_UPLOAD_DATA_ROWS:
            self._fail_job(
                f"File contains {total_rows} data rows, which exceeds the maximum limit of {MAX_BULK_UPLOAD_DATA_ROWS} rows."
            )
            return self.job

        # Update total rows on job
        BulkUploadJob.objects.filter(id=self.job.id).update(total_rows=total_rows)
        self.job.total_rows = total_rows

        # 3. Pre-load catalogue reference caches
        self._warm_up_catalogue_caches()

        # 4. Iterate over rows with individual savepoints
        successful_count = 0
        failed_count = 0
        duplicate_count = 0

        for row_index, raw_row in enumerate(rows, start=1):
            normalized_row = {
                header_map[col]: val.strip()
                for col, val in raw_row.items()
                if col in header_map
            }

            # Check if row is completely empty
            if not any(normalized_row.values()):
                # Skip empty row without recording failure
                continue

            try:
                with transaction.atomic():
                    is_duplicate, is_skipped = self._handle_row(row_index, normalized_row)
                    if is_skipped:
                        duplicate_count += 1
                    else:
                        successful_count += 1
            except RowValidationError as val_err:
                self._record_row_error(row_index, val_err, normalized_row)
                failed_count += 1
            except Exception as unhandled_err:
                logger.exception("Unexpected error processing row %s of job %s", row_index, self.job.id)
                self._record_row_error(
                    row_index,
                    RowValidationError(
                        field_name="",
                        error_code="UNEXPECTED_SYSTEM_ERROR",
                        message=f"System error processing row: {unhandled_err}",
                    ),
                    normalized_row,
                )
                failed_count += 1

            # Atomic progress update every 25 rows or at end
            if (row_index % 25 == 0) or (row_index == total_rows):
                BulkUploadJob.objects.filter(id=self.job.id).update(
                    processed_rows=row_index,
                    successful_rows=successful_count,
                    failed_rows=failed_count,
                    duplicate_rows=duplicate_count,
                )

        # 5. Finalize status and conclude job
        self._conclude_job(successful_count, failed_count, duplicate_count)
        return self.job

    # -----------------------------------------------------------------------
    # File Reading & Validation
    # -----------------------------------------------------------------------

    def _read_and_validate_file(self) -> str:
        """Reads file, validates size, detects binary content and resolves text encoding."""
        if not self.job.file:
            raise ValueError("No uploaded file attached to this BulkUploadJob.")

        # Check size
        file_obj = self.job.file
        try:
            size = file_obj.size
        except Exception:
            size = self.job.file_size_bytes or 0

        if size > MAX_BULK_UPLOAD_FILE_SIZE_BYTES:
            raise ValueError(
                f"File size ({size / (1024 * 1024):.2f} MB) exceeds maximum allowed limit of 15 MB."
            )

        file_obj.seek(0)
        raw_bytes = file_obj.read()

        # Reject binary files masquerading as CSV
        if b'\x00' in raw_bytes[:4096]:
            raise ValueError("Uploaded file contains binary data or is not a valid text-based CSV file.")

        # Decode encoding (UTF-8 with BOM removal, or Latin-1 fallback)
        try:
            text = raw_bytes.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                text = raw_bytes.decode('latin-1')
            except Exception as dec_err:
                raise ValueError(f"Unable to decode CSV text with UTF-8 or Latin-1: {dec_err}")

        return text

    def _parse_csv_content(self, text: str) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
        """Parses CSV text, normalizes headers, and validates mandatory columns."""
        # Sniff delimiter safely
        sample = text[:4096]
        delimiter = ','
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample, delimiters=',;\t')
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ','

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        try:
            raw_headers = next(reader)
        except StopIteration:
            return [], {}

        # Build alias map
        alias_dict = (
            VEHICLE_COLUMN_ALIASES
            if self.job.upload_type == BulkUploadTypeChoices.VEHICLES
            else SPARE_PART_COLUMN_ALIASES
        )

        header_map: Dict[str, str] = {}
        for raw_h in raw_headers:
            clean_h = normalize_header(raw_h)
            mapped = alias_dict.get(clean_h)
            if mapped:
                header_map[raw_h] = mapped

        # Verify mandatory columns
        if self.job.upload_type == BulkUploadTypeChoices.VEHICLES:
            required = {'make', 'model', 'year', 'price'}
        else:
            required = {'name', 'brand', 'mpn', 'category', 'price'}

        mapped_fields = set(header_map.values())
        missing = required - mapped_fields
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise ValueError(f"Missing mandatory CSV column(s): {missing_str}.")

        # Collect data rows
        rows: List[Dict[str, str]] = []
        for row_vals in reader:
            if not row_vals or not any(row_vals):
                continue
            row_dict = {}
            for col_idx, raw_h in enumerate(raw_headers):
                if col_idx < len(row_vals):
                    row_dict[raw_h] = row_vals[col_idx]
                else:
                    row_dict[raw_h] = ""
            rows.append(row_dict)

        return rows, header_map

    # -----------------------------------------------------------------------
    # Catalogue Caches
    # -----------------------------------------------------------------------

    def _warm_up_catalogue_caches(self):
        """Pre-loads vehicle makes, models, and categories into memory for $O(1)$ lookups."""
        if self.job.upload_type == BulkUploadTypeChoices.VEHICLES:
            for make in VehicleMake.objects.filter(is_active=True):
                self._makes_cache[make.name.strip().lower()] = make
            for model in VehicleModel.objects.filter(is_active=True).select_related('make'):
                key = (model.make.name.strip().lower(), model.name.strip().lower())
                self._models_cache[key] = model
        else:
            for cat in PartCategory.objects.filter(is_active=True):
                self._categories_cache[cat.name.strip().lower()] = cat
                self._categories_cache[cat.slug.strip().lower()] = cat

    # -----------------------------------------------------------------------
    # Row Processing Dispatch
    # -----------------------------------------------------------------------

    def _handle_row(self, row_idx: int, row: Dict[str, str]) -> Tuple[bool, bool]:
        """Validates and creates one inventory listing. Returns (is_duplicate, is_skipped)."""
        if self.job.upload_type == BulkUploadTypeChoices.VEHICLES:
            return self._process_vehicle_row(row_idx, row)
        else:
            return self._process_spare_part_row(row_idx, row)

    # -----------------------------------------------------------------------
    # Vehicle Row Execution
    # -----------------------------------------------------------------------

    def _process_vehicle_row(self, row_idx: int, row: Dict[str, str]) -> Tuple[bool, bool]:
        # 1. Make
        raw_make = row.get('make', '').strip()
        if not raw_make:
            raise RowValidationError('make', 'MISSING_MAKE', "Vehicle make is required.")
        make_obj = self._makes_cache.get(raw_make.lower())
        if not make_obj:
            make_obj = VehicleMake.objects.filter(name__iexact=raw_make, is_active=True).first()
            if not make_obj:
                raise RowValidationError(
                    'make',
                    'INVALID_MAKE',
                    f"Vehicle make '{raw_make}' was not found in the platform catalogue.",
                )
            self._makes_cache[raw_make.lower()] = make_obj

        # 2. Model
        raw_model = row.get('model', '').strip()
        if not raw_model:
            raise RowValidationError('model', 'MISSING_MODEL', "Vehicle model is required.")
        model_key = (make_obj.name.strip().lower(), raw_model.lower())
        model_obj = self._models_cache.get(model_key)
        if not model_obj:
            model_obj = VehicleModel.objects.filter(make=make_obj, name__iexact=raw_model, is_active=True).first()
            if not model_obj:
                raise RowValidationError(
                    'model',
                    'INVALID_MODEL',
                    f"Vehicle model '{raw_model}' does not belong to make '{make_obj.name}'.",
                )
            self._models_cache[model_key] = model_obj

        # 3. Variant (Optional)
        raw_variant = row.get('variant', '').strip()
        variant_obj = None
        if raw_variant:
            variant_obj = VehicleVariant.objects.filter(
                model=model_obj, name__iexact=raw_variant, is_active=True
            ).first()

        # 4. Year
        raw_year = row.get('year', '').strip()
        try:
            year_val = int(raw_year)
            if year_val < 1900 or year_val > 2050:
                raise ValueError()
        except Exception:
            raise RowValidationError(
                'year',
                'INVALID_YEAR',
                f"Manufacturing year '{raw_year}' is invalid. Must be between 1900 and 2050.",
            )

        # 5. Price
        raw_price = row.get('price', '').strip()
        try:
            price_val = Decimal(raw_price)
            if price_val <= Decimal('0.00'):
                raise ValueError()
        except Exception:
            raise RowValidationError(
                'price',
                'INVALID_PRICE',
                f"Asking price '{raw_price}' must be a positive decimal greater than £0.00.",
            )

        # 6. Mileage
        raw_mileage = row.get('mileage', '').strip()
        mileage_val = 0
        if raw_mileage:
            try:
                mileage_val = int(raw_mileage)
                if mileage_val < 0:
                    raise ValueError()
            except Exception:
                raise RowValidationError('mileage', 'INVALID_MILEAGE', "Mileage cannot be negative.")

        # 7. Fuel Type
        raw_fuel = row.get('fuel_type', '').strip().upper()
        fuel_val = FuelTypeChoices.PETROL
        if raw_fuel:
            fuel_map = {
                'PETROL': FuelTypeChoices.PETROL,
                'DIESEL': FuelTypeChoices.DIESEL,
                'HYBRID': FuelTypeChoices.HYBRID,
                'EV': FuelTypeChoices.EV,
                'ELECTRIC': FuelTypeChoices.EV,
            }
            if raw_fuel not in fuel_map:
                raise RowValidationError(
                    'fuel_type',
                    'INVALID_FUEL_TYPE',
                    f"Unsupported fuel type '{row.get('fuel_type')}'. Supported: PETROL, DIESEL, HYBRID, EV.",
                )
            fuel_val = fuel_map[raw_fuel]

        # 8. Transmission
        raw_trans = row.get('transmission', '').strip().upper()
        trans_val = TransmissionChoices.AUTOMATIC
        if raw_trans:
            trans_map = {
                'AUTOMATIC': TransmissionChoices.AUTOMATIC,
                'AUTO': TransmissionChoices.AUTOMATIC,
                'MANUAL': TransmissionChoices.MANUAL,
                'DUAL_CLUTCH': TransmissionChoices.DUAL_CLUTCH,
                'DCT': TransmissionChoices.DUAL_CLUTCH,
                'DSG': TransmissionChoices.DUAL_CLUTCH,
            }
            if raw_trans not in trans_map:
                raise RowValidationError(
                    'transmission',
                    'INVALID_TRANSMISSION',
                    f"Unsupported transmission '{row.get('transmission')}'. Supported: AUTOMATIC, MANUAL, DUAL_CLUTCH.",
                )
            trans_val = trans_map[raw_trans]

        # 9. Condition
        raw_cond = row.get('condition', '').strip().upper()
        cond_val = VehicleConditionChoices.VERY_GOOD
        if raw_cond:
            valid_conds = {c.value for c in VehicleConditionChoices}
            if raw_cond not in valid_conds:
                raise RowValidationError(
                    'condition',
                    'INVALID_CONDITION',
                    f"Invalid vehicle condition '{row.get('condition')}'. Supported: {', '.join(sorted(valid_conds))}.",
                )
            cond_val = raw_cond

        # 10. VIN and Registration Checks (Duplicate Detection)
        vin = row.get('vin', '').strip().upper()
        reg_no = row.get('registration_number', '').strip().upper()

        if vin:
            # Intra-file duplicate
            if vin in self._file_vins:
                if self.job.duplicate_policy == BulkUploadDuplicatePolicy.SKIP:
                    return True, True
                raise RowValidationError('vin', 'DUPLICATE_VIN_IN_FILE', f"Duplicate VIN '{vin}' found within file.")
            # DB duplicate
            if VehicleListing.objects.filter(vin__iexact=vin, is_active=True).exists():
                if self.job.duplicate_policy == BulkUploadDuplicatePolicy.SKIP:
                    return True, True
                raise RowValidationError(
                    'vin',
                    'DUPLICATE_VIN_DATABASE',
                    f"An active vehicle listing with VIN '{vin}' already exists on the platform.",
                )
            self._file_vins.add(vin)

        if reg_no:
            # Intra-file duplicate
            if reg_no in self._file_registrations:
                if self.job.duplicate_policy == BulkUploadDuplicatePolicy.SKIP:
                    return True, True
                raise RowValidationError(
                    'registration_number',
                    'DUPLICATE_REGISTRATION_IN_FILE',
                    f"Duplicate registration '{reg_no}' found within file.",
                )
            # DB duplicate
            if VehicleListing.objects.filter(registration_number__iexact=reg_no, is_active=True).exists():
                if self.job.duplicate_policy == BulkUploadDuplicatePolicy.SKIP:
                    return True, True
                raise RowValidationError(
                    'registration_number',
                    'DUPLICATE_REGISTRATION_DATABASE',
                    f"An active vehicle listing with registration '{reg_no}' already exists.",
                )
            self._file_registrations.add(reg_no)

        # 11. Title
        title = row.get('title', '').strip()
        if not title:
            variant_str = f" {variant_obj.name}" if variant_obj else ""
            title = f"{year_val} {make_obj.name} {model_obj.name}{variant_str}"

        # 12. Create VehicleListing in PENDING_APPROVAL
        primary_img = row.get('primary_image_url', '').strip()
        VehicleListing.objects.create(
            seller=self.job.seller,
            organisation=self.job.organisation,
            title=title[:255],
            make=make_obj,
            model=model_obj,
            variant=variant_obj,
            year=year_val,
            registration_number=reg_no[:20],
            vin=vin[:50],
            mileage=mileage_val,
            fuel_type=fuel_val,
            transmission=trans_val,
            body_type=row.get('body_type', '').strip()[:50],
            price=price_val,
            currency=row.get('currency', '').strip().upper() or 'GBP',
            condition=cond_val,
            description=row.get('description', '').strip(),
            primary_image_url=primary_img,
            images=[primary_img] if primary_img else [],
            location_city=row.get('location_city', '').strip()[:100],
            location_postcode=row.get('location_postcode', '').strip()[:20],
            status=ListingStatusChoices.PENDING_APPROVAL,
            is_active=True,
            availability_status=VehicleListingAvailabilityChoices.AVAILABLE,
            submitted_at=timezone.now(),
        )

        return False, False

    # -----------------------------------------------------------------------
    # Spare Part Row Execution
    # -----------------------------------------------------------------------

    def _process_spare_part_row(self, row_idx: int, row: Dict[str, str]) -> Tuple[bool, bool]:
        # Resolve authoritative tax jurisdiction from dealership organisation
        org = self.job.organisation
        if not org and self.job.seller:
            membership = getattr(self.job.seller, 'organisation_memberships', None)
            if membership:
                active_mem = membership.filter(is_active=True).select_related('organisation').first()
                if active_mem:
                    org = active_mem.organisation

        org_jurisdiction = getattr(org, 'jurisdiction', None) if org else None
        if not org_jurisdiction or not str(org_jurisdiction).strip():
            raise RowValidationError(
                'organisation',
                'MISSING_JURISDICTION',
                "Dealership organisation must have a configured legal jurisdiction to determine tax routing.",
            )

        tax_country = resolve_tax_country_from_jurisdiction(org_jurisdiction)
        if not tax_country:
            raise RowValidationError(
                'organisation',
                'UNSUPPORTED_JURISDICTION',
                f"Dealership jurisdiction '{org_jurisdiction}' is not supported for tax routing. Supported jurisdictions: UK (GB-ENG, GB) or India (IN-*, IN).",
            )
        name = row.get('name', '').strip()
        if not name:
            raise RowValidationError('name', 'MISSING_NAME', "Part name is required.")

        brand = row.get('brand', '').strip()
        if not brand:
            raise RowValidationError('brand', 'MISSING_BRAND', "Manufacturer/Brand is required.")

        mpn = row.get('mpn', '').strip()
        if not mpn:
            raise RowValidationError('mpn', 'MISSING_MPN', "Manufacturer Part Number (MPN) is required.")

        # Duplicate check (brand + MPN)
        part_key = (brand.lower(), mpn.lower())
        if part_key in self._file_parts:
            if self.job.duplicate_policy == BulkUploadDuplicatePolicy.SKIP:
                return True, True
            raise RowValidationError(
                'mpn',
                'DUPLICATE_MPN_IN_FILE',
                f"Duplicate part with brand '{brand}' and MPN '{mpn}' found within file.",
            )

        # Check existing inventory
        filter_kwargs: Dict[str, Any] = {
            'brand__iexact': brand,
            'mpn__iexact': mpn,
            'is_active': True,
        }
        if self.job.organisation_id:
            filter_kwargs['organisation_id'] = self.job.organisation_id
        elif self.job.seller_id:
            filter_kwargs['seller_id'] = self.job.seller_id

        if SparePartListing.objects.filter(**filter_kwargs).exists():
            if self.job.duplicate_policy == BulkUploadDuplicatePolicy.SKIP:
                return True, True
            raise RowValidationError(
                'mpn',
                'DUPLICATE_MPN_DATABASE',
                f"Spare part '{brand} {mpn}' already exists in your active inventory.",
            )
        self._file_parts.add(part_key)

        # Category
        raw_cat = row.get('category', '').strip()
        if not raw_cat:
            raise RowValidationError('category', 'MISSING_CATEGORY', "Part taxonomy category is required.")

        cat_obj = self._categories_cache.get(raw_cat.lower())
        if not cat_obj:
            cat_obj = PartCategory.objects.filter(
                models.Q(name__iexact=raw_cat) | models.Q(slug__iexact=raw_cat),
                is_active=True,
            ).first()
            if not cat_obj:
                raise RowValidationError(
                    'category',
                    'INVALID_CATEGORY',
                    f"Taxonomy category '{raw_cat}' was not found in the platform catalogue.",
                )
            self._categories_cache[raw_cat.lower()] = cat_obj

        # Price
        raw_price = row.get('price', '').strip()
        try:
            price_val = Decimal(raw_price)
            if price_val <= Decimal('0.00'):
                raise ValueError()
        except Exception:
            raise RowValidationError('price', 'INVALID_PRICE', f"Price '{raw_price}' must be greater than £0.00.")

        # Compare-at price
        raw_compare = row.get('compare_at_price', '').strip()
        compare_val = None
        if raw_compare:
            try:
                compare_val = Decimal(raw_compare)
                if compare_val <= price_val:
                    raise RowValidationError(
                        'compare_at_price',
                        'INVALID_COMPARE_AT_PRICE',
                        "Compare-at price must be strictly greater than retail price.",
                    )
            except RowValidationError:
                raise
            except Exception:
                raise RowValidationError('compare_at_price', 'INVALID_COMPARE_AT_PRICE', "Invalid compare-at price.")

        # Stock quantity
        raw_stock = row.get('stock_quantity', '').strip()
        stock_val = 1
        if raw_stock:
            try:
                stock_val = int(raw_stock)
                if stock_val < 0:
                    raise ValueError()
            except Exception:
                raise RowValidationError('stock_quantity', 'INVALID_STOCK', "Stock quantity cannot be negative.")

        # Condition
        raw_cond = row.get('condition', '').strip().upper()
        cond_val = PartConditionChoices.NEW
        if raw_cond:
            valid_part_conds = {c.value for c in PartConditionChoices}
            if raw_cond not in valid_part_conds:
                raise RowValidationError(
                    'condition',
                    'INVALID_CONDITION',
                    f"Unsupported part condition '{row.get('condition')}'. Supported: {', '.join(sorted(valid_part_conds))}.",
                )
            cond_val = raw_cond

        # Sovereign Tax Routing (UK VAT vs Indian GST)
        raw_hsn = row.get('hsn_code', '').strip()
        raw_gst = row.get('gst_rate', '').strip()

        if tax_country == 'GB':
            # Sovereign UK VAT: Standard 20.00%, no Indian HSN code
            hsn_code = ""
            if raw_gst:
                try:
                    gst_rate = Decimal(raw_gst)
                    if gst_rate < Decimal('0.00') or gst_rate > Decimal('100.00'):
                        raise ValueError()
                except Exception:
                    raise RowValidationError('gst_rate', 'INVALID_VAT_RATE', f"Invalid UK VAT rate percentage '{raw_gst}'.")
            else:
                gst_rate = Decimal('20.00')
            # Statutory tax authority verification is kept distinct from application default rate classification
            is_tax_verified = False

        elif tax_country == 'IN':
            # Sovereign Indian GST: HSN code & statutory CBIC rate validation
            if raw_hsn and raw_gst:
                try:
                    gst_dec = Decimal(raw_gst)
                except Exception:
                    raise RowValidationError('gst_rate', 'INVALID_GST_RATE', f"Invalid GST rate percentage '{raw_gst}'.")
                is_valid, err_msg, is_verified = validate_gst_classification(raw_hsn, gst_dec)
                if not is_valid:
                    raise RowValidationError('gst_rate', 'INVALID_GST_CLASSIFICATION', err_msg or "Invalid GST rate for HSN.")
                hsn_code = raw_hsn
                gst_rate = gst_dec
                is_tax_verified = is_verified
            elif raw_hsn and not raw_gst:
                # Auto-lookup rate from official schedule
                from apps.marketplace.tax import get_official_hsn_entry
                entry = get_official_hsn_entry(raw_hsn)
                if entry:
                    hsn_code = raw_hsn
                    gst_rate = entry['standard_rate']
                    is_tax_verified = entry['is_verified']
                else:
                    hsn_code = raw_hsn
                    gst_rate = Decimal("18.00")
                    is_tax_verified = False
            else:
                # Auto-resolve default HSN & rate
                hsn_code, gst_rate = resolve_default_hsn_for_category(cat_obj.name, name)
                is_tax_verified = True
        else:
            raise RowValidationError(
                'organisation',
                'UNSUPPORTED_JURISDICTION',
                f"Unsupported sovereign tax country '{tax_country}'.",
            )

        # Parse OEM list
        raw_oem = row.get('oem_numbers', '').strip()
        oem_list = [s.strip() for s in raw_oem.split(',') if s.strip()] if raw_oem else []

        # Currency resolution
        row_currency = row.get('currency', '').strip().upper()
        default_currency = 'GBP' if tax_country == 'GB' else 'INR'
        currency_val = row_currency or default_currency

        # Create Part Listing with initial stock 0
        primary_img = row.get('primary_image_url', '').strip()
        listing = SparePartListing.objects.create(
            seller=self.job.seller,
            organisation=self.job.organisation,
            name=name[:255],
            brand=brand[:100],
            mpn=mpn[:100],
            oem_numbers=oem_list,
            category=cat_obj,
            description=row.get('description', '').strip(),
            price=price_val,
            compare_at_price=compare_val,
            currency=currency_val,
            stock_quantity=0,
            condition=cond_val,
            hsn_code=hsn_code,
            gst_rate=gst_rate,
            is_tax_verified=is_tax_verified,
            primary_image_url=primary_img,
            images=[primary_img] if primary_img else [],
            compatibility_notes=row.get('compatibility_notes', '').strip(),
            status=ListingStatusChoices.PENDING_APPROVAL,
            is_active=True,
            submitted_at=timezone.now(),
        )

        # Initial stock allocation through stock ledger
        if stock_val > 0:
            adjust_stock(
                listing=listing,
                delta=stock_val,
                reason=StockMovementReasonChoices.INITIAL,
                actor=self.job.seller,
                note=f"Initial stock allocation via bulk upload job {self.job.id}",
            )

        return False, False

    # -----------------------------------------------------------------------
    # Error Recording & Completion
    # -----------------------------------------------------------------------

    def _record_row_error(self, row_idx: int, err: RowValidationError, raw_row: Dict[str, str]):
        """Records an error row with formula-sanitized raw data."""
        sanitized_data = {k: sanitize_csv_formula(v) for k, v in raw_row.items()}
        BulkUploadRowError.objects.update_or_create(
            job=self.job,
            row_number=row_idx,
            defaults={
                'field_name': err.field_name,
                'error_code': err.error_code,
                'error_message': err.message,
                'raw_data': sanitized_data,
                'is_resolved': False,
            },
        )

    def _fail_job(self, summary: str):
        """Marks the job as fatally failed and logs audit entry."""
        BulkUploadJob.objects.filter(id=self.job.id).update(
            status=BulkUploadStatusChoices.FAILED,
            error_summary=summary,
            completed_at=timezone.now(),
        )
        self.job.refresh_from_db()
        self._record_audit_and_notification("FAILED")

    def _conclude_job(self, successful: int, failed: int, duplicates: int):
        """Concludes the job, updates final status, writes audit entry and sends notification."""
        if failed > 0 and successful > 0:
            final_status = BulkUploadStatusChoices.PARTIALLY_FAILED
        elif failed > 0 and successful == 0:
            final_status = BulkUploadStatusChoices.FAILED
        else:
            final_status = BulkUploadStatusChoices.COMPLETED

        BulkUploadJob.objects.filter(id=self.job.id).update(
            status=final_status,
            successful_rows=successful,
            failed_rows=failed,
            duplicate_rows=duplicates,
            completed_at=timezone.now(),
        )
        self.job.refresh_from_db()
        self._record_audit_and_notification(final_status)

    def _record_audit_and_notification(self, final_status: str):
        """Writes audit entry and dispatches notification to seller."""
        audit_entry = record_audit_entry(
            event_type="marketplace.bulk_upload.completed",
            action="bulk_upload:process",
            resource_type="BulkUploadJob",
            resource_id=str(self.job.id),
            actor_id=getattr(self.job.seller, 'id', None),
            operating_org_id=self.job.organisation_id,
            status="SUCCESS" if final_status == BulkUploadStatusChoices.COMPLETED else "PARTIAL",
            metadata={
                "job_id": str(self.job.id),
                "upload_type": self.job.upload_type,
                "status": final_status,
                "total_rows": self.job.total_rows,
                "successful_rows": self.job.successful_rows,
                "failed_rows": self.job.failed_rows,
                "duplicate_rows": self.job.duplicate_rows,
            },
        )

        if self.job.seller:
            title = (
                f"Bulk Upload Completed ({self.job.successful_rows}/{self.job.total_rows} items)"
                if final_status == BulkUploadStatusChoices.COMPLETED
                else f"Bulk Upload Completed with Errors ({self.job.failed_rows} failures)"
            )
            msg = (
                f"Your {self.job.get_upload_type_display()} import has finished. "
                f"Successfully imported: {self.job.successful_rows}, "
                f"Failed: {self.job.failed_rows}, "
                f"Skipped duplicates: {self.job.duplicate_rows}."
            )
            try:
                create_notification(
                    recipient=self.job.seller,
                    audit_entry=audit_entry,
                    title=title,
                    message=msg,
                    resource_type="BulkUploadJob",
                    resource_id=str(self.job.id),
                )
            except Exception as notif_err:
                logger.warning("Could not dispatch notification for job %s: %s", self.job.id, notif_err)


    def retry_failed_rows(self) -> BulkUploadJob:
        """Retries only unresolved failed rows for this job without touching successful listings."""
        unresolved_errors = list(self.job.row_errors.filter(is_resolved=False).order_by('row_number'))
        if not unresolved_errors:
            return self.job

        self._warm_up_catalogue_caches()
        resolved_count = 0

        for err_record in unresolved_errors:
            raw_row = err_record.raw_data or {}
            cleaned_row = {
                k: (
                    v[1:]
                    if isinstance(v, str) and v.startswith("'") and v[1:].startswith(('=', '+', '-', '@', '\t', '\r'))
                    else v
                )
                for k, v in raw_row.items()
            }

            try:
                with transaction.atomic():
                    self._handle_row(err_record.row_number, cleaned_row)
                err_record.is_resolved = True
                err_record.save(update_fields=['is_resolved', 'updated_at'])
                resolved_count += 1
            except RowValidationError as val_err:
                err_record.error_code = val_err.error_code
                err_record.error_message = val_err.message
                err_record.field_name = val_err.field_name
                err_record.save(update_fields=['error_code', 'error_message', 'field_name', 'updated_at'])
            except Exception as exc:
                err_record.error_message = f"Retry error: {exc}"
                err_record.save(update_fields=['error_message', 'updated_at'])

        if resolved_count > 0:
            BulkUploadJob.objects.filter(id=self.job.id).update(
                successful_rows=F('successful_rows') + resolved_count,
                failed_rows=F('failed_rows') - resolved_count,
            )
            self.job.refresh_from_db()

        remaining_unresolved = self.job.row_errors.filter(is_resolved=False).count()
        if remaining_unresolved == 0:
            final_status = BulkUploadStatusChoices.COMPLETED
        else:
            final_status = BulkUploadStatusChoices.PARTIALLY_FAILED

        BulkUploadJob.objects.filter(id=self.job.id).update(
            status=final_status,
            completed_at=timezone.now(),
        )
        self.job.refresh_from_db()
        self._record_audit_and_notification(final_status)
        return self.job


def generate_csv_template(upload_type: str) -> str:
    """Generates a downloadable CSV sample template with headers and realistic example rows."""
    output = io.StringIO()
    writer = csv.writer(output)
    clean_type = str(upload_type or '').strip().upper()

    if clean_type in ('VEHICLES', 'VEHICLE'):
        headers = [
            'make', 'model', 'variant', 'year', 'price', 'currency', 'fuel_type',
            'transmission', 'mileage', 'condition', 'vin', 'registration_number',
            'body_type', 'location_city', 'location_postcode', 'description', 'primary_image_url'
        ]
        sample_rows = [
            [
                'BMW', '3 Series', '320d M Sport', '2022', '23500.00', 'GBP', 'DIESEL',
                'AUTOMATIC', '32000', 'VERY_GOOD', 'WBA3X11000K123456', 'AB22CDE',
                'Saloon', 'London', 'SW1A 1AA', 'Full service history, 1 owner, excellent condition.',
                'https://images.unsplash.com/photo-1555215695-3004980ad54e'
            ],
            [
                'Audi', 'A4', '2.0 TDI S Line', '2021', '21000.00', 'GBP', 'DIESEL',
                'AUTOMATIC', '45000', 'GOOD', 'WAUZZZF40MA123456', 'EF21GHI',
                'Saloon', 'Manchester', 'M1 1AA', 'Well maintained company car, motorway miles.',
                'https://images.unsplash.com/photo-1603584173870-7f23fdae1b7a'
            ]
        ]
    else:
        headers = [
            'name', 'brand', 'mpn', 'oem_numbers', 'category', 'price',
            'compare_at_price', 'currency', 'stock_quantity', 'condition',
            'hsn_code', 'gst_rate', 'description', 'primary_image_url', 'compatibility_notes'
        ]
        sample_rows = [
            [
                'Front Ceramic Brake Pad Set', 'Brembo', 'P85020', '1K0698151, 1K0698151E',
                'Braking Systems', '42.50', '55.00', 'GBP', '20', 'NEW',
                '8708', '28.00', 'Premium low-metallic front brake pad set.',
                'https://images.unsplash.com/photo-1486006920555-c77dce18193b',
                'Fits VW Golf MK7, Audi A3 8V, Seat Leon 5F'
            ],
            [
                'Oil Filter Element', 'Bosch', 'F026407008', '03L115562',
                'Filters', '8.99', '12.50', 'GBP', '50', 'NEW',
                '8421', '18.00', 'High efficiency engine oil filter element with O-ring seal.',
                '', 'Fits 2.0 TDI engines'
            ]
        ]

    writer.writerow(headers)
    for row in sample_rows:
        writer.writerow(row)
    return output.getvalue()


def generate_error_csv(job: BulkUploadJob) -> str:
    """Generates an export CSV file containing only failed rows with error descriptions.

    All cell values are sanitized against formula injection.
    """
    errors = job.row_errors.all().order_by('row_number')
    output = io.StringIO()
    writer = csv.writer(output)

    all_raw_cols: List[str] = []
    for err in errors:
        for k in err.raw_data.keys():
            if k not in all_raw_cols:
                all_raw_cols.append(k)

    headers = ['row_number', 'error_field', 'error_code', 'error_message'] + all_raw_cols
    writer.writerow([sanitize_csv_formula(h) for h in headers])

    for err in errors:
        row = [
            err.row_number,
            sanitize_csv_formula(err.field_name),
            sanitize_csv_formula(err.error_code),
            sanitize_csv_formula(err.error_message),
        ]
        for col in all_raw_cols:
            val = err.raw_data.get(col, '')
            row.append(sanitize_csv_formula(val))
        writer.writerow(row)

    return output.getvalue()


def recover_stuck_bulk_upload_jobs(stuck_threshold_minutes: int = 30) -> int:
    """Recovers jobs stuck in PROCESSING due to worker crashes or termination."""
    cutoff = timezone.now() - timezone.timedelta(minutes=stuck_threshold_minutes)
    stuck_jobs = BulkUploadJob.objects.filter(
        status=BulkUploadStatusChoices.PROCESSING,
        started_at__lte=cutoff,
    )
    recovered = 0
    for job in stuck_jobs:
        has_success = job.successful_rows > 0
        new_status = (
            BulkUploadStatusChoices.PARTIALLY_FAILED
            if has_success
            else BulkUploadStatusChoices.FAILED
        )
        job.status = new_status
        job.error_summary = "Processing interrupted by worker crash or termination."
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'error_summary', 'completed_at', 'updated_at'])
        recovered += 1

    return recovered


def recover_pending_bulk_upload_jobs(max_age_minutes: int = 120) -> int:
    """Finds PENDING bulk upload jobs and re-dispatches them to Celery.

    Safe recovery mechanism when Redis or the Celery worker was temporarily offline.
    """
    from apps.marketplace.tasks import dispatch_bulk_upload_job

    cutoff = timezone.now() - timezone.timedelta(minutes=max_age_minutes)
    pending_jobs = BulkUploadJob.objects.filter(
        status=BulkUploadStatusChoices.PENDING,
        created_at__gte=cutoff,
    ).order_by('created_at')

    dispatched = 0
    for job in pending_jobs:
        dispatch_bulk_upload_job(job.id)
        dispatched += 1

    return dispatched
