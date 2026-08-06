import requests
import json
import time

url = "http://localhost:4000/v1/chat/completions"
models = ["gemini-flash-lite", "gemini-flash", "google-ai-pro"]
messages = [{"role": "user", "content": "Напиши подробный технический обзор на 5 абзацев о квантовой запутанности, включая уравнения и объяснения."}]

print(f"{'Модель':<20} | {'Фактическая модель':<35} | {'Статус':<15} | {'Экономия (USD)':<15}")
print("-" * 90)

for model in models:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 500
    }
    
    # First request
    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json", "X-Session-Id": f"test-{model}"})
    if resp.status_code == 200:
        data = resp.json()
        stats = data.get("tokensaver_stats", {})
        actual_model = str(stats.get("model", "unknown"))
        saved_usd = float(stats.get("saved_usd") or 0.0)
        cache_status = "Кэш: " + str(stats.get("cached", False))
        print(f"{model:<20} | {actual_model:<35} | {cache_status:<15} | ${saved_usd:.6f}")
    else:
         print(f"{model:<20} | Error {resp.status_code}")

print("\n--- Проверка срабатывания кэша (повторный запрос) ---")
for model in models:
    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json", "X-Session-Id": f"test-{model}"})
    if resp.status_code == 200:
        data = resp.json()
        stats = data.get("tokensaver_stats", {})
        actual_model = str(stats.get("model", "unknown"))
        saved_usd = float(stats.get("saved_usd") or 0.0)
        cache_status = "Кэш: " + str(stats.get("cached", False))
        print(f"{model:<20} | {actual_model:<35} | {cache_status:<15} | ${saved_usd:.6f}")
