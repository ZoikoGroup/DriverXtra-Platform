"""Exceptions for the DriverXtra tax calculation engine."""


class TaxEngineError(Exception):
    """Base exception for all tax engine operational and calculation errors."""
    pass


class TaxAuthorizationError(TaxEngineError):
    """Raised when a supplier attempts to levy or invoice tax without legal authorization."""
    pass


class UnclassifiedItemError(TaxEngineError):
    """Raised when a line item lacks a verified statutory HSN or SAC classification."""
    pass


class AmbiguousPlaceOfSupplyError(TaxEngineError):
    """Raised when conflicting evidence prevents lawful determination of place of supply."""
    pass


class BlockedInvoiceError(TaxEngineError):
    """Raised when invoicing is blocked due to unverified, suspended, or provisional state."""
    pass

