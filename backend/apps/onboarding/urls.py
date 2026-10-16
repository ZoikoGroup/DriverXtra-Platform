from django.urls import path
from apps.onboarding.views import (
    SellerApplicationMeView,
    SellerApplicationSubmitView,
    AdminSellerApplicationListView,
    AdminSellerApplicationDetailView,
    AdminSellerApplicationReviewView,
)

urlpatterns = [
    # Applicant endpoints
    path('seller/application/', SellerApplicationMeView.as_view(), name='seller-application-me'),
    path('seller/application/submit/', SellerApplicationSubmitView.as_view(), name='seller-application-submit'),

    # Admin & Staff review endpoints
    path('admin/seller-applications/', AdminSellerApplicationListView.as_view(), name='admin-seller-applications-list'),
    path('admin/seller-applications/<uuid:id>/', AdminSellerApplicationDetailView.as_view(), name='admin-seller-applications-detail'),
    path('admin/seller-applications/<uuid:id>/review/', AdminSellerApplicationReviewView.as_view(), name='admin-seller-applications-review'),
]
