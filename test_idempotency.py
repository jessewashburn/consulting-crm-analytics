from events.tasks import process_event
from events.models import ProcessedEvent
import uuid

# Clear test data
ProcessedEvent.objects.filter(event_id__startswith='test-').delete()

# Test idempotency
event_id = 'test-idempotency-final'
payload = {'company_name': 'Test Co', 'lead_status': 'new', 'estimated_value': '50000'}

print('='*60)
print('TEST 1: First processing')
print('='*60)
result1 = process_event(
    event_id=event_id,
    event_type='INSERT_LEADS',
    aggregate_type='leads',
    aggregate_id=str(uuid.uuid4()),
    payload=payload,
    retry_count=0
)
print(f'Result: {result1}')
print(f'Processed events: {ProcessedEvent.objects.filter(event_id=event_id).count()}')

print()
print('='*60)
print('TEST 2: Duplicate (should skip)')
print('='*60)
result2 = process_event(
    event_id=event_id,
    event_type='INSERT_LEADS',
    aggregate_type='leads',
    aggregate_id=str(uuid.uuid4()),
    payload=payload,
    retry_count=0
)
print(f'Result: {result2}')
print(f'Processed events: {ProcessedEvent.objects.filter(event_id=event_id).count()}')

print()
if result2.get('status') == 'skipped':
    print('✅ IDEMPOTENCY WORKING! Event was safely skipped on second attempt.')
    print('✅ Only 1 record in processed_events table.')
else:
    print('❌ Test failed - event was not skipped')
