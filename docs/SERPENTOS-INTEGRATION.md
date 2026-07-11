# Интеграция token-saver с Serpentos Agent OS

## Быстрый старт

```bash
# 1. Секреты через Doppler (никаких .env с ключами!)
doppler setup --project serpentos --config dev

# 2. Поднять весь прокси-стек
doppler run -- docker compose -f docker-compose.proxy.yml up -d

# 3. Подключить агентов (добавить в ~/.zshrc или .envrc)
export OPENAI_BASE_URL="http://localhost:4000/v1"
export ANTHROPIC_BASE_URL="http://localhost:4000/v1"
export OPENAI_API_KEY="$(doppler secrets get LITELLM_MASTER_KEY --plain)"
```

После этого **все** агенты Serpentos автоматически идут через прокси:
- Claude Code: `ANTHROPIC_BASE_URL` перехватывается
- OpenCode/Cline: `OPENAI_BASE_URL` перехватывается
- Кастомные скрипты: используют тот же endpoint

## Архитектура

```
Агент (claude/kiro/ceo-agent)
        ↓
http://localhost:4000/v1  ← LiteLLM Proxy (token-saver)
        ↓
┌───────────────────────────────────┐
│  Semantic Cache (Redis, 95% hit?) │ ← отдаёт кэш, не дёргает API
│  Rate Limiter (per agent-id)      │ ← блокирует зависшие агенты
│  Cost Router                      │ ← heavy→claude, light→ollama
│  Fallback Chain                   │ ← mlx→ollama→nvidia→gemini→claude
└───────────────────────────────────┘
        ↓
  Реальный LLM провайдер
```

## Маршрутизация запросов

### Смысловое разделение через `model` в запросе:

| Агент делает запрос к | Реальный маршрут | Стоимость |
|-----------------------|------------------|-----------|
| `model: "light"` | qwen2.5-coder:7b (Ollama) | $0 |
| `model: "heavy"` | claude-sonnet → gemini fallback | ~$0.01/запрос |
| `model: "video"` | gemini-2.0-flash (лучший для мультимодал) | ~$0.001 |
| `model: "mlx-coder-7b"` | MLX local (M1/M2) | $0 |
| `model: "claude-sonnet"` | Anthropic напрямую | ~$0.015/запрос |

### Семантический кэш

Если агент отправляет похожий запрос (cosine similarity ≥ 0.95), прокси отдаёт кэш из Redis мгновенно, не тратя токены:

```bash
# Проверить статистику кэша
curl http://localhost:4000/cache/ping
curl http://localhost:4000/spend/logs  # аудит расходов
```

## Per-Agent Rate Limits (Audit Trail)

Каждый агент Serpentos передаёт свой ID через заголовок:

```python
# В агенте (пример для Python)
import litellm
response = litellm.completion(
    model="light",
    messages=[...],
    metadata={"user": "ceo-agent"}  # agent_id для аудита
)
```

Лимиты настраиваются через LiteLLM virtual keys (Dashboard на :4001):
- `ceo-agent`: $2/день, 100 RPM
- `video-agent`: $5/день, 50 RPM  
- `autosave-agent`: $0.1/день, 10 RPM (защита от циклов!)

Все расходы пишутся в PostgreSQL и совместимы со схемой `logs/audit.jsonl` из `SECURITY.md`.

## Интеграция в docker-compose Serpentos

Добавить в `docker-compose.video-pipeline.yml`:

```yaml
# В конец файла
extend:
  file: ../token-saver/docker-compose.proxy.yml  # если token-saver рядом
  service: proxy
```

Или подключиться к уже запущенному стеку через external network:

```yaml
networks:
  default:
    external: true
    name: serpentos-proxy
```

## Dashboard

- **LiteLLM UI**: http://localhost:4001 — расходы, модели, ключи
- **Redis Commander** (опционально): `docker run -p 8081:8081 rediscommander/redis-commander --redis-host redis`
- **Grafana** (опционально): подключить к PostgreSQL для метрик

## Troubleshooting

```bash
# Логи прокси
docker logs serpentos-proxy -f

# Проверить доступность
curl http://localhost:4000/health

# Тест запроса
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "light", "messages": [{"role": "user", "content": "ping"}]}'

# Статус кэша
curl http://localhost:4000/cache/ping

# Бюджет агентов
curl http://localhost:4000/spend/logs -H "Authorization: Bearer $LITELLM_MASTER_KEY"
```
