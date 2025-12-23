"""
URL Configuration for analytics project.
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework import routers

from api import views

# API Router
router = routers.DefaultRouter()
router.register(r'daily-metrics', views.DailyAccountMetricViewSet)
router.register(r'funnel-metrics', views.LeadFunnelMetricViewSet)
router.register(r'revenue-metrics', views.RevenueMetricViewSet)
router.register(r'event-counts', views.EventCountViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
]
