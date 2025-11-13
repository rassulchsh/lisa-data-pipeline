import os, json, argparse, re
from pathlib import Path

def tokenize(s: str):
    return set(re.findall(r"[a-z0-9]+", s.lower()))

def signature(dialog):
    toks = set()
    for t in dialog:
        if t.get("role") == "assistant":
            for tc in t.get("tool_calls", []):
                args = tc.get("args", {})
                if "title" in args:
                    toks |= tokenize(args["title"])
                if "items" in args and isinstance(args["items"], list):
                    for it in args["items"]:
                        toks |= tokenize(str(it))
    return toks

def jaccard(a, b):
    if not a and not b: return 1.0
    return len(a & b) / max(1, len(a | b))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", default="dataset/dialogs/en/drafts")
    ap.add_argument("--outdir", default="dataset/dialogs/en/drafts_dedup")
    ap.add_argument("--threshold", type=float, default=0.85)
    args = ap.parse_args()

    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    sigs = []
    kept = 0
    for fn in sorted(os.listdir(args.indir)):
        if not fn.endswith(".json"): continue
        path = os.path.join(args.indir, fn)
        try:
            d = json.load(open(path,"r",encoding="utf-8"))
        except Exception:
            continue
        sig = signature(d)
        if all(jaccard(sig, s) < args.threshold for s in sigs):
            # keep
            out = os.path.join(args.outdir, fn)
            json.dump(d, open(out,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
            sigs.append(sig)
            kept += 1
    print(f"Kept {kept} dialogs into {args.outdir}")

if __name__ == "__main__":
    main()
