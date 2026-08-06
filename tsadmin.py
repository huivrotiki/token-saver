#!/usr/bin/env python3
"""tsadmin — TokenSaver admin CLI"""
import sys

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

BASE = "http://localhost:4000"


def status():
    try:
        h = requests.get(f"{BASE}/health", timeout=2).json()
        s = requests.get(f"{BASE}/stats", timeout=2).json()
    except Exception as e:
        print(f"❌  TokenSaver offline: {e}")
        return
    print(f"✅  TokenSaver  v{h.get('version','?')}  device={h.get('device_id','?')}")
    print(f"    Redis: {'✅' if h.get('redis') else '⚠️  off'}  "
          f"Embed: {'✅' if h.get('embed_model') else '⚠️  off'}  "
          f"Sessions active: {h.get('sessions_active', 0)}")
    agents  = s.get("agents_tracked", 0)
    cache   = s.get("cache_entries", 0)
    l1      = s.get("l1_size", 0)
    total_s = s.get("total_sessions", 0)
    print(f"    Cache entries: {cache}  L1: {l1}  Sessions: {total_s}  Agents tracked: {agents}")


def help_():
    print("Usage: tsadmin [status]")


cmds = {"status": status, "--help": help_, "-h": help_}
cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
cmds.get(cmd, lambda: (print(f"Unknown command: {cmd}"), help_()))()
