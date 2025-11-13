from __future__ import annotations
import json, os, re, uuid, argparse
from typing import Any, Dict, List, Optional, Tuple

SUPPORTED = {
    "api.create_slide",
    "api.add_bullet_points",
    "api.add_picture_with_caption",
    "api.change_layout",
    "api.edit_text", 
}

LAYOUT_MAP = {
    "title": "TitleOnly",                 
    "title only": "TitleOnly",
    "section header": "TitleOnly",
    "title and content": "TitleBullets",
    "title & bullets": "TitleBullets",
    "content with title": "TitleBullets",
    "comparison": "TwoColumn",
    "two column": "TwoColumn",
    "two columns": "TwoColumn",
    "split left image": "SplitLeftImage",
    "split right image": "SplitRightImage",
    "split (left)": "SplitLeftImage",
    "split (right)": "SplitRightImage",
    "picture with caption": "SplitRightImage",
    "image only": "FullImage",
    "full image": "FullImage",
    "quote": "Quote",
    "blank": "TitleOnly",
}

def to_layout(name: Optional[str]) -> str:
    if not name: return "TitleBullets"
    n = name.strip().lower()
    if n in LAYOUT_MAP: return LAYOUT_MAP[n]
    if "full" in n and "image" in n: return "FullImage"
    if "split" in n and "left" in n: return "SplitLeftImage"
    if "split" in n and "right" in n: return "SplitRightImage"
    if "two" in n and "column" in n: return "TwoColumn"
    if "title" in n and "content" in n: return "TitleBullets"
    if "title only" in n or "section" in n or n == "title": return "TitleOnly"
    if "quote" in n: return "Quote"
    return "TitleBullets"

def user_turn(text: str, lang: str) -> Dict[str, Any]:
    return {"role": "user", "lang": lang, "text": text}

def tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    return {"role": "assistant", "tool_calls": [{"name": name, "args": args}]}

def norm_points(points: Optional[List[str]], numbered: Optional[bool]) -> Dict[str, Any]:
    items = list(points or [])
    if len(items) < 3:
        items += [f"Point {i}" for i in range(1, 4 - len(items))]
    if len(items) > 7:
        items = items[:7]
    typ = "numbered" if numbered else "bullets"
    return {"type": typ, "items": items}

TOOL_BLOCKS_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL | re.IGNORECASE)
API_NAME_RE    = re.compile(r"api\.(\w+)\s*\(", re.IGNORECASE)
PAREN_RE       = re.compile(r"\((.*)\)", re.DOTALL)

def extract_kw(arg_str: str, key: str) -> Optional[str]:
    m = re.search(rf"{re.escape(key)}\s*=\s*['\"](.*?)['\"]", arg_str)
    return m.group(1) if m else None

def extract_bool(arg_str: str, key: str) -> Optional[bool]:
    m = re.search(rf"{re.escape(key)}\s*=\s*(True|False)", arg_str, re.IGNORECASE)
    if not m: return None
    return m.group(1).lower() == "true"

def extract_int(arg_str: str, key: str) -> Optional[int]:
    m = re.search(rf"{re.escape(key)}\s*=\s*(\d+)", arg_str)
    return int(m.group(1)) if m else None

def extract_points_list(arg_str: str) -> List[str]:
    m = re.search(r"points\s*=\s*\[(.*?)\]", arg_str, re.DOTALL | re.IGNORECASE)
    if not m: return []
    inner = m.group(1)
    vals = re.findall(r"['\"](.*?)['\"]", inner)
    return [v for v in vals if v.strip()]

def parse_positional_args(arg_str: str) -> List[str]:
    parts: List[str] = []
    buf = []
    in_quote = None
    i = 0
    while i < len(arg_str):
        ch = arg_str[i]
        if in_quote:
            buf.append(ch)
            if ch == in_quote:
                in_quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == ",":
            parts.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return parts

def parse_tool_blocks_from_text(text: str) -> List[Dict[str, Any]]:
    """Extract ALL tool calls from a text blob."""
    out: List[Dict[str, Any]] = []
    for block in TOOL_BLOCKS_RE.findall(text or ""):
        mn = API_NAME_RE.search(block)
        if not mn:
            continue
        api_name = f"api.{mn.group(1)}"
        pm = PAREN_RE.search(block)
        arg_str = pm.group(1) if pm else ""
        title    = extract_kw(arg_str, "title")
        subtitle = extract_kw(arg_str, "subtitle")
        layout   = extract_kw(arg_str, "layout")
        name     = extract_kw(arg_str, "name")  
        prompt   = extract_kw(arg_str, "prompt")
        caption  = extract_kw(arg_str, "caption") or extract_kw(arg_str, "text")
        slide_no = extract_int(arg_str, "slide_no")
        numbered = extract_bool(arg_str, "numbered")
        points   = extract_points_list(arg_str)

        args: Dict[str, Any] = {}

        if api_name == "api.create_slide":
            args = {"title": title, "subtitle": subtitle, "layout": layout}

        elif api_name == "api.add_bullet_points":
            args = {"slide_no": slide_no, "points": points, "numbered": bool(numbered)}

        elif api_name == "api.add_picture_with_caption":
            args = {"slide_no": slide_no, "prompt": prompt, "caption": caption}

        elif api_name == "api.change_layout":
            args = {"slide_no": slide_no, "name": name or layout}

        elif api_name == "api.edit_text":
            idx = extract_int(arg_str, "index")
            txt = extract_kw(arg_str, "text")
            sn  = slide_no
            if sn is None or idx is None or txt is None:
                parts = parse_positional_args(arg_str)
                try:
                    if sn is None and len(parts) > 0:
                        sn = int(re.sub(r"[^\d]", "", parts[0])) if re.search(r"\d", parts[0]) else None
                    if idx is None and len(parts) > 1:
                        idx = int(re.sub(r"[^\d]", "", parts[1])) if re.search(r"\d", parts[1]) else None
                    if txt is None and len(parts) > 2:
                        txt = parts[2].strip().strip("'").strip('"')
                except Exception:
                    pass
            args = {"slide_no": sn, "index": idx, "text": txt}

        else:
            continue

        out.append({"name": api_name, "args": args})
    return out

def seed_iter_from_file(payload: Any) -> List[Dict[str, Any]]:
    ops: List[Dict[str, Any]] = []
    if isinstance(payload, dict) and "conversations" in payload and isinstance(payload["conversations"], list):
        for item in payload["conversations"]:
            text = item.get("text", "") if isinstance(item, dict) else ""
            ops.extend(parse_tool_blocks_from_text(text))
    elif isinstance(payload, list):
        for s in payload:
            if isinstance(s, dict) and "text" in s:
                ops.extend(parse_tool_blocks_from_text(s["text"]))
    return ops

def op_to_turns(seed_op: Dict[str, Any], default_slide_no: int, lang_user: str = "en") -> List[Dict[str, Any]]:
    turns: List[Dict[str, Any]] = []
    name = seed_op.get("name") or ""
    args = seed_op.get("args") or {}
    slide_no = args.get("slide_no") or default_slide_no

    if name == "api.create_slide":
        title = args.get("title") or "New Slide"
        subtitle = args.get("subtitle")
        layout = to_layout(args.get("layout"))
        turns.append(user_turn(f"Create a slide titled '{title}' using a suitable layout.", lang_user))
        turns.append(tool_call("insert_slide_after", {
            "after_slide_no": 1,   
            "title": title,
            "layout": layout
        }))
        if subtitle:
            turns.append(tool_call("edit_content", {
                "slide_no": 2,
                "type": "text",
                "text": subtitle
            }))

    elif name == "api.add_bullet_points":
        points = args.get("points") or []
        numbered = bool(args.get("numbered"))
        blk = norm_points(points, numbered)
        turns.append(user_turn(f"Add {'numbered' if numbered else 'bulleted'} points to slide {slide_no}.", lang_user))
        turns.append(tool_call("edit_content", {
            "slide_no": slide_no,
            "type": blk["type"],
            "items": blk["items"]
        }))

    elif name == "api.add_picture_with_caption":
        prompt = args.get("prompt") or "Relevant illustration"
        caption = args.get("caption")
        turns.append(user_turn(f"Add an illustrative image to slide {slide_no}.", lang_user))
        turns.append(tool_call("set_image", {
            "slide_no": slide_no,
            "prompt": prompt
        }))
        if caption:
            turns.append(tool_call("edit_content", {
                "slide_no": slide_no,
                "type": "text",
                "text": caption
            }))

    elif name == "api.change_layout":
        layout = to_layout(args.get("name"))
        turns.append(user_turn(f"Change layout of slide {slide_no} to {layout}.", lang_user))
        turns.append(tool_call("set_layout", {
            "slide_no": slide_no,
            "layout": layout
        }))

    elif name == "api.edit_text":
        idx = args.get("index")
        txt = args.get("text")
        if idx == 0:
            turns.append(user_turn(f"Change the title of slide {slide_no}.", lang_user))
            turns.append(tool_call("edit_slide", {
                "slide_no": slide_no,
                "title": txt or "Updated Title"
            }))
        else:
            turns.append(user_turn(f"Update the text content on slide {slide_no}.", lang_user))
            turns.append(tool_call("edit_content", {
                "slide_no": slide_no,
                "type": "text",
                "text": txt or "Updated text"
            }))

    else:
        return []

    return turns

def build_dialog_from_chunk(chunk: List[Dict[str, Any]],
                            deck_lang: str,
                            deck_title: str,
                            template: str,
                            include_agenda: bool = True,
                            lang_user: str = "en") -> List[Dict[str, Any]]:
    dialog: List[Dict[str, Any]] = []
    title_line = f"Create a {'German' if deck_lang=='de' else 'English'} presentation titled '{deck_title}'."
    dialog.append(user_turn(title_line, lang_user))
    dialog.append(tool_call("create_presentation", {
        "language": deck_lang,
        "template": template,
        "title": deck_title
    }))

    if include_agenda:
        agenda = ["Introduction", "Core Concepts", "Examples", "Summary"] \
                 if deck_lang == "en" else ["Einführung", "Grundlagen", "Beispiele", "Zusammenfassung"]
        dialog.append(user_turn(f"Set the agenda with {len(agenda)} items.", lang_user))
        dialog.append(tool_call("set_agenda", {"items": agenda}))

    default_slide_no = 2  
    for op in chunk:
        if op.get("name") not in SUPPORTED:
            continue
        dialog.extend(op_to_turns(op, default_slide_no=default_slide_no, lang_user=lang_user))
    dialog.append(user_turn("Show the slide index.", lang_user))
    dialog.append(tool_call("get_slide_index", {}))
    return dialog

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", default="dataset/dialogs/seeds/formatted_data.json")
    ap.add_argument("--outdir", default="dataset/dialogs/en/drafts")
    ap.add_argument("--lang", default="en", choices=["en","de"], help="Deck target language")
    ap.add_argument("--title", default="Seed Deck")
    ap.add_argument("--template", default="Minimal")
    ap.add_argument("--max-dialogs", type=int, default=3)
    ap.add_argument("--max-ops-per-dialog", type=int, default=12)
    args = ap.parse_args()

    if not os.path.isfile(args.infile):
        raise SystemExit(f"Seed file not found: {args.infile}")

    os.makedirs(args.outdir, exist_ok=True)

    try:
        payload = json.load(open(args.infile, "r", encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"Failed to read JSON: {e}")

    ops = seed_iter_from_file(payload)
    ops = [op for op in ops if op.get("name") in SUPPORTED]

    print(f"Loaded seeds (conversations): {len(payload.get('conversations', [])) if isinstance(payload, dict) else 'n/a'}")
    print(f"Supported ops found: {len(ops)}")

    if not ops:
        first = payload.get("conversations", [{}])[0] if isinstance(payload, dict) else (payload[0] if isinstance(payload, list) and payload else {})
        print("No supported operations found. First item preview:\n", str(first)[:800])
        return

    dialogs_written = 0
    i = 0
    while dialogs_written < args.max_dialogs and i < len(ops):
        chunk = ops[i:i + args.max_ops_per_dialog]
        dialog = build_dialog_from_chunk(
            chunk=chunk,
            deck_lang=args.lang,
            deck_title=(args.title if dialogs_written == 0 else f"{args.title} {dialogs_written+1}"),
            template=args.template,
            include_agenda=True,
            lang_user="en"
        )
        outname = f"{uuid.uuid4().hex[:8]}_{args.title.lower().replace(' ', '_')}.json"
        outpath = os.path.join(args.outdir, outname)
        with open(outpath, "w", encoding="utf-8") as f:
            json.dump(dialog, f, ensure_ascii=False, indent=2)
        print("Wrote", outpath)

        dialogs_written += 1
        i += args.max_ops_per_dialog

    if dialogs_written == 0:
        print("No dialogs written — check seed structure and SUPPORTED mapping.")

if __name__ == "__main__":
    main()
