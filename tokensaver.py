#!/usr/bin/env python3
"""
TokenSaver v5.2 — 10 механик экономии токенов
Fix #3: SQLite WAL mode + PRAGMA busy_timeout (concurrent subagents)
Fix #5: X-Claude-Code-Agent-Id / Parent-Agent-Id tracking + agent cost tree

Run: python3 tokensaver.py --server
Docs: README.md
"""
import re, time, hashlib, json, subprocess, uuid, platform, os, logging, sqlite3
from pathlib import Path
from typing import Optional

_ts_dir = Path.home() / ".tokensaver"
_ts_dir.mkdir(exist_ok=True)
logging.basicConfig(
    filename=_ts_dir / "tokensaver.log",
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("ts")

# ── ENV ───────────────────────────────────────────────────────
_env = _ts_dir / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# ── Redis ─────────────────────────────────────────────────────
try:
    import redis as redis_lib
    _r = redis_lib.Redis(host="localhost", port=6379, decode_responses=True, socket_timeout=1)
    _r.ping(); REDIS_OK = True
except Exception:
    _r = None; REDIS_OK = False

# ═══════════════════════════════════════════════════════════════
# DATABASE — кэш + сессии + агенты
# FIX #3: WAL mode + busy_timeout для параллельных субагентов
# ═══════════════════════════════════════════════════════════════
def _make_db() -> sqlite3.Connection:
    db = sqlite3.connect(
        str(_ts_dir / "tokensaver.db"),
        check_same_thread=False,
        timeout=10  # fallback timeout
    )
    # FIX #3: WAL mode — позволяет параллельные reads во время write
    # IMMEDIATE transactions предотвращают SQLITE_BUSY при concurrent writes
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")   # 5 сек ждать вместо SQLITE_BUSY
    db.execute("PRAGMA synchronous=NORMAL")  # баланс надёжность/скорость
    db.execute("PRAGMA cache_size=-8000")    # 8MB page cache
    db.executescript("""
        CREATE TABLE IF NOT EXISTS cache (
            key  TEXT PRIMARY KEY,
            val  TEXT,
            ts   REAL,
            vec  BLOB
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT PRIMARY KEY,
            history     TEXT,
            updated_at  REAL,
            model       TEXT,
            msg_count   INTEGER DEFAULT 0,
            cost_total  REAL DEFAULT 0.0
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at);

        -- FIX #5: таблица субагентов для cost attribution
        CREATE TABLE IF NOT EXISTS agents (
            agent_id        TEXT PRIMARY KEY,
            parent_agent_id TEXT,
            session_id      TEXT,
            first_seen      REAL,
            last_seen       REAL,
            request_count   INTEGER DEFAULT 0,
            token_input     INTEGER DEFAULT 0,
            token_output    INTEGER DEFAULT 0,
            cost_total      REAL DEFAULT 0.0,
            model_last      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_agents_session ON agents(session_id);
        CREATE INDEX IF NOT EXISTS idx_agents_parent  ON agents(parent_agent_id);
    """)
    db.commit()
    return db

_db = _make_db()

def _db_write(sql: str, params: tuple = ()):
    """Thread-safe запись с BEGIN IMMEDIATE (предотвращает SQLITE_BUSY)."""
    for attempt in range(3):
        try:
            with _db:  # автоматический commit/rollback
                _db.execute("BEGIN IMMEDIATE" if attempt == 0 else "BEGIN")
                _db.execute(sql, params)
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < 2:
                time.sleep(0.1 * (attempt + 1))
                log.warning(f"DB_LOCKED attempt={attempt+1}, retrying")
            else:
                log.error(f"DB_WRITE_FAIL: {e}")
                raise

# ═══════════════════════════════════════════════════════════════
# FIX #5: Agent Cost Tracking
# Источник: Claude Code LLM Gateway docs — X-Claude-Code-Agent-Id
# https://code.claude.com/docs/en/llm-gateway
# ═══════════════════════════════════════════════════════════════
def agent_record(agent_id: str, parent_agent_id: Optional[str],
                 session_id: str, model: str,
                 token_in: int, token_out: int, cost: float):
    """Записать/обновить статистику субагента."""
    if not agent_id:
        return
    now = time.time()
    _db.execute("""
        INSERT INTO agents(
            agent_id, parent_agent_id, session_id, first_seen, last_seen,
            request_count, token_input, token_output, cost_total, model_last
        ) VALUES(?,?,?,?,?,1,?,?,?,?)
        ON CONFLICT(agent_id) DO UPDATE SET
            last_seen    = excluded.last_seen,
            request_count= agents.request_count + 1,
            token_input  = agents.token_input  + excluded.token_input,
            token_output = agents.token_output + excluded.token_output,
            cost_total   = agents.cost_total   + excluded.cost_total,
            model_last   = excluded.model_last
    """, (agent_id, parent_agent_id, session_id, now, now,
           token_in, token_out, cost, model))
    _db.commit()
    log.info(f"AGENT_RECORDED id={agent_id[:8]} parent={str(parent_agent_id)[:8]} "
             f"cost={cost:.5f} in={token_in} out={token_out}")

def agent_tree(session_id: str) -> list:
    """Вернуть дерево субагентов для сессии (для дашборда)."""
    rows = _db.execute(
        "SELECT agent_id, parent_agent_id, request_count, "
        "token_input, token_output, cost_total, model_last, last_seen "
        "FROM agents WHERE session_id=? ORDER BY first_seen",
        (session_id,)
    ).fetchall()
    return [{
        "agent_id":        r[0],
        "parent_agent_id": r[1],
        "requests":        r[2],
        "token_input":     r[3],
        "token_output":    r[4],
        "cost_total":      round(r[5], 6),
        "model":           r[6],
        "last_seen":       r[7],
    } for r in rows]

def agent_stats_all() -> dict:
    """Топ агентов по стоимости (для /stats endpoint)."""
    rows = _db.execute(
        "SELECT agent_id, parent_agent_id, cost_total, request_count "
        "FROM agents ORDER BY cost_total DESC LIMIT 20"
    ).fetchall()
    return {
        "top_agents": [{
            "agent_id": r[0][:16] + "...",
            "parent":   (r[1] or "")[:16],
            "cost":     round(r[2], 6),
            "requests": r[3]
        } for r in rows]
    }

# ═══════════════════════════════════════════════════════════════
# МЕХАНИКА 7: Device Fingerprint
# ═══════════════════════════════════════════════════════════════
def get_device_id() -> str:
    parts = []
    try:
        out = subprocess.run(["ioreg","-rd1","-c","IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=3).stdout
        for line in out.splitlines():
            if "IOPlatformUUID" in line:         parts.append(line.split('"')[-2])
            if "IOPlatformSerialNumber" in line: parts.append(line.split('"')[-2])
    except Exception: pass
    parts += [str(uuid.getnode()), platform.processor() or "x"]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]

DEVICE_ID = get_device_id()

# ═══════════════════════════════════════════════════════════════
# МЕХАНИКА 6: Детектор приватности
# ═══════════════════════════════════════════════════════════════
_PRIV = [re.compile(r, re.I) for r in [
    r"\b\d{16}\b",
    r"(password|secret|пароль|passwd)\s*[=:]\s*\S+",
    r"sk-[a-zA-Z0-9]{32,}",
    r"AIza[0-9A-Za-z\-_]{35}",
    r"nvapi-[a-zA-Z0-9_-]{30,}",
    r"(BEGIN|-----BEGIN)\s+(RSA|EC|OPENSSH|PGP)",
    r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36}",
    r"eyJ[A-Za-z0-9_-]{20,}\.eyJ",
]]
def is_sensitive(text: str) -> bool:
    return any(p.search(text) for p in _PRIV)

# ═══════════════════════════════════════════════════════════════
# МЕХАНИКА 1: Классификатор сложности
# ═══════════════════════════════════════════════════════════════
_LITE_KW   = {"переведи","translate","перевод","define","что значит",
               "rename","format","pretty","отформатируй"}
_SIMPLE_KW = {"объясни","explain","что такое","what is","расскажи","опиши"}
_MEDIUM_KW = {"напиши","write","реализуй","implement","создай","сделай","код","code",
               "миграция","deploy","docker","vercel","webhook"}
_DEEP_KW   = {"архитектура","architecture","стратегия","strategy","проанализируй",
               "analyze","сравни","review","debug","исправь",
               "security","безопасность","oauth","production","doppler"}
FORCE_DEEP = {"security","безопасность","production","продакшн","auth",
              "аутентификация","password","пароль","payment","оплата"}

def classify(prompt: str) -> str:
    words = set(prompt.lower().split())
    if words & FORCE_DEEP: return "deep"
    n = len(prompt)
    if n < 80  and words & _LITE_KW:   return "lite"
    if n < 300 and words & _SIMPLE_KW: return "simple"
    if words & _DEEP_KW or n > 600:    return "deep"
    if words & _MEDIUM_KW:             return "medium"
    return "simple" if n < 200 else "medium"

def is_code_task(prompt: str) -> bool:
    return bool({"код","code","функция","function","class","def ","implement",
                 "написать","реализовать","debug","fix","баг"} & set(prompt.lower().split()))

# ═══════════════════════════════════════════════════════════════
# МЕХАНИКА 2: Семантический кэш L1/L2/L3 + Q4 Fuzzy
# ═══════════════════════════════════════════════════════════════
_L1: dict = {}
_L1_VEC: list = []
_L1_MAX = 200
_FUZZY_THRESHOLD = 0.85
_FUZZY_MAX_VECS  = 500
_NO_CACHE = re.compile(
    r"(сегодня|сейчас|текущий|today|current|right now|latest news|мой баланс)", re.I
)

_embed_model = None
_embed_ok    = False

def _load_embed():
    global _embed_model, _embed_ok
    if _embed_ok or _embed_model is not None:
        return _embed_ok
    try:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        _embed_ok = True
        log.info("EMBED_MODEL_LOADED all-MiniLM-L6-v2")
    except ImportError:
        log.warning("EMBED_MISSING: pip install sentence-transformers")
        _embed_ok = False
    except Exception as e:
        log.warning(f"EMBED_LOAD_FAIL: {e}")
        _embed_ok = False
    return _embed_ok

def _embed(text: str):
    if not _load_embed(): return None
    try:
        return _embed_model.encode(text[:512], normalize_embeddings=True,
                                   show_progress_bar=False)
    except Exception:
        return None

def _cosine(a, b) -> float:
    try:
        import numpy as np
        return float(np.dot(a, b))
    except Exception:
        return 0.0

def _ck(prompt: str) -> str:
    return "ts:" + hashlib.sha256(prompt.strip().lower().encode()).hexdigest()[:20]

def cache_get(prompt: str) -> Optional[str]:
    if _NO_CACHE.search(prompt): return None
    key = _ck(prompt)
    if key in _L1: return _L1[key]
    if REDIS_OK:
        v = _r.get(key)
        if v: _L1[key] = v; return v
    row = _db.execute("SELECT val FROM cache WHERE key=? AND ts>?",
                      (key, time.time()-604800)).fetchone()
    if row: _L1[key] = row[0]; return row[0]
    if _L1_VEC:
        vec = _embed(prompt)
        if vec is not None:
            best_s, best_k = 0.0, None
            for sv, sk in _L1_VEC:
                s = _cosine(vec, sv)
                if s > best_s: best_s, best_k = s, sk
            if best_s >= _FUZZY_THRESHOLD and best_k in _L1:
                log.info(f"FUZZY_HIT_L1 sim={best_s:.3f}")
                return _L1[best_k]
            rows = _db.execute(
                "SELECT key, val, vec FROM cache WHERE ts>? AND vec IS NOT NULL LIMIT 100",
                (time.time()-604800,)
            ).fetchall()
            best_s, best_v = 0.0, None
            for rk, rv, rv_blob in rows:
                if rv_blob is None: continue
                try:
                    import numpy as np
                    rv_arr = np.frombuffer(rv_blob, dtype=np.float32)
                    s = _cosine(vec, rv_arr)
                    if s > best_s: best_s, best_v = s, rv
                except Exception: continue
            if best_s >= _FUZZY_THRESHOLD and best_v:
                log.info(f"FUZZY_HIT_SQLITE sim={best_s:.3f}")
                _L1[key] = best_v
                return best_v
    return None

def cache_set(prompt: str, response: str):
    if _NO_CACHE.search(prompt): return
    key = _ck(prompt)
    _L1[key] = response
    if len(_L1) > _L1_MAX: del _L1[next(iter(_L1))]
    vec = _embed(prompt)
    if vec is not None:
        _L1_VEC.append((vec, key))
        if len(_L1_VEC) > _FUZZY_MAX_VECS: _L1_VEC.pop(0)
    if REDIS_OK: _r.setex(key, 86400, response)
    vec_blob = None
    if vec is not None:
        try:
            import numpy as np
            vec_blob = np.array(vec, dtype=np.float32).tobytes()
        except Exception: pass
    _db.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?,?)",
                (key, response, time.time(), vec_blob))
    _db.commit()

# ═══════════════════════════════════════════════════════════════
# Q2: Session Persistence (SQLite WAL, TTL=24h)
# ═══════════════════════════════════════════════════════════════
SESSION_TTL = 86400
MAX_HISTORY = 40

def session_load(session_id: str) -> list:
    row = _db.execute(
        "SELECT history, updated_at FROM sessions WHERE session_id=?", (session_id,)
    ).fetchone()
    if not row: return []
    if time.time() - row[1] > SESSION_TTL:
        _db.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        _db.commit(); return []
    try: return json.loads(row[0])
    except Exception: return []

def session_save(session_id: str, history: list, model: str = "", cost: float = 0.0):
    trimmed = history[-MAX_HISTORY:]
    _db.execute("""
        INSERT INTO sessions(session_id, history, updated_at, model, msg_count, cost_total)
        VALUES(?,?,?,?,1,?)
        ON CONFLICT(session_id) DO UPDATE SET
            history=excluded.history, updated_at=excluded.updated_at,
            model=excluded.model,
            msg_count=sessions.msg_count+1,
            cost_total=sessions.cost_total+excluded.cost_total
    """, (session_id, json.dumps(trimmed), time.time(), model, cost))
    _db.commit()

def session_cleanup():
    n = _db.execute("DELETE FROM sessions WHERE updated_at<?",
                    (time.time()-SESSION_TTL,)).rowcount
    _db.commit()
    return n

def session_stats() -> dict:
    r = _db.execute(
        "SELECT COUNT(*),COALESCE(SUM(msg_count),0),COALESCE(SUM(cost_total),0) "
        "FROM sessions WHERE updated_at>?", (time.time()-SESSION_TTL,)
    ).fetchone()
    return {"active":r[0] or 0,"total_msgs":r[1] or 0,"total_cost":round(r[2] or 0,5)}

# ═══════════════════════════════════════════════════════════════
# МЕХАНИКА 3: RTK
# ═══════════════════════════════════════════════════════════════
_RTK = [re.compile(p, re.I|re.MULTILINE) for p in [
    r"^(конечно|certainly|sure|of course|абсолютно)[!,.]?\s+",
    r"^(отличный вопрос|great question)[!.]?\s+",
    r"^(я рад помочь|happy to help)[^.]*\.\s+",
    r"(надеюсь.{0,40}помог|hope this helps)[.!]*\s*$",
    r"(если.{0,40}вопрос.{0,40}обращайтесь|feel free to ask)[^.]*[.!]*\s*$",
    r"^(как ИИ|as an AI|as a language model)[^.]*\.\s*",
]]
def rtk(text: str) -> str:
    for p in _RTK: text = p.sub("", text)
    return text.strip()

# ═══════════════════════════════════════════════════════════════
# МЕХАНИКА 4: Thinking Budget
# ═══════════════════════════════════════════════════════════════
BUDGET = {"lite": 0, "simple": 0, "medium": 512, "deep": 5000}

# ═══════════════════════════════════════════════════════════════
# МЕХАНИКА 5: Local Routing (Ollama)
# ═══════════════════════════════════════════════════════════════
def _ollama_has(model: str) -> bool:
    try:
        out = subprocess.run(["ollama","list"], capture_output=True, text=True, timeout=2).stdout
        return model.split(":")[0] in out
    except: return False

_ROUTE = {
    # cloud fallback = бесплатный NVIDIA NIM (проверенная модель). Gemini-ключ просрочен.
    "lite":   ("ollama/llama3.2:3b",   "nvidia/meta/llama-3.1-8b-instruct"),
    "simple": ("ollama/llama3.2:3b",   "nvidia/meta/llama-3.1-8b-instruct"),
    "medium": ("ollama/qwen2.5:7b",    "vertex/gemini-2.5-flash"),
    # deep БЕЗ Anthropic (баланса нет): Gemini 2.5 Pro через gcloud ADC — топ-качество.
    "deep":   (None,                    "vertex/gemini-2.5-pro"),
}

CLOUD_ONLY = os.environ.get("TOKENSAVER_CLOUD_ONLY", "0") == "1"

def select_model(level: str, code: bool, private: bool):
    # CLOUD_ONLY: пропускаем локальные Ollama, сразу облачный fallback (NVIDIA NIM free).
    if CLOUD_ONLY:
        return _ROUTE[level][1], False
    # Код любого локального tier → qwen2.5-coder:7b (быстрый, не reasoning).
    # qwen3 — thinking-модель: на CPU генерит огромные reasoning-трейсы и ловит таймаут.
    if code and level != "deep":
        for m in ["qwen2.5-coder:7b", "llama3.2:3b"]:
            if _ollama_has(m): return f"ollama/{m}", True
    if private or level in ("lite","simple"):
        for m in (["qwen2.5-coder:7b","llama3.2:3b"] if code else ["llama3.2:3b"]):
            if _ollama_has(m): return f"ollama/{m}", True
    local_m, cloud_m = _ROUTE[level]
    if local_m and _ollama_has(local_m.split("/")[1]): return local_m, True
    return cloud_m, False

# ═══════════════════════════════════════════════════════════════
# МЕХАНИКА 8: Провайдерский кэш
# ═══════════════════════════════════════════════════════════════
DEFAULT_SYSTEM = (
    "You are a helpful, concise assistant. "
    "Skip preamble. Answer directly. No filler phrases."
)

def build_messages(prompt: str, model: str, history: list, system: str) -> list:
    if "claude" in model:
        return [{"role":"user","content":[
            {"type":"text","text":system,"cache_control":{"type":"ephemeral"}},
            {"type":"text","text":prompt}
        ]}]
    return [{"role":"system","content":system}] + history[-6:] + \
           [{"role":"user","content":prompt}]

# ═══════════════════════════════════════════════════════════════
# Q1: Auto Compact + Quality Check + Fallback gemini-flash
# ═══════════════════════════════════════════════════════════════
COMPACT_THRESHOLD   = 0.60
COMPACT_QUALITY_MIN = 0.82
CONTEXT_LIMITS = {
    "anthropic/claude-opus-4-8":   1_000_000,
    "vertex/gemini-2.5-flash":     1_048_576,
    "vertex/gemini-2.5-pro":       2_097_152,
    "gemini/gemini-2.0-flash":     1_048_576,
    "gemini/gemini-2.0-flash-lite":1_048_576,
    "ollama/llama3.2:3b":          128_000,
    "ollama/qwen3:8b":             32_000,
    "default":                     32_000,
}
COMPACT_SYSTEM = (
    "Summarize this conversation. PRESERVE verbatim: file paths, error messages, "
    "function/variable names, code snippets, TODOs, task progress. "
    "COMPRESS: explanations, reasoning, repeated context. FORMAT: bullet points."
)

def _extract_terms(messages: list) -> set:
    text = " ".join(str(m.get("content","")) for m in messages)
    terms = set()
    terms.update(re.findall(r'/[\w/.-]+\.(?:py|js|ts|yaml|json|md)', text))
    terms.update(re.findall(r'\bdef\s+(\w+)', text))
    terms.update(re.findall(r'\bclass\s+(\w+)', text))
    terms.update(re.findall(r'(?:Error|Exception):\s*(\w+)', text))
    return {t.lower() for t in terms if len(t) > 3}

def _quality(summary: str, terms: set) -> float:
    if not terms: return 1.0
    sl = summary.lower()
    return sum(1 for t in terms if t in sl) / len(terms)

def _compact_with(model_id: str, history_text: str, is_local: bool) -> Optional[str]:
    try:
        from litellm import completion
        kw = {"model": model_id,
              "messages": [{"role":"user","content": COMPACT_SYSTEM+"\n\n"+history_text}],
              "max_tokens": 1000}
        if is_local:
            kw["api_base"] = "http://localhost:11434"
        elif "nvidia" in model_id:
            kw["model"]    = "openai/" + model_id.split("nvidia/",1)[-1]
            kw["api_base"] = "https://integrate.api.nvidia.com/v1"
            kw["api_key"]  = os.environ.get("NVIDIA_NIM_API_KEY","")
        elif model_id.startswith("vertex/"):
            kw["model"]           = "vertex_ai/" + model_id.split("vertex/",1)[-1]
            kw["vertex_project"]  = os.environ.get("VERTEX_PROJECT","")
            kw["vertex_location"] = os.environ.get("VERTEX_LOCATION","us-central1")
        r = completion(**kw)
        return r.choices[0].message.content or ""
    except Exception as e:
        log.warning(f"COMPACT_FAIL model={model_id}: {e}")
        return None

def _count_tokens(messages: list) -> int:
    return sum(len(str(m.get("content",""))) // 4 for m in messages)

def maybe_compact(messages: list, model: str, verbose: bool = True) -> tuple:
    limit = CONTEXT_LIMITS.get(model, CONTEXT_LIMITS["default"])
    if _count_tokens(messages) < limit * COMPACT_THRESHOLD:
        return messages, False
    sys_msgs = [m for m in messages if m.get("role") == "system"]
    non_sys  = [m for m in messages if m.get("role") != "system"]
    recent   = non_sys[-4:]
    to_compact = non_sys[:-4]
    if not to_compact: return messages, False
    terms = _extract_terms(to_compact)
    hist_text = "\n".join(
        f"[{m['role'].upper()}]: {str(m.get('content',''))[:1000]}" for m in to_compact
    )
    summary, used_model, quality = None, "none", 0.0
    # Compactor order: fast FREE cloud (NIM) first — local Ollama is too slow on CPU
    # for the request path. Local kept as offline fallback only.
    candidates = [
        ("nvidia/meta/llama-3.1-8b-instruct", False),
        ("vertex/gemini-2.5-flash",           False),
    ]
    for lm in ["llama3.2:3b", "qwen2.5:7b"]:
        if _ollama_has(lm):
            candidates.append((f"ollama/{lm}", True))
    for model_id, is_local in candidates:
        s = _compact_with(model_id, hist_text, is_local=is_local)
        if s:
            q = _quality(s, terms)
            if q >= COMPACT_QUALITY_MIN or model_id.startswith(("nvidia/", "vertex/")):
                summary, used_model, quality = s, model_id, q
                if verbose: print(f"🗜️  COMPACT model={model_id} quality={q:.2f}")
                break
            elif verbose:
                print(f"🗜️⚡ {model_id} quality={q:.2f} < {COMPACT_QUALITY_MIN} → next")
    if summary is not None:
        log.info(f"COMPACT model={used_model} quality={quality:.2f}")
    if summary is None:
        return messages, False
    saved = _count_tokens(messages) - _count_tokens(
        sys_msgs + [{"role":"system","content":summary}] + recent)
    if verbose: print(f"   saved={saved} tok | {len(to_compact)} msgs → 1 summary")
    log.info(f"COMPACT_DONE saved={saved} quality={quality:.2f} model={used_model}")
    return sys_msgs + [
        {"role":"system","content":
         f"[AUTO-COMPACT v5 | {used_model.split('/')[-1]} | q={quality:.2f}]\n{summary}"},
        *recent
    ], True

# ═══════════════════════════════════════════════════════════════
# МЕХАНИКА 10: Dedup
# ═══════════════════════════════════════════════════════════════
_dedup: dict = {}

def check_dedup(prompt: str) -> Optional[str]:
    key = hashlib.md5(prompt.encode()).hexdigest()
    if key in _dedup:
        r, ts = _dedup[key]
        if time.time()-ts < 2.0: return r
    return None

def set_dedup(prompt: str, response: str):
    _dedup[hashlib.md5(prompt.encode()).hexdigest()] = (response, time.time())

# ═══════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ ask()
# ═══════════════════════════════════════════════════════════════
try:
    from litellm import completion
    LITELLM_OK = True
except ImportError:
    LITELLM_OK = False

def ask(prompt: str, system: str = DEFAULT_SYSTEM,
        history: list = None, verbose: bool = True) -> dict:
    t0 = time.time()
    history = history or []
    stats = {"cached":False,"local":False,"sensitive":False,"level":None,
             "model":None,"tokens_saved":0,"provider_cache":False,
             "cost_usd":0.0,"compacted":False,"deduped":False}

    dedup = check_dedup(prompt)
    if dedup:
        stats["deduped"] = True
        if verbose: print(f"♻️  DEDUP $0.00")
        return {"response": dedup, "stats": stats}

    if not history:
        cached = cache_get(prompt)
        if cached:
            stats["cached"] = True
            if verbose: print(f"💾 CACHE HIT $0.00 ({(time.time()-t0)*1000:.0f}ms)")
            return {"response": cached, "stats": stats}

    private = is_sensitive(prompt)
    stats["sensitive"] = private
    level = classify(prompt)
    stats["level"] = level
    model, is_local = select_model(level, is_code_task(prompt), private)
    stats["model"] = model
    stats["local"] = is_local

    if history:
        messages, compacted = maybe_compact(
            build_messages(prompt, model, history, system), model, verbose)
        stats["compacted"] = compacted
    else:
        messages = build_messages(prompt, model, [], system)

    if not LITELLM_OK:
        return {"response": "[pip install litellm]", "stats": stats}

    budget = BUDGET.get(level, 0)

    # opencode lane — делегирование на opencode CLI (subscription = $0 за токены).
    # model вида "opencode/<provider>/<model>" или env TOKENSAVER_OPENCODE_MODEL.
    if model.startswith("opencode/"):
        oc_model = model.split("opencode/",1)[-1]
        try:
            p = subprocess.run(
                ["opencode","run",prompt] + (["-m",oc_model] if oc_model else []),
                capture_output=True, text=True, timeout=180
            )
            raw = (p.stdout or p.stderr or "").strip()
            stats["cost_usd"] = 0.0  # subscription
            stats["baseline_usd"] = round(len(prompt.split())*1.3*0.00002, 6)
            stats["saved_usd"] = stats["baseline_usd"]
            cache_set(prompt, raw) if not history else None
            return {"response": rtk(raw), "stats": stats}
        except Exception as e:
            log.error(f"opencode_lane error: {e}")
            return {"response": f"[opencode error: {e}]", "stats": stats}

    kwargs = {"model": model, "messages": messages}
    if is_local: kwargs["api_base"] = "http://localhost:11434"
    if budget > 0 and "claude" in model:
        # Opus 4.8/4.7 не принимают enabled+budget_tokens (400) — только adaptive thinking.
        if "opus-4-8" in model or "opus-4-7" in model:
            kwargs["thinking"] = {"type":"adaptive"}
            kwargs["output_config"] = {"effort":"high"}
        else:
            kwargs["thinking"] = {"type":"enabled","budget_tokens":budget}
    if "nvidia" in model or "kimi" in model:
        # litellm к кастомному OpenAI-совместимому endpoint: префикс openai/ + сам путь модели.
        # model вида "nvidia/meta/llama-3.1-8b-instruct" → "openai/meta/llama-3.1-8b-instruct"
        kwargs["model"]    = "openai/" + model.split("nvidia/",1)[-1]
        kwargs["api_base"] = "https://integrate.api.nvidia.com/v1"
        kwargs["api_key"]  = os.environ.get("NVIDIA_NIM_API_KEY","")
    if model.startswith("vertex/"):
        # Vertex AI Gemini через ADC gcloud (без API-ключа). model: "vertex/gemini-2.5-flash"
        kwargs["model"]           = "vertex_ai/" + model.split("vertex/",1)[-1]
        kwargs["vertex_project"]  = os.environ.get("VERTEX_PROJECT","")
        kwargs["vertex_location"] = os.environ.get("VERTEX_LOCATION","us-central1")

    try:
        resp = completion(**kwargs)
        raw  = resp.choices[0].message.content or ""
        usage = getattr(resp,"usage",None)
        if usage and hasattr(usage,"cache_read_input_tokens"):
            stats["provider_cache"] = (usage.cache_read_input_tokens or 0) > 0
        if usage:
            tok_in  = getattr(usage,"prompt_tokens",0) or 0
            tok_out = getattr(usage,"completion_tokens",0) or 0
            # baseline = во сколько обошёлся бы Claude Opus 4.8 на тех же токенах ($5/$25 за 1M)
            baseline = round(tok_in*0.000005 + tok_out*0.000025, 6)
            free = is_local or ("nvidia" in model) or ("kimi" in model)
            if free:
                actual = 0.0
            elif "vertex" in model or "gemini" in model:
                if "pro" in model:
                    # Gemini 2.5 Pro: ~$1.25/1M in, ~$10/1M out
                    actual = round(tok_in*0.00000125 + tok_out*0.00001, 6)
                else:
                    # Gemini 2.5 Flash: ~$0.30/1M in, ~$2.50/1M out
                    actual = round(tok_in*0.0000003 + tok_out*0.0000025, 6)
            else:
                # любой прочий (на случай ручного override) = baseline
                actual = baseline
            stats["baseline_usd"] = baseline
            stats["cost_usd"]     = actual
            stats["saved_usd"]    = round(baseline - actual, 6)
            stats["token_input"]  = tok_in
            stats["token_output"] = tok_out
    except Exception as e:
        log.error(f"LLM_ERROR model={model}: {e}")
        return {"response": f"[Error: {e}]", "stats": stats}

    compressed = rtk(raw)
    stats["tokens_saved"] = max(0, len(raw.split())-len(compressed.split()))
    if not history: cache_set(prompt, compressed)
    set_dedup(prompt, compressed)

    ms = (time.time()-t0)*1000
    if verbose:
        icons = "🏠" if is_local else "☁️"
        flags = ("🔒" if private else "") + ("🗜️" if stats["compacted"] else "") + \
                ("📦" if stats["provider_cache"] else "")
        print(f"{icons}{flags} {model.split('/')[-1]} | {level} | "
              f"-{stats['tokens_saved']}tok | ${stats['cost_usd']:.5f} | {ms:.0f}ms")
    log.info(f"OK model={model} level={level} local={is_local} "
             f"compact={stats['compacted']} cost={stats['cost_usd']:.5f} ms={ms:.0f}")
    return {"response": compressed, "stats": stats}

# ═══════════════════════════════════════════════════════════════
# HTTP PROXY SERVER — Claude Code / OpenAI compatible
# FIX #5: перехват X-Claude-Code-Agent-Id / X-Claude-Code-Parent-Agent-Id
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", action="store_true")
    ap.add_argument("--prompt", type=str)
    args = ap.parse_args()

    if args.prompt:
        r = ask(args.prompt)
        print("\n" + r["response"])

    elif args.server:
        cleaned = session_cleanup()
        if cleaned: print(f"🧹 Cleaned {cleaned} expired sessions")
        from flask import Flask, request, jsonify
        app = Flask("tokensaver")

        @app.route("/chat/completions", methods=["POST"])
        @app.route("/v1/chat/completions", methods=["POST"])
        def proxy():
            data = request.json or {}
            msgs = data.get("messages", [])

            # FIX #5: перехват Agent ID заголовков (Claude Code LLM Gateway)
            # Docs: https://code.claude.com/docs/en/llm-gateway
            agent_id        = (request.headers.get("X-Claude-Code-Agent-Id") or
                               request.headers.get("anthropic-beta", "").split(",")[0] or
                               None)
            parent_agent_id = request.headers.get("X-Claude-Code-Parent-Agent-Id") or None

            session_id = (request.headers.get("X-Session-Id") or
                          data.get("session_id") or
                          (f"agent-{agent_id[:16]}" if agent_id else "default"))

            prompt = msgs[-1].get("content","") if msgs else ""
            system = next((m["content"] for m in msgs if m.get("role")=="system"),
                          DEFAULT_SYSTEM)
            history = session_load(session_id)
            result  = ask(prompt, system=system, history=history)
            history.append({"role":"user","content":prompt})
            history.append({"role":"assistant","content":result["response"]})
            s = result["stats"]
            session_save(session_id, history,
                         model=s.get("model",""),
                         cost=s.get("cost_usd",0.0))

            # FIX #5: записать статистику субагента
            if agent_id:
                agent_record(
                    agent_id=agent_id,
                    parent_agent_id=parent_agent_id,
                    session_id=session_id,
                    model=s.get("model",""),
                    token_in=s.get("token_input",0),
                    token_out=s.get("token_output",0),
                    cost=s.get("cost_usd",0.0)
                )

            return jsonify({
                "choices":[{"message":{"role":"assistant",
                            "content":result["response"]},"finish_reason":"stop"}],
                "model": s.get("model"),
                "session_id": session_id,
                "agent_id": agent_id,
                "tokensaver_stats": s
            })

        @app.route("/health")
        def health():
            sess = session_stats()
            return jsonify({"status":"ok","version":"5.2",
                            "device_id":DEVICE_ID[:8]+"...","redis":REDIS_OK,
                            "ollama":_ollama_has("llama3.2"),
                            "embed_model":_embed_ok,
                            "sessions_active":sess["active"],
                            "db_mode":"WAL"})

        @app.route("/sessions")
        def sessions_ep(): return jsonify(session_stats())

        @app.route("/sessions/cleanup", methods=["POST"])
        def cleanup_ep(): return jsonify({"cleaned": session_cleanup()})

        @app.route("/stats")
        def stats_ep():
            ct = _db.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            cv = _db.execute("SELECT COUNT(*) FROM cache WHERE vec IS NOT NULL").fetchone()[0]
            ag = _db.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            return jsonify({"cache_entries":ct,"cache_with_vectors":cv,
                            "agents_tracked":ag,
                            "l1_size":len(_L1),"l1_vecs":len(_L1_VEC),
                            "redis":REDIS_OK,
                            **session_stats(),
                            **agent_stats_all()})

        # FIX #5: новый endpoint — дерево субагентов для дашборда
        @app.route("/agents")
        def agents_ep():
            session_id = request.args.get("session_id", "default")
            return jsonify(agent_tree(session_id))

        @app.route("/agents/all")
        def agents_all_ep():
            return jsonify(agent_stats_all())

        print(f"\nTokenSaver v5.2 → http://localhost:4000")
        print(f"Device : TS-{DEVICE_ID[:4].upper()}-{DEVICE_ID[4:8].upper()}")
        print(f"Redis  : {'✅' if REDIS_OK else '⚠️  off'}")
        print(f"Ollama : {'✅' if _ollama_has('llama3.2') else '⚠️  not found'}")
        print(f"Fuzzy  : {'✅ all-MiniLM-L6-v2' if _embed_ok else '⚠️  pip install sentence-transformers'}")
        print(f"DB     : WAL mode ✅  {_ts_dir / 'tokensaver.db'}")
        print(f"Agents : /agents?session_id=... | /agents/all")
        print(f"")
        app.run(host="0.0.0.0", port=4000, debug=False)

    else:
        session_id = f"interactive-{DEVICE_ID[:8]}"
        print("TokenSaver v5.2 · Ctrl+C — выход\n")
        while True:
            try:
                p = input("You: ").strip()
                if not p: continue
                h = session_load(session_id)
                r = ask(p, history=h)
                h.append({"role":"user","content":p})
                h.append({"role":"assistant","content":r["response"]})
                session_save(session_id, h,
                             model=r["stats"].get("model",""),
                             cost=r["stats"].get("cost_usd",0.0))
                print(f"AI: {r['response']}\n")
            except KeyboardInterrupt:
                print("\nПока!"); break
