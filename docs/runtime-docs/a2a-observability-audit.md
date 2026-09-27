# A2A Heartbeat Observability Audit

## Changes made (all files lint-clean, 115 tests pass):

### adapter_server.py (sandbox-side)
1. ✅ `logging.basicConfig(level=INFO)` in `main()` — was missing, all logs were at WARNING default
2. ✅ File logging to `/tmp/adapter.log` — persistent post-mortem via `docker exec cat /tmp/adapter.log`
3. ✅ Event-loop watchdog thread — detects if asyncio loop is blocked (ERROR log)
4. ✅ `_with_heartbeats` full lifecycle: stream_id, drain task start/chunk/end, heartbeat count+timing, stream complete stats
5. ✅ `/message:stream` request logging with prompt preview, context_id, task_id
6. ✅ Active stream tracker (`_active_streams` dict) 
7. ✅ `/debug/streams` endpoint for live inspection
8. ✅ `_track_stream` / `_untrack_stream` for stream state (fixed: _untrack_stream now called in finally block)

### copilot_backend.py (sandbox-side)
9. ✅ `_on_event` callback: INFO level (was DEBUG)
10. ✅ `session.send()` explicit timing with WARNING if >5s (event loop block indicator)
11. ✅ `_run_turn` heartbeat yield: INFO level with elapsed time
12. ✅ `_run_turn` event dequeue: INFO level with elapsed + event type
13. ✅ `_run_turn` terminal event: INFO level
14. ✅ `_run_turn` finally block: INFO level (was DEBUG)

### as_client.py (backend-side)
15. ✅ Stream open log with URL, context_id, timeout config
16. ✅ Stream connected log with status code and connection time
17. ✅ Every SSE line logged at INFO with line#, gap, elapsed
18. ✅ Gap >30s logged at WARNING level
19. ✅ Stream error logged at ERROR with full stats (lines, events, max_gap, duration)
20. ✅ Stream close log with full stats

### inner_loop.py (backend-side)
21. ✅ Heartbeat received logged at DEBUG
22. ✅ Bridged tool execution: INFO log when starting (SSE read paused)
23. ✅ Bridged tool execution: INFO log when complete with duration
24. ✅ Bridged tool execution: WARNING if tool took >30s

## What this will tell us:

### If event loop is blocked (Hypothesis A):
- Watchdog thread will emit: "EVENT LOOP BLOCKED: no response for 5s"
- session.send() timing will show >5s duration
- No heartbeat logs from _with_heartbeats (loop can't run wait_for)

### If heartbeats generated but not reaching client (Hypothesis B):
- adapter logs show heartbeat injection
- client logs show NO SSE lines during gap
- Client max_gap > 120s → ReadTimeout

### If stream dies silently (Hypothesis C):
- drain task will log "ended" or "generator raised" 
- _with_heartbeats will log "stream complete"
- But client won't see the close

### If bridged tool blocks the SSE read loop (Hypothesis D):
- inner_loop.py will log "starting bridged tool execution (SSE read loop paused)"
- Tool duration will be logged
- Heartbeats accumulate in httpx buffer (not read until tool completes)
