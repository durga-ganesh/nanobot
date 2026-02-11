# Nanobot Concurrency Analysis

**Date:** 2026-02-10
**Analyzed Version:** 0.1.3.post6

---

## Executive Summary

Nanobot runs in a **single Python process** using **asyncio** for concurrency. While this simplifies the architecture, it introduces several **potential race conditions** where shared mutable state is accessed without proper synchronization.

**Key Finding:** ⚠️ The codebase has **minimal explicit locking**, relying on asyncio's cooperative multitasking, which is generally safe but has edge cases where race conditions can occur.

---

## 🔍 Analysis by Component

### 1. MessageBus Queues ✅ SAFE

**File:** `nanobot/bus/queue.py`

**Shared State:**
- `inbound: asyncio.Queue[InboundMessage]`
- `outbound: asyncio.Queue[OutboundMessage]`
- `_outbound_subscribers: dict[str, list[Callback]]`

**Thread Safety:**
✅ **SAFE** - `asyncio.Queue` is coroutine-safe by design
- Queue operations (`put()`, `get()`) are atomic and safe for concurrent access
- No race conditions expected during queue operations

**Potential Issue:**
⚠️ **Subscriber dictionary** (`_outbound_subscribers`) is modified without locks:
```python
def subscribe_outbound(self, channel: str, callback: Callable):
    if channel not in self._outbound_subscribers:
        self._outbound_subscribers[channel] = []
    self._outbound_subscribers[channel].append(callback)
```

**Impact:** LOW
- Subscriptions typically happen only during startup (channel initialization)
- No concurrent subscription additions in normal operation
- Read operations during dispatch are safe (dict reads are atomic in CPython)

---

### 2. SessionManager ⚠️ RACE CONDITIONS POSSIBLE

**File:** `nanobot/session/manager.py`

**Shared State:**
- `_cache: dict[str, Session]` - In-memory session cache
- Files on disk: `~/.nanobot/sessions/{session_key}.jsonl`

**Race Condition #1: Cache Access**
```python
def get_or_create(self, key: str) -> Session:
    # Check cache
    if key in self._cache:  # ← Race: Another coroutine could modify cache here
        return self._cache[key]

    # Load or create
    session = self._load(key)
    if session is None:
        session = Session(key=key)

    self._cache[key] = session  # ← Race: Parallel get_or_create could create duplicate
    return session
```

**Scenario:**
1. Coroutine A checks cache, key not found
2. Coroutine B checks cache, key not found (before A completes)
3. Both create Session objects
4. Both write to `_cache[key]` - last write wins, one Session instance is lost

**Impact:** MEDIUM
- Lost session data if parallel requests for same session
- Can happen when same user sends messages from different threads (e.g., Telegram updates)

**Race Condition #2: File Writes**
```python
def save(self, session: Session) -> None:
    path = self._get_session_path(session.key)

    with open(path, "w") as f:  # ← No file locking!
        # Write metadata
        # Write messages

    self._cache[session.key] = session
```

**Scenario:**
1. Coroutine A starts writing session file
2. Coroutine B starts writing same session file
3. File corruption or data loss possible

**Impact:** MEDIUM
- Rare in practice (requires rapid-fire messages from same user)
- File system may serialize writes, but not guaranteed

**Race Condition #3: Message Append**
```python
# In Session class
def add_message(self, role: str, content: str, **kwargs: Any) -> None:
    msg = {...}
    self.messages.append(msg)  # ← NOT atomic!
    self.updated_at = datetime.now()
```

**Scenario:**
1. If same Session object is shared between coroutines
2. Parallel `add_message()` calls could interleave
3. List append is atomic in CPython, but `updated_at` update is separate

**Impact:** LOW
- CPython GIL makes list.append() atomic
- Timestamp might be slightly off but not critical

---

### 3. MemoryStore ⚠️ RACE CONDITIONS POSSIBLE

**File:** `nanobot/agent/memory.py`

**Shared State:**
- Files on disk: `~/.nanobot/workspace/memory/YYYY-MM-DD.md`
- Files on disk: `~/.nanobot/workspace/memory/MEMORY.md`

**Race Condition #1: Today's Memory Append**
```python
def append_today(self, content: str) -> None:
    today_file = self.get_today_file()

    if today_file.exists():
        existing = today_file.read_text(encoding="utf-8")  # ← Race window here
        content = existing + "\n" + content
    else:
        header = f"# {today_date()}\n\n"
        content = header + content

    today_file.write_text(content, encoding="utf-8")  # ← Could overwrite concurrent write
```

**Scenario:**
1. Coroutine A reads file: "Memory A"
2. Coroutine B reads file: "Memory A"
3. A writes: "Memory A\nNew content A"
4. B writes: "Memory A\nNew content B" ← **Overwrites A's addition!**

**Impact:** HIGH
- Lost memory entries
- Can happen if agent writes to memory during parallel operations

**Race Condition #2: Long-term Memory Write**
```python
def write_long_term(self, content: str) -> None:
    self.memory_file.write_text(content, encoding="utf-8")
```

**Impact:** MEDIUM
- Same issue as append_today
- Less frequent (long-term memory updated rarely)

---

### 4. CronService ⚠️ POTENTIAL ISSUES

**File:** `nanobot/cron/service.py`

**Shared State:**
- `_store: CronStore | None` - In-memory job store
- File on disk: `~/.nanobot/data/cron/jobs.json`

**Race Condition #1: Store Modification**
```python
def add_job(self, name: str, schedule: CronSchedule, ...) -> CronJob:
    store = self._load_store()  # ← Gets reference to _store

    job = CronJob(...)
    store.jobs.append(job)  # ← Modifies shared list
    self._save_store()  # ← Writes to disk
    self._arm_timer()

    return job
```

**Scenario:**
1. Coroutine A calls `add_job()`, modifies `store.jobs`
2. Coroutine B calls `remove_job()` simultaneously
3. Both save to disk - last write wins, one operation is lost

**Impact:** MEDIUM
- Rare (cron operations are infrequent)
- Could lose job additions/removals
- File corruption unlikely but possible

**Race Condition #2: Timer Arming**
```python
def _arm_timer(self) -> None:
    if self._timer_task:
        self._timer_task.cancel()  # ← Cancel existing timer

    # ... compute delay ...

    self._timer_task = asyncio.create_task(tick())  # ← Create new timer
```

**Scenario:**
1. Two calls to `_arm_timer()` in quick succession
2. Both could create tasks
3. First task might not be canceled properly

**Impact:** LOW
- Worst case: timer fires twice (job runs twice)
- Jobs track `last_run_at_ms` to prevent rapid re-runs

---

### 5. SubagentManager ✅ MOSTLY SAFE

**File:** `nanobot/agent/subagent.py`

**Shared State:**
- `_running_tasks: dict[str, asyncio.Task[None]]`

**Concurrency Pattern:**
```python
async def spawn(self, task: str, ...) -> str:
    task_id = str(uuid.uuid4())[:8]

    bg_task = asyncio.create_task(self._run_subagent(...))
    self._running_tasks[task_id] = bg_task  # ← Write to dict

    bg_task.add_done_callback(lambda _: self._running_tasks.pop(task_id, None))
```

**Analysis:**
✅ **SAFE** - Task IDs are unique (UUID), no key collisions
✅ **SAFE** - Done callback runs in event loop, serialized
✅ **SAFE** - Dict operations on unique keys are safe

**Impact:** NONE

---

### 6. Mochat Channel ✅ HAS EXPLICIT LOCKING

**File:** `nanobot/channels/mochat.py`

**Shared State:**
- `_target_locks: dict[str, asyncio.Lock]`
- Various state dictionaries

**Locking Pattern:**
```python
# Per-target locking for message sending
lock = self._target_locks.setdefault(f"{target_kind}:{target_id}", asyncio.Lock())
async with lock:
    # Send message safely
    ...

# State modification with lock
async with state.lock:
    # Modify state
    ...
```

**Analysis:**
✅ **SAFE** - Uses `asyncio.Lock` for critical sections
✅ **SAFE** - Per-target locks prevent message order issues
✅ **BEST PRACTICE** - This is the ONLY channel that uses explicit locking!

**Impact:** NONE - This is the correct pattern!

---

### 7. AgentLoop ✅ MOSTLY SAFE

**File:** `nanobot/agent/loop.py`

**Shared State:**
- Tools registry
- Session manager (analyzed separately)
- Provider (stateless)

**Concurrency Pattern:**
```python
async def run(self) -> None:
    while self._running:
        msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)

        try:
            response = await self._process_message(msg)
            if response:
                await self.bus.publish_outbound(response)
        except Exception as e:
            # Error handling
```

**Analysis:**
✅ **SAFE** - Processes messages serially from queue
✅ **SAFE** - Each message gets independent context
⚠️ **DEPENDS** - Safety depends on SessionManager (which has issues)

**Issue:**
- If multiple messages for same session arrive rapidly, session state could be corrupted
- AgentLoop itself doesn't prevent parallel processing of same session

**Impact:** MEDIUM (inherited from SessionManager)

---

## 🎯 Concurrency Model Analysis

### AsyncIO Cooperative Multitasking

**How It Works:**
- Single-threaded event loop
- Coroutines yield control at `await` points
- No true parallelism (except I/O operations)

**Implications:**
1. **No race conditions within atomic Python operations**
   - Dictionary lookups are atomic
   - List appends are atomic (CPython GIL)

2. **Race conditions occur at await boundaries**
   ```python
   if key not in dict:      # ← Atomic check
       await some_io()       # ← Yield point! Another coroutine can run
       dict[key] = value     # ← State may have changed
   ```

3. **File I/O is a major yield point**
   - `file.read_text()` is blocking (yielding)
   - Another coroutine can run during file operations
   - No file-level locking by default

---

## 🐛 Identified Race Conditions

### Critical (Need Immediate Fix)

1. **MemoryStore.append_today()**
   - **Severity:** HIGH
   - **Scenario:** Lost memory entries during parallel writes
   - **Fix:** Use file locking or atomic append

2. **SessionManager.get_or_create()**
   - **Severity:** MEDIUM
   - **Scenario:** Duplicate session objects, lost messages
   - **Fix:** Add `asyncio.Lock` per session key

### Medium (Monitor and Fix)

3. **SessionManager.save()**
   - **Severity:** MEDIUM
   - **Scenario:** File corruption during parallel saves
   - **Fix:** Use file locking (fcntl on Unix, msvcrt on Windows)

4. **CronService job modifications**
   - **Severity:** MEDIUM
   - **Scenario:** Lost job additions/removals
   - **Fix:** Add lock around store modifications

### Low (Unlikely but Possible)

5. **MessageBus._outbound_subscribers**
   - **Severity:** LOW
   - **Scenario:** Subscription corruption during startup
   - **Fix:** Initialize all subscriptions before starting

---

## 🛡️ Recommended Fixes

### Fix #1: SessionManager with Lock

```python
class SessionManager:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.sessions_dir = ensure_dir(Path.home() / ".nanobot" / "sessions")
        self._cache: dict[str, Session] = {}
        self._locks: dict[str, asyncio.Lock] = {}  # ← ADD THIS

    async def get_or_create(self, key: str) -> Session:
        # Get or create lock for this session key
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        async with self._locks[key]:  # ← LOCK HERE
            # Check cache
            if key in self._cache:
                return self._cache[key]

            # Load or create
            session = self._load(key)
            if session is None:
                session = Session(key=key)

            self._cache[key] = session
            return session

    async def save(self, session: Session) -> None:
        async with self._locks.get(session.key, asyncio.Lock()):  # ← LOCK HERE
            path = self._get_session_path(session.key)

            # Consider using aiofiles for async file I/O
            with open(path, "w") as f:
                # Write data
                ...

            self._cache[session.key] = session
```

### Fix #2: MemoryStore with Atomic Append

```python
import fcntl  # Unix only, use msvcrt on Windows

class MemoryStore:
    def append_today(self, content: str) -> None:
        today_file = self.get_today_file()

        # Open in append mode with locking
        with open(today_file, "a", encoding="utf-8") as f:
            try:
                # Acquire exclusive lock
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)

                # If file is empty, write header
                if f.tell() == 0:
                    f.write(f"# {today_date()}\n\n")

                # Append content
                f.write(content + "\n")

            finally:
                # Release lock
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

**Alternative: Use aiofiles**
```python
import aiofiles
import aiofiles.os

async def append_today(self, content: str) -> None:
    today_file = self.get_today_file()

    # Atomic append using aiofiles
    async with aiofiles.open(today_file, "a", encoding="utf-8") as f:
        if not await aiofiles.os.path.exists(today_file):
            await f.write(f"# {today_date()}\n\n")
        await f.write(content + "\n")
```

### Fix #3: CronService with Lock

```python
class CronService:
    def __init__(self, store_path: Path, on_job: Callable | None = None):
        self.store_path = store_path
        self.on_job = on_job
        self._store: CronStore | None = None
        self._timer_task: asyncio.Task | None = None
        self._running = False
        self._lock = asyncio.Lock()  # ← ADD THIS

    async def add_job(self, name: str, schedule: CronSchedule, ...) -> CronJob:
        async with self._lock:  # ← LOCK HERE
            store = self._load_store()
            now = _now_ms()

            job = CronJob(...)
            store.jobs.append(job)
            self._save_store()
            self._arm_timer()

            return job

    async def remove_job(self, job_id: str) -> bool:
        async with self._lock:  # ← LOCK HERE
            store = self._load_store()
            before = len(store.jobs)
            store.jobs = [j for j in store.jobs if j.id != job_id]
            removed = len(store.jobs) < before

            if removed:
                self._save_store()
                self._arm_timer()

            return removed
```

---

## 📊 Risk Assessment Summary

| Component | Race Condition Risk | Impact | Priority |
|-----------|-------------------|---------|----------|
| MessageBus Queues | ✅ None | N/A | N/A |
| SessionManager Cache | ⚠️ High | MEDIUM | HIGH |
| SessionManager Files | ⚠️ Medium | MEDIUM | MEDIUM |
| MemoryStore Append | ⚠️ High | HIGH | HIGH |
| MemoryStore Long-term | ⚠️ Medium | MEDIUM | MEDIUM |
| CronService Store | ⚠️ Medium | MEDIUM | MEDIUM |
| SubagentManager | ✅ None | N/A | N/A |
| Mochat Channel | ✅ None (has locks) | N/A | N/A |
| AgentLoop | ⚠️ Inherited | MEDIUM | HIGH |

---

## 🎓 Why These Issues Exist

1. **Asyncio Mental Model:**
   - Developers assume "single-threaded = safe"
   - Forgot that `await` creates yield points
   - CPython GIL creates false sense of security

2. **File I/O Assumptions:**
   - File system operations feel "atomic"
   - No built-in locking in Python standard library
   - OS may or may not serialize writes

3. **Rare Occurrence:**
   - Race conditions require precise timing
   - Most operations complete before yield
   - Testing doesn't reveal these issues easily

4. **Performance Trade-off:**
   - Adding locks everywhere hurts performance
   - Over-locking can cause deadlocks
   - Developers prefer minimal locking

---

## 🔬 Testing for Race Conditions

### Stress Test Example

```python
import asyncio
import pytest

@pytest.mark.asyncio
async def test_session_manager_race():
    manager = SessionManager(Path("/tmp/test"))

    # Simulate 100 concurrent get_or_create calls for same session
    tasks = [
        manager.get_or_create("test:session")
        for _ in range(100)
    ]

    sessions = await asyncio.gather(*tasks)

    # All should return same object
    assert all(s is sessions[0] for s in sessions)

    # Cache should have exactly one entry
    assert len(manager._cache) == 1
```

### File Race Test

```python
@pytest.mark.asyncio
async def test_memory_append_race():
    store = MemoryStore(Path("/tmp/test"))

    # Concurrent appends
    tasks = [
        store.append_today(f"Entry {i}")
        for i in range(100)
    ]

    await asyncio.gather(*tasks)

    # Read file and verify all entries present
    content = store.read_today()
    for i in range(100):
        assert f"Entry {i}" in content
```

---

## 🌟 Best Practices Observed

### Good: Mochat's Locking Pattern

The Mochat channel is the **only component** that uses explicit locking correctly:

```python
# Per-target message sending lock
lock = self._target_locks.setdefault(target_key, asyncio.Lock())
async with lock:
    # Critical section: send message
    ...

# State modification lock
async with state.lock:
    # Critical section: modify state
    ...
```

**Why this is good:**
- Prevents message reordering
- Ensures state consistency
- Fine-grained locking (per-target, not global)
- Minimal performance impact

### Good: Unique IDs for Subagents

```python
task_id = str(uuid.uuid4())[:8]
```

**Why this is good:**
- No key collisions possible
- Safe concurrent spawning
- No locking needed

---

## 💡 Recommendations

### Immediate Actions (High Priority)

1. ✅ Add `asyncio.Lock` to `SessionManager.get_or_create()` and `save()`
2. ✅ Add file locking or atomic append to `MemoryStore.append_today()`
3. ✅ Add lock to `CronService` for store modifications

### Medium Term (Improve Robustness)

4. ✅ Use `aiofiles` for async file I/O throughout
5. ✅ Add stress tests for concurrent operations
6. ✅ Document concurrency assumptions in each module
7. ✅ Add logging for detected race conditions

### Long Term (Architecture)

8. ✅ Consider using a proper database (SQLite) for sessions instead of files
9. ✅ Consider using Redis for distributed session storage
10. ✅ Add distributed locking if running multiple instances

---

## 📝 Conclusion

While nanobot's single-process asyncio model is generally safe, there are **several race conditions** in:
- Session management (cache and file writes)
- Memory operations (file appends)
- Cron service (store modifications)

**Good news:**
- Issues are well-understood and fixable
- Impact is MEDIUM (rare but possible data loss)
- Fixes are straightforward (add `asyncio.Lock`)

**Action items:**
1. Add locks to identified critical sections
2. Use atomic file operations or file locking
3. Add stress tests to verify fixes
4. Consider architectural improvements (database, Redis)

The codebase is **production-ready with low-to-medium traffic**, but **needs hardening for high-concurrency scenarios**.

---

**Analysis Date:** 2026-02-10
**Analyzed By:** AI Assistant
**Version:** 0.1.3.post6
