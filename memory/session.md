# Last Session

> Обновляй этот файл после каждой значимой сессии.
> Формат: дата + что сделано + что осталось.

## 2026-06-09

### Сделано
- ✅ opencode.json переписан: 9router провайдер, правильные Gemini model ID
- ✅ AGENTS.md создан с полным контекстом стека
- ✅ bootstrap.sh создан — единый запуск всего стека
- ✅ memory/ структура создана (этот файл)
- ✅ 9router запускается (меню появляется на :20128)
- ✅ google/skills секция добавлена в AGENTS.md

### Осталось
- ❌ NINEROUTER_KEY — получить из Web UI → API Keys
- ❌ ChromaDB не запущен на VM
- ❌ Ветка docs/handoff-22 не запушена (13 коммитов)
- ❌ End-to-end тест OpenCode → 9router → модель
- ❌ Supabase L4 кэш не подключён

### Следующий промт для агента

```
Прочитай memory/ и AGENTS.md.
Статус: 9router запущен, NINEROUTER_KEY нужен.
Задача: получи ключ из 9router Web UI, добавь в ~/.tokensaver/.env,
проверь curl http://localhost:20128/v1/models
```
