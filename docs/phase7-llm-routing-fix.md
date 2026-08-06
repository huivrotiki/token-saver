# Phase 7 — LLM Routing Fix

## Context

TokenSaver proxy (:4000) is live but Claude Code CLI can't use it:
- Proxy exposes `/v1/chat/completions` (OpenAI format)
- Claude Code SDK requires `/v1/messages` (Anthropic format)
- Groq breaks Claude Code with 128-tool limit
- `tsadmin` status CLI doesn't exist yet

## Task 1 — `/v1/messages` adapter

File: `~/token-saver/tokensaver.py`

```python
@app.route("/v1/messages", methods=["POST"])
def anthropic_messages():
    """Anthropic SDK adapter: translates /v1/messages ↔ /v1/chat/completions"""
    body = request.get_json(force=True)
    
    messages = []
    if body.get("system"):
        messages.append({"role": "system", "content": body["system"]})
    for m in body.get("messages", []):
        content = m["content"]
        if isinstance(content, list):
            content = " ".join(
                b.get("text", "") for b in content if b.get("type") == "text"
            )
        messages.append({"role": m["role"], "content": content})
    
    # Groq 128-tools guard
    tools = body.get("tools", [])
    model = body.get("model", "")
    if "groq" in model.lower() and len(tools) > 128:
        tools = tools[:128]
    
    openai_req = {
        "model": body.get("model", "claude-sonnet"),
        "messages": messages,
        "max_tokens": body.get("max_tokens", 4096),
        "stream": body.get("stream", False),
    }
    if tools:
        openai_req["tools"] = [_convert_anthropic_tool(t) for t in tools]
    
    result = _forward_openai_request(openai_req, request.headers)
    
    if body.get("stream"):
        return result
    
    oai = result.get_json()
    choice = oai["choices"][0]["message"]
    return jsonify({
        "id": oai.get("id", "msg_tokensaver"),
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": choice["content"]}],
        "model": oai.get("model", openai_req["model"]),
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": oai.get("usage", {}).get("prompt_tokens", 0),
            "output_tokens": oai.get("usage", {}).get("completion_tokens", 0),
        },
    })
```

## Task 2 — Wire Claude Code

Add to `~/.claude/settings.json`:
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:4000"
  }
}
```

Restart:
```bash
pkill -f tokensaver.py && cd ~/token-saver && python3 tokensaver.py &
```

## Task 3 — tsadmin CLI

File: `~/token-saver/tsadmin.py`

```python
#!/usr/bin/env python3
"""tsadmin — TokenSaver admin CLI"""
import sys, json
try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

BASE = "http://localhost:4000"

def status():
    try:
        h = requests.get(f"{BASE}/health", timeout=2).json()
        s = requests.get(f"{BASE}/stats", timeout=2).json()
    except Exception as e:
        print(f"❌ TokenSaver offline: {e}"); return
    print(f"✅ TokenSaver  v{h.get('version','?')}  redis={h.get('redis')}  embed={h.get('embed_model')}")
    print(f"   Sessions: {h.get('sessions_active',0)}  Cost: ${s.get('total_cost',0):.4f}  Msgs: {s.get('total_msgs',0)}")
    print(f"   Cache entries: {s.get('cache_entries',0)}  L1 size: {s.get('l1_size',0)}")

cmds = {"status": status}
cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
cmds.get(cmd, lambda: print(f"Unknown: {cmd}. Available: {list(cmds.keys())}"))()
```

Install:
```bash
chmod +x ~/token-saver/tsadmin.py
ln -sf ~/token-saver/tsadmin.py /opt/homebrew/bin/tsadmin
```

## Execution Order

1. Extract `_forward_openai_request()` helper from existing `/v1/chat/completions`
2. Add `/v1/messages` route + Groq guard
3. Restart TokenSaver
4. Add `ANTHROPIC_BASE_URL` to `~/.claude/settings.json`
5. Create `tsadmin.py` + symlink
6. Verify all 3 DoD items

## Verification

```bash
# 1. Anthropic endpoint live
curl -s -X POST http://localhost:4000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet","messages":[{"role":"user","content":"ping"}],"max_tokens":10}' \
  | jq .type  # → "message"

# 2. Claude Code routes through proxy
ANTHROPIC_BASE_URL=http://localhost:4000 claude --print "say hi"

# 3. tsadmin works
tsadmin status

# 4. Stats increment after Claude Code call
tsadmin status  # cost/msgs should increase
```

## DoD Checklist

- [ ] `/v1/messages` returns `{"type": "message"}`
- [ ] Claude Code CLI routes through proxy
- [ ] Groq 128-tools guard active
- [ ] `tsadmin status` shows live stats
- [ ] ROADMAP.md Phase 7 checkboxes green
