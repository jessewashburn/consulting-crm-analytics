"""
Celery tasks for event processing.
"""
import json
import logging
from datetime import date
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

import boto3

from .models import DailyAccountMetric, LeadFunnelMetric, RevenueMetric, EventCount

logger = logging.getLogger(__name__)


@shared_task
def poll_event_outbox():
    """
    Poll the event_outbox table for unprocessed events.
    Publish to SQS and mark as processed.
    """
    batch_size = settings.EVENT_BATCH_SIZE
    
    with connection.cursor() as cursor:
        # Fetch unprocessed events
        cursor.execute("""
            SELECT id, event_type, aggregate_type, aggregate_id, payload, created_at
            FROM event_outbox
            WHERE processed_at IS NULL
            ORDER BY created_at
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        """, [batch_size])
        
        events = cursor.fetchall()
        
        if not events:
            logger.info("No unprocessed events found")
            return 0
        
        logger.info(f"Found {len(events)} unprocessed events")
        
        # Publish to SQS (if configured)
        if settings.SQS_QUEUE_URL:
            try:
                sqs = boto3.client('sqs', region_name=settings.AWS_REGION)
                
                for event in events:
                    event_id, event_type, aggregate_type, aggregate_id, payload, created_at = event
                    
                    message_body = json.dumps({
                        'event_id': str(event_id),
                        'event_type': event_type,
                        'aggregate_type': aggregate_type,
                        'aggregate_id': str(aggregate_id),
                        'payload': payload,
                        'created_at': created_at.isoformat(),
                    })
                    
                    sqs.send_message(
                        QueueUrl=settings.SQS_QUEUE_URL,
                        MessageBody=message_body
                    )
                
                logger.info(f"Published {len(events)} events to SQS")
            except Exception as e:
                logger.error(f"Failed to publish to SQS: {e}")
                return 0
        
        # Mark events as processed
        event_ids = [str(event[0]) for event in events]
        cursor.execute("""
            UPDATE event_outbox
            SET processed_at = NOW(), published_at = NOW()
            WHERE id = ANY(%s)
        """, [event_ids])
        
        # Process events locally (for now, until SQS consumer is set up)
        for event in events:
            event_id, event_type, aggregate_type, aggregate_id, payload, created_at = event
            process_event.delay(event_type, aggregate_type, str(aggregate_id), payload)
        
        logger.info(f"Marked {len(events)} events as processed")
        
        return len(events)


@shared_task
def process_event(event_type, aggregate_type, aggregate_id, payload):
    """
    Process a single event and update analytics tables.
    """
    logger.info(f"Processing event: {event_type} for {aggregate_type}:{aggregate_id}")
    
    try:
        # Track event count
        today = date.today()
        EventCount.objects.update_or_create(
            date=today,
            event_type=event_type,
            aggregate_type=aggregate_type,
            defaults={'count': models.F('count') + 1}
        )
        
        # Route to specific handler
        if aggregate_type == 'leads':
            _process_lead_event(event_type, payload)
        elif aggregate_type == 'accounts':
            _process_account_event(event_type, payload)
        elif aggregate_type == 'projects':
            _process_project_event(event_type, payload)
        elif aggregate_type == 'activities':
            _process_activity_event(event_type, payload)
        
        # Archive to S3 (optional)
        if settings.S3_BUCKET_NAME:
            _archive_to_s3(event_type, aggregate_type, aggregate_id, payload)
        
    except Exception as e:
        logger.error(f"Error processing event {event_type}: {e}", exc_info=True)


def _process_lead_event(event_type, payload):
    """Update lead funnel metrics."""
    today = date.today()
    lead_status = payload.get('lead_status', 'new')
    estimated_value = Decimal(payload.get('estimated_value') or 0)
    
    metric, created = LeadFunnelMetric.objects.get_or_create(date=today)
    
    if 'INSERT' in event_type or 'UPDATE' in event_type:
        # Increment appropriate funnel stage
        if lead_status == 'new':
            metric.new_leads += 1
        elif lead_status == 'contacted':
            metric.contacted_leads += 1
        elif lead_status == 'qualified':
            metric.qualified_leads += 1
        elif lead_status == 'won':
            metric.won_leads += 1
            metric.won_value += estimated_value
        elif lead_status == 'lost':
            metric.lost_leads += 1
            metric.lost_value += estimated_value
        
        metric.total_estimated_value += estimated_value
        metric.save()


def _process_account_event(event_type, payload):
    """Update account metrics."""
    # Placeholder for account-specific logic
    logger.info(f"Processing account event: {event_type}")


def _process_project_event(event_type, payload):
    """Update project and revenue metrics."""
    account_id = payload.get('account_id')
    contract_value = Decimal(payload.get('contract_value') or 0)
    
    if account_id and contract_value:
        today = date.today()
        month_start = date(today.year, today.month, 1)
        
        # Update revenue metrics
        RevenueMetric.objects.update_or_create(
            month=month_start,
            account_id=account_id,
            defaults={
                'contracted_value': models.F('contracted_value') + contract_value,
                'projects_count': models.F('projects_count') + 1,
            }
        )


def _process_activity_event(event_type, payload):
    """Update activity metrics."""
    related_id = payload.get('related_id')
    activity_type = payload.get('activity_type')
    
    # Update daily account metrics if related to an account
    # This would require looking up the account from related_id
    logger.info(f"Processing activity event: {event_type} - {activity_type}")


def _archive_to_s3(event_type, aggregate_type, aggregate_id, payload):
    """Archive raw event to S3."""
    try:
        s3 = boto3.client('s3', region_name=settings.AWS_REGION)
        
        today = date.today()
        key = f"events/{today.year}/{today.month:02d}/{today.day:02d}/{aggregate_type}/{aggregate_id}.json"
        
        s3.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=json.dumps(payload),
            ContentType='application/json'
        )
        
        logger.info(f"Archived event to S3: {key}")
    except Exception as e:
        logger.error(f"Failed to archive to S3: {e}")
