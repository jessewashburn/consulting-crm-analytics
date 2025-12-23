# CRM Analytics Architecture

## System Overview

This system implements an **event-driven analytics pipeline** that processes CRM events asynchronously without impacting transactional workloads.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CRM TRANSACTIONAL LAYER                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Supabase PostgreSQL (System of Record)                              │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │   │
│  │  │  leads   │  │ accounts │  │ projects │  │activities│            │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘            │   │
│  │       │             │             │             │                    │   │
│  │       └─────────────┴─────────────┴─────────────┘                    │   │
│  │                          │                                            │   │
│  │                   [Database Triggers]                                │   │
│  │                          │                                            │   │
│  │                          ▼                                            │   │
│  │               ┌────────────────────┐                                 │   │
│  │               │   event_outbox     │  ◄── Transactional Outbox       │   │
│  │               │  - event_id (PK)   │      Pattern (At-least-once)    │   │
│  │               │  - event_type      │                                 │   │
│  │               │  - aggregate_id    │                                 │   │
│  │               │  - payload         │                                 │   │
│  │               │  - created_at      │                                 │   │
│  │               │  - processed_at    │                                 │   │
│  │               │  - retry_count     │                                 │   │
│  │               └────────┬───────────┘                                 │   │
│  └─────────────────────────┼─────────────────────────────────────────────┘   │
└────────────────────────────┼──────────────────────────────────────────────────┘
                             │
                             │ Polling (every 30s)
                             │ SELECT ... WHERE processed_at IS NULL
                             │ FOR UPDATE SKIP LOCKED
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ASYNC PROCESSING LAYER (Django)                         │
│  ┌───────────────────────────────────────────────────────────────────┐     │
│  │  Celery Beat (Scheduler)                                           │     │
│  │  ┌──────────────────────────────────────────────────┐             │     │
│  │  │  Task: poll_event_outbox (every 30s)             │             │     │
│  │  └──────────────────┬───────────────────────────────┘             │     │
│  └────────────────────┼───────────────────────────────────────────────┘     │
│                       │                                                      │
│                       │ Publish batch                                        │
│                       ▼                                                      │
│  ┌────────────────────────────────────────────────────────┐                │
│  │  AWS SQS Queue: crm-events                             │                │
│  │  - Decouples producer from consumer                    │                │
│  │  - Handles backpressure                                │                │
│  │  - Built-in retry with exponential backoff             │                │
│  │  - Dead-letter queue for poison messages               │                │
│  └────────────────────┬───────────────────────────────────┘                │
│                       │                                                      │
│                       │ Consume messages                                     │
│                       ▼                                                      │
│  ┌───────────────────────────────────────────────────────────────────┐     │
│  │  Celery Workers (6 concurrent processes)                           │     │
│  │  ┌────────────────────────────────────────────────────┐           │     │
│  │  │  Task: process_event                               │           │     │
│  │  │  - Idempotency check (event_id)                    │           │     │
│  │  │  - Business logic routing                          │           │     │
│  │  │  - Update analytics aggregates                     │           │     │
│  │  │  - Archive to S3                                   │           │     │
│  │  │  - Error handling & retries                        │           │     │
│  │  └────────────┬───────────────────┬───────────────────┘           │     │
│  └───────────────┼───────────────────┼─────────────────────────────────     │
└──────────────────┼───────────────────┼──────────────────────────────────────┘
                   │                   │
                   │                   │ On Failure (after retries)
                   │                   ▼
                   │         ┌──────────────────────────┐
                   │         │  failed_events table     │
                   │         │  - event_id              │
                   │         │  - error_message         │
                   │         │  - retry_count           │
                   │         │  - failed_at             │
                   │         └──────────────────────────┘
                   │
                   │ On Success
                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ANALYTICS & STORAGE LAYER                           │
│  ┌──────────────────────────┐      ┌──────────────────────────┐            │
│  │  AWS S3 (Archive)        │      │  PostgreSQL (Analytics)  │            │
│  │  events/                 │      │  ┌────────────────────┐  │            │
│  │    2025/12/22/           │      │  │ daily_account_     │  │            │
│  │      leads/               │      │  │   metrics          │  │            │
│  │        {uuid}.json       │      │  ├────────────────────┤  │            │
│  │                          │      │  │ lead_funnel_       │  │            │
│  │  - Immutable audit log   │      │  │   metrics          │  │            │
│  │  - Replay capability     │      │  ├────────────────────┤  │            │
│  │  - Compliance            │      │  │ revenue_metrics    │  │            │
│  └──────────────────────────┘      │  ├────────────────────┤  │            │
│                                     │  │ event_counts       │  │            │
│                                     │  └────────────────────┘  │            │
│                                     │                          │            │
│                                     │  - Pre-aggregated data   │            │
│                                     │  - Fast queries for BI   │            │
│                                     └────────────┬─────────────┘            │
└────────────────────────────────────────────────┼──────────────────────────────┘
                                                  │
                                                  │ REST API
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API & BI LAYER                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Django REST Framework                                               │   │
│  │  GET /api/daily-metrics/     - Account-level daily rollups           │   │
│  │  GET /api/funnel-metrics/    - Lead conversion funnel                │   │
│  │  GET /api/revenue-metrics/   - Revenue by account/month              │   │
│  │  GET /api/event-counts/      - Processing health metrics             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                       │
│                                      │ Consumed by                           │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  BI Dashboard (Metabase/Superset/Custom)                             │   │
│  │  - Real-time CRM analytics                                            │   │
│  │  - Sales pipeline health                                              │   │
│  │  - Revenue tracking                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Event Capture (Transactional)
```
CRM Action (INSERT/UPDATE/DELETE)
  → PostgreSQL Transaction Begins
  → Business table modified (leads, accounts, etc.)
  → Trigger fires
  → event_outbox row inserted (SAME TRANSACTION)
  → Transaction Commits
  ✓ Event guaranteed to be captured (no data loss)
```

### 2. Event Polling (Every 30s)
```
Celery Beat Scheduler
  → Triggers poll_event_outbox task
  → SELECT ... WHERE processed_at IS NULL FOR UPDATE SKIP LOCKED
  → Batch of up to 100 events retrieved
  → Events published to SQS
  → event_outbox rows marked as processed
  ✓ At-least-once delivery guaranteed
```

### 3. Event Processing (Async)
```
Celery Worker
  → Receives message from SQS
  → Idempotency check (event_id already processed?)
  → Route to handler (lead, account, project, activity)
  → Update analytics aggregates
  → Archive raw event to S3
  → Mark as complete
  ✓ Failure handling with retries
```

### 4. Analytics Consumption (On-Demand)
```
BI Dashboard / API Client
  → GET /api/daily-metrics/?date=2025-12-22
  → Django REST Framework
  → Query pre-aggregated analytics tables
  → Return JSON response
  ✓ Fast queries, no impact on transactional DB
```

## Key Design Decisions

### Transactional Outbox Pattern
**Why:** Ensures events are never lost. The event is written in the same database transaction as the business data.

**Alternative Rejected:** Direct async publish (loses events if publish fails after DB commit).

### Polling Instead of Change Data Capture (CDC)
**Why:** Simpler to implement, maintain, and debug. CDC (Debezium, etc.) adds operational complexity.

**Trade-off:** 30-second latency is acceptable for analytics workloads.

### SQS as Message Queue
**Why:** 
- Fully managed (no ops overhead)
- Built-in retry with exponential backoff
- Dead-letter queue support
- 1M free requests/month

**Alternative Considered:** Kafka (overkill for this scale).

### Separate Analytics Database
**Why:** Could use same Postgres instance with separate tables. Already doing this.

**Future:** Move to Redshift/BigQuery at higher scale for columnar storage.

### S3 Event Archive
**Why:**
- Immutable audit log
- Enables event replay if analytics tables corrupted
- Compliance/audit requirements
- Cheap long-term storage

## Failure Handling

### Idempotency
- Each event has a unique `event_id` (UUID)
- Before processing, check if already processed
- Duplicate events are safely ignored

### Retries
- SQS automatically retries failed messages
- Celery tasks have built-in retry logic
- Exponential backoff prevents thundering herd

### Dead Letter Queue
- After 3 failed attempts, move to `failed_events` table
- Manual investigation and replay possible
- Alerts can be configured

### Monitoring Points
1. Event outbox lag (unprocessed events count)
2. SQS queue depth (backlog)
3. Failed event count
4. Processing latency (p50, p99)

## Scalability Considerations

**Current Capacity:**
- ~10,000 events/day
- 30s latency acceptable

**Scaling Levers:**
1. Increase Celery worker count (horizontal)
2. Reduce polling interval (10s, 5s)
3. Increase batch size (100 → 500)
4. Add read replicas for analytics queries
5. Shard by event type

**Breaking Point:**
- ~100,000 events/day → Consider CDC (Debezium)
- Analytics tables too large → Move to columnar DB (Redshift)
- Real-time requirements (<1s) → Stream processing (Kafka + Flink)

## Technology Choices

| Component | Technology | Why |
|-----------|-----------|-----|
| Transactional DB | PostgreSQL (Supabase) | Strong ACID guarantees, triggers, JSONB |
| Message Queue | AWS SQS | Fully managed, simple, cheap |
| Task Scheduler | Celery Beat | Standard Python async |
| Worker Pool | Celery | Battle-tested, good monitoring |
| Object Storage | AWS S3 | Cheap, durable (99.999999999%) |
| Analytics DB | PostgreSQL | Same as transactional (simpler ops) |
| API Framework | Django REST Framework | Fast development, good docs |

## Cost Estimate

**Monthly costs at 10,000 events/day:**
- SQS: $0 (within free tier)
- S3: ~$0.10 (5GB storage)
- Compute: ~$0 (local dev) or ~$7/month (t3.micro EC2)
- **Total: < $10/month**

## Next Steps

1. ✅ Event capture with triggers
2. ✅ Async processing with Celery
3. ✅ AWS integration (SQS, S3)
4. 🔄 Add idempotency checks
5. 🔄 Add failed_events table
6. ⏳ Implement actual analytics aggregation logic
7. ⏳ Build BI dashboards (Metabase)
8. ⏳ Add monitoring & alerts
9. ⏳ Deploy to AWS EC2/ECS
