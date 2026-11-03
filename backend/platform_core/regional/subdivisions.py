"""Authoritative ISO 3166-2 subdivisions and regional attributes for supported countries.

Strict separation of concerns:
- Organisation jurisdiction: ISO 3166-2 code (e.g. 'IN-TG', 'GB-ENG')
- Country code: ISO 3166-1 alpha-2 code (e.g. 'IN', 'GB')
- GST state code: 2-digit CBIC numeric code (e.g. '36' for Telangana), separate from jurisdiction.
- Subdivision name: Official territorial name.
"""

from dataclasses import dataclass
import re
from typing import Optional, Dict


@dataclass(frozen=True)
class SubdivisionSpecification:
    """Represents a validated first-level national subdivision (state, province, country)."""
    code: str                      # ISO 3166-2 code (e.g. 'IN-TG', 'GB-ENG')
    name: str                      # Territorial name (e.g. 'Telangana', 'England')
    country_code: str              # ISO 3166-1 alpha-2 (e.g. 'IN', 'GB')
    gst_state_code: Optional[str]  # 2-digit CBIC GST code if applicable (e.g. '36'), NOT the jurisdiction!
    gst_state_name: Optional[str]  # Official name according to CBIC GST schedule if applicable


# =============================================================================
# UNITED KINGDOM SUBDIVISIONS (ISO 3166-2:GB)
# =============================================================================

UK_SUBDIVISIONS: Dict[str, SubdivisionSpecification] = {
    'GB-ENG': SubdivisionSpecification(
        code='GB-ENG',
        name='England',
        country_code='GB',
        gst_state_code=None,
        gst_state_name=None,
    ),
    'GB-SCT': SubdivisionSpecification(
        code='GB-SCT',
        name='Scotland',
        country_code='GB',
        gst_state_code=None,
        gst_state_name=None,
    ),
    'GB-WLS': SubdivisionSpecification(
        code='GB-WLS',
        name='Wales',
        country_code='GB',
        gst_state_code=None,
        gst_state_name=None,
    ),
    'GB-NIR': SubdivisionSpecification(
        code='GB-NIR',
        name='Northern Ireland',
        country_code='GB',
        gst_state_code=None,
        gst_state_name=None,
    ),
}


# =============================================================================
# INDIA SUBDIVISIONS (ISO 3166-2:IN)
# Official 36 States & Union Territories with statutory 2-digit CBIC GST state codes
# =============================================================================

INDIA_SUBDIVISIONS: Dict[str, SubdivisionSpecification] = {
    'IN-TG': SubdivisionSpecification(
        code='IN-TG',
        name='Telangana',
        country_code='IN',
        gst_state_code='36',
        gst_state_name='Telangana',
    ),
    'IN-MH': SubdivisionSpecification(
        code='IN-MH',
        name='Maharashtra',
        country_code='IN',
        gst_state_code='27',
        gst_state_name='Maharashtra',
    ),
    'IN-DL': SubdivisionSpecification(
        code='IN-DL',
        name='Delhi',
        country_code='IN',
        gst_state_code='07',
        gst_state_name='Delhi',
    ),
    'IN-KA': SubdivisionSpecification(
        code='IN-KA',
        name='Karnataka',
        country_code='IN',
        gst_state_code='29',
        gst_state_name='Karnataka',
    ),
    'IN-TN': SubdivisionSpecification(
        code='IN-TN',
        name='Tamil Nadu',
        country_code='IN',
        gst_state_code='33',
        gst_state_name='Tamil Nadu',
    ),
    'IN-GJ': SubdivisionSpecification(
        code='IN-GJ',
        name='Gujarat',
        country_code='IN',
        gst_state_code='24',
        gst_state_name='Gujarat',
    ),
    'IN-UP': SubdivisionSpecification(
        code='IN-UP',
        name='Uttar Pradesh',
        country_code='IN',
        gst_state_code='09',
        gst_state_name='Uttar Pradesh',
    ),
    'IN-WB': SubdivisionSpecification(
        code='IN-WB',
        name='West Bengal',
        country_code='IN',
        gst_state_code='19',
        gst_state_name='West Bengal',
    ),
    'IN-RJ': SubdivisionSpecification(
        code='IN-RJ',
        name='Rajasthan',
        country_code='IN',
        gst_state_code='08',
        gst_state_name='Rajasthan',
    ),
    'IN-KL': SubdivisionSpecification(
        code='IN-KL',
        name='Kerala',
        country_code='IN',
        gst_state_code='32',
        gst_state_name='Kerala',
    ),
    'IN-AP': SubdivisionSpecification(
        code='IN-AP',
        name='Andhra Pradesh',
        country_code='IN',
        gst_state_code='37',
        gst_state_name='Andhra Pradesh',
    ),
    'IN-MP': SubdivisionSpecification(
        code='IN-MP',
        name='Madhya Pradesh',
        country_code='IN',
        gst_state_code='23',
        gst_state_name='Madhya Pradesh',
    ),
    'IN-PB': SubdivisionSpecification(
        code='IN-PB',
        name='Punjab',
        country_code='IN',
        gst_state_code='03',
        gst_state_name='Punjab',
    ),
    'IN-HR': SubdivisionSpecification(
        code='IN-HR',
        name='Haryana',
        country_code='IN',
        gst_state_code='06',
        gst_state_name='Haryana',
    ),
    'IN-BR': SubdivisionSpecification(
        code='IN-BR',
        name='Bihar',
        country_code='IN',
        gst_state_code='10',
        gst_state_name='Bihar',
    ),
    'IN-OR': SubdivisionSpecification(
        code='IN-OR',
        name='Odisha',
        country_code='IN',
        gst_state_code='21',
        gst_state_name='Odisha',
    ),
    'IN-AS': SubdivisionSpecification(
        code='IN-AS',
        name='Assam',
        country_code='IN',
        gst_state_code='18',
        gst_state_name='Assam',
    ),
    'IN-JH': SubdivisionSpecification(
        code='IN-JH',
        name='Jharkhand',
        country_code='IN',
        gst_state_code='20',
        gst_state_name='Jharkhand',
    ),
    'IN-CT': SubdivisionSpecification(
        code='IN-CT',
        name='Chhattisgarh',
        country_code='IN',
        gst_state_code='22',
        gst_state_name='Chhattisgarh',
    ),
    'IN-UT': SubdivisionSpecification(
        code='IN-UT',
        name='Uttarakhand',
        country_code='IN',
        gst_state_code='05',
        gst_state_name='Uttarakhand',
    ),
    'IN-HP': SubdivisionSpecification(
        code='IN-HP',
        name='Himachal Pradesh',
        country_code='IN',
        gst_state_code='02',
        gst_state_name='Himachal Pradesh',
    ),
    'IN-GA': SubdivisionSpecification(
        code='IN-GA',
        name='Goa',
        country_code='IN',
        gst_state_code='30',
        gst_state_name='Goa',
    ),
    'IN-TR': SubdivisionSpecification(
        code='IN-TR',
        name='Tripura',
        country_code='IN',
        gst_state_code='16',
        gst_state_name='Tripura',
    ),
    'IN-ML': SubdivisionSpecification(
        code='IN-ML',
        name='Meghalaya',
        country_code='IN',
        gst_state_code='17',
        gst_state_name='Meghalaya',
    ),
    'IN-MN': SubdivisionSpecification(
        code='IN-MN',
        name='Manipur',
        country_code='IN',
        gst_state_code='14',
        gst_state_name='Manipur',
    ),
    'IN-NL': SubdivisionSpecification(
        code='IN-NL',
        name='Nagaland',
        country_code='IN',
        gst_state_code='13',
        gst_state_name='Nagaland',
    ),
    'IN-MZ': SubdivisionSpecification(
        code='IN-MZ',
        name='Mizoram',
        country_code='IN',
        gst_state_code='15',
        gst_state_name='Mizoram',
    ),
    'IN-AR': SubdivisionSpecification(
        code='IN-AR',
        name='Arunachal Pradesh',
        country_code='IN',
        gst_state_code='12',
        gst_state_name='Arunachal Pradesh',
    ),
    'IN-SK': SubdivisionSpecification(
        code='IN-SK',
        name='Sikkim',
        country_code='IN',
        gst_state_code='11',
        gst_state_name='Sikkim',
    ),
    'IN-JK': SubdivisionSpecification(
        code='IN-JK',
        name='Jammu and Kashmir',
        country_code='IN',
        gst_state_code='01',
        gst_state_name='Jammu and Kashmir',
    ),
    'IN-LA': SubdivisionSpecification(
        code='IN-LA',
        name='Ladakh',
        country_code='IN',
        gst_state_code='38',
        gst_state_name='Ladakh',
    ),
    'IN-CH': SubdivisionSpecification(
        code='IN-CH',
        name='Chandigarh',
        country_code='IN',
        gst_state_code='04',
        gst_state_name='Chandigarh',
    ),
    'IN-PY': SubdivisionSpecification(
        code='IN-PY',
        name='Puducherry',
        country_code='IN',
        gst_state_code='34',
        gst_state_name='Puducherry',
    ),
    'IN-AN': SubdivisionSpecification(
        code='IN-AN',
        name='Andaman and Nicobar Islands',
        country_code='IN',
        gst_state_code='35',
        gst_state_name='Andaman and Nicobar Islands',
    ),
    'IN-DH': SubdivisionSpecification(
        code='IN-DH',
        name='Dadra and Nagar Haveli and Daman and Diu',
        country_code='IN',
        gst_state_code='26',
        gst_state_name='Dadra and Nagar Haveli and Daman and Diu',
    ),
    'IN-LD': SubdivisionSpecification(
        code='IN-LD',
        name='Lakshadweep',
        country_code='IN',
        gst_state_code='31',
        gst_state_name='Lakshadweep',
    ),
}



# Full statutory 15-character GSTIN format:
# - 2 digits (state code, 01 to 38)
# - 10 characters PAN (5 letters, 4 digits, 1 letter)
# - 1 alphanumeric entity code (1-9, A-Z)
# - 1 letter 'Z'
# - 1 check digit/character (alphanumeric)
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")


def get_subdivision_by_gst_state_code(gst_state_code: Optional[str]) -> Optional[SubdivisionSpecification]:
    """Retrieves SubdivisionSpecification by 2-digit CBIC GST state code (e.g. '36' -> IN-TG)."""
    if not gst_state_code:
        return None
    code_str = str(gst_state_code).strip().zfill(2)
    for sub in INDIA_SUBDIVISIONS.values():
        if sub.gst_state_code == code_str:
            return sub
    return None


def derive_jurisdiction_from_tax_id(tax_id: Optional[str], country_code: Optional[str]) -> Optional[str]:
    """Infers canonical ISO 3166-2 jurisdiction code from tax identification number if possible.

    Requirements:
    - Enforces full statutory 15-character GSTIN structural format before extracting state code.
    - Validates that the first two digits correspond to an authoritative ISO 3166-2 subdivision.
    - Rejects truncated, malformed, or unsupported tax IDs.
    - Never derives jurisdiction from only the first two digits of an invalid tax ID.
    - Note: Structural format validation does NOT prove active registration on the GST portal.
    """
    if not tax_id or not country_code or not isinstance(tax_id, str):
        return None

    norm_country = str(country_code).strip().upper()
    clean_tax_id = tax_id.strip().upper()

    if norm_country in ('IN', 'INDIA', 'BHARAT'):
        if len(clean_tax_id) != 15:
            return None
        if not GSTIN_REGEX.match(clean_tax_id):
            return None
        sub = get_subdivision_by_gst_state_code(clean_tax_id[:2])
        if sub:
            return sub.code

    return None
