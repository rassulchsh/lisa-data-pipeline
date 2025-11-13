import json, glob

def slide_mix(state):
    mc = state.get("mix_counts", {})
    total = sum(mc.values()) or 1
    return {k: round(v*100/total, 1) for k, v in mc.items()}

def main():
    paths = glob.glob("dataset/dialogs/**/processed/*.json", recursive=True)
    if not paths:
        print("No processed dialogs found.")
        return

    turns = 0
    ok = 0
    langs = {"de":0, "en":0}
    ops = {}

    for p in paths:
        dialog = json.load(open(p))
        for t in dialog:
            if t["role"] == "user":
                langs[t["lang"]] = langs.get(t["lang"], 0) + 1
            if t["role"] != "assistant": 
                continue
            for tc in t.get("tool_calls", []):
                ops[tc["name"]] = ops.get(tc["name"], 0) + 1
            if "validation" in t:
                turns += 1
                ok += 1 if t["validation"]["ok"] else 0

    print(f"Dialogs: {len(paths)}")
    print(f"Assistant turns with validation: {turns} | OK: {ok} ({ok*100/max(1,turns):.1f}%)")
    print("Language balance (user turns):", langs)
    print("Operation coverage:", ops)
    
    last = json.load(open(paths[-1]))
    last_state = next((t.get('state_after') for t in reversed(last) if 'state_after' in t), None)
    if last_state:
        print("Sample final slide mix (%):", slide_mix(last_state))

if __name__ == "__main__":
    main()
