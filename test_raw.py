import requests
import json
import os

url = "http://localhost:4000/v1/chat/completions"
payload = {
    "model": "google-ai-pro",
    "messages": [{"role": "user", "content": "hello"}],
    "max_tokens": 10
}
resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
print("Status Code:", resp.status_code)
print("Response:", resp.text)
