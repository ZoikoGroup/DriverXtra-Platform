"""API views and serializers for DriverXtra regional configuration."""

from rest_framework import views, status, permissions
from rest_framework.response import Response
from .specs import COUNTRY_SPECIFICATIONS, get_supported_country_codes


class RegionalConfigListView(views.APIView):
    """Authoritative platform regional configuration discovery endpoint.

    GET /api/v1/regions/
    Exposes supported countries, default currencies, odometer units, tax schemes,
    and valid subdivisions for frontend and API consumers.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        data = []
        for code in get_supported_country_codes():
            spec = COUNTRY_SPECIFICATIONS[code]
            data.append({
                'country_code': spec.country_code.value,
                'name': spec.name,
                'default_currency': spec.default_currency.value,
                'default_odometer_unit': spec.default_odometer_unit.value,
                'default_jurisdiction': spec.default_jurisdiction,
                'supported_currencies': [c.value for c in spec.supported_currencies],
                'supported_odometer_units': [u.value for u in spec.supported_odometer_units],
                'tax_config': spec.tax_config.get_tax_summary(),
                'payment_config': spec.payment_config.get_payment_summary(),
                'subdivisions': [
                    {
                        'code': sub.code,
                        'name': sub.name,
                        'country_code': sub.country_code,
                        'gst_state_code': sub.gst_state_code,
                        'gst_state_name': sub.gst_state_name,
                    }
                    for sub in spec.subdivisions.values()
                ],
            })

        return Response({'supported_countries': data}, status=status.HTTP_200_OK)

