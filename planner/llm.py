import os, json, time
from typing import Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import OpenAI
from openai import BadRequestError, APITimeoutError, APIError

MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def _extract_json(text: str) -> Dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end+1])
    return json.loads(text)  

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=6),
    retry=retry_if_exception_type((BadRequestError, APITimeoutError, APIError, ValueError, json.JSONDecodeError))
)
def llm_call(prompt: str, max_tokens: int = 800) -> Dict[str, Any]:
    sys = "You must answer with STRICT, VALID JSON (json). No prose."
    chat = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":sys},
            {"role":"user","content":prompt}
        ],
        temperature=0.3,
        response_format={"type":"json_object"},
        max_tokens=max_tokens
    )
    text = chat.choices[0].message.content or "{}"
    return _extract_json(text)
