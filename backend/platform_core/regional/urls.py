"""URL routing for platform regional configuration."""

from django.urls import path
from .api import RegionalConfigListView

urlpatterns = [
    path('', RegionalConfigListView.as_view(), name='regional-config-list'),
]

