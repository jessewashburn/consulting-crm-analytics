"""
Django management command to backfill analytics from event_outbox.
"""
from django.core.management.base import BaseCommand
from django.db import connection
from events.models import EventCount, LeadFunnelMetric
from decimal import Decimal


class Command(BaseCommand):
    help = 'Backfill analytics tables from event_outbox'

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write("BACKFILLING EVENT COUNTS")
        self.stdout.write("=" * 60)
        
        with connection.cursor() as cursor:
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
            self.stdout.write(f"\nFound {len(rows)} unique event type/date combinations\n")
            
            for event_date, event_type, aggregate_type, count in rows:
                obj, created = EventCount.objects.update_or_create(
                    date=event_date,
                    event_type=event_type,
                    aggregate_type=aggregate_type,
                    defaults={'count': count}
                )
                
                action = "Created" if created else "Updated"
                self.stdout.write(f"  {action}: {event_date} | {event_type:20} | {aggregate_type:10} | count: {count}")
        
        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("SUMMARY")
        self.stdout.write("=" * 60)
        total_records = EventCount.objects.count()
        total_events = sum(ec.count for ec in EventCount.objects.all())
        self.stdout.write(f"Total EventCount records: {total_records}")
        self.stdout.write(f"Total events tracked: {total_events}")
        
        # Verification
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("VERIFICATION")
        self.stdout.write("=" * 60)
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM event_outbox")
            total_outbox = cursor.fetchone()[0]
        
        self.stdout.write(f"\nEvents in outbox: {total_outbox}")
        self.stdout.write(f"Events in analytics: {total_events}")
        
        if total_outbox == total_events:
            self.stdout.write(self.style.SUCCESS("✅ MATCH! All events accounted for."))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️  MISMATCH! Difference: {abs(total_outbox - total_events)}"))
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("✅ BACKFILL COMPLETE"))
        self.stdout.write("=" * 60)
        self.stdout.write("\nNext: Test the API")
        self.stdout.write("  python manage.py runserver")
        self.stdout.write("  curl http://localhost:8000/api/event-counts/")
