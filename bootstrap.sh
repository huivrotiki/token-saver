#!/usr/bin/env bash
# =============================================================
# bootstrap.sh — Universal AI Stack (Hermes Edition)
# Запускает TokenSaver(:4000) + Hermes/OmniRoute(:20128) + Redis + ChromaDB
# Настраивает env для: Claude Code, OpenCode, Gemini, Cursor, Zed
#
# Использование:
#   bash bootstrap.sh          # запустить стек
#   bash bootstrap.sh --stop   # остановить всё
#   bash bootstrap.sh --status # проверить статус
#   bash bootstrap.sh --install # первая установка
# =============================================================
set -euo pipefail

# ── Цвета ─────────────────────────────────────────────────────
GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

# ── Пути ──────────────────────────────────────────────────────
TS_DIR="$HOME/.tokensaver"
REPO_DIR="$HOME/token-saver"          # TokenSaver repo
HERMES_DIR="$HOME/serpentos/Hermes_Omni"  # OmniRoute (Hermes) repo
NODE_BIN="$HOME/.hermes/node/bin"
LOG_DIR="$TS_DIR/logs"
mkdir -p "$TS_DIR" "$LOG_DIR"

# ── Загрузить .env ────────────────────────────────────────────
load_env() {
  [ -f "$TS_DIR/.env" ] && set -o allexport && source "$TS_DIR/.env" && set +o allexport || true
}
load_env

# ── Проверка порта ────────────────────────────────────────────
port_free() { ! lsof -i ":$1" &>/dev/null; }
port_up()   {   lsof -i ":$1" &>/dev/null; }

log() { echo -e "${CYAN}[bootstrap]${NC} $*"; }
ok()  { echo -e "${GREEN}✅${NC} $*"; }
warn(){ echo -e "${YELLOW}⚠️ ${NC} $*"; }
err() { echo -e "${RED}❌${NC} $*"; }

# =============================================================
# STATUS
# =============================================================
show_status() {
  echo -e "\n${BOLD}⚡ AI Stack Status (Hermes Edition)${NC}\n"
  port_up 6379  && ok  "Redis          :6379" || warn "Redis          :6379  DOWN"
  port_up 4000  && ok  "TokenSaver     :4000  → omni-main cascade (Antigravity $0)" || warn "TokenSaver     :4000  DOWN"
  port_up 4001  && ok  "BG Router      :4001" || warn "BG Router      :4001  DOWN"
  port_up 20128 && ok  "Hermes/OmniRoute :20128" || warn "Hermes/OmniRoute :20128  DOWN"
  port_up 8000  && ok  "ChromaDB       :8000" || warn "ChromaDB       :8000  DOWN"
  port_up 8050  && ok  "Dashboard      :8050" || warn "Dashboard      :8050  DOWN"

  echo ""
  echo -e "${BOLD}Env vars:${NC}"
  [ -n "${ANTHROPIC_API_KEY:-}" ]  && ok  "ANTHROPIC_API_KEY"   || warn "ANTHROPIC_API_KEY   not set"
  [ -n "${GEMINI_API_KEY:-}" ]     && ok  "GEMINI_API_KEY"      || warn "GEMINI_API_KEY      not set"
  [ -n "${NINEROUTER_KEY:-}" ]     && ok  "NINEROUTER_KEY"      || warn "NINEROUTER_KEY      not set"
  [ -n "${NVIDIA_NIM_API_KEY:-}" ] && ok  "NVIDIA_NIM_API_KEY" || warn "NVIDIA_NIM_API_KEY  not set"
  [ -n "${OPENAI_API_KEY:-}" ]     && ok  "OPENAI_API_KEY"      || warn "OPENAI_API_KEY      not set"
  echo ""
}

# =============================================================
# STOP
# =============================================================
stop_stack() {
  log "Останавливаю стек..."
  pkill -f "tokensaver.py"    2>/dev/null && ok "TokenSaver остановлен"   || true
  pkill -f "background_router" 2>/dev/null && ok "BG Router остановлен"    || true
  pkill -f "dashboard.py"     2>/dev/null && ok "Dashboard остановлен"    || true
  pkill -f "chroma run"       2>/dev/null && ok "ChromaDB остановлен"     || true
  # Hermes/OmniRoute — остановить по порту
  lsof -ti :20128 | xargs kill -9 2>/dev/null && ok "Hermes/OmniRoute остановлен" || true
  ok "Стек остановлен"
}

# =============================================================
# INSTALL (первая установка)
# =============================================================
install_deps() {
  log "Устанавливаю зависимости..."

  # Python
  pip install --quiet \
    litellm flask redis dash plotly requests \
    anthropic google-generativeai openai \
    sentence-transformers chromadb httpx \
    python-dotenv 2>&1 | tail -3
  ok "Python deps установлены"

  # Hermes/OmniRoute (уже склонирован, npm install если нужно)
  if [ -d "${HERMES_DIR:-$HOME/serpentos/Hermes_Omni}" ]; then
    ok "Hermes/OmniRoute найден — npm install если нужно"
    cd "${HERMES_DIR:-$HOME/serpentos/Hermes_Omni}" && npm install --silent 2>/dev/null || true
    cd - > /dev/null
  else
    warn "Hermes_Omni не найден — клонируй вручную"
  fi

  # ChromaDB CLI
  pip install --quiet chromadb 2>&1 | tail -1
  ok "ChromaDB установлен"

  # Redis
  if command -v brew &>/dev/null; then
    brew list redis &>/dev/null || brew install redis --quiet
    ok "Redis установлен"
  fi

  # .env шаблон
  if [ ! -f "$TS_DIR/.env" ]; then
    cat > "$TS_DIR/.env" << 'ENVEOF'
# AI Stack — API Keys (chmod 600!)
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
NVIDIA_NIM_API_KEY=nvapi-...
OPENAI_API_KEY=sk-...
NINEROUTER_KEY=

# Supabase (опционально — L4 кэш)
SUPABASE_URL=
SUPABASE_KEY=

# ChromaDB
CHROMADB_HOST=localhost
CHROMADB_PORT=8000

# 9Router
NINEROUTER_BASE_URL=http://localhost:20128/v1

# Лимиты
WARN_LIMIT_USD=5.0
CRITICAL_LIMIT_USD=20.0
ENVEOF
    chmod 600 "$TS_DIR/.env"
    warn "Добавь ключи в $TS_DIR/.env"
  fi

  # Shell aliases
  local SHELL_RC="$HOME/.zshrc"
  [ -f "$HOME/.bashrc" ] && SHELL_RC="$HOME/.bashrc"
  grep -q "bootstrap.sh" "$SHELL_RC" 2>/dev/null || cat >> "$SHELL_RC" << ALIASEOF

# AI Stack bootstrap
export PATH="$NODE_BIN:\$PATH"
export ANTHROPIC_BASE_URL=http://localhost:4000
export OPENAI_BASE_URL=http://localhost:20128/v1
alias ai-start='bash $REPO_DIR/bootstrap.sh'
alias ai-stop='bash $REPO_DIR/bootstrap.sh --stop'
alias ai-status='bash $REPO_DIR/bootstrap.sh --status'
alias ai-dash='python3 $REPO_DIR/dashboard.py'
alias ai-log='tail -f $TS_DIR/logs/tokensaver.log'
alias ai-stats='curl -s http://localhost:4000/stats | python3 -m json.tool'
alias ai-health='curl -s http://localhost:4000/health | python3 -m json.tool'
ALIASEOF
  ok "Алиасы добавлены → source $SHELL_RC"
}

# =============================================================
# START STACK
# =============================================================
start_stack() {
  echo -e "\n${BOLD}${BLUE}⚡ Запускаю AI Stack...${NC}\n"
  load_env
  export PATH="$NODE_BIN:$PATH"

  # ── 1. Redis ────────────────────────────────────────────────
  if port_free 6379; then
    if command -v brew &>/dev/null; then
      brew services start redis 2>/dev/null || redis-server --daemonize yes 2>/dev/null || true
    else
      redis-server --daemonize yes 2>/dev/null || true
    fi
    sleep 0.5
    port_up 6379 && ok "Redis :6379" || warn "Redis не запустился (продолжаю без него)"
  else
    ok "Redis :6379 уже запущен"
  fi

  # ── 2. ChromaDB ─────────────────────────────────────────────
  if port_free 8000; then
    if command -v chroma &>/dev/null; then
      nohup chroma run --path "$TS_DIR/chroma" --port 8000 \
        > "$LOG_DIR/chroma.log" 2>&1 &
      sleep 1
      port_up 8000 && ok "ChromaDB :8000" || warn "ChromaDB не запустился"
    else
      warn "ChromaDB не установлен (pip install chromadb)"
    fi
  else
    ok "ChromaDB :8000 уже запущен"
  fi

  # ── 3. TokenSaver :4000 ─────────────────────────────────────
  if port_free 4000; then
    nohup python3 "$REPO_DIR/tokensaver.py" --server \
      > "$LOG_DIR/tokensaver.log" 2>&1 &
    sleep 1.5
    port_up 4000 && ok "TokenSaver :4000" || err "TokenSaver не запустился! Лог: $LOG_DIR/tokensaver.log"
  else
    ok "TokenSaver :4000 уже запущен"
  fi

  # ── 4. Background Router :4001 ──────────────────────────────
  if port_free 4001; then
    nohup python3 "$REPO_DIR/background_router.py" --daemon \
      > "$LOG_DIR/bg_router.log" 2>&1 &
    sleep 0.5
    port_up 4001 && ok "BG Router :4001" || warn "BG Router не запустился"
  else
    ok "BG Router :4001 уже запущен"
  fi

  # ── 5. Hermes/OmniRoute :20128 ──────────────────────────────
  if port_free 20128; then
    if [ -d "$HERMES_DIR" ] && [ -f "$HERMES_DIR/package.json" ]; then
      log "Запускаю Hermes/OmniRoute из $HERMES_DIR..."
      cd "$HERMES_DIR"
      # Использовать prod build если есть, иначе dev
      if [ -d "$HERMES_DIR/dist" ] && [ -f "$HERMES_DIR/dist/index.js" ]; then
        PORT=20128 nohup node "$HERMES_DIR/dist/index.js" \
          > "$LOG_DIR/hermes.log" 2>&1 &
      else
        PORT=20128 nohup npm run dev \
          > "$LOG_DIR/hermes.log" 2>&1 &
      fi
      cd - > /dev/null
      sleep 5  # OmniRoute/Next.js нужно время на запуск
      port_up 20128 && ok "Hermes/OmniRoute :20128 (omni-main ready)" \
        || warn "Hermes ещё грузится... проверь: tail -f $LOG_DIR/hermes.log"
    else
      warn "Hermes_Omni не найден в $HERMES_DIR — пропускаю"
      warn "Клонируй: git clone https://github.com/huivrotiki/Hermes_Omni $HERMES_DIR"
    fi
  else
    ok "Hermes/OmniRoute :20128 уже запущен"
  fi

  # ── 6. Экспорт env для агентов ──────────────────────────────
  echo ""
  echo -e "${BOLD}Настройка агентов:${NC}"
  echo ""
  echo -e "  ${CYAN}Claude Code:${NC}"
  echo "    export ANTHROPIC_BASE_URL=http://localhost:4000"
  echo ""
  echo -e "  ${CYAN}OpenCode (opencode.json):${NC}"
  echo '    "baseURL": "http://localhost:20128/v1"   # 9router'
  echo '    "baseURL": "http://localhost:4000/v1"    # tokensaver'
  echo ""
  echo -e "  ${CYAN}Cursor / Zed / Windsurf:${NC}"
  echo "    OpenAI base URL → http://localhost:20128/v1"
  echo "    API Key        → ${NINEROUTER_KEY:-<set NINEROUTER_KEY>}"
  echo ""
  echo -e "  ${CYAN}Gemini (прямой):${NC}"
  echo "    GEMINI_API_KEY установлен: $([ -n "${GEMINI_API_KEY:-}" ] && echo '✅' || echo '❌ добавь в ~/.tokensaver/.env')"
  echo ""

  # ── 7. Итоговый статус ──────────────────────────────────────
  show_status

  echo -e "${BOLD}Dashboard:${NC} python3 $REPO_DIR/dashboard.py  →  http://localhost:8050"
  echo -e "${BOLD}Логи:${NC}      tail -f $LOG_DIR/tokensaver.log"
  echo ""
  ok "Стек запущен!"
}

# =============================================================
# ENTRYPOINT
# =============================================================
case "${1:-start}" in
  --stop)    stop_stack  ;;
  --status)  load_env; show_status ;;
  --install) install_deps ;;
  start|--start|"")
    # Клонировать репо если не существует
    if [ ! -f "$REPO_DIR/tokensaver.py" ]; then
      warn "Репо не найдено в $REPO_DIR"
      log "Клонирую..."
      git clone https://github.com/huivrotiki/token-saver.git "$REPO_DIR" 2>/dev/null \
        || { err "Клонирование не удалось. Положи репо в $REPO_DIR"; exit 1; }
    fi
    start_stack
    ;;
  *)
    echo "Использование: bash bootstrap.sh [--install|--start|--stop|--status]"
    exit 1
    ;;
esac
