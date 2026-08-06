# Tech Stack

## Локальный AI-стек

| Сервис | Порт | Команда запуска | Статус |
|--------|------|-----------------|--------|
| Redis | 6379 | `brew services start redis` | нужен для L2 кэша |
| ChromaDB | 8000 | `chroma run --path ~/.tokensaver/chroma` | векторная память |
| TokenSaver | 4000 | `python3 ~/token-saver/tokensaver.py --server` | главный прокси |
| BG Router | 4001 | `python3 ~/token-saver/background_router.py --daemon` | RTK оптимизация |
| 9Router | 20128 | `node ~/.hermes/node/lib/node_modules/9router/cli.js --listen 20128` | AI гейтвей |
| Dashboard | 8050 | `python3 ~/token-saver/dashboard.py` | метрики |

## Один команда запуска всего

```bash
bash ~/token-saver/bootstrap.sh
```

## Подключение агентов

```bash
# Claude Code
export ANTHROPIC_BASE_URL=http://localhost:4000

# OpenCode (opencode.json)
# baseURL: http://localhost:20128/v1  (9router)
# baseURL: http://localhost:4000/v1   (tokensaver)

# Cursor / Zed / Windsurf
# OpenAI base URL → http://localhost:20128/v1
# API Key → $NINEROUTER_KEY
```

## Модели (рабочие ID)

```
gemini-2.5-flash-preview-05-20   # быстрый, дешёвый
gemini-2.5-pro-preview-06-05     # мощный
gemini-2.0-flash-001
gemini-1.5-pro-002
gemini-1.5-flash-002
claude-sonnet-4-5                # через 9router: kr/claude-sonnet-4.5
```

## Известные проблемы

- `gcloud auth application-default login` не работает в non-interactive терминале
- `bash tool` требует поле `description` — если ошибка, переформулируй запрос
- `source .env` в bash tool не персистирует — используй `export $(grep -v '^#' .env | xargs)`
- 9router нужен NINEROUTER_KEY — получить: Web UI → API Keys → Create
