#!/usr/bin/env python3
"""
TokenSaver — NVIDIA NIM Rate Limiter (Q5 fix)
nim_queue.py — отдельный модуль

NVIDIA NIM лимит: 40 RPM = 1 запрос каждые 1.5 сек
Архитектура: TokenBucket + asyncio.Queue + daemon thread worker
Интеграция: from nim_queue import nim_call
"""
import asyncio, threading, time, logging
import queue as _q
from concurrent.futures import Future as _Future

log = logging.getLogger("ts.nim")

NIM_RPM_LIMIT = 40
NIM_INTERVAL  = 60.0 / NIM_RPM_LIMIT  # 1.5 sec
NIM_QUEUE_MAX = 200
NIM_TIMEOUT   = 30.0
NIM_RETRY_MAX = 3


class _TokenBucket:
    """Sliding window rate limiter. consume() блокирует до timeout."""
    def __init__(self, rate=NIM_RPM_LIMIT):
        self._rate, self._tokens = rate, float(rate)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, timeout=NIM_TIMEOUT) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(float(self._rate),
                    self._tokens + (now - self._last) * self._rate / 60.0)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
            wait = min(NIM_INTERVAL * 0.5, deadline - time.monotonic())
            if wait <= 0:
                log.warning("NIM_BUCKET_TIMEOUT")
                return False
            time.sleep(wait)

    @property
    def available(self): return round(self._tokens, 1)


class NimQueue:
    """
    Sync interface over asyncio loop in daemon thread.
    Flask (sync) -> .call(fn) -> blocks via Future.result()
    Worker enforces NIM_INTERVAL gap + exponential backoff on 429.
    """
    def __init__(self):
        self._q      = _q.Queue(maxsize=NIM_QUEUE_MAX)
        self._bucket = _TokenBucket()
        self._loop   = asyncio.new_event_loop()
        self._last   = 0.0
        self._lock   = threading.Lock()
        self._stats  = dict(enqueued=0, processed=0, errors=0,
                            rate_limited=0, retried=0, dropped=0, queue_size=0)
        threading.Thread(target=self._run, daemon=True, name="nim-worker").start()
        log.info(f"NIM_QUEUE_STARTED rpm={NIM_RPM_LIMIT} interval={NIM_INTERVAL:.2f}s")

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._worker())

    async def _worker(self):
        while True:
            try:
                fut, fn, a, kw = await self._loop.run_in_executor(
                    None, lambda: self._q.get(timeout=1))
            except _q.Empty:
                continue
            except Exception:
                await asyncio.sleep(0.1); continue

            gap = NIM_INTERVAL - (time.monotonic() - self._last)
            if gap > 0: await asyncio.sleep(gap)

            result = err = None
            for attempt in range(NIM_RETRY_MAX):
                if not self._bucket.consume(NIM_TIMEOUT):
                    err = RuntimeError("NIM bucket timeout")
                    with self._lock: self._stats["rate_limited"] += 1
                    break
                try:
                    result = await self._loop.run_in_executor(None, lambda: fn(*a, **kw))
                    self._last = time.monotonic()
                    with self._lock: self._stats["processed"] += 1
                    break
                except Exception as e:
                    s = str(e)
                    if ("429" in s or "rate" in s.lower()) and attempt < NIM_RETRY_MAX-1:
                        wait = NIM_INTERVAL * (2**attempt)  # 1.5 -> 3 -> 6s
                        log.warning(f"NIM_429 attempt={attempt+1} retry_in={wait:.1f}s")
                        with self._lock:
                            self._stats["rate_limited"] += 1
                            self._stats["retried"]      += 1
                        await asyncio.sleep(wait)
                    else:
                        err = e
                        with self._lock: self._stats["errors"] += 1
                        log.error(f"NIM_ERROR: {e}"); break
            try:
                if err: fut.set_exception(err)
                elif not fut.done(): fut.set_result(result)
            except Exception: pass
            self._q.task_done()
            with self._lock: self._stats["queue_size"] = self._q.qsize()

    def submit(self, fn, *a, **kw) -> _Future:
        fut = _Future()
        try:
            self._q.put_nowait((fut, fn, a, kw))
            with self._lock:
                self._stats["enqueued"]  += 1
                self._stats["queue_size"] = self._q.qsize()
        except _q.Full:
            with self._lock: self._stats["dropped"] += 1
            log.error(f"NIM_QUEUE_FULL size={self._q.qsize()}")
            fut.set_exception(RuntimeError(f"NIM queue full ({NIM_QUEUE_MAX})"))
        return fut

    def call(self, fn, *a, timeout=NIM_TIMEOUT+10, **kw):
        """Sync call through queue. Blocks caller thread."""
        return self.submit(fn, *a, **kw).result(timeout=timeout)

    def stats(self) -> dict:
        with self._lock: s = dict(self._stats)
        s.update(rpm_limit=NIM_RPM_LIMIT, interval_sec=round(NIM_INTERVAL,2),
                 queue_max=NIM_QUEUE_MAX, bucket_tokens=self._bucket.available)
        return s

    def wait_all(self):
        """Block until queue is empty (graceful shutdown)."""
        self._q.join()


_instance: "NimQueue | None" = None
_init_lock = threading.Lock()

def get_nim_queue() -> NimQueue:
    global _instance
    if _instance is None:
        with _init_lock:
            if _instance is None:
                _instance = NimQueue()
    return _instance

def nim_call(fn, *a, timeout=NIM_TIMEOUT+10, **kw):
    """
    Main entrypoint. Routes fn() through NIM rate-limited queue.

    Usage:
        from litellm import completion
        from nim_queue import nim_call

        resp = nim_call(completion,
            model="nvidia/moonshotai/kimi-k2.5",
            messages=[{"role":"user","content":"hi"}],
            api_base="https://integrate.api.nvidia.com/v1",
            api_key=os.environ["NVIDIA_NIM_API_KEY"])
    """
    return get_nim_queue().call(fn, *a, timeout=timeout, **kw)

def nim_stats() -> dict:
    """Queue stats: enqueued, processed, errors, rate_limited, queue_size..."""
    return get_nim_queue().stats()


if __name__ == "__main__":
    import random
    q = NimQueue()
    print(f"Self-test: 10 requests @ {NIM_RPM_LIMIT} RPM limit")
    t0 = time.time()
    futs = [q.submit(lambda i=i: (time.sleep(0.1) or f"ok_{i}"), ) for i in range(10)]
    for i, f in enumerate(futs):
        r = f.result(60)
        print(f"  [{time.time()-t0:5.1f}s] {r}")
    s = q.stats()
    total = time.time()-t0
    print(f"\nStats: {s}")
    print(f"Total={total:.1f}s avg={total/10:.2f}s/req effective_rpm={10/total*60:.1f}")
