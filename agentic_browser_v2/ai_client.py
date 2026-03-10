# ─────────────────────────── AI Communication ───────────────────────────

import time
import requests


def send_prompt(messages):
    """Send messages to local proxy API with conversation-style messages."""
    url = "http://localhost:8000/v1/chat/completions"
    new_chat_url = "http://localhost:8000/v1/chat/new"
    payload = {
        "model": "glm-4.7",
        "messages": messages,
        "stream": False
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 5-minute timeout to allow GLM-4.7 enough time for complex queries
            response = requests.post(url, json=payload, timeout=300)
            if response.status_code == 200:
                data = response.json()
                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"].get("content", "")
            print(f"  ⚠ API Error {response.status_code}: {response.text[:200]}")
        except Exception as e:
            print(f"  ⚠ Connection error/timeout: {e}")
            
        if attempt < max_retries - 1:
            print(f"  🔄 Retrying (attempt {attempt + 2}/{max_retries}). Starting new GLM session...")
            try:
                requests.post(new_chat_url, timeout=30)
                time.sleep(2)
            except Exception as e:
                print(f"  ⚠ Failed to reset chat: {e}")
                
    return ""
