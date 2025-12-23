"""
REST API views for analytics data.
"""
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend

from events.models import DailyAccountMetric, LeadFunnelMetric, RevenueMetric, EventCount
from .serializers import (
    DailyAccountMetricSerializer,
    LeadFunnelMetricSerializer,
    RevenueMetricSerializer,
    EventCountSerializer
)


class DailyAccountMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API for daily account metrics.
    Filter by date range and account.
    """
    queryset = DailyAccountMetric.objects.all()
    serializer_class = DailyAccountMetricSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['date', 'account_id', 'account_name']
    ordering_fields = ['date', 'total_contract_value', 'total_activities']
    ordering = ['-date']


class LeadFunnelMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API for lead funnel metrics.
    """
    queryset = LeadFunnelMetric.objects.all()
    serializer_class = LeadFunnelMetricSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['date']
    ordering = ['-date']


class RevenueMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API for revenue metrics.
    """
    queryset = RevenueMetric.objects.all()
    serializer_class = RevenueMetricSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['month', 'account_id', 'account_name']
    ordering_fields = ['month', 'contracted_value']
    ordering = ['-month']


class EventCountViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API for event processing metrics.
    """
    queryset = EventCount.objects.all()
    serializer_class = EventCountSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['date', 'event_type', 'aggregate_type']
    ordering = ['-date', 'event_type']
