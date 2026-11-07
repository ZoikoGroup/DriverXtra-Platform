from django.urls import path

from .views import (
    AdminGateDetailView,
    AdminGateListCreateView,
    AdminGateTransitionView,
    AdminOutboxListView,
    AdminQuoteListView,
    AdminQuotePreviewView,
    AdminRateDetailView,
    AdminRateListCreateView,
    AdminRateTransitionView,
    AdminRoleProfileDetailView,
    AdminRoleProfileListCreateView,
    AdminRoleProfileNewVersionView,
    AdminRoleProfileTransitionView,
    AdminSkuDetailView,
    AdminSkuListCreateView,
    AdminSkuNewVersionView,
    AdminSkuTransitionView,
    PublicPlansView,
    QuoteAcceptView,
    QuoteCreateView,
    QuoteDetailView,
)

urlpatterns = [
    # Public / customer
    path('commercial/plans/', PublicPlansView.as_view(), name='commercial-plans'),
    path('commercial/quotes/', QuoteCreateView.as_view(), name='commercial-quotes'),
    path('commercial/quotes/<uuid:id>/', QuoteDetailView.as_view(), name='commercial-quote-detail'),
    path('commercial/quotes/<uuid:id>/accept/', QuoteAcceptView.as_view(), name='commercial-quote-accept'),

    # Admin: SKU catalogue
    path('commercial/admin/skus/', AdminSkuListCreateView.as_view(), name='commercial-admin-skus'),
    path('commercial/admin/skus/<uuid:id>/', AdminSkuDetailView.as_view(), name='commercial-admin-sku-detail'),
    path('commercial/admin/skus/<uuid:id>/status/', AdminSkuTransitionView.as_view(), name='commercial-admin-sku-status'),
    path('commercial/admin/skus/<uuid:id>/new-version/', AdminSkuNewVersionView.as_view(), name='commercial-admin-sku-version'),

    # Admin: rate schedules
    path('commercial/admin/rate-schedules/', AdminRateListCreateView.as_view(), name='commercial-admin-rates'),
    path('commercial/admin/rate-schedules/<uuid:id>/', AdminRateDetailView.as_view(), name='commercial-admin-rate-detail'),
    path('commercial/admin/rate-schedules/<uuid:id>/status/', AdminRateTransitionView.as_view(), name='commercial-admin-rate-status'),

    # Admin: party role profiles
    path('commercial/admin/role-profiles/', AdminRoleProfileListCreateView.as_view(), name='commercial-admin-role-profiles'),
    path('commercial/admin/role-profiles/<uuid:id>/', AdminRoleProfileDetailView.as_view(), name='commercial-admin-role-profile-detail'),
    path('commercial/admin/role-profiles/<uuid:id>/status/', AdminRoleProfileTransitionView.as_view(), name='commercial-admin-role-profile-status'),
    path('commercial/admin/role-profiles/<uuid:id>/new-version/', AdminRoleProfileNewVersionView.as_view(), name='commercial-admin-role-profile-version'),

    # Admin: country gates
    path('commercial/admin/country-gates/', AdminGateListCreateView.as_view(), name='commercial-admin-gates'),
    path('commercial/admin/country-gates/<uuid:id>/', AdminGateDetailView.as_view(), name='commercial-admin-gate-detail'),
    path('commercial/admin/country-gates/<uuid:id>/transition/', AdminGateTransitionView.as_view(), name='commercial-admin-gate-transition'),

    # Admin: quotes, preview and event outbox
    path('commercial/admin/quote-preview/', AdminQuotePreviewView.as_view(), name='commercial-admin-quote-preview'),
    path('commercial/admin/quotes/', AdminQuoteListView.as_view(), name='commercial-admin-quotes'),
    path('commercial/admin/outbox/', AdminOutboxListView.as_view(), name='commercial-admin-outbox'),
]
