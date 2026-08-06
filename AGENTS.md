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
| 9router запускается (меню появляется) | ✅ |
| **NINEROUTER_KEY получен и установлен** | ❌ |
| RTK компрессия проверена через дашборд | ❌ |
| End-to-end тест OpenCode → 9router → модель | ❌ |

---

## Google Agent Skills

**Репозиторий:** `github.com/google/skills`

Официальные skill-файлы от Google: агент читает их автоматически и знает правильные model ID,
параметры API и паттерны Gemini без дополнительных инструкций.

```bash
# Установить (один раз)
npx skills add google/skills

# Выбрать из списка:
# ✓ Gemini API on Agent Platform
# ✓ Gemini Interactions API on Agent Platform
```

### Доступные skills

| Skill | Что даёт |
|-------|----------|
| Gemini API on Agent Platform | Правильные model ID, параметры generateContent, safety settings |
| Gemini Interactions API | Паттерны multi-turn, streaming, function calling |

### Правильные model ID для Agent Platform

```
gemini-2.5-pro-preview-06-05
gemini-2.5-flash-preview-05-20
gemini-2.0-flash-001
gemini-1.5-pro-002
gemini-1.5-flash-002
```

> ⚠️ Не существуют: `gemini-3.x`, `gemma-4`, `gemini-2.5-pro-preview-05-06` (устаревший)

### ADC для Agent Platform (если нужен Vertex)

```bash
# Только в интерактивном терминале (Terminal.app, не в Claude Code)
gcloud auth application-default login
gcloud config set project <PROJECT_ID>
```

> Примечание: `gcloud auth` не работает в non-interactive среде.
> Если ADC не настроен — используй Google AI Studio с `GEMINI_API_KEY`.

---

## Главный блокер: NINEROUTER_KEY

9router запускается (меню появляется), но требует API ключ для провайдеров.

```bash
# Получить ключ:
# 1. Запустить 9router
node /Users/work/.hermes/node/lib/node_modules/9router/cli.js --listen 20128
# 2. В меню выбрать: Web UI
# 3. Dashboard → API Keys → Create → скопировать

# Установить:
echo "NINEROUTER_KEY=<ключ>" >> ~/.tokensaver/.env
export NINEROUTER_KEY=<ключ>
```

**Запуск 9router без зависания терминала:**
```bash
nohup node /Users/work/.hermes/node/lib/node_modules/9router/cli.js \
  --listen 20128 > /tmp/9router.log 2>&1 &
echo "PID: $!"
curl http://localhost:20128/v1/models 2>/dev/null && echo "✅ OK"
```

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
ai-start          # Redis + tokensaver :4000
ai-dash           # dashboard :8050
curl http://localhost:4000/health
ai-stats

# ~/.tokensaver/.env
GEMINI_API_KEY=AIza...
NVIDIA_NIM_API_KEY=nvapi-...
NINEROUTER_BASE_URL=http://localhost:20128/v1
NINEROUTER_KEY=<key>
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

- `gcloud auth application-default login` не работает в non-interactive терминале — используй Google AI Studio вместо Vertex
- Doppler secrets не содержат `NINEROUTER_KEY` — получить вручную с 9router.com → Web UI → API Keys
- `source .env` в bash tool не персистирует переменные — использовать `export $(grep -v '^#' .env | xargs)`
- bash tool требует поле `description` — если агент выдаёт `Invalid input: description undefined`, переформулируй запрос или перезапусти сессию
- git не инициализирован в `/Users/work/serpentos` — если нужен: `cd /Users/work/serpentos && git init && git add . && git commit -m 'init'`

---

*Обновлено: 2026-06-09 | TokenSaver v5.3 | github.com/huivrotiki/token-saver*
