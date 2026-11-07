from rest_framework import status
from rest_framework.exceptions import APIException


class CommercialRuleViolation(APIException):
    """A commercial control rule blocked the operation.

    Rendered by the project's exception handler as
    {"status": "error", "code": <http>, "message": <message>, "details": {"detail": ..., "rule": <RULE_CODE>}}.
    """

    status_code = status.HTTP_409_CONFLICT
    default_code = 'commercial_rule_violation'

    def __init__(self, rule: str, message: str, status_code: int = None):
        self.rule = rule
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        super().__init__({'detail': message, 'rule': rule})


class ImmutableCommercialRecordError(ValueError):
    """Raised when code attempts to mutate or delete an append-only commercial record."""
