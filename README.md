# CRM Analytics Service

Django-based analytics and event processing service for the consulting CRM. This service consumes events from the transactional database, processes them asynchronously via AWS SQS, and generates analytics-ready data models.

## � See It Working (30 seconds)

```bash
cd consulting-crm-analytics
source venv/Scripts/activate
python show_analytics.py
```

**Output:**
```
📊 ANALYTICS WORKING - REAL BUSINESS DATA

Event Activity:
  2025-12-23 | INSERT_ACCOUNTS      | Count: 1
  2025-12-23 | INSERT_LEADS         | Count: 3
  2025-12-23 | UPDATE_LEADS         | Count: 1

Business Metrics:
  📈 Total Leads Created: 4
  🔄 Lead Updates: 1
  🏢 Total Accounts Created: 1

✅ ANALYTICS ARE REAL
```

**This proves:** Events flow from CRM → Analytics → Queryable Insights

## �📐 Architecture Overview

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the complete architecture diagram and design decisions.

See **[docs/IDEMPOTENCY.md](docs/IDEMPOTENCY.md)** for production-grade failure handling and idempotency implementation.

### How Data Flows (30-second version)

1. **CRM Event Occurs** → User creates/updates lead in Supabase
2. **Trigger Fires** → Event automatically inserted into `event_outbox` (same transaction)
3. **Celery Polls** → Every 30s, batch of events fetched and published to SQS
4. **Workers Process** → Celery workers consume from SQS, update analytics tables, archive to S3
5. **API Serves** → Django REST API exposes pre-aggregated data to dashboards

**Key Properties:** 
- ✅ Events never lost (transactional outbox)
- ✅ Processing is idempotent (safe to retry)
- ✅ Failures are retried automatically (exponential backoff)
- ✅ Dead-letter queue for permanent failures

## Architecture

```
┌─────────────────┐
│ Supabase/       │
│ Postgres        │◄─── Transactional CRM data
│ event_outbox    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Event Poller    │◄─── Celery Beat (scheduled)
│ (Celery Task)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ AWS SQS         │◄─── Decoupled event queue
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Event Workers   │◄─── Celery workers
│ (Process events)│
└────────┬────────┘
         │
         ├──► AWS S3 (raw archive)
         └──► Analytics DB (aggregates)
```

## Components

### 1. Event Poller (`events/tasks.py`)
- Polls `event_outbox` table for unprocessed events
- Publishes to SQS
- Marks events as processed

### 2. Event Processor (`events/consumers.py`)
- Consumes from SQS
- Validates and normalizes events
- Updates analytics tables
- Archives raw events to S3

### 3. Analytics Models (`events/models.py`)
- Time-series aggregates
- Daily/weekly/monthly rollups
- Funnel metrics
- Revenue tracking

### 4. REST API (`api/`)
- Read-only endpoints for dashboards
- Filtered by date range, account, etc.
- Optimized for BI queries

## Setup

### 1. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your actual credentials
```

### 3. Run Migrations

```bash
python manage.py migrate
```

### 4. Start Services

**Terminal 1 - Django API:**
```bash
python manage.py runserver
```

**Terminal 2 - Celery Worker:**
```bash
celery -A analytics worker --loglevel=info
```

**Terminal 3 - Celery Beat (Scheduler):**
```bash
celery -A analytics beat --loglevel=info
```

## Development Workflow

1. **Add new analytics table** → Create model in `events/models.py`
2. **Add event processor** → Update `events/consumers.py`
3. **Expose via API** → Add view in `api/views.py`
4. **Test locally** → Insert test data in CRM backend

## AWS Resources Needed

- **SQS Queue:** `crm-events`
- **S3 Bucket:** `crm-events-archive`
- **IAM Role/User:** with `sqs:SendMessage`, `sqs:ReceiveMessage`, `s3:PutObject`

## Next Steps

- [ ] Set up AWS SQS queue
- [ ] Create S3 bucket for event archive
- [ ] Configure IAM credentials
- [ ] Deploy to EC2 or ECS
- [ ] Integrate BI tool (Metabase/Superset)
