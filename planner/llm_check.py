from __future__ import annotations
import os, json, re
from typing import Dict, Any
from tenacity import retry, wait_exponential, stop_after_attempt
from openai import OpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
API_KEY = os.environ.get("OPENAI_API_KEY")
if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set. Put it in .env or your shell env.")

client = OpenAI(api_key=API_KEY)

JSON_HINT_SYSTEM = (
    "You are a strict JSON generator. "
    "Always return ONLY valid JSON (no prose, no markdown). "
    "If unsure, return an empty JSON object {}. The word json is intentionally present."
)

def _parse_last_json_blob(text: str) -> Dict[str, Any]:
    i = text.rfind("{")
    j = text.rfind("}")
    if i != -1 and j != -1 and j > i:
        return json.loads(text[i:j+1])
    return {}

@retry(wait=wait_exponential(min=1, max=8), stop=stop_after_attempt(3))
def llm_call(prompt: str, max_tokens: int = 700) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": JSON_HINT_SYSTEM},
        {"role": "user", "content": prompt}
    ]
    try:
        chat = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            response_format={"type": "json_object"},  
            max_tokens=max_tokens,
        )
        content = chat.choices[0].message.content or "{}"
        return json.loads(content)
    except Exception as e:
        pass

    chat = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=max_tokens,
    )
    content = chat.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except Exception:
        return _parse_last_json_blob(content)
