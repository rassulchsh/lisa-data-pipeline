import os, sys, json, glob, copy, requests

BASE_URL = os.environ.get("MOCK_BASE_URL", "http://127.0.0.1:8000")

def deep_drop_nones(x):
    if isinstance(x, dict):
        return {k: deep_drop_nones(v) for k, v in x.items() if v is not None}
    if isinstance(x, list):
        return [deep_drop_nones(v) for v in x if v is not None]
    return x

def get_index(deck_id):
    r = requests.get(f"{BASE_URL}/get_slide_index", params={"deck_id": deck_id}, timeout=15)
    r.raise_for_status()
    return r.json().get("slide_index", [])

def last_slide_no(deck_id):
    idx = get_index(deck_id)
    return idx[-1]["no"] if idx else 0

def ensure_slide_exists(deck_id, slide_no):
    current_last = last_slide_no(deck_id)
    while current_last < slide_no:
        payload = {
            "deck_id": deck_id,
            "after_slide_no": current_last if current_last >= 1 else 1,
            "title": f"Placeholder {current_last+1}",
            "layout": "TitleOnly"
        }
        r = requests.post(f"{BASE_URL}/insert_slide_after", json=payload, timeout=15)
        r.raise_for_status()
        current_last = last_slide_no(deck_id)

def call_endpoint(name, args):
    path_map = {
        "create_presentation": "/create_presentation",
        "set_agenda": "/set_agenda",
        "insert_slide_after": "/insert_slide_after",
        "edit_slide": "/edit_slide",
        "edit_content": "/edit_content",
        "set_layout": "/set_layout",
        "set_image": "/set_image",
        "reorder_slides": "/reorder_slides",
        "go_to_slide": "/go_to_slide",
        "get_slide_index": "/get_slide_index",
        "export_pptx": "/export_pptx",
    }
    path = path_map[name]
    try:
        if name == "get_slide_index":
            resp = requests.get(f"{BASE_URL}{path}", params=args, timeout=15)
        else:
            resp = requests.post(f"{BASE_URL}{path}", json=args, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError:
        print("\n[HTTP ERROR]", name)
        try: print("URL:", resp.request.url)
        except: pass
        try: print("Payload:", json.dumps(args, ensure_ascii=False))
        except: pass
        try:
            print("Response status:", resp.status_code)
            print("Response body:", resp.text[:2000])
        except: pass
        raise

def check_slide_numbers(state):
    nums = [s["no"] for s in state.get("slides", [])]
    return nums == list(range(1, len(nums)+1))

def check_list_lengths(state):
    ok = True
    for s in state.get("slides", []):
        for b in s.get("content", []):
            if b.get("type") in ("bullets", "numbered"):
                n = len(b.get("items", []))
                ok = ok and (3 <= n <= 7)
    return ok

def image_ok_for_layout(layout, size):
    if not size: return True
    if layout == "FullImage": return size == "512x768"
    if layout in ("SplitLeftImage","SplitRightImage"): return size == "768x512"
    return size in ("768x512","512x768")

def check_image_sizes(state):
    ok = True
    for s in state.get("slides", []):
        img = s.get("image")
        if img:
            ok = ok and image_ok_for_layout(s.get("layout"), img.get("size"))
    return ok

def check_layout_preserve(prev, curr, changed_no):
    if not isinstance(changed_no, int): return True
    try:
        p = next(x for x in prev["slides"] if x["no"] == changed_no)
        c = next(x for x in curr["slides"] if x["no"] == changed_no)
    except StopIteration:
        return False
    return (p.get("content") == c.get("content")) and (("image" not in p) or (c.get("image") is not None))

def approx_mix_ok(state):
    mc = state.get("mix_counts", {})
    total = sum(mc.values()) or 1
    return all(v/total <= 0.85 for v in mc.values())

def process_dialog(path):
    dialog = json.load(open(path, "r", encoding="utf-8"))
    deck_id = None
    prev_state = None

    for turn in dialog:
        if turn.get("role") != "assistant":
            continue
        for tc in turn.get("tool_calls", []):
            args = copy.deepcopy(tc.get("args", {}))

            if tc["name"] != "create_presentation":
                if deck_id:
                    args.setdefault("deck_id", deck_id)
                if tc["name"] == "get_slide_index":
                    args = {"deck_id": deck_id}

            if tc["name"] in {"edit_slide","edit_content","set_layout","set_image"} and deck_id:
                slide_no = args.get("slide_no")
                if isinstance(slide_no, int) and slide_no >= 2:
                    ensure_slide_exists(deck_id, slide_no)

            result = call_endpoint(tc["name"], args)
            diff = {k:v for k,v in result.items() if k!="deck_state"}
            if diff:
                turn.setdefault("tool_result", {})
                turn["tool_result"]["diff"] = diff

            if "deck_state" in result and result["deck_state"] is not None:
                state = result["deck_state"]
                turn.setdefault("tool_result", {})
                turn["tool_result"]["deck_state"] = state
                turn["state_after"] = state

                if not deck_id:
                    deck_id = state["deck_id"]

                checks = {
                    "slide_numbers": check_slide_numbers(state),
                    "list_length_ok": check_list_lengths(state),
                    "image_size_ok": check_image_sizes(state),
                    "layout_preserve_ok": True,
                    "mix_within_bounds": approx_mix_ok(state)
                }
                if tc["name"] == "set_layout" and prev_state is not None:
                    changed_no = args.get("slide_no")
                    checks["layout_preserve_ok"] = check_layout_preserve(prev_state, state, changed_no)

                ok_flags = ["slide_numbers","list_length_ok","image_size_ok","layout_preserve_ok"]
                turn["validation"] = {"ok": all(checks[k] for k in ok_flags), "checks": checks}

                prev_state = state
    dialog = deep_drop_nones(dialog)

    out_path = path.replace("/drafts/", "/processed/")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dialog, f, ensure_ascii=False, indent=2)
    return out_path

def main():
    files = glob.glob("dataset/dialogs/*/drafts/*.json", recursive=True)
    if not files:
        print("No drafts found.")
        sys.exit(0)
    written = [process_dialog(p) for p in files]
    print("Processed ->")
    for w in written:
        print("  ", w)

if __name__ == "__main__":
    main()
