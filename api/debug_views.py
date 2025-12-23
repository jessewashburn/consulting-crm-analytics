"""
Debug API views for developer console.
Simple endpoints to observe event processing pipeline.
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import connection
from events.models import EventCount, ProcessedEvent, FailedEvent
from datetime import date, timedelta


@api_view(['GET'])
def events_list(request):
    """List recent events from event_outbox with status."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                eo.id,
                eo.event_id,
                eo.event_type,
                eo.aggregate_type,
                eo.aggregate_id,
                eo.created_at,
                eo.processed_at,
                eo.retry_count,
                CASE 
                    WHEN fe.event_id IS NOT NULL THEN 'failed'
                    WHEN pe.event_id IS NOT NULL THEN 'processed'
                    WHEN eo.processed_at IS NOT NULL THEN 'completed'
                    ELSE 'pending'
                END as status
            FROM event_outbox eo
            LEFT JOIN processed_events pe ON eo.event_id = pe.event_id
            LEFT JOIN failed_events fe ON eo.event_id = fe.event_id AND fe.resolved_at IS NULL
            ORDER BY eo.created_at DESC
            LIMIT 50
        """)
        
        columns = [col[0] for col in cursor.description]
        events = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    return Response({
        'count': len(events),
        'events': events
    })


@api_view(['GET'])
def event_trace(request, event_id):
    """Trace a single event through the entire pipeline."""
    trace = {
        'event_id': event_id,
        'outbox': None,
        'processed': None,
        'failed': None,
        'analytics': []
    }
    
    # Get from event_outbox
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, event_type, aggregate_type, aggregate_id, 
                   payload, created_at, processed_at, published_at, 
                   retry_count, last_error
            FROM event_outbox
            WHERE event_id = %s
        """, [event_id])
        
        row = cursor.fetchone()
        if row:
            trace['outbox'] = {
                'id': str(row[0]),
                'event_type': row[1],
                'aggregate_type': row[2],
                'aggregate_id': str(row[3]),
                'payload': row[4],
                'created_at': row[5].isoformat() if row[5] else None,
                'processed_at': row[6].isoformat() if row[6] else None,
                'published_at': row[7].isoformat() if row[7] else None,
                'retry_count': row[8],
                'last_error': row[9]
            }
    
    # Check if processed
    try:
        processed = ProcessedEvent.objects.get(event_id=event_id)
        trace['processed'] = {
            'processed_at': processed.processed_at.isoformat(),
            'event_type': processed.event_type,
            'aggregate_type': processed.aggregate_type
        }
    except ProcessedEvent.DoesNotExist:
        pass
    
    # Check if failed
    try:
        failed = FailedEvent.objects.filter(event_id=event_id, resolved_at__isnull=True).first()
        if failed:
            trace['failed'] = {
                'error_message': failed.error_message,
                'retry_count': failed.retry_count,
                'first_failed_at': failed.first_failed_at.isoformat(),
                'last_failed_at': failed.last_failed_at.isoformat()
            }
    except:
        pass
    
    # Find related analytics
    if trace['outbox']:
        event_type = trace['outbox']['event_type']
        aggregate_type = trace['outbox']['aggregate_type']
        created_date = trace['outbox']['created_at'][:10] if trace['outbox']['created_at'] else None
        
        if created_date:
            event_counts = EventCount.objects.filter(
                date=created_date,
                event_type=event_type,
                aggregate_type=aggregate_type
            ).values()
            trace['analytics'] = list(event_counts)
    
    return Response(trace)


@api_view(['GET'])
def analytics_summary(request):
    """Summary metrics for analytics dashboard."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)
    
    # Event counts
    total_events = EventCount.objects.aggregate(
        total=models.Sum('count')
    )['total'] or 0
    
    today_events = EventCount.objects.filter(date=today).aggregate(
        total=models.Sum('count')
    )['total'] or 0
    
    # By type
    by_type = EventCount.objects.values('event_type').annotate(
        total=models.Sum('count')
    ).order_by('-total')
    
    # Daily trend (last 7 days)
    daily_trend = EventCount.objects.filter(
        date__gte=week_ago
    ).values('date').annotate(
        total=models.Sum('count')
    ).order_by('date')
    
    # Processing health
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE processed_at IS NULL) as pending,
                COUNT(*) FILTER (WHERE processed_at IS NOT NULL) as processed,
                COUNT(*) as total
            FROM event_outbox
        """)
        pending, processed, total = cursor.fetchone()
    
    failed_count = FailedEvent.objects.filter(resolved_at__isnull=True).count()
    
    return Response({
        'totals': {
            'all_time': total_events,
            'today': today_events,
            'pending': pending,
            'processed': processed,
            'failed': failed_count
        },
        'by_type': list(by_type),
        'daily_trend': list(daily_trend),
        'health': {
            'success_rate': round((processed / total * 100) if total > 0 else 0, 2),
            'processing': pending,
            'failed': failed_count
        }
    })


@api_view(['POST'])
def create_test_event(request):
    """Create a test event directly in event_outbox for testing."""
    import uuid
    from django.utils import timezone
    
    event_type = request.data.get('event_type', 'INSERT_LEADS')
    aggregate_type = request.data.get('aggregate_type', 'leads')
    
    # Build test payload
    payload = {
        'id': str(uuid.uuid4()),
        'company_name': request.data.get('company_name', 'Test Company'),
        'lead_status': request.data.get('lead_status', 'new'),
        'estimated_value': request.data.get('estimated_value', '50000'),
        'test_event': True,
        'created_via': 'developer_console'
    }
    
    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO event_outbox (event_type, aggregate_type, aggregate_id, payload)
            VALUES (%s, %s, %s, %s)
            RETURNING id, event_id, created_at
        """, [
            event_type,
            aggregate_type,
            payload['id'],
            payload
        ])
        
        row = cursor.fetchone()
        
    return Response({
        'success': True,
        'event': {
            'id': str(row[0]),
            'event_id': row[1],
            'event_type': event_type,
            'created_at': row[2].isoformat(),
            'payload': payload
        }
    })

from django.db import models
