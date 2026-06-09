# Project: Serpentos

## Что это

Serpentos — основной рабочий проект. Включает:
- **ectic** — дизайн-система / UI-фреймворк (mono reskin в процессе)
- **Antigravity** — менеджер задач / оркестратор агентов
- **TokenSaver** — прокси для экономии токенов AI
- **9Router** — локальный AI-гейтвей

## Пути

```
/Users/work/serpentos/          # корень проекта
/Users/work/serpentos/opencode.json  # конфиг провайдеров
~/token-saver/                  # TokenSaver репо
~/.tokensaver/.env              # API ключи
~/.tokensaver/tokensaver.db     # SQLite кэш + сессии
```

## Текущая ветка

`docs/handoff-22` — опережает origin на 13 коммитов (незапушено)

## Статус задач

- [ ] Получить NINEROUTER_KEY (9router Web UI → API Keys)
- [ ] Запушить ветку docs/handoff-22
- [ ] Настроить gcloud ADC для Vertex (опционально)
- [ ] End-to-end тест OpenCode → 9router → модель
