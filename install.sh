#!/usr/bin/env bash
# TokenSaver v5.0 — установка одной командой
set -e

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
TS_DIR="$HOME/.tokensaver"

echo -e "${BLUE}⚡ TokenSaver v5.0 — установка${NC}"
mkdir -p "$TS_DIR"

# Python зависимости
pip install litellm flask redis --quiet
echo -e "${GREEN}✅ litellm flask redis${NC}"

# sentence-transformers (опционально)
read -p "🧠 Установить sentence-transformers? (+30% fuzzy cache, ~80MB) [y/N]: " yn
if [[ "$yn" == [Yy]* ]]; then
    pip install sentence-transformers --quiet
    echo -e "${GREEN}✅ sentence-transformers${NC}"
fi

# Bash алиасы
SHELL_RC="$HOME/.zshrc"
[ -f "$HOME/.bashrc" ] && SHELL_RC="$HOME/.bashrc"

grep -q "ts-start" "$SHELL_RC" 2>/dev/null || cat >> "$SHELL_RC" << 'ALIASES'

# TokenSaver v5.0 aliases
alias ts-start='python3 ~/token-saver/tokensaver.py --server'
alias ts-dash='python3 ~/token-saver/dashboard.py'
alias ts-log='tail -f ~/.tokensaver/tokensaver.log'
alias ts-stats='curl -s http://localhost:4000/stats | python3 -m json.tool'
alias ts-health='curl -s http://localhost:4000/health | python3 -m json.tool'
alias ts-sessions='curl -s http://localhost:4000/sessions | python3 -m json.tool'
ALIASES
echo -e "${GREEN}✅ Алиасы добавлены в $SHELL_RC${NC}"

# .env шаблон
if [ ! -f "$TS_DIR/.env" ]; then
cat > "$TS_DIR/.env" << 'ENVFILE'
# TokenSaver v5.0 keys — chmod 600 этот файл!
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
NVIDIA_NIM_API_KEY=nvapi-...
OPENAI_API_KEY=sk-...
ENVFILE
chmod 600 "$TS_DIR/.env"
echo -e "${YELLOW}⚠️  Добавь ключи в $TS_DIR/.env${NC}"
fi

# Ollama проверка
if command -v ollama &>/dev/null; then
    echo -e "${GREEN}✅ Ollama найден${NC}"
    echo "   Рекомендуемые модели:"
    echo "   ollama pull llama3.2:3b       (lite/simple, 2GB)"
    echo "   ollama pull qwen3:14b          (medium, 9GB)"
    echo "   ollama pull qwen2.5-coder:7b   (код, 5GB)"
else
    echo -e "${YELLOW}⚠️  Ollama не найден — установи: https://ollama.com${NC}"
fi

echo ""
echo -e "${GREEN}✅ TokenSaver v5.0 установлен!${NC}"
echo ""
echo "Следующие шаги:"
echo "  1. Добавь ключи в $TS_DIR/.env"
echo "  2. Запусти: ts-start"
echo "  3. Claude Code: export ANTHROPIC_BASE_URL=http://localhost:4000"
echo "  4. Dashboard: ts-dash → http://localhost:8050"
