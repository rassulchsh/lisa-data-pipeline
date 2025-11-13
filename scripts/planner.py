from __future__ import annotations
import os, argparse, json
from typing import List, Dict, Any
from planner.llm import llm_call
from planner.utils import load_prompts, render, jdump, choose_k, normalize_bullets, uid_from

def user_turn(text: str, lang="en"): 
    return {"role":"user","lang":lang,"text":text}

def tool_call(name: str, args: Dict[str,Any]): 
    return {"role":"assistant","tool_calls":[{"name":name,"args":args}]}

def needs_image(layout: str) -> bool:
    return layout in {"SplitLeftImage","SplitRightImage","FullImage"}

def synthesize_dialog(topic: Dict[str,Any],
                      agenda: List[Dict[str,Any]],
                      plan: Dict[str,Any],
                      images: Dict[str,Any],
                      lang="en",
                      template="Minimal") -> List[Dict[str,Any]]:
    title = topic["title"].strip()[:100] or "Untitled"
    dlg: List[Dict[str,Any]] = []
    dlg += [
        user_turn(f"Create an English presentation titled '{title}'.", lang),
        tool_call("create_presentation", {"language":lang, "template":template, "title":title})
    ]
    agenda_titles = [a["title"] for a in agenda]
    dlg += [
        user_turn(f"Set the agenda with {len(agenda_titles)} items.", lang),
        tool_call("set_agenda", {"items": agenda_titles})
    ]
    after_no = 1
    for block in plan.get("plan", []):
        ag_title = block.get("agenda_title", "Section")
        slides = block.get("slides", [])
        if not slides:
            slides = [{"layout":"TitleBullets"}]
        first_slide_no = None
        for s in slides:
            layout = s.get("layout","TitleBullets")
            dlg += [
                user_turn(f"Create a slide titled '{ag_title}' using a suitable layout.", lang),
                tool_call("insert_slide_after", {"after_slide_no": after_no, "title": ag_title, "layout": layout})
            ]
            after_no += 1
            if first_slide_no is None:
                first_slide_no = after_no - 1
            if needs_image(layout):
                prompt = None
                for img in images.get("images", []):
                    if img.get("agenda_title","").strip().lower() == ag_title.strip().lower():
                        prompt = img.get("prompt")
                        break
                prompt = prompt or f"{ag_title}, academic diagram"
                dlg += [ tool_call("set_image", {"slide_no": first_slide_no, "prompt": prompt}) ]
    slide_no = 2
    for a in agenda:
        bullets = normalize_bullets(a.get("bullets", []))
        dlg += [
            user_turn(f"Add bulleted points to slide {slide_no}.", lang),
            tool_call("edit_content", {"slide_no":slide_no, "type":"bullets", "items": bullets})
        ]
        slide_no += 1
    dlg += [ user_turn("Show the slide index.", lang), tool_call("get_slide_index", {}) ]
    return dlg

def make_agenda_items(raw_agenda: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    out = []
    for a in raw_agenda[:3]:
        title = a.get("title") or "Section"
        bullets = normalize_bullets(a.get("bullets") or [])
        out.append({"title": title, "bullets": bullets})
    if len(out) < 2:
        out.append({"title":"Overview","bullets":["Point 1","Point 2","Point 3"]})
    return out[:3]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="dataset/dialogs/en/drafts")
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--areas_k", type=int, default=8)
    ap.add_argument("--topics_per_area", type=int, default=20)  
    args = ap.parse_args()

    prompts = load_prompts()
    style = prompts.get("style_preamble","")
    areas_prompt = render(prompts["areas_prompt"], style_preamble=style)
    areas_resp = llm_call(areas_prompt)
    areas = areas_resp.get("areas", [])
    if not areas:
        raise SystemExit("No areas returned by LLM.")
    areas = choose_k(areas, args.areas_k)

    dialogs_written = 0
    for area in areas:
        if dialogs_written >= args.count: break
        area_name = area["name"]
        tprompt = render(prompts["topics_prompt"], style_preamble=style, area=area_name)
        topics_resp = llm_call(tprompt)
        topics = topics_resp.get("topics", [])
        topics = choose_k(topics, min(args.topics_per_area, len(topics)))

        for topic in topics:
            if dialogs_written >= args.count: break
            title = topic["title"]
            aprompt = render(prompts["agenda_prompt"], style_preamble=style, title=title)
            agenda_resp = llm_call(aprompt)
            agenda_items = make_agenda_items(agenda_resp.get("agenda", []))
            agenda_titles = [a["title"] for a in agenda_items]
            sprompt = render(prompts["slide_plan_prompt"], style_preamble=style, agenda_titles=json.dumps(agenda_titles, ensure_ascii=False))
            plan_resp = llm_call(sprompt)
            iprompt = render(prompts["image_prompts_prompt"], style_preamble=style, title=title, agenda_titles=json.dumps(agenda_titles, ensure_ascii=False))
            images_resp = llm_call(iprompt)
            dialog = synthesize_dialog(topic, agenda_items, plan_resp, images_resp, lang="en", template="Minimal")
            # meta 
            meta = {
                "area": area_name,
                "topic_desc": topic.get("desc",""),
                "images": images_resp.get("images", []),
                "planner_version": prompts.get("version","v1"),
            }
            dialog.insert(1, {"role":"assistant","analysis":json.dumps(meta, ensure_ascii=False)})

            fname = f"{uid_from(area_name+'|'+title)}_{title.lower().replace(' ','_')}.json"
            outpath = os.path.join(args.outdir, fname)
            jdump(outpath, dialog)
            print("Wrote", outpath)
            dialogs_written += 1

    print(f"\nGenerated {dialogs_written} draft dialogs -> {args.outdir}")

if __name__ == "__main__":
    main()
