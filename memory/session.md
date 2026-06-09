# Last Session

> Обновляй этот файл после каждой значимой сессии.
> Формат: дата + что сделано + что осталось.

## 2026-06-09

### Сделано
- ✅ opencode.json переписан: 9router провайдер, ChromaDB localhost fix
- ✅ AGENTS.md создан с полным контекстом стека
- ✅ bootstrap.sh создан — единый запуск всего стека
- ✅ memory/ структура создана
- ✅ 9router запущен — 300+ моделей доступно
- ✅ docs/handoff-22 запушена (92 объекта)
- ✅ NINEROUTER_KEY — есть в Doppler serpent/dev_personal

### Осталось
- ❌ End-to-end тест OpenCode → 9router → модель (curl с реальным ключом)
- ❌ ChromaDB не запущен локально (memory-mcp смотрит на VM 34.44.215.238)
- ❌ Supabase L4 кэш не подключён к tokensaver
- ❌ hcom скрипт не найден
- ❌ memory/ ещё не скопирована в /Users/work/serpentos/

---

## Промт для новой сессии Claude Code

```
KONTEXT: проект Serpentos, ветка docs/handoff-22.

ПРОЧИТАЙ: ~/token-saver/memory/ (все файлы) + AGENTS.md

ТЕКУЩИЙ СТАТУС:
- 9router работает на :20128, NINEROUTER_KEY в Doppler
- bootstrap.sh есть: bash ~/token-saver/bootstrap.sh
- opencode.json обновлён (instructions + ChromaDB localhost)
- ChromaDB смотрел на VM 34.44.215.238 — нужно localhost

ЗАДАЧИ (по приоритету):
1. Запустить стек: doppler run --project serpent --config dev_personal -- bash ~/token-saver/bootstrap.sh
2. End-to-end тест: curl http://localhost:20128/v1/chat/completions с kr/claude-haiku-4.5
3. Скопировать memory/ в /Users/work/serpentos/memory/
4. Найти hcom: find /Users/work/serpentos -name 'hcom*' && git log --all -S 'hcom' --oneline
5. Обновить memory/session.md по завершению

НЕ ДЕЛАЙ:
- не переписывай opencode.json без просьбы
- не меняй ANTHROPIC_BASE_URL если не просили
- не трогай Redis/Ollama если недоступны
```
