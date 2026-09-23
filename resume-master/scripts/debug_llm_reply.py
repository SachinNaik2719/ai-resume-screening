"""Cheap LLM probe: one tiny structured call per model until one works."""
import sys

sys.path.insert(0, "src")

import httpx

from resume_screener.config import load_settings

settings = load_settings()
url = settings.llm_base_url.rstrip("/") + "/chat/completions"

# Ordered by preference: capable flash models, then lite variants.
MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
]

for model in MODELS:
    payload = {
        "model": model,
        "messages": [{"role": "user",
                      "content": 'Reply with only this JSON: {"ok": true}'}],
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }
    try:
        response = httpx.post(
            url,
            headers={"Authorization": "Bearer " + settings.llm_api_key,
                     "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"].get("content")
            print(f"{model:26s} -> 200 | {str(content)[:60]!r}")
            print(f"WORKING_MODEL={model}")
            break
        text = response.text
        hint = ""
        if "quotaId" in text:
            start = text.find('"quotaId"')
            hint = text[start:start + 100].replace("\\n", " ")
        elif "Please retry in" in text:
            hint = "minute-limit, retry in " + text.split("Please retry in")[1][:30]
        elif "message" in text:
            start = text.find('"message"')
            hint = text[start:start + 140]
        print(f"{model:26s} -> {response.status_code} | {hint}")
    except Exception as exc:  # noqa: BLE001
        print(f"{model:26s} -> ERR {type(exc).__name__}")
