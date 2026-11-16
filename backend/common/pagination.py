"""
Scalable enterprise pagination utilities for DriverXtra.
Supports 20 (default), 50, and 100 records per page with database-level slicing.
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as DRFValidationError


class ScalableAdminPagination(PageNumberPagination):
    """
    Standard scalable pagination class for enterprise account listings.
    Supports 20 (default), 50, and 100 records per page.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_page_size(self, request):
        if self.page_size_query_param:
            val = request.query_params.get(self.page_size_query_param)
            if val is not None:
                try:
                    val_int = int(val)
                except (ValueError, TypeError):
                    raise DRFValidationError({"page_size": "Page size must be a positive integer."})
                if val_int < 1:
                    raise DRFValidationError({"page_size": "Page size must be at least 1."})
                return min(val_int, self.max_page_size)
        return self.page_size

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'page_size': self.get_page_size(self.request),
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })

