from rest_framework import generics, permissions, status, views
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from common.permissions import IsPlatformStaff, HasPermission
from platform_core.audit.writer import record_audit_entry
from apps.catalogue.models import (
    VehicleMake,
    VehicleModel,
    VehicleVariant,
    PartCategory,
    Part,
    PartCompatibility,
    FitmentTypeChoices,
    VehicleCatalogueApplication,
    CataloguePhotoProposal,
    CatalogueApplicationStatusChoices,
)
from apps.catalogue.serializers import (
    VehicleMakeSerializer,
    VehicleModelSerializer,
    VehicleVariantSerializer,
    PartCategorySerializer,
    PartSerializer,
    PartCompatibilitySerializer,
    FitmentCheckSerializer,
    VehicleCatalogueApplicationSerializer,
    VehicleCatalogueApplicationReviewSerializer,
    CataloguePhotoProposalSerializer,
    CataloguePhotoProposalReviewSerializer,
)
from apps.catalogue.services import evaluate_canonical_fitment


def log_catalogue_audit(request, event_type: str, action: str, resource_type: str, resource_id: str, metadata: dict = None):
    corr_id = getattr(request, 'correlation_id', '')
    actor_id = getattr(request.user, 'id', None) if (request.user and request.user.is_authenticated) else None
    record_audit_entry(
        event_type=event_type,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        actor_id=actor_id,
        correlation_id=corr_id,
        metadata=metadata or {},
    )


class VehicleMakeListCreateView(generics.ListCreateAPIView):
    """List vehicle makes (public/auth) or add a make (staff with catalogue.manage).

    GET /api/v1/catalogue/makes/
    POST /api/v1/catalogue/makes/
    """
    queryset = VehicleMake.objects.filter(is_active=True).prefetch_related('models')
    serializer_class = VehicleMakeSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsPlatformStaff(), HasPermission('catalogue.manage')()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        instance = serializer.save()
        log_catalogue_audit(
            self.request,
            event_type="catalogue.make.created",
            action="catalogue:make.create",
            resource_type="VehicleMake",
            resource_id=instance.id,
            metadata={"name": instance.name},
        )


class VehicleMakeDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve details, update or deactivate a vehicle make.

    GET /api/v1/catalogue/makes/<id>/
    PATCH /api/v1/catalogue/makes/<id>/
    """
    serializer_class = VehicleMakeSerializer
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        if user and user.is_authenticated and (user.is_staff or user.has_role('ADMIN')):
            return VehicleMake.objects.all().prefetch_related('models')
        return VehicleMake.objects.filter(is_active=True).prefetch_related('models')

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT'):
            return [IsPlatformStaff(), HasPermission('catalogue.manage')()]
        return [permissions.AllowAny()]

    def perform_update(self, serializer):
        old_active = serializer.instance.is_active
        instance = serializer.save()
        changed = list(serializer.validated_data.keys())
        meta = {"changed_fields": changed, "name": instance.name}
        event = "catalogue.make.updated"
        if old_active is True and instance.is_active is False:
            event = "catalogue.make.deactivated"
            meta["deactivated"] = True
        log_catalogue_audit(
            self.request,
            event_type=event,
            action="catalogue:make.update",
            resource_type="VehicleMake",
            resource_id=instance.id,
            metadata=meta,
        )


class VehicleModelListCreateView(generics.ListCreateAPIView):
    """List vehicle models filtered by make, or create model (staff with catalogue.manage).

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
            return [IsPlatformStaff(), HasPermission('catalogue.manage')()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        instance = serializer.save()
        log_catalogue_audit(
            self.request,
            event_type="catalogue.model.created",
            action="catalogue:model.create",
            resource_type="VehicleModel",
            resource_id=instance.id,
            metadata={"name": instance.name, "make_id": str(instance.make_id)},
        )


class VehicleModelDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve details, update or deactivate a vehicle model.

    GET /api/v1/catalogue/models/<id>/
    PATCH /api/v1/catalogue/models/<id>/
    """
    serializer_class = VehicleModelSerializer
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        if user and user.is_authenticated and (user.is_staff or user.has_role('ADMIN')):
            return VehicleModel.objects.all().select_related('make').prefetch_related('variants')
        return VehicleModel.objects.filter(is_active=True).select_related('make').prefetch_related('variants')

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT'):
            return [IsPlatformStaff(), HasPermission('catalogue.manage')()]
        return [permissions.AllowAny()]

    def perform_update(self, serializer):
        old_active = serializer.instance.is_active
        instance = serializer.save()
        changed = list(serializer.validated_data.keys())
        meta = {"changed_fields": changed, "name": instance.name}
        event = "catalogue.model.updated"
        if old_active is True and instance.is_active is False:
            event = "catalogue.model.deactivated"
            meta["deactivated"] = True
        log_catalogue_audit(
            self.request,
            event_type=event,
            action="catalogue:model.update",
            resource_type="VehicleModel",
            resource_id=instance.id,
            metadata=meta,
        )


class VehicleVariantListCreateView(generics.ListCreateAPIView):
    """List vehicle variants filtered by model or year, or create variant (staff with catalogue.manage).

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
            return [IsPlatformStaff(), HasPermission('catalogue.manage')()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        instance = serializer.save()
        log_catalogue_audit(
            self.request,
            event_type="catalogue.variant.created",
            action="catalogue:variant.create",
            resource_type="VehicleVariant",
            resource_id=instance.id,
            metadata={"name": instance.name, "model_id": str(instance.model_id), "year": instance.year},
        )


class VehicleVariantDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve details, update or deactivate a specific vehicle variant.

    GET /api/v1/catalogue/variants/<id>/
    PATCH /api/v1/catalogue/variants/<id>/
    """
    serializer_class = VehicleVariantSerializer
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        if user and user.is_authenticated and (user.is_staff or user.has_role('ADMIN')):
            return VehicleVariant.objects.all().select_related('model', 'model__make')
        return VehicleVariant.objects.filter(is_active=True).select_related('model', 'model__make')

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT'):
            return [IsPlatformStaff(), HasPermission('catalogue.manage')()]
        return [permissions.AllowAny()]

    def perform_update(self, serializer):
        old_active = serializer.instance.is_active
        instance = serializer.save()
        changed = list(serializer.validated_data.keys())
        meta = {"changed_fields": changed, "display_name": instance.display_name}
        event = "catalogue.variant.updated"
        if old_active is True and instance.is_active is False:
            event = "catalogue.variant.deactivated"
            meta["deactivated"] = True
        log_catalogue_audit(
            self.request,
            event_type=event,
            action="catalogue:variant.update",
            resource_type="VehicleVariant",
            resource_id=instance.id,
            metadata=meta,
        )


class PartCategoryListCreateView(generics.ListCreateAPIView):
    """List part categories hierarchy or create category (staff with catalogue.manage).

    GET /api/v1/catalogue/categories/
    POST /api/v1/catalogue/categories/
    """
    serializer_class = PartCategorySerializer

    def get_queryset(self):
        queryset = PartCategory.objects.filter(is_active=True).select_related('parent')
        if self.request.query_params.get('root_only', 'false').lower() in ('true', '1'):
            queryset = queryset.filter(parent__isnull=True)
        return queryset

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsPlatformStaff(), HasPermission('catalogue.manage')()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        instance = serializer.save()
        log_catalogue_audit(
            self.request,
            event_type="catalogue.category.created",
            action="catalogue:category.create",
            resource_type="PartCategory",
            resource_id=instance.id,
            metadata={"name": instance.name, "slug": instance.slug},
        )


class PartCategoryDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve details, update or deactivate a part category.

    GET /api/v1/catalogue/categories/<id>/
    PATCH /api/v1/catalogue/categories/<id>/
    """
    serializer_class = PartCategorySerializer
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        if user and user.is_authenticated and (user.is_staff or user.has_role('ADMIN')):
            return PartCategory.objects.all().select_related('parent')
        return PartCategory.objects.filter(is_active=True).select_related('parent')

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT'):
            return [IsPlatformStaff(), HasPermission('catalogue.manage')()]
        return [permissions.AllowAny()]

    def perform_update(self, serializer):
        old_active = serializer.instance.is_active
        instance = serializer.save()
        changed = list(serializer.validated_data.keys())
        meta = {"changed_fields": changed, "slug": instance.slug}
        event = "catalogue.category.updated"
        if old_active is True and instance.is_active is False:
            event = "catalogue.category.deactivated"
            meta["deactivated"] = True
        log_catalogue_audit(
            self.request,
            event_type=event,
            action="catalogue:category.update",
            resource_type="PartCategory",
            resource_id=instance.id,
            metadata=meta,
        )


class PartListCreateView(generics.ListCreateAPIView):
    """List spare parts catalogue or add part (staff with catalogue.manage).

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
            return [IsPlatformStaff(), HasPermission('catalogue.manage')()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        instance = serializer.save()
        log_catalogue_audit(
            self.request,
            event_type="catalogue.part.created",
            action="catalogue:part.create",
            resource_type="Part",
            resource_id=instance.id,
            metadata={"brand": instance.brand, "mpn": instance.mpn},
        )


class PartDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve full detail, update or deactivate a canonical part in the catalogue.

    GET /api/v1/catalogue/parts/<id>/
    PATCH /api/v1/catalogue/parts/<id>/
    """
    serializer_class = PartSerializer
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        if user and user.is_authenticated and (user.is_staff or user.has_role('ADMIN')):
            return Part.objects.all().select_related('category').prefetch_related('compatibilities')
        return Part.objects.filter(is_active=True).select_related('category').prefetch_related('compatibilities')

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT'):
            return [IsPlatformStaff(), HasPermission('catalogue.manage')()]
        return [permissions.AllowAny()]

    def perform_update(self, serializer):
        old_active = serializer.instance.is_active
        instance = serializer.save()
        changed = list(serializer.validated_data.keys())
        meta = {"changed_fields": changed, "brand": instance.brand, "mpn": instance.mpn}
        event = "catalogue.part.updated"
        if old_active is True and instance.is_active is False:
            event = "catalogue.part.deactivated"
            meta["deactivated"] = True
        log_catalogue_audit(
            self.request,
            event_type=event,
            action="catalogue:part.update",
            resource_type="Part",
            resource_id=instance.id,
            metadata=meta,
        )


class PartCompatibilityListCreateView(generics.ListCreateAPIView):
    """List or add part-to-vehicle compatibility mappings.

    GET /api/v1/catalogue/compatibility/?part_id=<uuid>&variant_id=<uuid>
    POST /api/v1/catalogue/compatibility/
    """
    serializer_class = PartCompatibilitySerializer

    def get_queryset(self):
        queryset = PartCompatibility.objects.select_related(
            'part', 'vehicle_variant', 'vehicle_variant__model', 'vehicle_variant__model__make'
        )
        part_id = self.request.query_params.get('part_id') or self.kwargs.get('id')
        variant_id = self.request.query_params.get('variant_id') or self.request.query_params.get('vehicle_variant_id')

        if part_id:
            queryset = queryset.filter(part_id=part_id)
        if variant_id:
            queryset = queryset.filter(vehicle_variant_id=variant_id)

        return queryset

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsPlatformStaff(), HasPermission('catalogue.manage')()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        instance = serializer.save()
        log_catalogue_audit(
            self.request,
            event_type="catalogue.compatibility.created",
            action="catalogue:compatibility.create",
            resource_type="PartCompatibility",
            resource_id=instance.id,
            metadata={
                "part_id": str(instance.part_id),
                "vehicle_variant_id": str(instance.vehicle_variant_id),
                "fitment_type": instance.fitment_type,
            },
        )


class PartCompatibilityDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update (fitment_type, qualifications, notes), or delete a compatibility record.

    GET /api/v1/catalogue/compatibility/<id>/
    PATCH /api/v1/catalogue/compatibility/<id>/
    DELETE /api/v1/catalogue/compatibility/<id>/
    """
    queryset = PartCompatibility.objects.select_related(
        'part', 'vehicle_variant', 'vehicle_variant__model', 'vehicle_variant__model__make'
    )
    serializer_class = PartCompatibilitySerializer
    lookup_field = 'id'

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT', 'DELETE'):
            return [IsPlatformStaff(), HasPermission('catalogue.manage')()]
        return [permissions.AllowAny()]

    def perform_update(self, serializer):
        old_fitment = serializer.instance.fitment_type
        instance = serializer.save()
        changed = list(serializer.validated_data.keys())
        meta = {
            "changed_fields": changed,
            "part_id": str(instance.part_id),
            "vehicle_variant_id": str(instance.vehicle_variant_id),
        }
        if 'fitment_type' in changed:
            meta["old_fitment_type"] = old_fitment
            meta["new_fitment_type"] = instance.fitment_type
        log_catalogue_audit(
            self.request,
            event_type="catalogue.compatibility.updated",
            action="catalogue:compatibility.update",
            resource_type="PartCompatibility",
            resource_id=instance.id,
            metadata=meta,
        )

    def perform_destroy(self, instance):
        part_id = str(instance.part_id)
        variant_id = str(instance.vehicle_variant_id)
        instance_id = str(instance.id)
        instance.delete()
        log_catalogue_audit(
            self.request,
            event_type="catalogue.compatibility.deleted",
            action="catalogue:compatibility.delete",
            resource_type="PartCompatibility",
            resource_id=instance_id,
            metadata={"part_id": part_id, "vehicle_variant_id": variant_id},
        )


class FitmentEvaluationView(views.APIView):
    """Evaluate compatibility between a specific part and vehicle variant.

    GET /api/v1/catalogue/fitment/?part_id=<uuid>&vehicle_variant_id=<uuid>
    POST /api/v1/catalogue/fitment/
    """
    permission_classes = [permissions.AllowAny]

    def _evaluate(self, part_id, variant_id):
        part = generics.get_object_or_404(Part, id=part_id, is_active=True)
        variant = generics.get_object_or_404(VehicleVariant, id=variant_id, is_active=True)
        return evaluate_canonical_fitment(part, variant)

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


class VehicleCatalogueApplicationListCreateView(generics.ListCreateAPIView):
    """List vehicle catalogue applications or submit a new vehicle for catalogue inclusion.

    GET /api/v1/catalogue/applications/
    POST /api/v1/catalogue/applications/
    """
    serializer_class = VehicleCatalogueApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = VehicleCatalogueApplication.objects.select_related(
            'seller', 'make', 'reviewed_by', 'created_model', 'created_variant'
        )
        is_reviewer = (
            user.is_staff
            or user.has_role('ADMIN')
            or user.has_role('MARKETPLACE_ADMIN')
            or user.has_role('STAFF')
        )
        if not is_reviewer:
            qs = qs.filter(seller=user)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param.upper())
        return qs

    def perform_create(self, serializer):
        instance = serializer.save(seller=self.request.user)
        log_catalogue_audit(
            self.request,
            event_type="catalogue.application.submitted",
            action="catalogue:application.submit",
            resource_type="VehicleCatalogueApplication",
            resource_id=instance.id,
            metadata={"make_name": instance.make_name, "model_name": instance.model_name},
        )


class VehicleCatalogueApplicationDetailView(generics.RetrieveAPIView):
    """Retrieve details of a vehicle catalogue application.

    GET /api/v1/catalogue/applications/<id>/
    """
    serializer_class = VehicleCatalogueApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        qs = VehicleCatalogueApplication.objects.select_related(
            'seller', 'make', 'reviewed_by', 'created_model', 'created_variant'
        )
        is_reviewer = (
            user.is_staff
            or user.has_role('ADMIN')
            or user.has_role('MARKETPLACE_ADMIN')
            or user.has_role('STAFF')
        )
        if not is_reviewer:
            qs = qs.filter(seller=user)
        return qs


class VehicleCatalogueApplicationReviewView(views.APIView):
    """Review (approve, reject, or request changes on) a vehicle catalogue application.

    POST /api/v1/catalogue/applications/<id>/review/
    """
    permission_classes = [IsPlatformStaff, HasPermission('catalogue.manage')]

    def post(self, request, id):
        app = VehicleCatalogueApplication.objects.filter(id=id).first()
        if not app:
            return Response({"error": "Vehicle catalogue application not found."}, status=status.HTTP_404_NOT_FOUND)

        if app.seller == request.user and not request.user.is_superuser:
            return Response(
                {"error": "Self-approval violation: You cannot review or approve your own vehicle catalogue application."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = VehicleCatalogueApplicationReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data['action']
        rejection_reason = serializer.validated_data.get('rejection_reason', '')
        admin_notes = serializer.validated_data.get('admin_notes', '')

        if action == 'APPROVE':
            with transaction.atomic():
                if app.make:
                    make = app.make
                else:
                    make, _ = VehicleMake.objects.get_or_create(
                        name__iexact=app.make_name.strip(),
                        defaults={'name': app.make_name.strip(), 'is_active': True},
                    )

                model, created = VehicleModel.objects.get_or_create(
                    make=make,
                    name__iexact=app.model_name.strip(),
                    defaults={
                        'name': app.model_name.strip(),
                        'year_start': app.year_start,
                        'year_end': app.year_end,
                        'image_url': app.primary_image_url,
                        'is_active': True,
                    },
                )
                if not created and not model.image_url and app.primary_image_url:
                    model.image_url = app.primary_image_url
                    model.save(update_fields=['image_url'])

                created_variant = None
                if app.variant_name and app.year:
                    created_variant, _ = VehicleVariant.objects.get_or_create(
                        model=model,
                        name__iexact=app.variant_name.strip(),
                        year=app.year,
                        engine_code=app.engine_code.strip(),
                        defaults={
                            'name': app.variant_name.strip(),
                            'fuel_type': app.fuel_type,
                            'transmission': app.transmission,
                            'body_type': app.body_type,
                            'power_bhp': app.power_bhp,
                            'engine_capacity_cc': app.engine_capacity_cc,
                            'is_active': True,
                        },
                    )

                app.created_model = model
                app.created_variant = created_variant
                app.status = CatalogueApplicationStatusChoices.APPROVED
                app.rejection_reason = ""
                app.reviewed_by = request.user
                app.reviewed_at = timezone.now()
                if admin_notes:
                    app.admin_notes = admin_notes
                app.save()

            log_catalogue_audit(
                request,
                event_type="catalogue.application.approved",
                action="catalogue:application.approve",
                resource_type="VehicleCatalogueApplication",
                resource_id=app.id,
                metadata={"action": "APPROVE", "model_id": str(model.id)},
            )

        elif action == 'REJECT':
            app.status = CatalogueApplicationStatusChoices.REJECTED
            app.rejection_reason = rejection_reason
            app.reviewed_by = request.user
            app.reviewed_at = timezone.now()
            if admin_notes:
                app.admin_notes = admin_notes
            app.save()
            log_catalogue_audit(
                request,
                event_type="catalogue.application.rejected",
                action="catalogue:application.reject",
                resource_type="VehicleCatalogueApplication",
                resource_id=app.id,
                metadata={"action": "REJECT", "reason": rejection_reason},
            )

        elif action == 'REQUEST_CHANGES':
            app.status = CatalogueApplicationStatusChoices.CHANGES_REQUESTED
            app.rejection_reason = rejection_reason
            app.reviewed_by = request.user
            app.reviewed_at = timezone.now()
            if admin_notes:
                app.admin_notes = admin_notes
            app.save()
            log_catalogue_audit(
                request,
                event_type="catalogue.application.changes_requested",
                action="catalogue:application.request_changes",
                resource_type="VehicleCatalogueApplication",
                resource_id=app.id,
                metadata={"action": "REQUEST_CHANGES", "reason": rejection_reason},
            )

        detail = VehicleCatalogueApplicationSerializer(app, context={'request': request})
        return Response(
            {
                "status": "success",
                "message": f"Catalogue application {action.lower()}d successfully.",
                "application": detail.data,
            },
            status=status.HTTP_200_OK,
        )


class CataloguePhotoProposalListCreateView(generics.ListCreateAPIView):
    """List or submit photo update proposals for approved catalogue models.

    GET /api/v1/catalogue/photo-proposals/
    POST /api/v1/catalogue/photo-proposals/
    """
    serializer_class = CataloguePhotoProposalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = CataloguePhotoProposal.objects.select_related(
            'seller', 'model', 'model__make', 'reviewed_by'
        )
        is_reviewer = (
            user.is_staff
            or user.has_role('ADMIN')
            or user.has_role('MARKETPLACE_ADMIN')
            or user.has_role('STAFF')
        )
        if not is_reviewer:
            qs = qs.filter(seller=user)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param.upper())
        return qs

    def perform_create(self, serializer):
        instance = serializer.save(seller=self.request.user)
        log_catalogue_audit(
            self.request,
            event_type="catalogue.photo_proposal.submitted",
            action="catalogue:photo_proposal.submit",
            resource_type="CataloguePhotoProposal",
            resource_id=instance.id,
            metadata={"model_id": str(instance.model_id), "proposed_image_url": instance.proposed_image_url},
        )


class CataloguePhotoProposalDetailView(generics.RetrieveAPIView):
    """Retrieve details of a catalogue photo proposal.

    GET /api/v1/catalogue/photo-proposals/<id>/
    """
    serializer_class = CataloguePhotoProposalSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        qs = CataloguePhotoProposal.objects.select_related(
            'seller', 'model', 'model__make', 'reviewed_by'
        )
        is_reviewer = (
            user.is_staff
            or user.has_role('ADMIN')
            or user.has_role('MARKETPLACE_ADMIN')
            or user.has_role('STAFF')
        )
        if not is_reviewer:
            qs = qs.filter(seller=user)
        return qs


class CataloguePhotoProposalReviewView(views.APIView):
    """Review (approve or reject) a catalogue photo proposal.

    POST /api/v1/catalogue/photo-proposals/<id>/review/
    """
    permission_classes = [IsPlatformStaff, HasPermission('catalogue.manage')]

    def post(self, request, id):
        proposal = CataloguePhotoProposal.objects.filter(id=id).first()
        if not proposal:
            return Response({"error": "Catalogue photo proposal not found."}, status=status.HTTP_404_NOT_FOUND)

        if proposal.seller == request.user and not request.user.is_superuser:
            return Response(
                {"error": "Self-approval violation: You cannot review or approve your own catalogue photo proposal."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CataloguePhotoProposalReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data['action']
        rejection_reason = serializer.validated_data.get('rejection_reason', '')
        admin_notes = serializer.validated_data.get('admin_notes', '')

        if action == 'APPROVE':
            with transaction.atomic():
                proposal.model.image_url = proposal.proposed_image_url
                proposal.model.save(update_fields=['image_url'])
                proposal.status = CatalogueApplicationStatusChoices.APPROVED
                proposal.rejection_reason = ""
                proposal.reviewed_by = request.user
                proposal.reviewed_at = timezone.now()
                if admin_notes:
                    proposal.admin_notes = admin_notes
                proposal.save()

            log_catalogue_audit(
                request,
                event_type="catalogue.photo_proposal.approved",
                action="catalogue:photo_proposal.approve",
                resource_type="CataloguePhotoProposal",
                resource_id=proposal.id,
                metadata={"model_id": str(proposal.model_id), "image_url": proposal.proposed_image_url},
            )

        elif action == 'REJECT':
            proposal.status = CatalogueApplicationStatusChoices.REJECTED
            proposal.rejection_reason = rejection_reason
            proposal.reviewed_by = request.user
            proposal.reviewed_at = timezone.now()
            if admin_notes:
                proposal.admin_notes = admin_notes
            proposal.save()
            log_catalogue_audit(
                request,
                event_type="catalogue.photo_proposal.rejected",
                action="catalogue:photo_proposal.reject",
                resource_type="CataloguePhotoProposal",
                resource_id=proposal.id,
                metadata={"model_id": str(proposal.model_id), "reason": rejection_reason},
            )

        detail = CataloguePhotoProposalSerializer(proposal, context={'request': request})
        return Response(
            {
                "status": "success",
                "message": f"Catalogue photo proposal {action.lower()}d successfully.",
                "proposal": detail.data,
            },
            status=status.HTTP_200_OK,
        )
