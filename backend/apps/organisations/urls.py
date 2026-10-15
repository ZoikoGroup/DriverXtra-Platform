from django.urls import path
from .views import (
    OrganisationListCreateView,
    OrganisationDetailView,
    OrganisationMemberListCreateView,
)

urlpatterns = [
    path('organisations/', OrganisationListCreateView.as_view(), name='organisation-list-create'),
    path('organisations/<uuid:id>/', OrganisationDetailView.as_view(), name='organisation-detail'),
    path('organisations/<uuid:id>/members/', OrganisationMemberListCreateView.as_view(), name='organisation-members'),
]
