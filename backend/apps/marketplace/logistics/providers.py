from typing import Dict, Any, List, Optional
from apps.marketplace.models import CarrierChoices
from apps.marketplace.logistics.base import BaseLogisticsProvider


class ManualCarrierProvider(BaseLogisticsProvider):
    """
    Standard manual tracking adapter for local and custom couriers.
    Validates non-empty references and generates custom tracking URLs if provided.
    """
    provider_name = 'MANUAL'

    def validate_tracking_reference(self, tracking_number: str) -> bool:
        clean = (tracking_number or "").strip()
        return len(clean) >= 3

    def generate_tracking_url(self, tracking_number: str) -> str:
        return ""

    def get_supported_countries(self) -> List[str]:
        return ["IN", "GB", "GLOBAL"]


class BlueDartCarrierProvider(BaseLogisticsProvider):
    provider_name = CarrierChoices.BLUE_DART

    def validate_tracking_reference(self, tracking_number: str) -> bool:
        clean = (tracking_number or "").strip().replace('-', '').replace(' ', '').replace('_', '')
        # Blue Dart waybills are typically 8-11 alphanumeric characters
        return len(clean) >= 6 and clean.isalnum()

    def generate_tracking_url(self, tracking_number: str) -> str:
        return f"https://www.bluedart.com/tracking?handler=traking&action=custTrack&trackFor=0&trackNo={tracking_number.strip()}"

    def get_supported_countries(self) -> List[str]:
        return ["IN"]


class DelhiveryCarrierProvider(BaseLogisticsProvider):
    provider_name = CarrierChoices.DELHIVERY

    def validate_tracking_reference(self, tracking_number: str) -> bool:
        clean = (tracking_number or "").strip().replace('-', '').replace(' ', '').replace('_', '')
        return len(clean) >= 6 and clean.isalnum()

    def generate_tracking_url(self, tracking_number: str) -> str:
        return f"https://www.delhivery.com/track/package/{tracking_number.strip()}"

    def get_supported_countries(self) -> List[str]:
        return ["IN"]


class DTDCCarrierProvider(BaseLogisticsProvider):
    provider_name = CarrierChoices.DTDC

    def validate_tracking_reference(self, tracking_number: str) -> bool:
        clean = (tracking_number or "").strip().replace('-', '').replace(' ', '').replace('_', '')
        return len(clean) >= 6 and clean.isalnum()

    def generate_tracking_url(self, tracking_number: str) -> str:
        return f"https://www.dtdc.in/tracking/shipment-tracking.asp?trkType=awb&strCnno={tracking_number.strip()}"

    def get_supported_countries(self) -> List[str]:
        return ["IN"]


class RoyalMailCarrierProvider(BaseLogisticsProvider):
    provider_name = CarrierChoices.ROYAL_MAIL

    def validate_tracking_reference(self, tracking_number: str) -> bool:
        clean = (tracking_number or "").strip().replace('-', '').replace(' ', '').replace('_', '')
        return len(clean) >= 6 and clean.isalnum()

    def generate_tracking_url(self, tracking_number: str) -> str:
        return f"https://www.royalmail.com/track-your-item#/tracking-results/{tracking_number.strip()}"

    def get_supported_countries(self) -> List[str]:
        return ["GB"]


class DPDUKCarrierProvider(BaseLogisticsProvider):
    provider_name = CarrierChoices.DPD_UK

    def validate_tracking_reference(self, tracking_number: str) -> bool:
        clean = (tracking_number or "").strip().replace('-', '').replace(' ', '').replace('_', '')
        return len(clean) >= 6 and clean.isalnum()

    def generate_tracking_url(self, tracking_number: str) -> str:
        return f"https://track.dpd.co.uk/parcels/{tracking_number.strip()}"

    def get_supported_countries(self) -> List[str]:
        return ["GB"]


class EvriCarrierProvider(BaseLogisticsProvider):
    provider_name = CarrierChoices.EVRI

    def validate_tracking_reference(self, tracking_number: str) -> bool:
        clean = (tracking_number or "").strip().replace('-', '').replace(' ', '').replace('_', '')
        return len(clean) >= 6 and clean.isalnum()

    def generate_tracking_url(self, tracking_number: str) -> str:
        return f"https://www.evri.com/track-a-parcel/{tracking_number.strip()}"

    def get_supported_countries(self) -> List[str]:
        return ["GB"]


class DHLCarrierProvider(BaseLogisticsProvider):
    provider_name = CarrierChoices.DHL

    def validate_tracking_reference(self, tracking_number: str) -> bool:
        clean = (tracking_number or "").strip().replace('-', '').replace(' ', '').replace('_', '')
        return len(clean) >= 6 and clean.isalnum()

    def generate_tracking_url(self, tracking_number: str) -> str:
        return f"https://www.dhl.com/en/express/tracking.html?AWB={tracking_number.strip()}"

    def get_supported_countries(self) -> List[str]:
        return ["IN", "GB", "GLOBAL"]


class FedExCarrierProvider(BaseLogisticsProvider):
    provider_name = CarrierChoices.FEDEX

    def validate_tracking_reference(self, tracking_number: str) -> bool:
        clean = (tracking_number or "").strip().replace('-', '').replace(' ', '').replace('_', '')
        return len(clean) >= 6 and clean.isalnum()

    def generate_tracking_url(self, tracking_number: str) -> str:
        return f"https://www.fedex.com/fedextrack/?trknbr={tracking_number.strip()}"

    def get_supported_countries(self) -> List[str]:
        return ["IN", "GB", "GLOBAL"]


class UPSCarrierProvider(BaseLogisticsProvider):
    provider_name = CarrierChoices.UPS

    def validate_tracking_reference(self, tracking_number: str) -> bool:
        clean = (tracking_number or "").strip().replace('-', '').replace(' ', '').replace('_', '')
        return len(clean) >= 6 and clean.isalnum()

    def generate_tracking_url(self, tracking_number: str) -> str:
        return f"https://www.ups.com/track?tracknum={tracking_number.strip()}"

    def get_supported_countries(self) -> List[str]:
        return ["IN", "GB", "GLOBAL"]


# Registry of supported carrier adapters
CARRIER_PROVIDERS: Dict[str, BaseLogisticsProvider] = {
    CarrierChoices.BLUE_DART: BlueDartCarrierProvider(),
    CarrierChoices.DELHIVERY: DelhiveryCarrierProvider(),
    CarrierChoices.DTDC: DTDCCarrierProvider(),
    CarrierChoices.ROYAL_MAIL: RoyalMailCarrierProvider(),
    CarrierChoices.DPD_UK: DPDUKCarrierProvider(),
    CarrierChoices.EVRI: EvriCarrierProvider(),
    CarrierChoices.DHL: DHLCarrierProvider(),
    CarrierChoices.FEDEX: FedExCarrierProvider(),
    CarrierChoices.UPS: UPSCarrierProvider(),
    CarrierChoices.OTHER: ManualCarrierProvider(),
}


def get_carrier_provider(carrier_code: str) -> BaseLogisticsProvider:
    """Returns the adapter for a given carrier code, falling back to ManualCarrierProvider."""
    return CARRIER_PROVIDERS.get(carrier_code, ManualCarrierProvider())


def get_available_carriers_for_country(country_iso: str) -> List[Dict[str, str]]:
    """Returns list of carriers appropriate for destination country (IN or GB)."""
    norm_country = (country_iso or "").strip().upper()
    results = []
    for code, label in CarrierChoices.choices:
        provider = CARRIER_PROVIDERS.get(code)
        if not provider:
            results.append({"code": code, "name": label})
            continue
        supported = provider.get_supported_countries()
        if "GLOBAL" in supported or norm_country in supported:
            results.append({"code": code, "name": label})
    return results
