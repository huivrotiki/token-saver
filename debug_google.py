import requests
import json

url = "http://localhost:4000/v1/chat/completions"
payload = {
    "model": "google-ai-pro",
    "messages": [{"role": "user", "content": "Расскажи про космос в 2 предложениях."}],
    "max_tokens": 100
}
resp = requests.post(url, json=payload, headers={"Content-Type": "application/json", "X-Session-Id": "test-session"})
print("Status Code:", resp.status_code)
print("Headers:", dict(resp.headers))
print("Body:", resp.text)
