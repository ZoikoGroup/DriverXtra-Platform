from django.urls import path
from apps.marketplace.views import (
    MarketplaceVehicleListView,
    MarketplaceVehicleDetailView,
    MarketplacePartListView,
    MarketplacePartDetailView,
    SellerVehicleListCreateView,
    SellerVehicleDetailUpdateView,
    SellerVehicleResubmitView,
    SellerPartListCreateView,
    SellerPartDetailUpdateView,
    SellerPartResubmitView,
    PartStockAdjustmentView,
    PartStockHistoryView,
    LowStockPartListView,
    AdminVehicleListingListView,
    AdminVehicleListingDetailView,
    AdminVehicleListingReviewView,
    AdminPartListingListView,
    AdminPartListingDetailView,
    AdminPartListingReviewView,
)

urlpatterns = [
    # 1. Buyer Browse & Search (Approved items only)
    path('browse/vehicles/', MarketplaceVehicleListView.as_view(), name='marketplace-browse-vehicles'),
    path('browse/vehicles/<uuid:id>/', MarketplaceVehicleDetailView.as_view(), name='marketplace-browse-vehicle-detail'),
    path('browse/parts/', MarketplacePartListView.as_view(), name='marketplace-browse-parts'),
    path('browse/parts/<uuid:id>/', MarketplacePartDetailView.as_view(), name='marketplace-browse-part-detail'),

    # 2. Seller Inventory Management
    path('vehicles/', SellerVehicleListCreateView.as_view(), name='marketplace-seller-vehicles'),
    path('vehicles/<uuid:id>/', SellerVehicleDetailUpdateView.as_view(), name='marketplace-seller-vehicle-detail'),
    path('vehicles/<uuid:id>/submit/', SellerVehicleResubmitView.as_view(), name='marketplace-seller-vehicle-submit'),
    path('vehicles/<uuid:id>/resubmit/', SellerVehicleResubmitView.as_view(), name='marketplace-seller-vehicle-resubmit'),
    path('parts/', SellerPartListCreateView.as_view(), name='marketplace-seller-parts'),
    path('parts/low-stock/', LowStockPartListView.as_view(), name='marketplace-parts-low-stock'),
    path('parts/<uuid:id>/', SellerPartDetailUpdateView.as_view(), name='marketplace-seller-part-detail'),
    path('parts/<uuid:id>/submit/', SellerPartResubmitView.as_view(), name='marketplace-seller-part-submit'),
    path('parts/<uuid:id>/resubmit/', SellerPartResubmitView.as_view(), name='marketplace-seller-part-resubmit'),
    path('parts/<uuid:id>/stock/', PartStockAdjustmentView.as_view(), name='marketplace-part-stock-adjust'),
    path('parts/<uuid:id>/stock-history/', PartStockHistoryView.as_view(), name='marketplace-part-stock-history'),

    # 3. Admin Moderation & Approval Queues
    path('admin/vehicles/', AdminVehicleListingListView.as_view(), name='marketplace-admin-vehicles'),
    path('admin/vehicles/<uuid:id>/', AdminVehicleListingDetailView.as_view(), name='marketplace-admin-vehicle-detail'),
    path('admin/vehicles/<uuid:id>/review/', AdminVehicleListingReviewView.as_view(), name='marketplace-admin-vehicle-review'),
    path('admin/parts/', AdminPartListingListView.as_view(), name='marketplace-admin-parts'),
    path('admin/parts/<uuid:id>/', AdminPartListingDetailView.as_view(), name='marketplace-admin-part-detail'),
    path('admin/parts/<uuid:id>/review/', AdminPartListingReviewView.as_view(), name='marketplace-admin-part-review'),
]
