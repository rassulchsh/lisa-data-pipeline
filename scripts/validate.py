import json, sys, glob, os
from jsonschema import Draft7Validator, RefResolver

SCHEMA_DIR = "dataset/schema"

def deep_drop_nones(x):
    if isinstance(x, dict):
        return {k: deep_drop_nones(v) for k, v in x.items() if v is not None}
    if isinstance(x, list):
        return [deep_drop_nones(v) for v in x if v is not None]
    return x

def load_schemas():
    with open(os.path.join(SCHEMA_DIR, "deck_state.schema.json"), "r", encoding="utf-8") as f:
        deck_schema = json.load(f)
    with open(os.path.join(SCHEMA_DIR, "turn.schema.json"), "r", encoding="utf-8") as f:
        turn_schema = json.load(f)
    store = {
        "deck_state.schema.json": deck_schema,
    }
    resolver = RefResolver.from_schema(turn_schema, store=store)
    return Draft7Validator(turn_schema, resolver=resolver)

def validate_file(path: str, validator: Draft7Validator):
    data = json.load(open(path, "r", encoding="utf-8"))
    data = deep_drop_nones(data)  # sanitize
    errs = []
    if isinstance(data, list):
        for i, turn in enumerate(data):
            for e in validator.iter_errors(turn):
                errs.append(f"turn#{i}: {e.message}")
    else:
        errs.append("Dialog must be a JSON array of turns")
    return errs

def main():
    validator = load_schemas()
    paths = []
    paths += glob.glob("dataset/dialogs/*/drafts/*.json", recursive=True)
    paths += glob.glob("dataset/dialogs/*/processed/*.json", recursive=True)

    if not paths:
        print("No draft/processed dialogs found to validate.")
        sys.exit(0)

    errors = []
    for p in paths:
        es = validate_file(p, validator)
        if es:
            errors.append((p, es))

    if errors:
        for p, es in errors:
            print(f"[FAIL] {p}")
            for m in es:
                print("  -", m)
        sys.exit(1)

    print("OK: all draft/processed dialogs pass Draft-07 schemas.")

if __name__ == "__main__":
    main()
