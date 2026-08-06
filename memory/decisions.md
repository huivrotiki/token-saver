# Architecture Decision Records (ADR)

## ADR-001: TokenSaver как основной прокси

**Решение:** Все AI-запросы идут через TokenSaver `:4000`  
**Причина:** 10 механик экономии, $180→$1.80/мес  
**Дата:** 2026-06

## ADR-002: 9Router вместо OmniRouter

**Решение:** Заменить OmniRouter на 9Router `:20128`  
**Причина:** OmniRouter deprecated, 9Router поддерживает RTK-сжатие и smart fallback  
**Дата:** 2026-06

## ADR-003: Google AI Studio вместо Vertex

**Решение:** Использовать `GEMINI_API_KEY` вместо ADC/Vertex  
**Причина:** `gcloud auth` не работает в non-interactive среде агентов  
**Дата:** 2026-06

## ADR-004: SQLite WAL как основное хранилище

**Решение:** SQLite с WAL mode для кэша, сессий и agent tree  
**Причина:** Нет внешних зависимостей, поддержка concurrent subagents  
**Дата:** 2026-06

## ADR-005: AGENTS.md как shared memory для агентов

**Решение:** AGENTS.md в корне репо = главный контекст для всех агентов  
**Причина:** Claude Code, OpenCode, Gemini читают его автоматически  
**Дата:** 2026-06
