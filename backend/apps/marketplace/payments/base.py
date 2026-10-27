from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional


class BasePaymentProvider(ABC):
    """
    Abstract interface for international and country-specific online payment gateways.
    """
    provider_name: str

    @abstractmethod
    def create_payment_session(
        self,
        order: Any,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates an authoritative payment order or session with the external provider.
        Returns dictionary containing session credentials, client secrets, and transaction IDs.
        """
        pass

    @abstractmethod
    def verify_payment(
        self,
        order: Any,
        payload: Dict[str, Any],
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Cryptographically verifies the payment confirmation payload from the client/provider.
        Returns (is_valid, payment_id_or_error, extra_details).
        """
        pass

    @abstractmethod
    def verify_webhook(
        self,
        request_body: bytes,
        headers: Dict[str, str],
    ) -> Tuple[bool, Optional[str], Optional[str], Dict[str, Any]]:
        """
        Validates the webhook signature from the provider.
        Returns (is_valid, event_id, event_type, payload).
        """
        pass
