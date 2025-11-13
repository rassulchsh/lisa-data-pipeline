from fastapi import FastAPI, HTTPException
from typing import List
import uuid

from .state import DeckState, Slide, Image, store
from .rules import ensure_layout, enforce_list_length, image_size_for_layout, renumber

app = FastAPI(title="LISA Slides Mock Tools")


def must_state(deck_id: str) -> DeckState:
    if deck_id not in store:
        raise HTTPException(404, "Unknown deck_id")
    return store[deck_id]


@app.post("/create_presentation")
def create_presentation(payload: dict):
    language = payload.get("language", "de")
    template = payload.get("template", "Minimal")
    title = payload.get("title", "Titel")
    deck_id = str(uuid.uuid4())
    first = Slide(id=str(uuid.uuid4()), no=1, title=title, layout="TitleOnly")
    state = DeckState(deck_id=deck_id, language=language, template=template, slides=[first])
    state.tally_mix()
    store[deck_id] = state
    return {"diff": {"created": True}, "deck_state": state.model_dump()}

@app.post("/set_agenda")
def set_agenda(payload: dict):
    state = must_state(payload["deck_id"])
    agenda: List[str] = payload.get("items", [])
    state.agenda = agenda
    state.tally_mix()
    return {"diff": {"agenda_set": len(agenda)}, "deck_state": state.model_dump()}

@app.get("/get_slide_index")
def get_slide_index(deck_id: str):
    state = must_state(deck_id)
    state.refresh_slide_index()
    return {"slide_index": state.slide_index}

@app.post("/go_to_slide")
def go_to_slide(payload: dict):
    state = must_state(payload["deck_id"])
    slide = state.get_by_no(payload["slide_no"])
    return {"current_slide": {"no": slide.no, "title": slide.title, "layout": slide.layout}}

@app.post("/insert_slide_after")
def insert_slide_after(payload: dict):
    state = must_state(payload["deck_id"])
    after = payload["after_slide_no"]
    title = payload.get("title", "New Slide")
    layout = ensure_layout(payload.get("layout", "TitleBullets"))

    list_type = payload.get("list_type")        
    n_items = payload.get("n_items")             
    items = payload.get("items")                

    def make_block(_items):
        return {"type": "numbered" if list_type == "numbered" else "bullets", "items": _items}

    inserted_nos = []

    if list_type and (n_items or items):
        raw = items if items else [f"Item {i}" for i in range(1, int(n_items) + 1)]
        chunks = enforce_list_length(raw)
        cursor = after
        for idx, ch in enumerate(chunks):
            slide = Slide(
                id=str(uuid.uuid4()),
                no=0,
                title=title if idx == 0 else f"{title} (cont.)",
                layout=layout,
                content=[make_block(ch)]
            )
            state.slides.insert(cursor, slide)
            cursor += 1
        renumber(state.slides)
        inserted_nos = [s.no for s in state.slides[after:after+len(chunks)]]
    else:
        slide = Slide(id=str(uuid.uuid4()), no=0, title=title, layout=layout)
        state.slides.insert(after, slide)
        renumber(state.slides)
        inserted_nos = [slide.no]

    state.tally_mix()
    return {"diff": {"inserted": inserted_nos}, "deck_state": state.model_dump()}

@app.post("/edit_slide")
def edit_slide(payload: dict):
    state = must_state(payload["deck_id"])
    slide = state.get_by_no(payload["slide_no"])
    if "title" in payload:
        slide.title = payload["title"]
    if "text" in payload:
        slide.content = [{"type": "text", "text": payload["text"]}]
    state.tally_mix()
    return {"diff": {"edited": slide.no}, "deck_state": state.model_dump()}

@app.post("/edit_content")
def edit_content(payload: dict):
    state = must_state(payload["deck_id"])
    slide = state.get_by_no(payload["slide_no"])
    typ = payload["type"]

    if typ == "text":
        slide.content = [{"type": "text", "text": payload["text"]}]
    else:
        items = payload["items"]
        chunks = enforce_list_length(items)
        slide.content = [{"type": typ, "items": chunks[0]}]
        if len(chunks) > 1:
            insert_pos = slide.no  
            for ch in chunks[1:]:
                s2 = Slide(
                    id=str(uuid.uuid4()),
                    no=0,
                    title=f"{slide.title} (cont.)",
                    layout=slide.layout,
                    content=[{"type": typ, "items": ch}]
                )
                state.slides.insert(insert_pos, s2)
                insert_pos += 1
            renumber(state.slides)

    state.tally_mix()
    return {"diff": {"content_updated": slide.no}, "deck_state": state.model_dump()}

@app.post("/set_layout")
def set_layout(payload: dict):
    state = must_state(payload["deck_id"])
    slide = state.get_by_no(payload["slide_no"])
    slide.layout = ensure_layout(payload["layout"])
    state.tally_mix()
    return {"diff": {"layout_changed": slide.no, "layout": slide.layout},
            "deck_state": state.model_dump()}

@app.post("/set_image")
def set_image(payload: dict):
    state = must_state(payload["deck_id"])
    slide = state.get_by_no(payload["slide_no"])
    size = image_size_for_layout(slide.layout)
    prompt = payload["prompt"]
    slide.image = Image(prompt=prompt, size=size, alt=prompt[:60])
    state.tally_mix()
    return {"diff": {"image_added": slide.no, "size": size},
            "deck_state": state.model_dump()}

@app.post("/reorder_slides")
def reorder_slides(payload: dict):
    state = must_state(payload["deck_id"])
    order = payload["new_order"]
    mapping = {s.no: s for s in state.slides}
    try:
        state.slides = [mapping[i] for i in order]
    except KeyError:
        raise HTTPException(400, "new_order contains unknown slide numbers")
    renumber(state.slides)
    state.tally_mix()
    return {"diff": {"reordered": True}, "deck_state": state.model_dump()}

@app.post("/export_pptx")
def export_pptx(payload: dict):
    deck_id = payload["deck_id"]
    if deck_id not in store:
        raise HTTPException(404, "Unknown deck_id")
    return {"pptx_url": f"./exports/{deck_id}.pptx"}
