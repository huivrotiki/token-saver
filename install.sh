#!/usr/bin/env bash
# TokenSaver v5.1 — установка одной командой
set -e

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
TS_DIR="$HOME/.tokensaver"
REPO_DIR="$HOME/token-saver"

echo -e "${BLUE}⚡ TokenSaver v5.1 — установка${NC}"
mkdir -p "$TS_DIR"

# ── Python зависимости (полный стек) ─────────────────────────
echo -e "${BLUE}📦 Устанавливаю Python зависимости...${NC}"
pip install litellm flask redis dash plotly requests \
    anthropic google-generativeai openai \
    sentence-transformers --quiet
echo -e "${GREEN}✅ Все Python зависимости установлены${NC}"

# ── Redis ────────────────────────────────────────────────────
if command -v brew &>/dev/null; then
    brew list redis &>/dev/null || brew install redis --quiet
    brew services start redis 2>/dev/null || true
    echo -e "${GREEN}✅ Redis запущен${NC}"
elif command -v redis-server &>/dev/null; then
    redis-server --daemonize yes 2>/dev/null || true
    echo -e "${GREEN}✅ Redis запущен${NC}"
else
    echo -e "${YELLOW}⚠️  Redis не найден. Установи: brew install redis${NC}"
fi

# ── Ollama проверка ───────────────────────────────────────────
if command -v ollama &>/dev/null; then
    echo -e "${GREEN}✅ Ollama найден${NC}"
    echo "   Рекомендуемые модели:"
    echo "   ollama pull llama3.2:3b       (lite/simple, 2GB)"
    echo "   ollama pull qwen3:14b          (medium, 9GB)"
    echo "   ollama pull qwen2.5-coder:7b   (код, 5GB)"
else
    echo -e "${YELLOW}⚠️  Ollama не найден — установи: https://ollama.com${NC}"
fi

# ── .env шаблон ───────────────────────────────────────────────
if [ ! -f "$TS_DIR/.env" ]; then
cat > "$TS_DIR/.env" << 'ENVFILE'
# TokenSaver v5.1 — API ключи (chmod 600!)
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
NVIDIA_NIM_API_KEY=nvapi-...
OPENAI_API_KEY=sk-...

# Алерты
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SLACK_WEBHOOK_URL=
ALERT_EMAIL=

# Лимиты (USD/месяц)
WARN_LIMIT_USD=5.0
CRITICAL_LIMIT_USD=20.0
ENVFILE
chmod 600 "$TS_DIR/.env"
echo -e "${YELLOW}⚠️  Добавь ключи в $TS_DIR/.env${NC}"
fi

# ── Bash алиасы ───────────────────────────────────────────────
SHELL_RC="$HOME/.zshrc"
[ -f "$HOME/.bashrc" ] && SHELL_RC="$HOME/.bashrc"

grep -q "ts-start" "$SHELL_RC" 2>/dev/null || cat >> "$SHELL_RC" << ALIASES

# TokenSaver v5.1 aliases
alias ts-start='python3 $REPO_DIR/tokensaver.py --server'
alias ts-dash='python3 $REPO_DIR/dashboard.py'
alias ts-alerts='python3 $REPO_DIR/alerts.py'
alias ts-router='python3 $REPO_DIR/background_router.py'
alias ts-log='tail -f ~/.tokensaver/tokensaver.log'
alias ts-stats='curl -s http://localhost:4000/stats | python3 -m json.tool'
alias ts-health='curl -s http://localhost:4000/health | python3 -m json.tool'
alias ts-sessions='curl -s http://localhost:4000/sessions | python3 -m json.tool'

# Запустить весь стек
alias ai-start='redis-server --daemonize yes 2>/dev/null; python3 $REPO_DIR/tokensaver.py --server &'
alias ai-dash='python3 $REPO_DIR/dashboard.py'
alias ai-stats='curl -s http://localhost:4000/stats | python3 -m json.tool'
alias ai-stop='pkill -f tokensaver.py; pkill -f dashboard.py; pkill -f alerts.py'
ALIASES
echo -e "${GREEN}✅ Алиасы добавлены в $SHELL_RC${NC}"

# ── Проверка кэша ────────────────────────────────────────────
echo ""
echo -e "${BLUE}🔍 Проверка cache_control (Anthropic/Gemini)...${NC}"
python3 - << 'PYCHECK'
import os, sys
ts_dir = os.path.expanduser("~/.tokensaver")
env_file = os.path.join(ts_dir, ".env")
if os.path.exists(env_file):
    for line in open(env_file):
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

try:
    import redis as r
    c = r.Redis(host="localhost", port=6379, socket_timeout=1)
    c.ping()
    print("  ✅ Redis: OK")
except:
    print("  ⚠️  Redis: не подключён")

try:
    import litellm
    print(f"  ✅ LiteLLM: {litellm.__version__}")
except:
    print("  ❌ LiteLLM: не установлен")

try:
    import anthropic
    print(f"  ✅ Anthropic SDK: {anthropic.__version__}")
except:
    print("  ⚠️  Anthropic SDK: не установлен")

try:
    import google.generativeai
    print("  ✅ Google Generative AI SDK: OK")
except:
    print("  ⚠️  Google Generative AI SDK: не установлен")

try:
    from sentence_transformers import SentenceTransformer
    print("  ✅ sentence-transformers: OK (fuzzy cache активен)")
except:
    print("  ⚠️  sentence-transformers: не установлен (fuzzy cache отключён)")
PYCHECK

echo ""
echo -e "${GREEN}✅ TokenSaver v5.1 установлен!${NC}"
echo ""
echo "Следующие шаги:"
echo "  1. Добавь ключи в $TS_DIR/.env"
echo "  2. source $SHELL_RC"
echo "  3. Запусти: ai-start"
echo "  4. Claude Code: export ANTHROPIC_BASE_URL=http://localhost:4000"
echo "  5. Dashboard: ai-dash → http://localhost:8050"
