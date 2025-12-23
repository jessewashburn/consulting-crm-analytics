"""
Backfill analytics from existing events in event_outbox.

This script reads all processed events and populates the analytics tables
to prove the system works end-to-end with real data.
"""
from django.db import connection
from django.db.models import F
from events.models import EventCount, LeadFunnelMetric
from datetime import date, datetime
from decimal import Decimal

def backfill_event_counts():
    """Backfill EventCount from event_outbox."""
    print("="*60)
    print("BACKFILLING EVENT COUNTS")
    print("="*60)
    
    with connection.cursor() as cursor:
        # Get all events grouped by date and type
        cursor.execute("""
            SELECT 
                DATE(created_at) as event_date,
                event_type,
                aggregate_type,
                COUNT(*) as event_count
            FROM event_outbox
            GROUP BY DATE(created_at), event_type, aggregate_type
            ORDER BY event_date, event_type
        """)
        
        rows = cursor.fetchall()
        print(f"\nFound {len(rows)} unique event type/date combinations\n")
        
        for event_date, event_type, aggregate_type, count in rows:
            # Update or create EventCount
            obj, created = EventCount.objects.update_or_create(
                date=event_date,
                event_type=event_type,
                aggregate_type=aggregate_type,
                defaults={'count': count}
            )
            
            action = "Created" if created else "Updated"
            print(f"  {action}: {event_date} | {event_type:20} | {aggregate_type:10} | count: {count}")
    
    # Show summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    total_records = EventCount.objects.count()
    total_events = sum(ec.count for ec in EventCount.objects.all())
    print(f"Total EventCount records: {total_records}")
    print(f"Total events tracked: {total_events}")


def backfill_lead_funnel():
    """Backfill LeadFunnelMetric from lead events."""
    print("\n" + "="*60)
    print("BACKFILLING LEAD FUNNEL METRICS")
    print("="*60)
    
    with connection.cursor() as cursor:
        # Get lead events grouped by date and status
        cursor.execute("""
            SELECT 
                DATE(created_at) as event_date,
                payload->>'lead_status' as lead_status,
                payload->>'estimated_value' as estimated_value,
                COUNT(*) as lead_count
            FROM event_outbox
            WHERE aggregate_type = 'leads'
            GROUP BY DATE(created_at), payload->>'lead_status', payload->>'estimated_value'
            ORDER BY event_date
        """)
        
        rows = cursor.fetchall()
        print(f"\nFound {len(rows)} lead events\n")
        
        # Aggregate by date
        by_date = {}
        for event_date, lead_status, estimated_value_str, lead_count in rows:
            if event_date not in by_date:
                by_date[event_date] = {
                    'new': 0, 'contacted': 0, 'qualified': 0, 'won': 0, 'lost': 0,
                    'total_value': Decimal('0'), 'won_value': Decimal('0'), 'lost_value': Decimal('0')
                }
            
            # Count by status
            status = (lead_status or 'new').lower()
            if status in by_date[event_date]:
                by_date[event_date][status] += lead_count
            
            # Track value
            try:
                value = Decimal(estimated_value_str or '0')
                by_date[event_date]['total_value'] += value
                if status == 'won':
                    by_date[event_date]['won_value'] += value
                elif status == 'lost':
                    by_date[event_date]['lost_value'] += value
            except:
                pass
        
        # Create or update metrics
        for event_date, metrics in by_date.items():
            obj, created = LeadFunnelMetric.objects.update_or_create(
                date=event_date,
                defaults={
                    'new_leads': metrics['new'],
                    'contacted_leads': metrics['contacted'],
                    'qualified_leads': metrics['qualified'],
                    'won_leads': metrics['won'],
                    'lost_leads': metrics['lost'],
                    'total_estimated_value': metrics['total_value'],
                    'won_value': metrics['won_value'],
                    'lost_value': metrics['lost_value'],
                }
            )
            
            action = "Created" if created else "Updated"
            print(f"  {action}: {event_date}")
            print(f"    New: {metrics['new']}, Contacted: {metrics['contacted']}, Qualified: {metrics['qualified']}")
            print(f"    Won: {metrics['won']}, Lost: {metrics['lost']}")
            print(f"    Total Value: ${metrics['total_value']}")


def verify_data():
    """Verify the backfilled data matches source."""
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)
    
    with connection.cursor() as cursor:
        # Count total events in outbox
        cursor.execute("SELECT COUNT(*) FROM event_outbox")
        total_outbox = cursor.fetchone()[0]
        
        # Count total in analytics
        total_analytics = sum(ec.count for ec in EventCount.objects.all())
        
        print(f"\nEvents in outbox: {total_outbox}")
        print(f"Events in analytics: {total_analytics}")
        
        if total_outbox == total_analytics:
            print("✅ MATCH! All events accounted for.")
        else:
            print(f"⚠️  MISMATCH! Difference: {abs(total_outbox - total_analytics)}")
        
        # Show lead counts
        cursor.execute("SELECT COUNT(*) FROM event_outbox WHERE aggregate_type = 'leads'")
        leads_in_outbox = cursor.fetchone()[0]
        
        total_leads_in_funnel = sum(
            lf.new_leads + lf.contacted_leads + lf.qualified_leads + lf.won_leads + lf.lost_leads
            for lf in LeadFunnelMetric.objects.all()
        )
        
        print(f"\nLead events in outbox: {leads_in_outbox}")
        print(f"Leads in funnel metrics: {total_leads_in_funnel}")
        
        if leads_in_outbox == total_leads_in_funnel:
            print("✅ LEAD FUNNEL MATCH!")
        else:
            print(f"⚠️  Difference: {abs(leads_in_outbox - total_leads_in_funnel)}")


if __name__ == '__main__':
    backfill_event_counts()
    backfill_lead_funnel()
    verify_data()
    
    print("\n" + "="*60)
    print("✅ BACKFILL COMPLETE")
    print("="*60)
    print("\nNext: Test the API endpoints")
    print("  curl http://localhost:8000/api/event-counts/")
    print("  curl http://localhost:8000/api/funnel-metrics/")
