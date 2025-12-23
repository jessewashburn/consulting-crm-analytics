"""
Celery configuration for analytics project.
"""
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'analytics.settings')

app = Celery('analytics')

# Load config from Django settings with CELERY_ prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Periodic task schedule
app.conf.beat_schedule = {
    'poll-event-outbox': {
        'task': 'events.tasks.poll_event_outbox',
        'schedule': 30.0,  # Run every 30 seconds
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
