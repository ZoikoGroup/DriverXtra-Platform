from django.urls import path
from apps.catalogue.views import (
    VehicleMakeListCreateView,
    VehicleMakeDetailView,
    VehicleModelListCreateView,
    VehicleModelDetailView,
    VehicleVariantListCreateView,
    VehicleVariantDetailView,
    PartCategoryListCreateView,
    PartCategoryDetailView,
    PartListCreateView,
    PartDetailView,
    PartCompatibilityListCreateView,
    PartCompatibilityDetailView,
    FitmentEvaluationView,
)

urlpatterns = [
    # Vehicles
    path('catalogue/makes/', VehicleMakeListCreateView.as_view(), name='catalogue-makes-list'),
    path('catalogue/makes/<uuid:id>/', VehicleMakeDetailView.as_view(), name='catalogue-make-detail'),
    path('catalogue/models/', VehicleModelListCreateView.as_view(), name='catalogue-models-list'),
    path('catalogue/models/<uuid:id>/', VehicleModelDetailView.as_view(), name='catalogue-model-detail'),
    path('catalogue/variants/', VehicleVariantListCreateView.as_view(), name='catalogue-variants-list'),
    path('catalogue/variants/<uuid:id>/', VehicleVariantDetailView.as_view(), name='catalogue-variant-detail'),

    # Parts & Categories
    path('catalogue/categories/', PartCategoryListCreateView.as_view(), name='catalogue-categories-list'),
    path('catalogue/categories/<uuid:id>/', PartCategoryDetailView.as_view(), name='catalogue-category-detail'),
    path('catalogue/parts/', PartListCreateView.as_view(), name='catalogue-parts-list'),
    path('catalogue/parts/<uuid:id>/', PartDetailView.as_view(), name='catalogue-part-detail'),

    # Compatibility & Fitment
    path('catalogue/compatibility/', PartCompatibilityListCreateView.as_view(), name='catalogue-compatibility-list'),
    path('catalogue/compatibility/<uuid:id>/', PartCompatibilityDetailView.as_view(), name='catalogue-compatibility-detail'),
    path('catalogue/parts/<uuid:id>/compatibilities/', PartCompatibilityListCreateView.as_view(), name='catalogue-part-compatibilities-nested'),
    path('catalogue/parts/<uuid:id>/compatibility/', PartCompatibilityListCreateView.as_view(), name='catalogue-part-compatibility-nested'),
    path('catalogue/fitment/', FitmentEvaluationView.as_view(), name='catalogue-fitment-evaluation'),
]
