# ⚡ TokenSaver v5.0

**10 механик экономии токенов для Claude Code, Cursor, OpenCode.**
Сокращает расходы на AI с $180 до $1.80/мес.

## Что внутри

| Механика | Экономия |
|---|---|
| 🧠 Семантический кэш (exact + fuzzy) | 70% hit rate |
| 🗜️ Auto Compact (контекст) | -80% длинные сессии |
| 🏠 Локальная маршрутизация (Ollama) | -99.7% для simple/lite |
| ✂️ RTK (фильтр паразитных токенов) | -20% output |
| 🔒 PII guard + Device Fingerprint | безопасность |
| 💬 Session Persistence (SQLite) | история не теряется |

## Установка

```bash
git clone https://github.com/huivrotiki/token-saver
cd token-saver
bash install.sh
```

## Запуск

```bash
# Прокси (OpenAI-compatible)
python3 tokensaver.py --server    # → :4000

# Claude Code
export ANTHROPIC_BASE_URL=http://localhost:4000
claude

# Dashboard
python3 dashboard.py              # → :8050

# Проверка
curl http://localhost:4000/health
```

## Файлы

| Файл | Описание |
|---|---|
| `tokensaver.py` | Основной модуль — все 10 механик |
| `dashboard.py` | Real-time мониторинг (Dash/Plotly) |
| `TOKENSAVER_MASTER.md` | Полная документация |
| `litellm_config.yaml` | 8 провайдеров + роутинг |
| `install.sh` | Установка одной командой |

## Требования

- Python 3.10+
- `pip install litellm flask`
- Ollama (опционально, для local routing)
- `pip install sentence-transformers` (опционально, +30% fuzzy cache)

## Архитектура

```
Claude Code → TokenSaver :4000
                ├─ Fuzzy Cache hit? → ответ (бесплатно)
                ├─ Privacy check → PII? → Ollama only
                ├─ Classify → lite/simple/medium/deep
                ├─ Route → Ollama (free) / Gemini / Claude
                ├─ Auto Compact → если контекст > 78%
                └─ RTK → убрать паразитные токены
```

---

MIT License | [TOKENSAVER_MASTER.md](TOKENSAVER_MASTER.md) для полной документации
