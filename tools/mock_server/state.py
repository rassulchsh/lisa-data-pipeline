from pydantic import BaseModel, Field
from typing import List, Optional, Dict

store: Dict[str, "DeckState"] = {}

class Image(BaseModel):
    prompt: Optional[str] = None
    size: Optional[str] = None   
    url: Optional[str] = None
    alt: Optional[str] = None

class Slide(BaseModel):
    id: str
    no: int
    title: str
    layout: str
    content: List[dict] = Field(default_factory=list)  
    image: Optional[Image] = None

class DeckState(BaseModel):
    deck_id: str
    language: str
    template: str
    agenda: List[str] = Field(default_factory=list)
    slides: List[Slide] = Field(default_factory=list)
    mix_counts: dict = Field(default_factory=lambda: {"text_only": 0, "text_image": 0, "image_only": 0})
    slide_index: List[dict] = Field(default_factory=list)  # [{"no":1,"title":"..."}, ...]

    def get_by_no(self, no: int) -> Slide:
        for s in self.slides:
            if s.no == no:
                return s
        raise ValueError(f"Slide {no} not found.")

    def refresh_slide_index(self):
        self.slide_index = [{"no": s.no, "title": s.title} for s in self.slides]

    def tally_mix(self):
        text_only = text_image = image_only = 0
        for s in self.slides:
            has_text = bool(s.content)
            has_img = bool(s.image)
            if has_text and has_img:
                text_image += 1
            elif has_img:
                image_only += 1
            else:
                text_only += 1
        self.mix_counts = {"text_only": text_only, "text_image": text_image, "image_only": image_only}
        self.refresh_slide_index()
