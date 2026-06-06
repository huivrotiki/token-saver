#!/usr/bin/env python3
"""
TokenSaver v5.1 — Alerts
Каналы: Telegram, Slack, Email, Terminal
Запуск: python3 alerts.py
Фоновый: python3 alerts.py --daemon
"""
import os, time, json, logging, argparse, smtplib, sqlite3
from pathlib import Path
from email.mime.text import MIMEText
from datetime import datetime

TS_DIR = Path.home() / ".tokensaver"
TS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=TS_DIR / "alerts.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("ts.alerts")

# ── Загрузка .env ─────────────────────────────────────────────
def load_env():
    env_file = TS_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()

# ── Лимиты ────────────────────────────────────────────────────
THRESHOLDS = {
    "warn_usd":     float(os.environ.get("WARN_LIMIT_USD", "5.0")),
    "critical_usd": float(os.environ.get("CRITICAL_LIMIT_USD", "20.0")),
    "warn_tokens":  int(os.environ.get("WARN_LIMIT_TOKENS", "500000")),
    "critical_tokens": int(os.environ.get("CRITICAL_LIMIT_TOKENS", "2000000")),
    "error_rate":   float(os.environ.get("WARN_ERROR_RATE", "0.1")),  # 10%
}

# ── История отправленных алертов (деdup) ──────────────────────
_sent: dict = {}
ALERT_COOLDOWN = 3600  # 1 час между повторами одного типа

def _can_send(alert_type: str) -> bool:
    last = _sent.get(alert_type, 0)
    if time.time() - last > ALERT_COOLDOWN:
        _sent[alert_type] = time.time()
        return True
    return False

# ═══════════════════════════════════════════════════════════════
# КАНАЛЫ
# ═══════════════════════════════════════════════════════════════

def send_terminal(level: str, message: str):
    icons = {"INFO": "ℹ️", "WARN": "⚠️", "CRITICAL": "🚨", "OK": "✅"}
    icon = icons.get(level, "📢")
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {icon} [{level}] {message}")

def send_telegram(level: str, message: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    try:
        import urllib.request
        icons = {"INFO": "ℹ️", "WARN": "⚠️", "CRITICAL": "🚨", "OK": "✅"}
        text = f"{icons.get(level,'📢')} *TokenSaver [{level}]*\n{message}"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
        req = urllib.request.Request(url, data.encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        log.info(f"TELEGRAM_SENT level={level}")
        return True
    except Exception as e:
        log.warning(f"TELEGRAM_FAIL: {e}")
        return False

def send_slack(level: str, message: str) -> bool:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook:
        return False
    try:
        import urllib.request
        icons = {"INFO": ":information_source:", "WARN": ":warning:",
                 "CRITICAL": ":rotating_light:", "OK": ":white_check_mark:"}
        payload = {"text": f"{icons.get(level,':mega:')} *[{level}]* {message}"}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(webhook, data, {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
        log.info(f"SLACK_SENT level={level}")
        return True
    except Exception as e:
        log.warning(f"SLACK_FAIL: {e}")
        return False

def send_email(level: str, message: str) -> bool:
    email = os.environ.get("ALERT_EMAIL", "")
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", email)
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not email or not smtp_pass:
        return False
    try:
        msg = MIMEText(message)
        msg["Subject"] = f"[TokenSaver {level}] Alert"
        msg["From"] = smtp_user
        msg["To"] = email
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, [email], msg.as_string())
        log.info(f"EMAIL_SENT level={level} to={email}")
        return True
    except Exception as e:
        log.warning(f"EMAIL_FAIL: {e}")
        return False

# ═══════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ
# ═══════════════════════════════════════════════════════════════

def alert(level: str, message: str, alert_type: str = None):
    """Отправить алерт во все настроенные каналы."""
    if alert_type and not _can_send(alert_type):
        return  # cooldown
    send_terminal(level, message)
    send_telegram(level, message)
    send_slack(level, message)
    if level == "CRITICAL":
        send_email(level, message)

# ═══════════════════════════════════════════════════════════════
# МОНИТОРИНГ МЕТРИК
# ═══════════════════════════════════════════════════════════════

def get_stats() -> dict:
    """Получить статистику из tokensaver.db."""
    db_path = TS_DIR / "tokensaver.db"
    if not db_path.exists():
        return {}
    try:
        db = sqlite3.connect(str(db_path))
        row = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(msg_count),0), COALESCE(SUM(cost_total),0) "
            "FROM sessions WHERE updated_at>?",
            (time.time() - 86400,)
        ).fetchone()
        db.close()
        return {
            "active_sessions": row[0] or 0,
            "total_msgs": row[1] or 0,
            "cost_24h": round(row[2] or 0, 5),
        }
    except Exception as e:
        log.warning(f"DB_READ_FAIL: {e}")
        return {}

def check_and_alert():
    """Проверить метрики и отправить алерты если нужно."""
    # Проверить Redis
    try:
        import redis as r
        c = r.Redis(host="localhost", port=6379, socket_timeout=1)
        c.ping()
    except Exception:
        alert("WARN", "Redis недоступен — кэш работает только in-memory",
              alert_type="redis_down")

    # Проверить tokensaver сервер
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:4000/health", timeout=2)
    except Exception:
        alert("WARN", "TokenSaver сервер недоступен на :4000",
              alert_type="server_down")
        return

    # Проверить стоимость за 24h
    stats = get_stats()
    cost = stats.get("cost_24h", 0)
    if cost >= THRESHOLDS["critical_usd"]:
        alert("CRITICAL",
              f"💸 Расход за 24h: ${cost:.4f} — превышен CRITICAL лимит ${THRESHOLDS['critical_usd']}",
              alert_type="cost_critical")
    elif cost >= THRESHOLDS["warn_usd"]:
        alert("WARN",
              f"💰 Расход за 24h: ${cost:.4f} — превышен WARN лимит ${THRESHOLDS['warn_usd']}",
              alert_type="cost_warn")

def run_daemon(interval: int = 300):
    """Фоновый мониторинг каждые N секунд."""
    print(f"🔔 Alerts daemon запущен (интервал: {interval}s)")
    print(f"   Лимиты: WARN=${THRESHOLDS['warn_usd']} / CRITICAL=${THRESHOLDS['critical_usd']}")
    print(f"   Telegram: {'✅' if os.environ.get('TELEGRAM_BOT_TOKEN') else '⚠️ не настроен'}")
    print(f"   Slack:    {'✅' if os.environ.get('SLACK_WEBHOOK_URL') else '⚠️ не настроен'}")
    print(f"   Email:    {'✅' if os.environ.get('SMTP_PASS') else '⚠️ не настроен'}")
    while True:
        try:
            check_and_alert()
        except Exception as e:
            log.error(f"DAEMON_ERROR: {e}")
        time.sleep(interval)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", action="store_true", help="Фоновый мониторинг")
    ap.add_argument("--interval", type=int, default=300, help="Интервал в секундах")
    ap.add_argument("--test", action="store_true", help="Тест всех каналов")
    args = ap.parse_args()

    if args.test:
        print("🧪 Тест каналов алертов...")
        alert("INFO",  "✅ Тест канала INFO")
        alert("WARN",  "⚠️ Тест канала WARN")
        alert("CRITICAL", "🚨 Тест канала CRITICAL")
    elif args.daemon:
        run_daemon(args.interval)
    else:
        check_and_alert()
