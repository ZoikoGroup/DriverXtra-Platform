from rest_framework import generics, permissions, status, views
from rest_framework.response import Response
from django.db.models import Q
from common.permissions import IsPlatformStaff
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    PartCategory,
    Part,
    PartCompatibility,
    FitmentTypeChoices,
)
from apps.catalogue.serializers import (
    VehicleMakeSerializer,
    VehicleModelSerializer,
    VehicleVariantSerializer,
    PartCategorySerializer,
    PartSerializer,
    PartCompatibilitySerializer,
    FitmentCheckSerializer,
)


class VehicleMakeListCreateView(generics.ListCreateAPIView):
    """List vehicle makes (public/auth) or add a make (admin/staff only).

    GET /api/v1/catalogue/makes/
    POST /api/v1/catalogue/makes/
    """
    queryset = VehicleMake.objects.filter(is_active=True).prefetch_related('models')
    serializer_class = VehicleMakeSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsPlatformStaff()]
        return [permissions.AllowAny()]


class VehicleModelListCreateView(generics.ListCreateAPIView):
    """List vehicle models filtered by make, or create model (admin/staff only).

    GET /api/v1/catalogue/models/?make_id=<uuid>
    POST /api/v1/catalogue/models/
    """
    serializer_class = VehicleModelSerializer

    def get_queryset(self):
        queryset = VehicleModel.objects.filter(is_active=True).select_related('make').prefetch_related('variants')
        make_id = self.request.query_params.get('make_id') or self.request.query_params.get('make')
        if make_id:
            queryset = queryset.filter(make_id=make_id)
        return queryset

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsPlatformStaff()]
        return [permissions.AllowAny()]


class VehicleVariantListCreateView(generics.ListCreateAPIView):
    """List vehicle variants filtered by model or year, or create variant (admin/staff only).

    GET /api/v1/catalogue/variants/?model_id=<uuid>&year=2021
    POST /api/v1/catalogue/variants/
    """
    serializer_class = VehicleVariantSerializer

    def get_queryset(self):
        queryset = VehicleVariant.objects.filter(is_active=True).select_related('model', 'model__make')
        model_id = self.request.query_params.get('model_id') or self.request.query_params.get('model')
        year = self.request.query_params.get('year')
        if model_id:
            queryset = queryset.filter(model_id=model_id)
        if year:
            queryset = queryset.filter(year=year)
        return queryset

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsPlatformStaff()]
        return [permissions.AllowAny()]


class VehicleVariantDetailView(generics.RetrieveAPIView):
    """Retrieve details for a specific vehicle variant.

    GET /api/v1/catalogue/variants/<id>/
    """
    queryset = VehicleVariant.objects.filter(is_active=True).select_related('model', 'model__make')
    serializer_class = VehicleVariantSerializer
    lookup_field = 'id'
    permission_classes = [permissions.AllowAny]


class PartCategoryListCreateView(generics.ListCreateAPIView):
    """List part categories hierarchy or create category (admin/staff only).

    GET /api/v1/catalogue/categories/
    POST /api/v1/catalogue/categories/
    """
    serializer_class = PartCategorySerializer

    def get_queryset(self):
        queryset = PartCategory.objects.filter(is_active=True).select_related('parent')
        # If top_only=true, only return root categories (subcategories will be nested)
        if self.request.query_params.get('root_only', 'false').lower() in ('true', '1'):
            queryset = queryset.filter(parent__isnull=True)
        return queryset

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsPlatformStaff()]
        return [permissions.AllowAny()]


class PartListCreateView(generics.ListCreateAPIView):
    """List spare parts catalogue with category, brand, search, or add part (admin/staff only).

    GET /api/v1/catalogue/parts/?category_id=<uuid>&brand=Brembo&search=rotor
    POST /api/v1/catalogue/parts/
    """
    serializer_class = PartSerializer

    def get_queryset(self):
        queryset = Part.objects.filter(is_active=True).select_related('category').prefetch_related('compatibilities')
        category_id = self.request.query_params.get('category_id') or self.request.query_params.get('category')
        category_slug = self.request.query_params.get('category_slug')
        brand = self.request.query_params.get('brand')
        search = self.request.query_params.get('search')

        if category_id:
            queryset = queryset.filter(Q(category_id=category_id) | Q(category__parent_id=category_id))
        elif category_slug:
            queryset = queryset.filter(Q(category__slug=category_slug) | Q(category__parent__slug=category_slug))

        if brand:
            queryset = queryset.filter(brand__iexact=brand)

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(mpn__icontains=search) | Q(brand__icontains=search)
            )

        return queryset

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsPlatformStaff()]
        return [permissions.AllowAny()]


class PartDetailView(generics.RetrieveAPIView):
    """Retrieve full detail for a canonical part in the catalogue.

    GET /api/v1/catalogue/parts/<id>/
    """
    queryset = Part.objects.filter(is_active=True).select_related('category').prefetch_related('compatibilities')
    serializer_class = PartSerializer
    lookup_field = 'id'
    permission_classes = [permissions.AllowAny]


class PartCompatibilityListCreateView(generics.ListCreateAPIView):
    """List or add part-to-vehicle compatibility mappings.

    GET /api/v1/catalogue/compatibility/?part_id=<uuid>&variant_id=<uuid>
    POST /api/v1/catalogue/compatibility/
    """
    serializer_class = PartCompatibilitySerializer

    def get_queryset(self):
        queryset = PartCompatibility.objects.select_related('part', 'vehicle_variant', 'vehicle_variant__model', 'vehicle_variant__model__make')
        part_id = self.request.query_params.get('part_id') or self.kwargs.get('id')
        variant_id = self.request.query_params.get('variant_id') or self.request.query_params.get('vehicle_variant_id')

        if part_id:
            queryset = queryset.filter(part_id=part_id)
        if variant_id:
            queryset = queryset.filter(vehicle_variant_id=variant_id)

        return queryset

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsPlatformStaff()]
        return [permissions.AllowAny()]


class FitmentEvaluationView(views.APIView):
    """Evaluate compatibility between a specific part and vehicle variant.

    GET /api/v1/catalogue/fitment/?part_id=<uuid>&vehicle_variant_id=<uuid>
    POST /api/v1/catalogue/fitment/
    """
    permission_classes = [permissions.AllowAny]

    def _evaluate(self, part_id, variant_id):
        part = generics.get_object_or_404(Part, id=part_id, is_active=True)
        variant = generics.get_object_or_404(VehicleVariant, id=variant_id, is_active=True)

        # 1. Check for verified engineering compatibility record
        compatibility = PartCompatibility.objects.filter(
            part=part,
            vehicle_variant=variant,
        ).first()

        if compatibility:
            is_compatible = compatibility.fitment_type in (
                FitmentTypeChoices.CONFIRMED_FIT,
                FitmentTypeChoices.CONDITIONAL_FIT,
            )
            confidence = "HIGH" if compatibility.fitment_type == FitmentTypeChoices.CONFIRMED_FIT else "MEDIUM"
            evidence_level = "VERIFIED_MAPPING"
            reason = (
                compatibility.qualifications
                or compatibility.notes
                or "Confirmed fit verified against vehicle engineering database."
            )
            return {
                "outcome": compatibility.fitment_type,
                "status": compatibility.fitment_type,
                "fitment_type": compatibility.fitment_type,
                "is_compatible": is_compatible,
                "confidence": confidence,
                "evidence_level": evidence_level,
                "reason": reason,
                "qualifications": compatibility.qualifications or compatibility.notes or "Compatibility record verified in canonical database.",
                "part_id": str(part.id),
                "part_name": part.name,
                "part_mpn": part.mpn,
                "part_brand": part.brand,
                "vehicle_variant_id": str(variant.id),
                "vehicle_display": variant.display_name,
            }

        # 2. Universal Part Handling:
        # Universal parts must not automatically receive CONFIRMED_FIT with HIGH confidence
        # solely because they are marked universal by a source. Return CONDITIONAL_FIT with unverified declaration.
        if part.is_universal:
            return {
                "outcome": FitmentTypeChoices.CONDITIONAL_FIT,
                "status": FitmentTypeChoices.CONDITIONAL_FIT,
                "fitment_type": FitmentTypeChoices.CONDITIONAL_FIT,
                "is_compatible": True,
                "confidence": "LOW",
                "evidence_level": "UNVERIFIED_UNIVERSAL_DECLARATION",
                "reason": "Component is self-declared universal by supplier, but vehicle-specific clearance and capacity are not independently verified. Check handbook before fitting.",
                "qualifications": "Universal component declaration; independent vehicle clearance and specification check required.",
                "part_id": str(part.id),
                "part_name": part.name,
                "part_mpn": part.mpn,
                "part_brand": part.brand,
                "vehicle_variant_id": str(variant.id),
                "vehicle_display": variant.display_name,
            }

        # 3. Missing record: strict rule to never assume or guarantee compatibility
        return {
            "outcome": FitmentTypeChoices.UNKNOWN,
            "status": FitmentTypeChoices.UNKNOWN,
            "fitment_type": FitmentTypeChoices.UNKNOWN,
            "is_compatible": False,
            "confidence": "NONE",
            "evidence_level": "NO_EVIDENCE",
            "reason": "No confirmed compatibility record found for this part and vehicle variant. Consult vehicle handbook or workshop specialist.",
            "qualifications": "No verified compatibility record found for this part and vehicle variant combination. Consult vehicle handbook or workshop specialist.",
            "part_id": str(part.id),
            "part_name": part.name,
            "part_mpn": part.mpn,
            "part_brand": part.brand,
            "vehicle_variant_id": str(variant.id),
            "vehicle_display": variant.display_name,
        }

    def get(self, request):
        part_id = request.query_params.get('part_id')
        variant_id = request.query_params.get('vehicle_variant_id') or request.query_params.get('variant_id')

        if not part_id or not variant_id:
            return Response(
                {"status": "error", "message": "Both 'part_id' and 'vehicle_variant_id' query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = self._evaluate(part_id, variant_id)
        return Response(result, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = FitmentCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = self._evaluate(
            serializer.validated_data['part_id'],
            serializer.validated_data['vehicle_variant_id'],
        )
        return Response(result, status=status.HTTP_200_OK)
