"""Test suite for Phase 2: DriverXtra Multi-Country Regional Foundation (India + UK).

Verifies:
1. Reusable regional specifications for India (IN) and United Kingdom (GB).
2. Country-to-currency mapping (IN -> INR, GB -> GBP).
3. Country-to-odometer-unit mapping (IN -> km, GB -> mi).
4. Jurisdiction and subdivision validation (IN-TG, IN-MH, GB-ENG).
5. Separation of concerns: GST state code 36 vs jurisdiction IN-TG.
6. Model-level and API-level country/jurisdiction mismatch rejection.
7. Existing UK organisation preservation and backward compatibility.
8. Non-leakage: Indian organisations do not receive UK defaults.
9. Migration backfill integrity for verified and ambiguous records.
"""

import pytest
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APIClient

from platform_core.regional import (
    CountryCode,
    CurrencyCode,
    OdometerUnit,
    TaxScheme,
    get_country_spec,
    is_supported_country,
    get_supported_country_codes,
    get_default_currency_for_country,
    get_default_odometer_unit_for_country,
    get_default_jurisdiction_for_country,
    normalize_country_code,
    validate_country_code,
    validate_jurisdiction,
    derive_country_from_jurisdiction,
    INDIA_SUBDIVISIONS,
    UK_SUBDIVISIONS,
)
from apps.organisations.models import (
    Organisation,
    OrganisationMembership,
    OrganisationRoleChoices,
    OrganisationTypeChoices,
)
import importlib

migration_mod = importlib.import_module('apps.organisations.migrations.0002_organisation_country_and_regional_indices')
backfill_organisation_country_from_verified_data = migration_mod.backfill_organisation_country_from_verified_data


@pytest.mark.django_db
class TestRegionalConfigurationCore:
    """Tests for platform_core.regional specification registry."""

    def test_supported_countries(self):
        codes = get_supported_country_codes()
        assert 'IN' in codes
        assert 'GB' in codes
        assert is_supported_country('IN') is True
        assert is_supported_country('GB') is True
        assert is_supported_country('US') is False
        assert is_supported_country(None) is False

    def test_india_regional_spec(self):
        spec = get_country_spec('IN')
        assert spec.country_code == CountryCode.IN
        assert spec.name == 'India'
        assert spec.default_currency == CurrencyCode.INR
        assert spec.default_odometer_unit == OdometerUnit.KM
        assert spec.default_jurisdiction == 'IN-TG'
        assert spec.tax_config.tax_scheme == TaxScheme.GST
        assert spec.tax_config.tax_id_label == 'GSTIN'

        # Candidate service tax rate for motor vehicle repair (SAC 9987)
        assert str(spec.tax_config.default_candidate_rate_motor_repair) == '18.00'

        # Verify Telangana subdivision
        tg = spec.get_subdivision('IN-TG')
        assert tg is not None
        assert tg.name == 'Telangana'
        assert tg.country_code == 'IN'
        # Crucial separation: GST state code 36 must be distinct from jurisdiction IN-TG
        assert tg.gst_state_code == '36'
        assert tg.gst_state_code != tg.code

        # Verify Maharashtra subdivision
        mh = spec.get_subdivision('IN-MH')
        assert mh is not None
        assert mh.name == 'Maharashtra'
        assert mh.gst_state_code == '27'

        # Verify Delhi subdivision
        dl = spec.get_subdivision('IN-DL')
        assert dl is not None
        assert dl.gst_state_code == '07'

    def test_uk_regional_spec(self):
        spec = get_country_spec('GB')
        assert spec.country_code == CountryCode.GB
        assert spec.name == 'United Kingdom'
        assert spec.default_currency == CurrencyCode.GBP
        assert spec.default_odometer_unit == OdometerUnit.MI
        assert spec.default_jurisdiction == 'GB-ENG'
        assert spec.tax_config.tax_scheme == TaxScheme.VAT
        assert spec.tax_config.tax_id_label == 'VAT Number'
        assert str(spec.tax_config.default_candidate_rate_motor_repair) == '20.00'

        # England subdivision
        eng = spec.get_subdivision('GB-ENG')
        assert eng is not None
        assert eng.name == 'England'
        assert eng.country_code == 'GB'
        assert eng.gst_state_code is None

    def test_country_to_currency_mapping(self):
        assert get_default_currency_for_country('IN') == 'INR'
        assert get_default_currency_for_country('GB') == 'GBP'
        with pytest.raises(KeyError):
            get_default_currency_for_country('US')

    def test_country_to_odometer_unit_mapping(self):
        assert get_default_odometer_unit_for_country('IN') == 'km'
        assert get_default_odometer_unit_for_country('GB') == 'mi'
        with pytest.raises(KeyError):
            get_default_odometer_unit_for_country('FR')

    def test_country_to_jurisdiction_mapping(self):
        assert get_default_jurisdiction_for_country('IN') == 'IN-TG'
        assert get_default_jurisdiction_for_country('GB') == 'GB-ENG'

    def test_normalize_country_code(self):
        assert normalize_country_code('india') == 'IN'
        assert normalize_country_code('IND') == 'IN'
        assert normalize_country_code('Bharat') == 'IN'
        assert normalize_country_code('United Kingdom') == 'GB'
        assert normalize_country_code('UK') == 'GB'
        assert normalize_country_code('Great Britain') == 'GB'
        assert normalize_country_code('England') == 'GB'
        assert normalize_country_code('GBR') == 'GB'
        assert normalize_country_code('') is None
        assert normalize_country_code(None) is None


@pytest.mark.django_db
class TestRegionalValidators:
    """Tests for platform_core.regional validation functions."""

    def test_valid_country_and_jurisdiction(self):
        assert validate_jurisdiction('IN', 'IN-TG') == 'IN-TG'
        assert validate_jurisdiction('IN', 'IN-MH') == 'IN-MH'
        assert validate_jurisdiction('IN', 'in-dl') == 'IN-DL'
        assert validate_jurisdiction('GB', 'GB-ENG') == 'GB-ENG'
        assert validate_jurisdiction('GB', 'GB-SCT') == 'GB-SCT'

    def test_invalid_country_rejection(self):
        with pytest.raises(ValidationError) as exc:
            validate_country_code('US')
        assert "Unsupported country 'US'" in str(exc.value)

        with pytest.raises(ValidationError):
            validate_country_code('')

    def test_invalid_jurisdiction_rejection(self):
        with pytest.raises(ValidationError) as exc:
            validate_jurisdiction('IN', 'IN-UNKNOWN-99')
        assert "not a valid subdivision for 'India'" in str(exc.value)

        with pytest.raises(ValidationError) as exc:
            validate_jurisdiction('GB', 'GB-UNKNOWN')
        assert "not a valid subdivision for 'United Kingdom'" in str(exc.value)

    def test_country_jurisdiction_mismatch_rejection(self):
        # IN with UK subdivision GB-ENG
        with pytest.raises(ValidationError) as exc1:
            validate_jurisdiction('IN', 'GB-ENG')
        assert "mismatch" in str(exc1.value).lower()
        assert "belongs to 'United Kingdom' (GB), not 'India' (IN)" in str(exc1.value)

        # GB with Indian subdivision IN-TG
        with pytest.raises(ValidationError) as exc2:
            validate_jurisdiction('GB', 'IN-TG')
        assert "mismatch" in str(exc2.value).lower()
        assert "belongs to 'India' (IN), not 'United Kingdom' (GB)" in str(exc2.value)

        # GB with Indian subdivision IN-MH
        with pytest.raises(ValidationError) as exc3:
            validate_jurisdiction('GB', 'IN-MH')
        assert "mismatch" in str(exc3.value).lower()

    def test_derive_country_from_jurisdiction(self):
        assert derive_country_from_jurisdiction('GB-ENG') == 'GB'
        assert derive_country_from_jurisdiction('GB-SCT') == 'GB'
        assert derive_country_from_jurisdiction('IN-TG') == 'IN'
        assert derive_country_from_jurisdiction('IN-MH') == 'IN'
        assert derive_country_from_jurisdiction('UNKNOWN') is None


@pytest.mark.django_db
class TestOrganisationRegionalModel:
    """Tests for Organisation model country and jurisdiction enforcement."""

    def test_existing_uk_organisation_defaults_preserved(self, seller_user):
        org = Organisation.objects.create(
            name="Classic British Motors",
            created_by=seller_user,
        )
        assert org.country == 'GB'
        assert org.jurisdiction == 'GB-ENG'
        assert org.regional_specification.default_currency.value == 'GBP'
        assert org.regional_specification.default_odometer_unit.value == 'mi'
        assert org.regional_specification.tax_config.tax_scheme.value == 'VAT'

    def test_new_indian_organisation_with_telangana(self, seller_user):
        org = Organisation.objects.create(
            name="Apex Hyderabad Workshop",
            country='IN',
            jurisdiction='IN-TG',
            created_by=seller_user,
        )
        assert org.country == 'IN'
        assert org.jurisdiction == 'IN-TG'
        # Verify it did NOT receive UK defaults
        assert org.country != 'GB'
        assert org.jurisdiction != 'GB-ENG'
        assert org.regional_specification.default_currency.value == 'INR'
        assert org.regional_specification.default_odometer_unit.value == 'km'
        assert org.regional_specification.tax_config.tax_scheme.value == 'GST'
        assert org.subdivision_specification.gst_state_code == '36'
        assert org.subdivision_specification.name == 'Telangana'

    def test_new_indian_organisation_with_maharashtra(self, seller_user):
        org = Organisation.objects.create(
            name="Pune Technical Hub",
            country='IN',
            jurisdiction='IN-MH',
            created_by=seller_user,
        )
        assert org.country == 'IN'
        assert org.jurisdiction == 'IN-MH'
        assert org.subdivision_specification.gst_state_code == '27'

    def test_new_indian_organisation_auto_defaults_jurisdiction(self, seller_user):
        # When IN is specified without jurisdiction, auto-populates country default IN-TG
        org = Organisation.objects.create(
            name="Bangalore Auto Works",
            country='IN',
            jurisdiction='',
            created_by=seller_user,
        )
        assert org.country == 'IN'
        assert org.jurisdiction == 'IN-TG'

    def test_mismatch_rejection_at_model_level(self, seller_user):
        # IN with GB-ENG
        with pytest.raises(ValidationError) as exc:
            Organisation(
                name="Mismatch Workshop 1",
                country='IN',
                jurisdiction='GB-ENG',
                created_by=seller_user,
            ).save()
        assert "belongs to 'United Kingdom' (GB), not 'India' (IN)" in str(exc.value)

        # GB with IN-TG
        with pytest.raises(ValidationError) as exc2:
            Organisation(
                name="Mismatch Workshop 2",
                country='GB',
                jurisdiction='IN-TG',
                created_by=seller_user,
            ).save()
        assert "belongs to 'India' (IN), not 'United Kingdom' (GB)" in str(exc2.value)

    def test_invalid_country_rejected_at_model_level(self, seller_user):
        with pytest.raises(ValidationError):
            Organisation(
                name="Invalid Country Workshop",
                country='US',
                jurisdiction='US-CA',
                created_by=seller_user,
            ).save()

    def test_memberships_and_ownership_preserved(self, seller_user, buyer_user):
        org = Organisation.objects.create(
            name="Dual Jurisdiction Test Org",
            country='IN',
            jurisdiction='IN-TG',
            created_by=seller_user,
        )
        # Add buyer as TECHNICIAN
        membership = org.add_member(buyer_user, role=OrganisationRoleChoices.TECHNICIAN)
        assert membership.role == OrganisationRoleChoices.TECHNICIAN
        assert org.is_member(buyer_user) is True
        assert org.get_member_role(buyer_user) == OrganisationRoleChoices.TECHNICIAN
        assert org.memberships.count() == 1


@pytest.mark.django_db
class TestOrganisationRegionalAPI:
    """Tests for organisation endpoints and /api/v1/regions/ discovery."""

    def test_regions_public_discovery_endpoint(self, api_client):
        response = api_client.get('/api/v1/regions/')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert 'supported_countries' in data

        countries = {c['country_code']: c for c in data['supported_countries']}
        assert 'IN' in countries
        assert 'GB' in countries

        in_data = countries['IN']
        assert in_data['name'] == 'India'
        assert in_data['default_currency'] == 'INR'
        assert in_data['default_odometer_unit'] == 'km'
        assert in_data['default_jurisdiction'] == 'IN-TG'
        assert in_data['tax_config']['tax_scheme'] == 'GST'
        assert in_data['tax_config']['standard_candidate_service_rate'] == '18.00'

        # Check Telangana in subdivisions list
        tg_sub = next(s for s in in_data['subdivisions'] if s['code'] == 'IN-TG')
        assert tg_sub['name'] == 'Telangana'
        assert tg_sub['gst_state_code'] == '36'

        gb_data = countries['GB']
        assert gb_data['name'] == 'United Kingdom'
        assert gb_data['default_currency'] == 'GBP'
        assert gb_data['default_odometer_unit'] == 'mi'
        assert gb_data['default_jurisdiction'] == 'GB-ENG'

    def test_create_indian_organisation_via_api(self, seller_auth_client):
        payload = {
            'name': 'API Telangana Workshop',
            'type': OrganisationTypeChoices.WORKSHOP,
            'country': 'IN',
            'jurisdiction': 'IN-TG',
        }
        response = seller_auth_client.post('/api/v1/organisations/', payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data['country'] == 'IN'
        assert data['jurisdiction'] == 'IN-TG'
        assert data['default_currency'] == 'INR'
        assert data['default_odometer_unit'] == 'km'
        assert data['tax_scheme'] == 'GST'
        assert data['subdivision_name'] == 'Telangana'
        assert data['gst_state_code'] == '36'

    def test_create_uk_organisation_via_api_preserves_uk_defaults(self, seller_auth_client):
        payload = {
            'name': 'API London Diagnostics',
            'type': OrganisationTypeChoices.WORKSHOP,
        }
        response = seller_auth_client.post('/api/v1/organisations/', payload, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data['country'] == 'GB'
        assert data['jurisdiction'] == 'GB-ENG'
        assert data['default_currency'] == 'GBP'
        assert data['default_odometer_unit'] == 'mi'
        assert data['tax_scheme'] == 'VAT'
        assert data['subdivision_name'] == 'England'
        assert data['gst_state_code'] is None

    def test_api_rejects_country_jurisdiction_mismatch(self, seller_auth_client):
        payload = {
            'name': 'Mismatch API Org',
            'country': 'IN',
            'jurisdiction': 'GB-ENG',
        }
        response = seller_auth_client.post('/api/v1/organisations/', payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        error_text = str(response.json())
        assert "belongs to 'United Kingdom' (GB), not 'India' (IN)" in error_text

    def test_api_rejects_invalid_country(self, seller_auth_client):
        payload = {
            'name': 'Invalid Country API Org',
            'country': 'DE',
            'jurisdiction': 'DE-BY',
        }
        response = seller_auth_client.post('/api/v1/organisations/', payload, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        error_text = str(response.json())
        assert "Unsupported country 'DE'" in error_text


@pytest.mark.django_db
class TestOrganisationMigrationIntegrity:
    """Verifies data migration backfill logic on existing, verified, and ambiguous records."""

    def test_migration_backfill_resolves_verified_records(self, seller_user):
        # Create an org with GB-ENG
        uk_org = Organisation.objects.create(
            name="Legacy UK Motors",
            jurisdiction="GB-ENG",
            created_by=seller_user,
        )
        # Create an org with IN-MH
        in_org = Organisation.objects.create(
            name="Legacy Mumbai Spares",
            country="IN",
            jurisdiction="IN-MH",
            created_by=seller_user,
        )

        class FakeApp:
            def get_model(self, app_label, model_name):
                return Organisation

        # Execute backfill routine
        backfill_organisation_country_from_verified_data(FakeApp(), None)

        uk_org.refresh_from_db()
        in_org.refresh_from_db()

        assert uk_org.country == 'GB'
        assert uk_org.jurisdiction == 'GB-ENG'
        assert in_org.country == 'IN'
        assert in_org.jurisdiction == 'IN-MH'
