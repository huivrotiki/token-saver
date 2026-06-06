# TokenSaver v5.0 — Мастер-документ

> 10 механик экономии токенов | $180→$1.80/мес | Auto Compact + Fuzzy Cache + Session Persistence

---

## Все 10 механик

| # | Механика | Экономия |
|---|---|---|
| 1 | Классификатор сложности | ~60% |
| 2 | Семантический кэш L1/L2/L3 + Fuzzy | 20–70% (+30%) |
| 3 | RTK (Response Token Kompressor) | ~20% output |
| 4 | Thinking Budget | 10–40% reasoning |
| 5 | Локальная маршрутизация (Ollama) | до -99.7% |
| 6 | Детектор приватности (PII guard) | защита |
| 7 | Device Fingerprint | защита триала |
| 8 | Провайдерский кэш (Claude/Gemini) | ~90% повторов |
| 9 | Auto Compact (context compression) | ~80% длинных сессий |
| 10 | Prompt Dedup | ~100% дублей |

---

## Быстрый старт

```bash
# 1. Установка
curl -sSL https://raw.githubusercontent.com/huivrotiki/token-saver/main/install.sh | bash

# 2. Запуск прокси
python3 tokensaver.py --server     # → http://localhost:4000

# 3. Claude Code
export ANTHROPIC_BASE_URL=http://localhost:4000
claude

# 4. Dashboard
python3 dashboard.py               # → http://localhost:8050

# 5. Fuzzy Cache (опционально, +30% hit rate)
pip install sentence-transformers  # ~80MB, ленивая загрузка
```

---

## Архитектура

```
Claude Code / Cursor / Zed
         │  ANTHROPIC_BASE_URL=localhost:4000
         ▼
  ┌───────────────────────────────────────┐
  │         TokenSaver Proxy :4000      │
  │                                     │
  │  [1] Dedup check (2s window)        │
  │  [2] Fuzzy Cache (SHA + cosine≥.85) │
  │  [3] Privacy guard (PII → local)    │
  │  [4] Classify: lite/simple/med/deep │
  │  [5] Route: Ollama → Cloud          │
  │  [9] Auto Compact (78% threshold)   │
  │       ├─ local quality ≥ 0.82 ✓    │
  │       └─ fallback: gemini-flash     │
  │  [8] Provider cache (Claude/Gemini) │
  │  [3] RTK (strip filler)             │
  │  [4] Thinking Budget                │
  └───────────────────────────────────────┘
         │
    ┌────┴────┐
    │ Ollama  │  gemini-flash  │  claude-sonnet
    │ (free)  │  (cheap)       │  (deep only)
    └─────────┘
```

---

## Auto Compact (Q1 ✔)

- Порог: 78% заполнения контекста
- Попытка 1: local Ollama (бесплатно) → quality check
- Если keyword_hit_rate < 0.82 → fallback: gemini-flash-lite
- Сохраняет: пути файлов, имена функций, ошибки, TODO
- Режет: объяснения, повторы, болтовню

## Session Persistence (Q2 ✔)

- История сессий в SQLite `~/.tokensaver/tokensaver.db`
- TTL: 24 часа, автоочистка при старте
- X-Session-Id заголовок для привязки к Claude Code сессии
- Эндпоинты: GET /sessions, POST /sessions/cleanup

## Fuzzy Cache (Q4 ✔)

- Модель: all-MiniLM-L6-v2 (80MB, CPU, ленивая загрузка)
- Порог: cosine similarity ≥ 0.85
- Уровни: L1 RAM exact → L2 Redis → L3 SQLite → L1 RAM fuzzy → SQLite fuzzy
- Hit rate: ~40% exact + ~30% fuzzy = ~70% total

---

## Открытые вопросы

- Q5: NVIDIA NIM rate limit 40 RPM → asyncio queue
- Q6: Streaming support (SSE + RTK буферизация)
- Q7: Fine-tuned классификатор (sklearn вместо keywords)
- Q8: Multi-user режим (user_id в сессиях)
- Q9: Шифрование кэша GDPR (Fernet)
- Q10: Dashboard fuzzy hit rate метрика

---

*TokenSaver v5.0 | github.com/huivrotiki/token-saver*
