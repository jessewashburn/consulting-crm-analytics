"""
Celery tasks for event processing with idempotency and failure handling.
"""
import json
import logging
import traceback
from datetime import date
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

import boto3

from .models import (
    DailyAccountMetric, LeadFunnelMetric, RevenueMetric, EventCount,
    ProcessedEvent, FailedEvent
)

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [60, 300, 900]  # 1min, 5min, 15min


@shared_task
def poll_event_outbox():
    """
    Poll the event_outbox table for unprocessed events.
    Publish to SQS and mark as processed.
    """
    batch_size = settings.EVENT_BATCH_SIZE

    with connection.cursor() as cursor:
        # Fetch unprocessed events, prioritizing those with fewer retries
        cursor.execute("""
            SELECT id, event_id, event_type, aggregate_type, aggregate_id, 
                   payload, created_at, retry_count
            FROM event_outbox
            WHERE processed_at IS NULL
            ORDER BY retry_count ASC, created_at ASC
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
                    (event_uuid, event_id, event_type, aggregate_type, 
                     aggregate_id, payload, created_at, retry_count) = event

                    message_body = json.dumps({
                        'event_id': event_id,  # Use deterministic event_id
                        'event_type': event_type,
                        'aggregate_type': aggregate_type,
                        'aggregate_id': str(aggregate_id),
                        'payload': payload,
                        'created_at': created_at.isoformat(),
                        'retry_count': retry_count,
                    })

                    sqs.send_message(
                        QueueUrl=settings.SQS_QUEUE_URL,
                        MessageBody=message_body,
                        MessageDeduplicationId=event_id,  # Idempotent SQS
                        MessageGroupId=aggregate_type,  # FIFO grouping
                    )

                logger.info(f"Published {len(events)} events to SQS")
            except Exception as e:
                logger.error(f"Failed to publish to SQS: {e}")
                # Increment retry count for failed events
                event_uuids = [event[0] for event in events]
                cursor.execute("""
                    UPDATE event_outbox
                    SET retry_count = retry_count + 1,
                        last_error = %s
                    WHERE id = ANY(%s::uuid[])
                """, [str(e), event_uuids])
                return 0

        # Mark events as processed
        event_uuids = [event[0] for event in events]
        cursor.execute("""
            UPDATE event_outbox
            SET processed_at = NOW(), published_at = NOW()
            WHERE id = ANY(%s::uuid[])
        """, [event_uuids])

        # Process events locally (alternative to SQS consumer)
        for event in events:
            (event_uuid, event_id, event_type, aggregate_type, 
             aggregate_id, payload, created_at, retry_count) = event
            
            process_event.delay(
                event_id=event_id,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=str(aggregate_id),
                payload=payload,
                retry_count=retry_count
            )

        logger.info(f"Marked {len(events)} events as processed")

        return len(events)


@shared_task(bind=True, max_retries=MAX_RETRIES)
def process_event(self, event_id, event_type, aggregate_type, aggregate_id, payload, retry_count=0):
    """
    Process a single event with idempotency and failure handling.
    
    Args:
        event_id: Deterministic event identifier for idempotency
        event_type: Type of event (INSERT_LEADS, UPDATE_ACCOUNT, etc.)
        aggregate_type: Entity type (leads, accounts, projects, activities)
        aggregate_id: UUID of the entity
        payload: Event data (JSON)
        retry_count: Number of previous retry attempts
    """
    logger.info(f"Processing event: {event_type} ({event_id}) for {aggregate_type}:{aggregate_id}")

    # ===== IDEMPOTENCY CHECK =====
    # Check if this exact event has already been processed
    if ProcessedEvent.objects.filter(event_id=event_id).exists():
        logger.warning(f"Event {event_id} already processed, skipping (idempotent)")
        return {'status': 'skipped', 'reason': 'already_processed'}

    try:
        with transaction.atomic():
            # Track event count
            today = date.today()
            from django.db import models
            
            # Get or create, then increment
            event_count, created = EventCount.objects.get_or_create(
                date=today,
                event_type=event_type,
                aggregate_type=aggregate_type,
                defaults={'count': 0}
            )
            event_count.count = models.F('count') + 1
            event_count.save(update_fields=['count'])

            # Route to specific handler
            if aggregate_type == 'leads':
                _process_lead_event(event_type, payload)
            elif aggregate_type == 'accounts':
                _process_account_event(event_type, payload)
            elif aggregate_type == 'projects':
                _process_project_event(event_type, payload)
            elif aggregate_type == 'activities':
                _process_activity_event(event_type, payload)

            # Archive to S3 (optional, outside transaction)
            if settings.S3_BUCKET_NAME:
                _archive_to_s3(event_id, event_type, aggregate_type, aggregate_id, payload)

            # Mark as processed (idempotency record)
            ProcessedEvent.objects.create(
                event_id=event_id,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
            )

            logger.info(f"Successfully processed event {event_id}")
            return {'status': 'success', 'event_id': event_id}

    except Exception as e:
        error_message = str(e)
        error_trace = traceback.format_exc()
        
        logger.error(f"Error processing event {event_id}: {error_message}", exc_info=True)

        # ===== RETRY LOGIC =====
        if retry_count < MAX_RETRIES:
            # Retry with exponential backoff
            countdown = RETRY_BACKOFF_SECONDS[retry_count] if retry_count < len(RETRY_BACKOFF_SECONDS) else 900
            logger.warning(f"Retrying event {event_id} in {countdown}s (attempt {retry_count + 1}/{MAX_RETRIES})")
            
            raise self.retry(
                exc=e,
                countdown=countdown,
                kwargs={
                    'event_id': event_id,
                    'event_type': event_type,
                    'aggregate_type': aggregate_type,
                    'aggregate_id': aggregate_id,
                    'payload': payload,
                    'retry_count': retry_count + 1,
                }
            )
        else:
            # ===== DEAD LETTER QUEUE =====
            # Max retries exceeded, move to failed_events table
            logger.error(f"Max retries exceeded for event {event_id}, moving to failed_events")
            
            FailedEvent.objects.create(
                event_id=event_id,
                event_type=event_type,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                payload=payload,
                error_message=error_message,
                error_trace=error_trace,
                retry_count=retry_count,
            )
            
            # TODO: Send alert (email, Slack, PagerDuty)
            _send_failure_alert(event_id, event_type, error_message)
            
            return {'status': 'failed', 'event_id': event_id, 'error': error_message}


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
    from django.db import models
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
    logger.info(f"Processing activity event: {event_type} - {activity_type}")


def _archive_to_s3(event_id, event_type, aggregate_type, aggregate_id, payload):
    """Archive raw event to S3 with deterministic key."""
    try:
        s3 = boto3.client('s3', region_name=settings.AWS_REGION)

        today = date.today()
        # Use event_id in key for idempotent uploads
        key = f"events/{today.year}/{today.month:02d}/{today.day:02d}/{aggregate_type}/{event_id}.json"

        event_data = {
            'event_id': event_id,
            'event_type': event_type,
            'aggregate_type': aggregate_type,
            'aggregate_id': aggregate_id,
            'payload': payload,
            'archived_at': timezone.now().isoformat(),
        }

        s3.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=key,
            Body=json.dumps(event_data, indent=2),
            ContentType='application/json',
        )

        logger.info(f"Archived event to S3: {key}")
    except Exception as e:
        logger.error(f"Failed to archive to S3: {e}")
        # Don't fail the whole task if S3 fails
        pass


def _send_failure_alert(event_id, event_type, error_message):
    """Send alert when event fails after max retries."""
    # TODO: Implement alerting
    # Options:
    # - Send email via SES
    # - Post to Slack webhook
    # - Create PagerDuty incident
    # - Write to CloudWatch Logs
    
    logger.critical(
        f"ALERT: Event processing failed permanently",
        extra={
            'event_id': event_id,
            'event_type': event_type,
            'error': error_message,
        }
    )


@shared_task
def replay_failed_event(failed_event_id):
    """
    Manually replay a failed event from the failed_events table.
    
    Args:
        failed_event_id: UUID of the FailedEvent record
    """
    try:
        failed = FailedEvent.objects.get(id=failed_event_id)
        
        logger.info(f"Replaying failed event: {failed.event_id}")
        
        # Remove from processed events if exists (to allow reprocessing)
        ProcessedEvent.objects.filter(event_id=failed.event_id).delete()
        
        # Reprocess with retry_count=0
        result = process_event.delay(
            event_id=failed.event_id,
            event_type=failed.event_type,
            aggregate_type=failed.aggregate_type,
            aggregate_id=str(failed.aggregate_id),
            payload=failed.payload,
            retry_count=0
        )
        
        # Mark as resolved
        failed.resolved_at = timezone.now()
        failed.resolved_by = 'manual_replay'
        failed.save()
        
        logger.info(f"Successfully replayed failed event: {failed.event_id}")
        return {'status': 'replayed', 'event_id': failed.event_id}
        
    except FailedEvent.DoesNotExist:
        logger.error(f"Failed event {failed_event_id} not found")
        return {'status': 'error', 'message': 'Event not found'}
