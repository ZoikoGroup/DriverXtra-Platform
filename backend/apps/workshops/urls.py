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
    AdminWorkshopTaxAuthorizationView,
    WorkOrderManageListView,
    WorkOrderManageDetailView,
    WorkOrderAssignTechnicianView,
    WorkOrderStatusUpdateView,
    WorkOrderTaskCreateView,
    WorkOrderTaskDetailView,
    WorkOrderPartUsageListCreateView,
    WorkOrderPartUsageDetailView,
    WorkshopTechnicianListView,
    BuyerWorkOrderDetailView,
    WorkOrderChangeOrderListCreateView,
    ChangeOrderDetailView,
    ChangeOrderSubmitView,
    ChangeOrderCancelView,
    BuyerChangeOrderListView,
    BuyerChangeOrderApproveView,
    BuyerChangeOrderRejectView,
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

    # Work Orders & Workshop Execution
    path('manage/work-orders/', WorkOrderManageListView.as_view(), name='workshop-work-orders-list'),
    path('manage/work-orders/<uuid:id>/', WorkOrderManageDetailView.as_view(), name='workshop-work-order-detail'),
    path('manage/work-orders/<uuid:id>/assign-technician/', WorkOrderAssignTechnicianView.as_view(), name='workshop-work-order-assign-technician'),
    path('manage/work-orders/<uuid:id>/status/', WorkOrderStatusUpdateView.as_view(), name='workshop-work-order-status-update'),
    path('manage/work-orders/<uuid:id>/tasks/', WorkOrderTaskCreateView.as_view(), name='workshop-work-order-tasks'),
    path('manage/work-orders/<uuid:id>/tasks/<uuid:task_id>/', WorkOrderTaskDetailView.as_view(), name='workshop-work-order-task-detail'),
    path('manage/work-orders/<uuid:id>/parts/', WorkOrderPartUsageListCreateView.as_view(), name='workshop-work-order-parts'),
    path('manage/work-orders/<uuid:id>/parts/<uuid:part_id>/', WorkOrderPartUsageDetailView.as_view(), name='workshop-work-order-part-detail'),
    path('manage/technicians/', WorkshopTechnicianListView.as_view(), name='workshop-technicians-list'),

    # Buyer Work Order inspection
    path('bookings/my/<uuid:id>/work-order/', BuyerWorkOrderDetailView.as_view(), name='workshop-buyer-work-order'),

    # Change Orders (Workshop Management)
    path('manage/work-orders/<uuid:id>/change-orders/', WorkOrderChangeOrderListCreateView.as_view(), name='workshop-work-order-change-orders'),
    path('manage/change-orders/<uuid:id>/', ChangeOrderDetailView.as_view(), name='workshop-change-order-detail'),
    path('manage/change-orders/<uuid:id>/submit/', ChangeOrderSubmitView.as_view(), name='workshop-change-order-submit'),
    path('manage/change-orders/<uuid:id>/cancel/', ChangeOrderCancelView.as_view(), name='workshop-change-order-cancel'),

    # Change Orders (Buyer Authorization)
    path('bookings/my/<uuid:id>/change-orders/', BuyerChangeOrderListView.as_view(), name='workshop-buyer-change-orders-list'),
    path('change-orders/<uuid:id>/approve/', BuyerChangeOrderApproveView.as_view(), name='workshop-change-order-approve'),
    path('change-orders/<uuid:id>/reject/', BuyerChangeOrderRejectView.as_view(), name='workshop-change-order-reject'),

    # Platform administrator oversight
    path('admin/bookings/', AdminWorkshopBookingListView.as_view(), name='workshop-admin-bookings-list'),
    path('admin/<uuid:id>/tax-authorization/', AdminWorkshopTaxAuthorizationView.as_view(), name='workshop-admin-tax-authorization'),

    # Workshop detail lookup by UUID or slug (placed last to prevent collision with reserved endpoints)
    path('<str:id_or_slug>/', WorkshopDetailPublicView.as_view(), name='workshop-public-detail'),
]

