from typing import List, Iterable

VALID_LAYOUTS = {
    "TitleOnly",
    "TitleBullets",
    "SplitLeftImage",
    "SplitRightImage",
    "FullImage",
    "TwoColumn",
    "Quote",
}

def ensure_layout(layout: str) -> str:
    if layout not in VALID_LAYOUTS:
        raise ValueError(f"Unsupported layout: {layout}")
    return layout

def enforce_list_length(items: List[str]) -> List[List[str]]:
    n = len(items)
    if n < 3:
        raise ValueError("Too few items (<3).")
    if n <= 7:
        return [items]
    chunk_size = 5
    return [items[i:i+chunk_size] for i in range(0, n, chunk_size)]

def image_size_for_layout(layout: str) -> str:
    if layout == "FullImage":
        return "512x768"
    if layout in {"SplitLeftImage", "SplitRightImage"}:
        return "768x512"
    return "768x512"

def renumber(slides: Iterable):
    for i, s in enumerate(slides, start=1):
        s.no = i
