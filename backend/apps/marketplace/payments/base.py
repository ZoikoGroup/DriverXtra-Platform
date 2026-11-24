from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional


class BasePaymentProvider(ABC):
    """
    Abstract interface for international and country-specific online payment gateways.
    """
    provider_name: str
    # ISO 4217 codes this provider integration can actually charge. Single source of truth used both by
    # checkout availability (PaymentService) and by the provider's own currency guards.
    supported_currencies: frozenset = frozenset()

    def supports_currency(self, currency: Optional[str]) -> bool:
        """True only if this integration can charge the given ISO 4217 currency."""
        return (currency or '').strip().upper() in self.supported_currencies

    @property
    def is_ready(self) -> bool:
        """True when the provider can create real or permitted test sessions in this environment."""
        if getattr(self, 'test_mode', False):
            return True

        if not getattr(self, 'is_configured', False):
            return False

        # In production (test_mode=False), test credentials (rzp_test_..., sk_test_...) cannot process live payments
        clean_key = getattr(self, 'key_id', '') or getattr(self, 'publishable_key', '') or ''
        clean_secret = getattr(self, 'key_secret', '') or getattr(self, 'secret_key', '') or ''
        clean_key = clean_key.strip().lower()
        clean_secret = clean_secret.strip().lower()
        if clean_key.startswith(('rzp_test_', 'pk_test_')) or clean_secret.startswith(('rzp_test_', 'sk_test_')):
            return False

        return True

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

    @abstractmethod
    def issue_refund(
        self,
        payment_reference: str,
        amount: Any,
        currency: str,
        reason: str = '',
        refund_number: str = '',
        notes: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Initiates or registers an authentic refund with the gateway provider.
        Returns (is_success, gateway_refund_id_or_error, extra_details).
        """
        pass

    @abstractmethod
    def inquire_refund(
        self,
        payment_reference: str,
        refund_number: str,
        gateway_refund_id: Optional[str] = None,
    ) -> Tuple[str, Optional[str], Dict[str, Any]]:
        """
        Inquires the provider's authoritative refund state for an ambiguous or timed-out refund.
        Returns:
            status: 'SUCCEEDED' | 'FAILED' | 'PROCESSING' | 'NOT_FOUND' | 'UNKNOWN'
            gateway_refund_id_or_error: Gateway refund ID if found, or error message
            extra_details: Raw payload or diagnostics from provider
        """
        pass


