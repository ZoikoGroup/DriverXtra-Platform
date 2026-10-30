from django.urls import path
from apps.workshops.views import (
    WorkshopListPublicView,
    WorkshopDetailPublicView,
    WorkshopServiceCategoryListView,
    BuyerBookingListCreateView,
    BuyerBookingDetailView,
    BuyerBookingCancelView,
    BuyerQuotationAcceptView,
    BuyerQuotationRejectView,
    WorkshopProfileManageView,
    WorkshopOperatingHoursManageView,
    WorkshopServiceListCreateView,
    WorkshopServiceDetailView,
    WorkshopBookingManageListView,
    WorkshopBookingManageDetailView,
    WorkshopBookingStatusUpdateView,
    WorkshopQuotationCreateReviseView,
    WorkshopQuotationIssueView,
    WorkshopQuotationDetailView,
    AdminWorkshopBookingListView,
)

urlpatterns = [
    # Public taxonomy & browse
    path('', WorkshopListPublicView.as_view(), name='workshop-public-list'),
    path('categories/', WorkshopServiceCategoryListView.as_view(), name='workshop-categories-list'),

    # Buyer booking management
    path('bookings/', BuyerBookingListCreateView.as_view(), name='workshop-booking-create'),
    path('bookings/my/', BuyerBookingListCreateView.as_view(), name='workshop-booking-my-list'),
    path('bookings/my/<uuid:id>/', BuyerBookingDetailView.as_view(), name='workshop-booking-my-detail'),
    path('bookings/my/<uuid:id>/cancel/', BuyerBookingCancelView.as_view(), name='workshop-booking-my-cancel'),

    # Quotation viewing & responses
    path('quotations/<uuid:id>/', WorkshopQuotationDetailView.as_view(), name='workshop-quotation-detail'),
    path('quotations/<uuid:id>/accept/', BuyerQuotationAcceptView.as_view(), name='workshop-quotation-accept'),
    path('quotations/<uuid:id>/reject/', BuyerQuotationRejectView.as_view(), name='workshop-quotation-reject'),

    # Workshop console & operational management
    path('manage/profile/', WorkshopProfileManageView.as_view(), name='workshop-manage-profile'),
    path('manage/operating-hours/', WorkshopOperatingHoursManageView.as_view(), name='workshop-manage-operating-hours'),
    path('manage/services/', WorkshopServiceListCreateView.as_view(), name='workshop-manage-services'),
    path('manage/services/<uuid:id>/', WorkshopServiceDetailView.as_view(), name='workshop-manage-service-detail'),
    path('manage/bookings/', WorkshopBookingManageListView.as_view(), name='workshop-manage-bookings-list'),
    path('manage/bookings/<uuid:id>/', WorkshopBookingManageDetailView.as_view(), name='workshop-manage-booking-detail'),
    path('manage/bookings/<uuid:id>/status/', WorkshopBookingStatusUpdateView.as_view(), name='workshop-manage-booking-status'),
    path('manage/bookings/<uuid:id>/quotations/', WorkshopQuotationCreateReviseView.as_view(), name='workshop-manage-booking-quotations'),
    path('manage/quotations/<uuid:id>/', WorkshopQuotationDetailView.as_view(), name='workshop-manage-quotation-detail-staff'),
    path('manage/quotations/<uuid:id>/issue/', WorkshopQuotationIssueView.as_view(), name='workshop-manage-quotation-issue'),

    # Platform administrator oversight
    path('admin/bookings/', AdminWorkshopBookingListView.as_view(), name='workshop-admin-bookings-list'),

    # Workshop detail lookup by UUID or slug (placed last to prevent collision with reserved endpoints)
    path('<str:id_or_slug>/', WorkshopDetailPublicView.as_view(), name='workshop-public-detail'),
]

