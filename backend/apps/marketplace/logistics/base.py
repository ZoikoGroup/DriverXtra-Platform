from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from decimal import Decimal


class BaseLogisticsProvider(ABC):
    """
    Abstract interface for logistics carriers and delivery tracking providers.
    Supports domestic and international carriers (Blue Dart, Delhivery, Royal Mail, etc.).
    """
    provider_name: str = 'MANUAL'

    @abstractmethod
    def validate_tracking_reference(self, tracking_number: str) -> bool:
        """Validates tracking reference format for this carrier."""
        pass

    @abstractmethod
    def generate_tracking_url(self, tracking_number: str) -> str:
        """Constructs a direct public tracking URL for the carrier."""
        pass

    @abstractmethod
    def get_supported_countries(self) -> List[str]:
        """Returns list of ISO country codes supported by this carrier (e.g. ['IN'], ['GB'])."""
        pass
