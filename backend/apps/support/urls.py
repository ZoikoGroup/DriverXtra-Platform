from django.urls import path
from apps.support.views import (
    CustomerTicketCloseView,
    CustomerTicketDetailView,
    CustomerTicketListCreateView,
    CustomerTicketMessageView,
    StaffMetricsView,
    StaffSupportMemberListView,
    StaffTicketAssignView,
    StaffTicketDetailView,
    StaffTicketEscalateView,
    StaffTicketListView,
    StaffTicketMessageView,
    StaffTicketPriorityView,
    StaffTicketStatusView,
    TicketAttachmentDownloadView,
    TicketAttachmentUploadView,
)

app_name = 'support'

urlpatterns = [
    # Customer APIs
    path('tickets/', CustomerTicketListCreateView.as_view(), name='customer-ticket-list-create'),
    path('tickets/<str:identifier>/', CustomerTicketDetailView.as_view(), name='customer-ticket-detail'),
    path('tickets/<str:identifier>/messages/', CustomerTicketMessageView.as_view(), name='customer-ticket-message'),
    path('tickets/<str:identifier>/close/', CustomerTicketCloseView.as_view(), name='customer-ticket-close'),
    path('tickets/<str:identifier>/attachments/', TicketAttachmentUploadView.as_view(), name='ticket-attachment-upload'),

    # Staff Agent APIs
    path('agent/tickets/', StaffTicketListView.as_view(), name='staff-ticket-list'),
    path('agent/tickets/<str:identifier>/', StaffTicketDetailView.as_view(), name='staff-ticket-detail'),
    path('agent/tickets/<str:identifier>/assign/', StaffTicketAssignView.as_view(), name='staff-ticket-assign'),
    path('agent/tickets/<str:identifier>/status/', StaffTicketStatusView.as_view(), name='staff-ticket-status'),
    path('agent/tickets/<str:identifier>/priority/', StaffTicketPriorityView.as_view(), name='staff-ticket-priority'),
    path('agent/tickets/<str:identifier>/messages/', StaffTicketMessageView.as_view(), name='staff-ticket-message'),
    path('agent/tickets/<str:identifier>/escalate/', StaffTicketEscalateView.as_view(), name='staff-ticket-escalate'),
    path('agent/metrics/', StaffMetricsView.as_view(), name='staff-ticket-metrics'),
    path('agent/staff-list/', StaffSupportMemberListView.as_view(), name='staff-member-list'),

    # Attachment Download
    path('attachments/<uuid:attachment_id>/', TicketAttachmentDownloadView.as_view(), name='ticket-attachment-download'),
]

