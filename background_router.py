#!/usr/bin/env python3
"""
TokenSaver v5.1 — Background Router
Фоновый роутер: оптимизация промптов + маршрутизация + статистика
Запуск: python3 background_router.py
Фоновый: python3 background_router.py --daemon
"""
import os, re, time, json, hashlib, logging, argparse, threading
from pathlib import Path
from datetime import datetime
from typing import Optional

TS_DIR = Path.home() / ".tokensaver"
TS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=TS_DIR / "router.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("ts.router")

# ── Загрузка .env ─────────────────────────────────────────────
def load_env():
    env_file = TS_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()

# ═══════════════════════════════════════════════════════════════
# ОПТИМИЗАЦИЯ ПРОМПТОВ (RTK)
# ═══════════════════════════════════════════════════════════════

# Шаблоны для удаления филлеров
_FILLER_PATTERNS = [
    (re.compile(r'^(please |kindly |could you |would you )', re.I), ''),
    (re.compile(r'\b(very |really |basically |actually |literally )\b', re.I), ''),
    (re.compile(r'\b(just |simply )\b(?!in|out|for)', re.I), ''),
    (re.compile(r'  +'), ' '),
    (re.compile(r'\n{3,}'), '\n\n'),
]

# Замена многословных фраз
_REPLACEMENTS = [
    ("I would like you to", "Please"),
    ("Can you please", "Please"),
    ("I need you to", ""),
    ("Make sure to", "Ensure"),
    ("In order to", "To"),
    ("Due to the fact that", "Because"),
    ("At this point in time", "Now"),
    ("пожалуйста, можешь", "сделай"),
    ("не мог бы ты", ""),
    ("я бы хотел чтобы ты", ""),
]

def optimize_prompt(prompt: str) -> tuple[str, int]:
    """Оптимизировать промпт, вернуть (оптимизированный, кол-во сохранённых токенов)."""
    original_len = len(prompt.split())
    result = prompt
    for phrase, replacement in _REPLACEMENTS:
        result = result.replace(phrase, replacement)
    for pattern, replacement in _FILLER_PATTERNS:
        result = pattern.sub(replacement, result)
    result = result.strip()
    saved = original_len - len(result.split())
    return result, max(0, saved)

# ═══════════════════════════════════════════════════════════════
# СТАТИСТИКА И МЕТРИКИ
# ═══════════════════════════════════════════════════════════════

class RouterStats:
    def __init__(self):
        self.requests_total = 0
        self.requests_cached = 0
        self.requests_local = 0
        self.requests_nvidia = 0
        self.requests_gemini = 0
        self.requests_claude = 0
        self.tokens_saved_rtk = 0
        self.cost_total = 0.0
        self.cost_saved = 0.0
        self.errors = 0
        self._lock = threading.Lock()
        self._start_time = time.time()

    def record(self, model: str, cached: bool, tokens_saved: int, cost: float):
        with self._lock:
            self.requests_total += 1
            self.tokens_saved_rtk += tokens_saved
            self.cost_total += cost
            if cached:
                self.requests_cached += 1
                self.cost_saved += (cost * 10)  # оценка без кэша
            if "ollama" in model: self.requests_local += 1
            elif "nvidia" in model or "kimi" in model: self.requests_nvidia += 1
            elif "gemini" in model: self.requests_gemini += 1
            elif "claude" in model or "anthropic" in model: self.requests_claude += 1

    def to_dict(self) -> dict:
        with self._lock:
            uptime = int(time.time() - self._start_time)
            cache_rate = (self.requests_cached / max(self.requests_total, 1)) * 100
            return {
                "uptime_sec": uptime,
                "requests_total": self.requests_total,
                "cache_hit_rate_pct": round(cache_rate, 1),
                "requests_by_provider": {
                    "local": self.requests_local,
                    "nvidia_free": self.requests_nvidia,
                    "gemini": self.requests_gemini,
                    "claude": self.requests_claude,
                    "cached": self.requests_cached,
                },
                "tokens_saved_rtk": self.tokens_saved_rtk,
                "cost_total_usd": round(self.cost_total, 6),
                "cost_saved_est_usd": round(self.cost_saved, 4),
            }

stats = RouterStats()

# ═══════════════════════════════════════════════════════════════
# ВАЛИДАЦИЯ КЭША (ключевая проверка)
# ═══════════════════════════════════════════════════════════════

def validate_cache_hit(usage_obj) -> dict:
    """
    Проверить, сработал ли провайдерский кэш.
    Anthropic: cache_read_input_tokens / cache_creation_input_tokens
    OpenAI:    prompt_tokens_details.cached_tokens
    Gemini:    cached_content_token_count
    """
    result = {
        "provider_cache_hit": False,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "cached_tokens_openai": 0,
    }
    if usage_obj is None:
        return result
    # Anthropic
    read = getattr(usage_obj, "cache_read_input_tokens", 0) or 0
    write = getattr(usage_obj, "cache_creation_input_tokens", 0) or 0
    result["cache_read_tokens"] = read
    result["cache_write_tokens"] = write
    if read > 0:
        result["provider_cache_hit"] = True
        log.info(f"ANTHROPIC_CACHE_HIT read={read} write={write}")
    # OpenAI / NVIDIA NIM
    details = getattr(usage_obj, "prompt_tokens_details", None)
    if details:
        cached = getattr(details, "cached_tokens", 0) or 0
        result["cached_tokens_openai"] = cached
        if cached > 0:
            result["provider_cache_hit"] = True
            log.info(f"OPENAI_CACHE_HIT cached_tokens={cached}")
    # Gemini
    gemini_cached = getattr(usage_obj, "cached_content_token_count", 0) or 0
    if gemini_cached > 0:
        result["provider_cache_hit"] = True
        log.info(f"GEMINI_CACHE_HIT cached_tokens={gemini_cached}")
    return result

# ═══════════════════════════════════════════════════════════════
# РОУТЕР — обёртка над tokensaver.ask()
# ═══════════════════════════════════════════════════════════════

def route(prompt: str, session_id: str = "default",
          system: str = None, verbose: bool = True) -> dict:
    """
    Полный пайплайн:
    1. Оптимизация промпта (RTK)
    2. Передача в tokensaver.ask()
    3. Валидация провайдерского кэша
    4. Запись статистики
    """
    t0 = time.time()

    # Шаг 1: RTK
    optimized, saved_tokens = optimize_prompt(prompt)
    if saved_tokens > 0 and verbose:
        print(f"✂️  RTK: -{saved_tokens} токенов")

    # Шаг 2: tokensaver
    try:
        import sys
        sys.path.insert(0, str(Path.home() / "token-saver"))
        from tokensaver import ask, session_load, session_save, DEFAULT_SYSTEM
        history = session_load(session_id)
        result = ask(optimized, system=system or DEFAULT_SYSTEM,
                     history=history, verbose=verbose)
        s = result["stats"]

        # Шаг 3: Дополнительная валидация кэша если есть usage объект
        # (tokensaver уже проверяет cache_read_input_tokens)
        cache_valid = s.get("provider_cache", False)

        # Шаг 4: Статистика роутера
        stats.record(
            model=s.get("model", ""),
            cached=s.get("cached", False) or cache_valid,
            tokens_saved=saved_tokens + s.get("tokens_saved", 0),
            cost=s.get("cost_usd", 0.0)
        )

        result["stats"]["rtk_saved"] = saved_tokens
        result["stats"]["router_stats"] = stats.to_dict()
        result["stats"]["latency_ms"] = int((time.time() - t0) * 1000)
        return result

    except ImportError:
        log.error("tokensaver.py не найден в ~/token-saver/")
        return {"response": "[Error: tokensaver.py не найден]",
                "stats": {"error": "import_failed"}}
    except Exception as e:
        stats.errors += 1
        log.error(f"ROUTE_ERROR: {e}")
        return {"response": f"[Error: {e}]", "stats": {"error": str(e)}}

# ═══════════════════════════════════════════════════════════════
# HTTP СЕРВЕР (опционально, порт 4001)
# ═══════════════════════════════════════════════════════════════

def run_server(port: int = 4001):
    from flask import Flask, request, jsonify
    app = Flask("ts_router")

    @app.route("/route", methods=["POST"])
    def route_ep():
        data = request.json or {}
        prompt = data.get("prompt", "")
        session_id = data.get("session_id", "default")
        result = route(prompt, session_id=session_id)
        return jsonify(result)

    @app.route("/optimize", methods=["POST"])
    def optimize_ep():
        data = request.json or {}
        prompt = data.get("prompt", "")
        opt, saved = optimize_prompt(prompt)
        return jsonify({"optimized": opt, "tokens_saved": saved,
                        "original_words": len(prompt.split()),
                        "optimized_words": len(opt.split())})

    @app.route("/stats")
    def stats_ep():
        return jsonify(stats.to_dict())

    @app.route("/health")
    def health_ep():
        return jsonify({"status": "ok", "port": port})

    print(f"\n🔀 Background Router v5.1 → http://localhost:{port}")
    print(f"   /route    — полный пайплайн")
    print(f"   /optimize — только RTK")
    print(f"   /stats    — статистика роутера")
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true", help="Запустить HTTP сервер")
    ap.add_argument("--port", type=int, default=4001)
    ap.add_argument("--prompt", type=str, help="Быстрый тест")
    ap.add_argument("--optimize-only", type=str, dest="opt", help="Только RTK")
    args = ap.parse_args()

    if args.opt:
        opt, saved = optimize_prompt(args.opt)
        print(f"Оригинал:    {args.opt}")
        print(f"Оптимизован: {opt}")
        print(f"Сохранено:   {saved} токенов")
    elif args.prompt:
        r = route(args.prompt)
        print(f"\n{r['response']}")
    elif args.daemon:
        run_server(args.port)
    else:
        print("Используй --daemon, --prompt или --optimize-only")
        print("Пример: python3 background_router.py --optimize-only 'Could you please just write a function'")
