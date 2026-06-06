# TokenSaver v5.1

> Система оптимизации токенов и затрат на AI API.  
> **Экономия: $1,830 → ~$0.33 / месяц** при грамотной маршрутизации.

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    TokenSaver v5.1 Stack                    │
├─────────────────────────────────────────────────────────────┤
│  Claude Code / любой OpenAI-совместимый клиент              │
│         ↓  ANTHROPIC_BASE_URL=http://localhost:4000         │
├─────────────────────────────────────────────────────────────┤
│  tokensaver.py (:4000)   ←→  background_router.py (:4001)  │
│  • 10 механик экономии        • RTK оптимизация промптов   │
│  • Semantic fuzzy cache        • Валидация кэша             │
│  • Session persistence         • Статистика роутинга        │
│  • Auto-compact                                             │
├──────────────┬──────────────────┬───────────────────────────┤
│  Redis cache │  SQLite DB       │  alerts.py                │
│  (L2 кэш)   │  (кэш + сессии)  │  Telegram/Slack/Email     │
├──────────────┴──────────────────┴───────────────────────────┤
│                  dashboard.py (:8050)                       │
├─────────────────────────────────────────────────────────────┤
│               Иерархия роутинга моделей                     │
│  Ollama local ($0) → NVIDIA NIM free ($0, 40 RPM)           │
│    → Gemini Flash (дёшево) → Claude Sonnet (только deep)    │
└─────────────────────────────────────────────────────────────┘
```

## Файлы стека

| Файл | Размер | Что делает |
|------|--------|------------|
| `tokensaver.py` | ~30 KB | 10 механик экономии, Flask прокси `:4000` |
| `dashboard.py` | ~15 KB | Веб-дашборд `localhost:8050` |
| `background_router.py` | ~8 KB | RTK оптимизация + валидация кэша + статистика |
| `alerts.py` | ~6 KB | Алерты Telegram/Slack/Email/Terminal |
| `install.sh` | ~4 KB | Установка всего стека одной командой |
| `litellm_config.yaml` | ~2 KB | Конфигурация роутера моделей |
| `nim_queue.py` | ~7 KB | Очередь запросов для NVIDIA NIM (40 RPM) |

## Быстрый старт

```bash
# 1. Установка (один раз)
chmod +x install.sh && ./install.sh
source ~/.zshrc

# 2. Добавить API ключи
nano ~/.tokensaver/.env

# 3. Запустить весь стек
ai-start         # tokensaver на :4000
ai-dash          # dashboard на :8050

# 4. Подключить Claude Code
export ANTHROPIC_BASE_URL=http://localhost:4000

# 5. Проверить
curl http://localhost:4000/health
ai-stats
```

## Переменные окружения

```bash
# ~/.tokensaver/.env
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
NVIDIA_NIM_API_KEY=nvapi-...    # бесплатно: build.nvidia.com
OPENAI_API_KEY=sk-...           # опционально

# Алерты
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SLACK_WEBHOOK_URL=
ALERT_EMAIL=
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=

# Лимиты
WARN_LIMIT_USD=5.0
CRITICAL_LIMIT_USD=20.0
```

## Алиасы

| Алиас | Что делает |
|-------|------------|
| `ai-start` | Запускает Redis + tokensaver `:4000` |
| `ai-dash` | Запускает дашборд `:8050` |
| `ai-stats` | Показывает статистику JSON |
| `ai-stop` | Останавливает всё |
| `ts-start` | tokensaver сервер |
| `ts-dash` | дашборд |
| `ts-alerts` | alerts.py |
| `ts-router` | background_router.py |
| `ts-log` | tail логов |
| `ts-health` | health check |
| `ts-sessions` | статистика сессий |

## Иерархия роутинга

```
LITE/SIMPLE → Ollama local ($0)        ← если установлен
            → NVIDIA NIM free ($0)      ← fallback, 40 RPM
MEDIUM      → Ollama qwen3:14b ($0)    ← если установлен  
            → NVIDIA NIM / Gemini Flash ← fallback
DEEP        → Claude Sonnet            ← только сложные задачи
            → Gemini Flash             ← fallback
```

## Провайдерский кэш — как проверить

**Важно**: кэш не предполагать — проверять по usage полям:

| Провайдер | Поле для проверки | Мин. порог |
|-----------|-------------------|------------|
| Anthropic | `usage.cache_read_input_tokens > 0` | 1024 токенов |
| OpenAI | `usage.prompt_tokens_details.cached_tokens > 0` | 1024 токенов |
| Gemini | `usage.cached_content_token_count > 0` | 32K токенов |
| NVIDIA NIM | `usage.prompt_tokens_details.cached_tokens > 0` | зависит от модели |

Проверка в `background_router.py → validate_cache_hit(usage_obj)`.

## Лимиты алертов

| Метрика | WARN | CRITICAL |
|---------|------|----------|
| Расход USD/24h | $5 | $20 |
| Токены/24h | 500K | 2M |
| Error rate | 10% | — |

## Зависимости

```bash
# Python (все устанавливает install.sh)
pip install litellm flask redis dash plotly requests \
    anthropic google-generativeai openai \
    sentence-transformers

# System
brew install redis        # macOS
brew install ollama       # опционально
```

## Проекция экономии

| Сценарий | Без оптимизации | С TokenSaver |
|----------|-----------------|--------------|
| 100 req/day, Claude only | ~$1,830/мес | ~$0.33/мес |
| Mix: 70% local, 20% NIM, 10% Claude | — | $0–5/мес |
| Fuzzy cache hit rate 30%+ | — | дополнительно -30% |
