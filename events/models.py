"""
Analytics models for aggregated CRM metrics.
"""
from django.db import models
from django.utils import timezone


class ProcessedEvent(models.Model):
    """Track which events have been processed (idempotency)."""
    
    event_id = models.CharField(max_length=255, unique=True, db_index=True)
    event_type = models.CharField(max_length=100)
    aggregate_type = models.CharField(max_length=50)
    aggregate_id = models.UUIDField()
    processed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'processed_events'
        ordering = ['-processed_at']
        indexes = [
            models.Index(fields=['event_id']),
            models.Index(fields=['processed_at']),
            models.Index(fields=['aggregate_type', 'aggregate_id']),
        ]
    
    def __str__(self):
        return f"{self.event_type} - {self.event_id}"


class FailedEvent(models.Model):
    """Dead-letter queue for events that fail processing."""
    
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100, db_index=True)
    aggregate_type = models.CharField(max_length=50)
    aggregate_id = models.UUIDField()
    payload = models.JSONField()
    
    error_message = models.TextField()
    error_trace = models.TextField(blank=True, null=True)
    retry_count = models.IntegerField()
    
    first_failed_at = models.DateTimeField(auto_now_add=True)
    last_failed_at = models.DateTimeField(auto_now=True)
    
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=255, null=True, blank=True)
    
    class Meta:
        db_table = 'failed_events'
        ordering = ['-first_failed_at']
        indexes = [
            models.Index(fields=['event_type']),
            models.Index(fields=['resolved_at']),
            models.Index(fields=['-first_failed_at']),
        ]
    
    def __str__(self):
        return f"Failed: {self.event_type} - {self.event_id}"


class DailyAccountMetric(models.Model):
    """Daily rollup of account-level metrics."""
    
    date = models.DateField(db_index=True)
    account_id = models.UUIDField(db_index=True)
    account_name = models.CharField(max_length=255)
    
    # Activity counts
    total_activities = models.IntegerField(default=0)
    calls_count = models.IntegerField(default=0)
    emails_count = models.IntegerField(default=0)
    meetings_count = models.IntegerField(default=0)
    
    # Project metrics
    active_projects = models.IntegerField(default=0)
    total_contract_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'daily_account_metrics'
        unique_together = ['date', 'account_id']
        ordering = ['-date', 'account_name']
        indexes = [
            models.Index(fields=['date', 'account_id']),
        ]
    
    def __str__(self):
        return f"{self.account_name} - {self.date}"


class LeadFunnelMetric(models.Model):
    """Track lead progression through sales funnel."""
    
    date = models.DateField(db_index=True)
    
    # Funnel counts
    new_leads = models.IntegerField(default=0)
    contacted_leads = models.IntegerField(default=0)
    qualified_leads = models.IntegerField(default=0)
    won_leads = models.IntegerField(default=0)
    lost_leads = models.IntegerField(default=0)
    
    # Value metrics
    total_estimated_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    won_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    lost_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'lead_funnel_metrics'
        unique_together = ['date']
        ordering = ['-date']
    
    def __str__(self):
        return f"Funnel - {self.date}"


class RevenueMetric(models.Model):
    """Monthly revenue tracking by account and project."""
    
    month = models.DateField(db_index=True)  # Store as first day of month
    account_id = models.UUIDField(db_index=True, null=True, blank=True)
    account_name = models.CharField(max_length=255, null=True, blank=True)
    
    # Revenue
    contracted_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    projects_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'revenue_metrics'
        unique_together = ['month', 'account_id']
        ordering = ['-month', 'account_name']
    
    def __str__(self):
        return f"{self.account_name or 'Total'} - {self.month.strftime('%Y-%m')}"


class EventCount(models.Model):
    """Track event processing metrics."""
    
    date = models.DateField(db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    aggregate_type = models.CharField(max_length=50)
    
    count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'event_counts'
        unique_together = ['date', 'event_type', 'aggregate_type']
        ordering = ['-date', 'event_type']
    
    def __str__(self):
        return f"{self.event_type} - {self.date} ({self.count})"
