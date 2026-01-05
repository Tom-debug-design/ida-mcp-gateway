# agent_outbox

Legg JSON-jobber her. Runner plukker FIFO (eldst først).

## Job types

### WEB_SEARCH
```json
{
  "job_id": "job_001",
  "type": "WEB_SEARCH",
  "query": "best affiliate niches 2026",
  "num_results": 10,
  "recency_days": 30
}
