import os, json, random, hashlib
from typing import List, Dict, Any
from pathlib import Path
import yaml

RND = random.Random(42)

def load_prompts(path="planner/prompts.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def render(tmpl: str, **kv) -> str:
    out = tmpl
    for k,v in kv.items():
        out = out.replace("{{"+k+"}}", v if isinstance(v,str) else json.dumps(v, ensure_ascii=False))
    return out

def jdump(path: str, data: Any):
    Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def choose_k(seq, k):
    seq = list(seq)
    RND.shuffle(seq)
    return seq[:k]

def normalize_bullets(bullets: List[str]) -> List[str]:
    items = [b.strip() for b in bullets if b and b.strip()]
    if len(items) < 3:
        items += [f"Point {i}" for i in range(1, 4-len(items))]
    if len(items) > 7:
        items = items[:7]
    return items

def uid_from(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
