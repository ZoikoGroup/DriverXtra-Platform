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
    GSTOptionsView,
    OrderCheckoutView,
    BuyerOrderListView,
    BuyerOrderDetailView,
    BuyerOrderCancelView,
    SellerOrderListView,
    SellerOrderDetailView,
    SellerOrderStatusUpdateView,
    VehicleEnquiryCreateView,
    SellerVehicleEnquiryListView,
    SellerVehicleEnquiryDetailView,
    BuyerVehicleEnquiryListView,
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

    # 6. Tax Options, Order Checkout & Order Management
    path('tax/gst-options/', GSTOptionsView.as_view(), name='marketplace-tax-gst-options'),
    path('orders/checkout/', OrderCheckoutView.as_view(), name='marketplace-orders-checkout'),
    path('orders/calculate/', OrderCheckoutView.as_view(), name='marketplace-orders-calculate'),
    path('orders/', BuyerOrderListView.as_view(), name='marketplace-orders-list'),
    path('orders/<str:identifier>/cancel/', BuyerOrderCancelView.as_view(), name='marketplace-order-cancel'),
    path('orders/<str:identifier>/', BuyerOrderDetailView.as_view(), name='marketplace-order-detail'),

    # 6b. Seller Order Management (Multi-Seller Isolated Views & Workflow)
    path('seller/orders/', SellerOrderListView.as_view(), name='marketplace-seller-orders-list'),
    path('seller/orders/<str:identifier>/status/', SellerOrderStatusUpdateView.as_view(), name='marketplace-seller-order-status'),
    path('seller/orders/<str:identifier>/', SellerOrderDetailView.as_view(), name='marketplace-seller-order-detail'),

    # 7. Direct Buyer–Seller Connection (Vehicle Enquiries)
    path('vehicles/<uuid:id>/enquire/', VehicleEnquiryCreateView.as_view(), name='marketplace-vehicle-enquire'),
    path('seller/enquiries/', SellerVehicleEnquiryListView.as_view(), name='marketplace-seller-enquiries-list'),
    path('seller/enquiries/<uuid:id>/', SellerVehicleEnquiryDetailView.as_view(), name='marketplace-seller-enquiry-detail'),
    path('buyer/enquiries/', BuyerVehicleEnquiryListView.as_view(), name='marketplace-buyer-enquiries-list'),
]
