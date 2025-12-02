# Backend Improvement Todo List

Audit date: 2025-12-02

## High Priority

### 1. Client not unregistered on exception in SDK manager
- **File:** `sdk/manager.py:239-241`
- **Problem:** Client is registered in `self.active_clients[task_id]` for interruption, but if an unhandled exception occurs during `client.query()` or `receive_response()`, the client remains in the dict indefinitely.
- **Fix:** Wrap in try-finally to unregister client:
```python
self.active_clients[task_id] = client
try:
    await asyncio.wait_for(client.query(message_to_send), timeout=10.0)
    async for message in client.receive_response():
        # ... process
finally:
    self.active_clients.pop(task_id, None)
```

### 2. Race condition between write queue and cache invalidation
- **File:** `crud/messages.py:18-67`
- **Problem:** `create_message()` uses `@retry_on_db_lock` for write, but cache invalidation happens AFTER `db.commit()`. If another request reads cache before invalidation completes, it gets stale data.
- **Fix:** Move cache invalidation inside the retry-decorated function, or use atomic invalidation with write queue coordination.

---

## Medium Priority

### 3. Add composite index on (room_id, agent_id) for messages
- **File:** `models.py:131-136`
- **Problem:** Queries like `WHERE room_id = ? AND agent_id = ?` in `get_critic_messages()` and `get_messages_after_agent_response()` would benefit from composite index.
- **Fix:**
```python
__table_args__ = (
    Index("idx_message_room_id", "room_id"),
    Index("idx_message_agent_id", "agent_id"),
    Index("idx_message_room_timestamp", "room_id", "timestamp"),
    Index("idx_message_room_agent", "room_id", "agent_id"),  # Add this
)
```

### 4. Optimize room fetch in add_agent_to_room (message loading overhead)
- **File:** `crud/room_agents.py:26-58`
- **Problem:** `get_room_with_relationships()` eagerly loads ALL messages just to check `len(room.messages) > 0`. In large conversations, this is wasteful.
- **Fix:** Use a separate existence check:
```python
has_messages = await db.scalar(
    select(func.count()).where(models.Message.room_id == room_id).limit(1)
) > 0
```

### 5. Fix thread safety in LRU eviction logic
- **File:** `sdk/client_pool.py:62-70`
- **Problem:** `_evict_lru_client()` uses `min()` on `_last_used.keys()` without holding the lock, then calls `cleanup()` which acquires lock. Race condition possible.
- **Fix:** Find LRU client inside locked section:
```python
async def _evict_lru_client(self) -> None:
    async with self._lock:
        if not self._last_used:
            return
        oldest_task_id = min(self._last_used.keys(), key=lambda k: self._last_used[k])
        # ... cleanup inside lock
```

### 6. Replace string-based constraint error detection
- **File:** `routers/rooms.py:40-50`
- **Problem:** Error handling catches SQLite constraint error by string matching, which is fragile and platform-dependent.
- **Fix:**
```python
from sqlalchemy.exc import IntegrityError

try:
    # ... create room
except IntegrityError as e:
    if "rooms.name" in str(e.orig):
        raise RoomAlreadyExistsError(room.name)
    raise
```

### 7. Unvalidated limit parameter in message queries
- **File:** `crud/messages.py:127-154`
- **Problem:** `get_messages_since()` caps limit at 1000, but `get_recent_messages()` and `get_messages_after_agent_response()` accept unlimited limits.
- **Fix:** Add validation to all message query functions:
```python
limit = min(limit, 1000)  # Prevent memory issues
```

### 8. Inefficient room fetch in get_chatting_agents
- **File:** `routers/messages.py:89-94`
- **Problem:** Fetches ALL agents in room to build lookup map, even if only 2-3 are chatting.
- **Fix:** Query only chatting agents directly:
```python
chatting_agents = await crud.get_agents_by_ids(db, chatting_agent_ids)
```

### 9. Agent config cache doesn't track file modification time
- **File:** `models.py:56-112`
- **Problem:** `Agent.get_config_data()` uses 300s TTL but doesn't check if underlying `.md` file was modified. Affects hot-reload reliability.
- **Fix:** Store `(data, mtime)` in cache and compare on cache hit.

### 10. Settings singleton not thread-safe
- **File:** `core/settings.py:220-254`
- **Problem:** Global `_settings` singleton uses double-checked locking without lock. Multiple instances could be created under concurrent access.
- **Fix:**
```python
import threading
_settings_lock = threading.Lock()

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        with _settings_lock:
            if _settings is None:
                _settings = Settings(...)
    return _settings
```

### 11. Asyncio task leak in message router
- **File:** `routers/messages.py:174`
- **Problem:** `asyncio.create_task(trigger_agent_responses())` is fire-and-forget with no tracking. Silent failures possible.
- **Fix:** Store task references in orchestrator or app state:
```python
task = asyncio.create_task(trigger_agent_responses())
app.state.background_tasks.add(task)
task.add_done_callback(app.state.background_tasks.discard)
```

### 12. Message creation and room update not atomic
- **File:** `crud/messages.py:49-55`
- **Problem:** Message is added to session, then room is fetched and updated, then committed. If room doesn't exist, message could be orphaned.
- **Fix:** Check room existence before adding message:
```python
room = await db.get(models.Room, room_id)
if not room:
    raise RoomNotFoundError(room_id)
db.add(db_message)
```

### 13. Active room task cleanup missing from orchestrator shutdown
- **File:** `orchestration/orchestrator.py:121-149`
- **Problem:** If shutdown happens while tasks are running, they may be left orphaned.
- **Fix:** Await all active tasks before shutdown completes.

---

## Low Priority

### 14. SDK connection timeout not configurable
- **File:** `sdk/manager.py:264-269`
- **Problem:** Hard-coded 10-second timeout on `client.query()` may be too short.
- **Fix:** Add `AGENT_QUERY_TIMEOUT` env variable (default 10s).

### 15. Memory leak risk in cache pattern matching
- **File:** `utils/cache.py:112-126`
- **Problem:** `invalidate_pattern()` performs O(n) string prefix matching on ALL cache keys.
- **Fix:** Consider secondary index by pattern prefix for O(1) lookups.

### 16. Write queue fallback without proper error logging
- **File:** `utils/write_queue.py:159-165`
- **Problem:** If `_write_queue is None`, silently executes directly with weak warning.
- **Fix:** Log as ERROR or reject write to prevent inconsistency.

### 17. No request ID correlation in logs
- **File:** Multiple routers
- **Problem:** No request ID in logs makes tracing difficult.
- **Fix:** Add middleware to inject `X-Request-ID` header and log it.

### 18. Cache stats not exported as metrics
- **File:** `utils/cache.py:197-212`
- **Problem:** Cache stats logged every 5 minutes but no prometheus metrics.
- **Fix:** Export prometheus metrics for cache performance.

### 19. No error recovery/backoff in background scheduler
- **File:** `background_scheduler.py:111-115`
- **Problem:** Repeated errors continue without backoff or circuit breaker.
- **Fix:** Implement exponential backoff or error threshold monitoring.

### 20. Scheduler cleanup task tracking missing
- **File:** `background_scheduler.py:170-175`
- **Problem:** `_cleanup_completed_tasks()` removes tasks but never awaits their results.
- **Fix:** Store cleanup task references and await during shutdown.

### 21. Config loader doesn't detect env variable changes
- **File:** `config/loaders.py`
- **Problem:** Config cached with mtime checking, but env changes (like `DEBUG_AGENTS`) don't invalidate cache.
- **Fix:** Provide explicit cache clear endpoint or restart requirement (current behavior).

---

## Summary

| Priority | Count |
|----------|-------|
| High | 2 |
| Medium | 11 |
| Low | 8 |
| **Total** | **21** |

## Files Requiring Most Attention

1. `sdk/manager.py` - 2 issues (client cleanup, timeout)
2. `crud/messages.py` - 3 issues (race condition, validation, atomicity)
3. `models.py` - 2 issues (index, cache mtime)
4. `routers/messages.py` - 2 issues (efficiency, task tracking)
5. `sdk/client_pool.py` - 1 issue (thread safety)
6. `core/settings.py` - 1 issue (singleton safety)
