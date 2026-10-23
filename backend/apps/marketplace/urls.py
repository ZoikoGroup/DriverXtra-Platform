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
    PartPriceHistoryView,
    LowStockPartListView,
    CataloguePartOffersView,
    AdminVehicleListingListView,
    AdminVehicleListingDetailView,
    AdminVehicleListingReviewView,
    AdminPartListingListView,
    AdminPartListingDetailView,
    AdminPartListingReviewView,
    BuyerFavouriteVehicleListCreateView,
    BuyerFavouriteVehicleDetailView,
    BuyerFavouritePartListCreateView,
    BuyerFavouritePartDetailView,
    MarketplaceImageUploadView,
)

urlpatterns = [
    # 0. Media / Image Uploads
    path('upload-image/', MarketplaceImageUploadView.as_view(), name='marketplace-upload-image'),
    path('images/upload/', MarketplaceImageUploadView.as_view(), name='marketplace-images-upload'),

    # 1. Buyer Browse & Search (Approved items only)
    path('browse/vehicles/', MarketplaceVehicleListView.as_view(), name='marketplace-browse-vehicles'),
    path('browse/vehicles/<uuid:id>/', MarketplaceVehicleDetailView.as_view(), name='marketplace-browse-vehicle-detail'),
    path('browse/parts/', MarketplacePartListView.as_view(), name='marketplace-browse-parts'),
    path('browse/parts/<uuid:id>/', MarketplacePartDetailView.as_view(), name='marketplace-browse-part-detail'),
    path('browse/parts/catalogue/<uuid:catalogue_part_id>/offers/', CataloguePartOffersView.as_view(), name='marketplace-browse-catalogue-part-offers'),

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
    path('parts/<uuid:id>/price-history/', PartPriceHistoryView.as_view(), name='marketplace-part-price-history'),

    # 3. Admin Moderation & Approval Queues
    path('admin/vehicles/', AdminVehicleListingListView.as_view(), name='marketplace-admin-vehicles'),
    path('admin/vehicles/<uuid:id>/', AdminVehicleListingDetailView.as_view(), name='marketplace-admin-vehicle-detail'),
    path('admin/vehicles/<uuid:id>/review/', AdminVehicleListingReviewView.as_view(), name='marketplace-admin-vehicle-review'),
    path('admin/parts/', AdminPartListingListView.as_view(), name='marketplace-admin-parts'),
    path('admin/parts/<uuid:id>/', AdminPartListingDetailView.as_view(), name='marketplace-admin-part-detail'),
    path('admin/parts/<uuid:id>/review/', AdminPartListingReviewView.as_view(), name='marketplace-admin-part-review'),

    # 4. Buyer Saved Vehicle Favourites
    path('favourites/', BuyerFavouriteVehicleListCreateView.as_view(), name='marketplace-buyer-favourites'),
    path('favourites/<uuid:id>/', BuyerFavouriteVehicleDetailView.as_view(), name='marketplace-buyer-favourite-detail'),
    # Resilient aliases for US/UK spelling
    path('favorites/', BuyerFavouriteVehicleListCreateView.as_view(), name='marketplace-buyer-favorites'),
    path('favorites/<uuid:id>/', BuyerFavouriteVehicleDetailView.as_view(), name='marketplace-buyer-favorite-detail'),

    # 5. Buyer Saved Spare Part Favourites
    path('favourites/parts/', BuyerFavouritePartListCreateView.as_view(), name='marketplace-buyer-favourite-parts'),
    path('favourites/parts/<uuid:id>/', BuyerFavouritePartDetailView.as_view(), name='marketplace-buyer-favourite-part-detail'),
    path('favorites/parts/', BuyerFavouritePartListCreateView.as_view(), name='marketplace-buyer-favorite-parts'),
    path('favorites/parts/<uuid:id>/', BuyerFavouritePartDetailView.as_view(), name='marketplace-buyer-favorite-part-detail'),
]
