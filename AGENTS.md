# AGENTS.md — Контекст сессии для AI-агентов

> Этот файл читается автоматически Claude Code / OpenCode при старте сессии.
> Содержит актуальное состояние проекта, блокеры и следующие шаги.

---

## Цель

Настроить **9router** как локальный AI-гейтвей вместо OmniRouter.
Интегрировать с **TokenSaver** (`:4000`) и **OpenCode** (`opencode.json`).
Включить RTK token-сжатие. Маршрутизировать Gemini-модели через правильные провайдеры.

---

## Текущий статус

| Задача | Статус |
|--------|--------|
| opencode.json обновлён (9router провайдер, правильные model ID) | ✅ |
| Google AI Studio model ID исправлены | ✅ |
| vertex / agent-platform провайдеры удалены (ADC не настроен) | ✅ |
| TokenSaver v5.3 установлен, фиксы применены | ✅ |
| **9router запускается и не падает** | ❌ BLOCKER |
| NINEROUTER_KEY получен и установлен | ❌ |
| RTK компрессия проверена через дашборд | ❌ |
| End-to-end тест OpenCode → 9router → модель | ❌ |

---

## Главный блокер: 9router падает при старте

**Симптом:** процесс завершается мгновенно, `9router_output.log` пуст.

**Диагностика — выполнить последовательно:**

```bash
# 1. Добавить в PATH (если ещё не)
export PATH="/Users/work/.hermes/node/bin:$PATH"

# 2. Проверить что бинарь существует
ls -la /Users/work/.hermes/node/bin/9router
node /Users/work/.hermes/node/lib/node_modules/9router/cli.js --version

# 3. Запустить с явным логом
node /Users/work/.hermes/node/lib/node_modules/9router/cli.js \
  --listen 20128 2>&1 | tee /tmp/9router_output.log

# 4. Если ошибка про missing modules:
npm install -g 9router

# 5. Проверить нужен ли NINEROUTER_KEY
# Ключ получить: https://9router.com → Login → Dashboard → API Key
export NINEROUTER_KEY=<key_from_dashboard>
9router --listen 20128
```

**Вероятные причины падения:**
- Отсутствует `NINEROUTER_KEY` (требует OAuth login на 9router.com)
- Node.js модули не установлены полностью
- Порт 20128 уже занят (`lsof -i :20128`)

---

## Рабочие файлы

| Файл | Описание |
|------|----------|
| `/Users/work/serpentos/opencode.json` | Конфиг провайдеров OpenCode |
| `/Users/work/.hermes/node/bin/9router` | Бинарь 9router (symlink) |
| `~/.tokensaver/.env` | API ключи TokenSaver |
| `~/.tokensaver/tokensaver.db` | SQLite кэш и сессии |
| `~/.zshrc` | PATH должен включать `/Users/work/.hermes/node/bin` |
| `/Users/work/serpentos/SESSION-LIMBO.md` | Контекст сессии Antigravity |
| `/Users/work/serpentos/OS-NOTES.md` | Глобальный changelog проекта |
| `9router_output.log` | Лог запуска 9router (создать: `touch 9router_output.log`) |

---

## opencode.json — правильная конфигурация

```json
{
  "providers": {
    "9router": {
      "name": "9Router Local Gateway",
      "api": "openai",
      "models": [
        { "id": "kr/claude-sonnet-4.5",             "name": "Claude Sonnet 4.5 (KR)",      "contextLength": 200000 },
        { "id": "kr/claude-haiku-4-5",              "name": "Claude Haiku 4.5 (KR)",       "contextLength": 200000 },
        { "id": "oc/auto",                          "name": "OpenCode Auto (free)",         "contextLength": 200000 },
        { "id": "openrouter/google/gemini-2.5-flash:free", "name": "Gemini 2.5 Flash (free)", "contextLength": 1000000 },
        { "id": "nvidia/meta/llama-3.1-8b-instruct","name": "Llama 3.1 8B NIM (free)",    "contextLength": 128000 }
      ],
      "options": {
        "baseURL": "http://localhost:20128/v1",
        "apiKey": "{env:NINEROUTER_KEY}"
      }
    },
    "google": {
      "name": "Google AI Studio",
      "api": "google",
      "models": [
        { "id": "gemini-2.5-flash-preview-05-20", "name": "Gemini 2.5 Flash",   "contextLength": 1048576 },
        { "id": "gemini-2.5-pro-preview-06-05",  "name": "Gemini 2.5 Pro",     "contextLength": 2097152 },
        { "id": "gemini-2.0-flash-001",          "name": "Gemini 2.0 Flash",   "contextLength": 1048576 },
        { "id": "gemini-1.5-pro-002",            "name": "Gemini 1.5 Pro",     "contextLength": 2097152 },
        { "id": "gemini-1.5-flash-002",          "name": "Gemini 1.5 Flash",   "contextLength": 1048576 }
      ],
      "options": {
        "apiKey": "{env:GEMINI_API_KEY}"
      }
    },
    "tokensaver": {
      "name": "TokenSaver Local",
      "api": "openai",
      "models": [
        { "id": "tokensaver-auto", "name": "TokenSaver Auto", "contextLength": 128000 }
      ],
      "options": {
        "baseURL": "http://localhost:4000/v1",
        "apiKey": "local"
      }
    }
  },
  "model": "google/gemini-2.5-flash-preview-05-20"
}
```

---

## TokenSaver — быстрый старт

```bash
# Запустить
ai-start          # alias: Redis + tokensaver :4000
ai-dash           # alias: dashboard :8050

# Проверить
curl http://localhost:4000/health
ai-stats

# Переменные (добавить в ~/.tokensaver/.env)
GEMINI_API_KEY=AIza...
NVIDIA_NIM_API_KEY=nvapi-...
NINEROUTER_BASE_URL=http://localhost:20128/v1
```

---

## Архитектура стека

```
OpenCode / Claude Code
    │
    ├─→ 9Router :20128  (RTK сжатие, smart fallback)
    │       └─→ KR subscription / NIM free / OpenRouter free
    │
    └─→ TokenSaver :4000  (10 механик экономии)
            ├─→ Ollama local ($0)
            ├─→ NVIDIA NIM free ($0)
            └─→ Google Gemini (GEMINI_API_KEY)
```

---

## Известные проблемы

- `gcloud auth application-default login` не работает в non-interactive терминале — ADC не настроен, используй Google AI Studio вместо Vertex
- Doppler secrets не содержат `NINEROUTER_KEY` — получить вручную с 9router.com
- `source .env` в bash tool не персистирует переменные — использовать `export $(cat .env | xargs)` или устанавливать переменные напрямую
- git не инициализирован в `/Users/work/serpentos` — если нужен: `cd /Users/work/serpentos && git init && git add . && git commit -m 'init'`

---

*Обновлено: 2026-06-09 | TokenSaver v5.3 | github.com/huivrotiki/token-saver*
