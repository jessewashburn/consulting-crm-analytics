"""
URL Configuration for analytics project.
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework import routers

from api import views
from api import debug_views

# API Router
router = routers.DefaultRouter()
router.register(r'daily-metrics', views.DailyAccountMetricViewSet)
router.register(r'funnel-metrics', views.LeadFunnelMetricViewSet)
router.register(r'revenue-metrics', views.RevenueMetricViewSet)
router.register(r'event-counts', views.EventCountViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    # Debug endpoints for developer console
    path('api/debug/events/', debug_views.events_list, name='debug-events-list'),
    path('api/debug/trace/<str:event_id>/', debug_views.event_trace, name='debug-event-trace'),
    path('api/debug/summary/', debug_views.analytics_summary, name='debug-analytics-summary'),
    path('api/debug/fire/', debug_views.create_test_event, name='debug-fire-event'),
]
