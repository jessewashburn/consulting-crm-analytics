"""
DRF Serializers for analytics API.
"""
from rest_framework import serializers
from events.models import DailyAccountMetric, LeadFunnelMetric, RevenueMetric, EventCount


class DailyAccountMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyAccountMetric
        fields = '__all__'


class LeadFunnelMetricSerializer(serializers.ModelSerializer):
    conversion_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = LeadFunnelMetric
        fields = '__all__'
    
    def get_conversion_rate(self, obj):
        total = obj.new_leads + obj.contacted_leads + obj.qualified_leads + obj.won_leads + obj.lost_leads
        if total > 0:
            return round((obj.won_leads / total) * 100, 2)
        return 0


class RevenueMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = RevenueMetric
        fields = '__all__'


class EventCountSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventCount
        fields = '__all__'
