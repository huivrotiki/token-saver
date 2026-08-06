import requests
import json
import time

url = "http://localhost:4000/v1/chat/completions"
models = ["gemini-flash-lite", "gemini-flash", "google-ai-pro"]
messages = [{"role": "user", "content": "Расскажи про космос в 2 предложениях."}]

print(f"{'Model':<20} | {'Status':<6} | {'Time (s)':<8} | {'Tokens (In/Out)'}")
print("-" * 65)

for model in models:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 100
    }
    
    start = time.time()
    try:
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json", "X-Session-Id": "test-session"})
        elapsed = time.time() - start
        
        if resp.status_code == 200:
            data = resp.json()
            usage = data.get("usage", {})
            in_t = usage.get("prompt_tokens", 0)
            out_t = usage.get("completion_tokens", 0)
            print(f"{model:<20} | {resp.status_code:<6} | {elapsed:<8.2f} | {in_t}/{out_t}")
            # print headers for debug
            # print("Headers:", resp.headers)
        else:
            print(f"{model:<20} | {resp.status_code:<6} | {elapsed:<8.2f} | Error: {resp.text[:50]}")
    except Exception as e:
         print(f"{model:<20} | ERROR  | -        | {str(e)[:50]}")

print("\n--- Testing Cache (Savings) ---")
# Repeat for the exact same prompt to trigger cache
for model in models:
    start = time.time()
    try:
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json", "X-Session-Id": "test-session"})
        elapsed = time.time() - start
        if resp.status_code == 200:
            data = resp.json()
            usage = data.get("usage", {})
            in_t = usage.get("prompt_tokens", 0)
            out_t = usage.get("completion_tokens", 0)
            saved = resp.headers.get("X-Tokensaver-Saved", "N/A")
            cache_hit = resp.headers.get("X-Cache", "N/A")
            print(f"{model:<20} | Cached: {cache_hit} | Time: {elapsed:.2f}s | Saved Tokens: {saved} | Usage: {in_t}/{out_t}")
    except Exception as e:
        pass

