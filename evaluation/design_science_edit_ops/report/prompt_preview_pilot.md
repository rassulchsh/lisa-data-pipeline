# Prompt Preview - Pilot Benchmark

## pilot_001

Expected API call: edit_content
Expected slide: 3

```text
You are the Targeted Editing Engine of a slide-editing system.

Your task is to transform a user editing request into exactly one structured JSON operation.

Rules:
- Return JSON only.
- Do not explain outside JSON.
- Do not rewrite the full deck.
- Use only one allowed api_call.
- Keep the operation local to the requested slide or section.
- Include review_status = "pending".
- Include a short reason.

Allowed api_call values:
edit_content, edit_slide, set_layout, move_slide, insert_slide_after, delete_slide, set_image

Required JSON structure:
{
  "api_call": "...",
  "slide_no": null_or_integer,
  "arguments": {},
  "reason": "...",
  "review_status": "pending"
}

Allowed argument patterns by api_call:

edit_content:
- Use {"target": "bullets", "instruction": "..."} for instruction-style content edits.
- Or use {"replace_slide": {"title": "...", "bullets": ["...", "..."]}} for concrete replacement edits.

edit_slide:
- Use {"instruction": "..."} or {"new_title": "..."} for slide-level edits.
- Or use {"replace_slide": {"title": "...", "bullets": ["...", "..."]}} when replacing slide-level content.

set_layout:
- Use {"layout": "..."}.

move_slide:
- Use {"after_slide_no": 3}, {"before_slide_no": 8}, or {"new_position": {"relation": "...", "reference_slide_no": 3}}.

insert_slide_after:
- Use {"after_slide_no": 3, "title": "...", "instruction": "..."}.

delete_slide:
- Use an empty arguments object: {}.

set_image:
- Use {"image_intent": "...", "instruction": "..."} or {"image_prompt": "..."}.

Operation selection guide:
- Use edit_content when the user asks to rewrite, shorten, expand, clarify, or improve bullet text/content inside an existing slide without changing the slide structure.
- Use edit_slide when the user asks to change the slide title, overall slide framing, or multiple slide-level elements.
- Use set_layout only when the user asks for a layout change.
- Use move_slide only when the user asks to reorder an existing slide.
- Use insert_slide_after only when the user asks to add a new slide after an existing slide.
- Use delete_slide only when the user asks to remove an existing slide.
- Use set_image only when the user asks to add, replace, or modify a slide image/visual.

Deck state:
{
  "title": "Impacts of Urban Green Infrastructure on Air Quality in Major Cities",
  "slides": [
    {
      "slide_no": 1,
      "role": "opening",
      "title": "Impacts of Urban Green Infrastructure on Air Quality in Major Cities",
      "layout": "TitleSlide",
      "bullets": [],
      "has_citation": false,
      "has_image": false
    },
    {
      "slide_no": 2,
      "role": "agenda",
      "title": "Agenda",
      "layout": "AgendaSlide",
      "bullets": [
        "Pathways and Sources of Air Quality Impacts",
        "Empirical Evidence on Air Quality Measurements",
        "Health and Ecosystem Consequences of Air Quality Changes",
        "Comparative Analysis",
        "Policy and Mitigation Strategies",
        "Evidence Gaps and Uncertainties"
      ],
      "has_citation": false,
      "has_image": false
    },
    {
      "slide_no": 3,
      "role": "problem_framing",
      "title": "Environmental Stakes of Urban Green Infrastructure on Air Quality",
      "layout": "TitleBullets",
      "bullets": [
        "What does the current evidence reveal about urban green infrastructure, and why does it matter?",
        "Evidence indicates that green and grey infrastructure interact with local meteorological conditions and traffic-related air pollution.",
        "To what extent does urban green infrastructure influence air quality in major cities?",
        "This deck focuses on pathways and sources of air quality impacts from urban green infrastructure.",
        "Main argument: measured evidence provides a nuanced basis for targeted mitigation strategies. Source: nature.com, Evaluating green and grey urban infrastructure impacts on particulate pollution"
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 4,
      "role": "mechanism",
      "title": "Pathways and Sources of Air Quality Impacts from Urban Green Infrastructure",
      "layout": "SplitRightImage",
      "bullets": [
        "A Dublin city-square case study examined evolving green and grey urban morphologies.",
        "Parks are significant parts of urban landscapes and influence local air quality conditions.",
        "Green and grey infrastructure effects vary with traffic, weather, and urban form."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 5,
      "role": "evidence",
      "title": "Empirical Evidence on Air Quality Measurements in Urban Green Spaces",
      "layout": "SplitRightImage",
      "bullets": [
        "The evidence is indirect and should be interpreted cautiously.",
        "A monitoring campaign and ENVI-met modelling were used to assess current and future scenarios.",
        "Urban parks contain substantial tree assets that may affect air quality outcomes."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 6,
      "role": "implications",
      "title": "Health and Ecosystem Consequences of Air Quality Changes from Urban Green Infrastructure",
      "layout": "SplitRightImage",
      "bullets": [
        "The evidence gives this section indirect support.",
        "Green roofs and tree barriers can improve air quality and reduce heat-island effects.",
        "Green infrastructure can reduce particulate pollution and ground-level ozone."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 7,
      "role": "comparison",
      "title": "Comparative Analysis of Urban Green Infrastructure and Alternative Air Quality Interventions",
      "layout": "DataCallout",
      "bullets": [
        "The current evidence gives this section only indirect support, so treat it as a cautious interpretation."
      ],
      "has_citation": false,
      "has_image": false
    },
    {
      "slide_no": 8,
      "role": "policy",
      "title": "Policy and Mitigation Strategies for Managing Air Quality Impacts of Urban Green Infrastructure",
      "layout": "SplitRightImage",
      "bullets": [
        "The evidence gives this section indirect support.",
        "Urban parks have substantial structural value.",
        "Green infrastructure can improve runoff quality, reduce flooding, lower heat, and reduce building energy demand."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 9,
      "role": "limitations",
      "title": "Evidence Gaps and Uncertainties in Assessing Air Quality Impacts of Urban Green Infrastructure",
      "layout": "TitleBullets",
      "bullets": [
        "The evidence gives this section indirect support.",
        "Effects of parks and open space vary by city scale, parkland amount, and tree cover.",
        "Heat islands emerge when natural land cover is replaced by pavement, buildings, and other heat-retaining surfaces."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 10,
      "role": "synthesis",
      "title": "Synthesis and Recommendations for Future Urban Green Infrastructure Planning",
      "layout": "TitleBullets",
      "bullets": [
        "Green and grey infrastructure interact with weather and traffic-related air pollution.",
        "The Dublin case examined local urban development and park growth effects.",
        "Limitation: when measured effects are unavailable, frame health and ecosystem effects as open questions.",
        "Outlook: further evidence would sharpen these conclusions."
      ],
      "has_citation": false,
      "has_image": false
    }
  ]
}

User request:
Please rewrite only the bullet text on slide 3 more clearly, but keep the nature.com citation about particulate pollution. Do not change the slide title, layout, or any other slide.

```

## pilot_002

Expected API call: edit_content
Expected slide: 5

```text
You are the Targeted Editing Engine of a slide-editing system.

Your task is to transform a user editing request into exactly one structured JSON operation.

Rules:
- Return JSON only.
- Do not explain outside JSON.
- Do not rewrite the full deck.
- Use only one allowed api_call.
- Keep the operation local to the requested slide or section.
- Include review_status = "pending".
- Include a short reason.

Allowed api_call values:
edit_content, edit_slide, set_layout, move_slide, insert_slide_after, delete_slide, set_image

Required JSON structure:
{
  "api_call": "...",
  "slide_no": null_or_integer,
  "arguments": {},
  "reason": "...",
  "review_status": "pending"
}

Allowed argument patterns by api_call:

edit_content:
- Use {"target": "bullets", "instruction": "..."} for instruction-style content edits.
- Or use {"replace_slide": {"title": "...", "bullets": ["...", "..."]}} for concrete replacement edits.

edit_slide:
- Use {"instruction": "..."} or {"new_title": "..."} for slide-level edits.
- Or use {"replace_slide": {"title": "...", "bullets": ["...", "..."]}} when replacing slide-level content.

set_layout:
- Use {"layout": "..."}.

move_slide:
- Use {"after_slide_no": 3}, {"before_slide_no": 8}, or {"new_position": {"relation": "...", "reference_slide_no": 3}}.

insert_slide_after:
- Use {"after_slide_no": 3, "title": "...", "instruction": "..."}.

delete_slide:
- Use an empty arguments object: {}.

set_image:
- Use {"image_intent": "...", "instruction": "..."} or {"image_prompt": "..."}.

Operation selection guide:
- Use edit_content when the user asks to rewrite, shorten, expand, clarify, or improve bullet text/content inside an existing slide without changing the slide structure.
- Use edit_slide when the user asks to change the slide title, overall slide framing, or multiple slide-level elements.
- Use set_layout only when the user asks for a layout change.
- Use move_slide only when the user asks to reorder an existing slide.
- Use insert_slide_after only when the user asks to add a new slide after an existing slide.
- Use delete_slide only when the user asks to remove an existing slide.
- Use set_image only when the user asks to add, replace, or modify a slide image/visual.

Deck state:
{
  "title": "Impacts of Urban Green Infrastructure on Air Quality in Major Cities",
  "slides": [
    {
      "slide_no": 1,
      "role": "opening",
      "title": "Impacts of Urban Green Infrastructure on Air Quality in Major Cities",
      "layout": "TitleSlide",
      "bullets": [],
      "has_citation": false,
      "has_image": false
    },
    {
      "slide_no": 2,
      "role": "agenda",
      "title": "Agenda",
      "layout": "AgendaSlide",
      "bullets": [
        "Pathways and Sources of Air Quality Impacts",
        "Empirical Evidence on Air Quality Measurements",
        "Health and Ecosystem Consequences of Air Quality Changes",
        "Comparative Analysis",
        "Policy and Mitigation Strategies",
        "Evidence Gaps and Uncertainties"
      ],
      "has_citation": false,
      "has_image": false
    },
    {
      "slide_no": 3,
      "role": "problem_framing",
      "title": "Environmental Stakes of Urban Green Infrastructure on Air Quality",
      "layout": "TitleBullets",
      "bullets": [
        "What does the current evidence reveal about urban green infrastructure, and why does it matter?",
        "Evidence indicates that green and grey infrastructure interact with local meteorological conditions and traffic-related air pollution.",
        "To what extent does urban green infrastructure influence air quality in major cities?",
        "This deck focuses on pathways and sources of air quality impacts from urban green infrastructure.",
        "Main argument: measured evidence provides a nuanced basis for targeted mitigation strategies. Source: nature.com, Evaluating green and grey urban infrastructure impacts on particulate pollution"
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 4,
      "role": "mechanism",
      "title": "Pathways and Sources of Air Quality Impacts from Urban Green Infrastructure",
      "layout": "SplitRightImage",
      "bullets": [
        "A Dublin city-square case study examined evolving green and grey urban morphologies.",
        "Parks are significant parts of urban landscapes and influence local air quality conditions.",
        "Green and grey infrastructure effects vary with traffic, weather, and urban form."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 5,
      "role": "evidence",
      "title": "Empirical Evidence on Air Quality Measurements in Urban Green Spaces",
      "layout": "SplitRightImage",
      "bullets": [
        "The evidence is indirect and should be interpreted cautiously.",
        "A monitoring campaign and ENVI-met modelling were used to assess current and future scenarios.",
        "Urban parks contain substantial tree assets that may affect air quality outcomes."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 6,
      "role": "implications",
      "title": "Health and Ecosystem Consequences of Air Quality Changes from Urban Green Infrastructure",
      "layout": "SplitRightImage",
      "bullets": [
        "The evidence gives this section indirect support.",
        "Green roofs and tree barriers can improve air quality and reduce heat-island effects.",
        "Green infrastructure can reduce particulate pollution and ground-level ozone."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 7,
      "role": "comparison",
      "title": "Comparative Analysis of Urban Green Infrastructure and Alternative Air Quality Interventions",
      "layout": "DataCallout",
      "bullets": [
        "The current evidence gives this section only indirect support, so treat it as a cautious interpretation."
      ],
      "has_citation": false,
      "has_image": false
    },
    {
      "slide_no": 8,
      "role": "policy",
      "title": "Policy and Mitigation Strategies for Managing Air Quality Impacts of Urban Green Infrastructure",
      "layout": "SplitRightImage",
      "bullets": [
        "The evidence gives this section indirect support.",
        "Urban parks have substantial structural value.",
        "Green infrastructure can improve runoff quality, reduce flooding, lower heat, and reduce building energy demand."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 9,
      "role": "limitations",
      "title": "Evidence Gaps and Uncertainties in Assessing Air Quality Impacts of Urban Green Infrastructure",
      "layout": "TitleBullets",
      "bullets": [
        "The evidence gives this section indirect support.",
        "Effects of parks and open space vary by city scale, parkland amount, and tree cover.",
        "Heat islands emerge when natural land cover is replaced by pavement, buildings, and other heat-retaining surfaces."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 10,
      "role": "synthesis",
      "title": "Synthesis and Recommendations for Future Urban Green Infrastructure Planning",
      "layout": "TitleBullets",
      "bullets": [
        "Green and grey infrastructure interact with weather and traffic-related air pollution.",
        "The Dublin case examined local urban development and park growth effects.",
        "Limitation: when measured effects are unavailable, frame health and ecosystem effects as open questions.",
        "Outlook: further evidence would sharpen these conclusions."
      ],
      "has_citation": false,
      "has_image": false
    }
  ]
}

User request:
Slide 5 is too wordy. Shorten the bullet list while preserving the source and leaving every other slide unchanged.

```

## pilot_003

Expected API call: edit_slide
Expected slide: 7

```text
You are the Targeted Editing Engine of a slide-editing system.

Your task is to transform a user editing request into exactly one structured JSON operation.

Rules:
- Return JSON only.
- Do not explain outside JSON.
- Do not rewrite the full deck.
- Use only one allowed api_call.
- Keep the operation local to the requested slide or section.
- Include review_status = "pending".
- Include a short reason.

Allowed api_call values:
edit_content, edit_slide, set_layout, move_slide, insert_slide_after, delete_slide, set_image

Required JSON structure:
{
  "api_call": "...",
  "slide_no": null_or_integer,
  "arguments": {},
  "reason": "...",
  "review_status": "pending"
}

Allowed argument patterns by api_call:

edit_content:
- Use {"target": "bullets", "instruction": "..."} for instruction-style content edits.
- Or use {"replace_slide": {"title": "...", "bullets": ["...", "..."]}} for concrete replacement edits.

edit_slide:
- Use {"instruction": "..."} or {"new_title": "..."} for slide-level edits.
- Or use {"replace_slide": {"title": "...", "bullets": ["...", "..."]}} when replacing slide-level content.

set_layout:
- Use {"layout": "..."}.

move_slide:
- Use {"after_slide_no": 3}, {"before_slide_no": 8}, or {"new_position": {"relation": "...", "reference_slide_no": 3}}.

insert_slide_after:
- Use {"after_slide_no": 3, "title": "...", "instruction": "..."}.

delete_slide:
- Use an empty arguments object: {}.

set_image:
- Use {"image_intent": "...", "instruction": "..."} or {"image_prompt": "..."}.

Operation selection guide:
- Use edit_content when the user asks to rewrite, shorten, expand, clarify, or improve bullet text/content inside an existing slide without changing the slide structure.
- Use edit_slide when the user asks to change the slide title, overall slide framing, or multiple slide-level elements.
- Use set_layout only when the user asks for a layout change.
- Use move_slide only when the user asks to reorder an existing slide.
- Use insert_slide_after only when the user asks to add a new slide after an existing slide.
- Use delete_slide only when the user asks to remove an existing slide.
- Use set_image only when the user asks to add, replace, or modify a slide image/visual.

Deck state:
{
  "title": "Impacts of Urban Green Infrastructure on Air Quality in Major Cities",
  "slides": [
    {
      "slide_no": 1,
      "role": "opening",
      "title": "Impacts of Urban Green Infrastructure on Air Quality in Major Cities",
      "layout": "TitleSlide",
      "bullets": [],
      "has_citation": false,
      "has_image": false
    },
    {
      "slide_no": 2,
      "role": "agenda",
      "title": "Agenda",
      "layout": "AgendaSlide",
      "bullets": [
        "Pathways and Sources of Air Quality Impacts",
        "Empirical Evidence on Air Quality Measurements",
        "Health and Ecosystem Consequences of Air Quality Changes",
        "Comparative Analysis",
        "Policy and Mitigation Strategies",
        "Evidence Gaps and Uncertainties"
      ],
      "has_citation": false,
      "has_image": false
    },
    {
      "slide_no": 3,
      "role": "problem_framing",
      "title": "Environmental Stakes of Urban Green Infrastructure on Air Quality",
      "layout": "TitleBullets",
      "bullets": [
        "What does the current evidence reveal about urban green infrastructure, and why does it matter?",
        "Evidence indicates that green and grey infrastructure interact with local meteorological conditions and traffic-related air pollution.",
        "To what extent does urban green infrastructure influence air quality in major cities?",
        "This deck focuses on pathways and sources of air quality impacts from urban green infrastructure.",
        "Main argument: measured evidence provides a nuanced basis for targeted mitigation strategies. Source: nature.com, Evaluating green and grey urban infrastructure impacts on particulate pollution"
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 4,
      "role": "mechanism",
      "title": "Pathways and Sources of Air Quality Impacts from Urban Green Infrastructure",
      "layout": "SplitRightImage",
      "bullets": [
        "A Dublin city-square case study examined evolving green and grey urban morphologies.",
        "Parks are significant parts of urban landscapes and influence local air quality conditions.",
        "Green and grey infrastructure effects vary with traffic, weather, and urban form."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 5,
      "role": "evidence",
      "title": "Empirical Evidence on Air Quality Measurements in Urban Green Spaces",
      "layout": "SplitRightImage",
      "bullets": [
        "The evidence is indirect and should be interpreted cautiously.",
        "A monitoring campaign and ENVI-met modelling were used to assess current and future scenarios.",
        "Urban parks contain substantial tree assets that may affect air quality outcomes."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 6,
      "role": "implications",
      "title": "Health and Ecosystem Consequences of Air Quality Changes from Urban Green Infrastructure",
      "layout": "SplitRightImage",
      "bullets": [
        "The evidence gives this section indirect support.",
        "Green roofs and tree barriers can improve air quality and reduce heat-island effects.",
        "Green infrastructure can reduce particulate pollution and ground-level ozone."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 7,
      "role": "comparison",
      "title": "Comparative Analysis of Urban Green Infrastructure and Alternative Air Quality Interventions",
      "layout": "DataCallout",
      "bullets": [
        "The current evidence gives this section only indirect support, so treat it as a cautious interpretation."
      ],
      "has_citation": false,
      "has_image": false
    },
    {
      "slide_no": 8,
      "role": "policy",
      "title": "Policy and Mitigation Strategies for Managing Air Quality Impacts of Urban Green Infrastructure",
      "layout": "SplitRightImage",
      "bullets": [
        "The evidence gives this section indirect support.",
        "Urban parks have substantial structural value.",
        "Green infrastructure can improve runoff quality, reduce flooding, lower heat, and reduce building energy demand."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 9,
      "role": "limitations",
      "title": "Evidence Gaps and Uncertainties in Assessing Air Quality Impacts of Urban Green Infrastructure",
      "layout": "TitleBullets",
      "bullets": [
        "The evidence gives this section indirect support.",
        "Effects of parks and open space vary by city scale, parkland amount, and tree cover.",
        "Heat islands emerge when natural land cover is replaced by pavement, buildings, and other heat-retaining surfaces."
      ],
      "has_citation": true,
      "has_image": false
    },
    {
      "slide_no": 10,
      "role": "synthesis",
      "title": "Synthesis and Recommendations for Future Urban Green Infrastructure Planning",
      "layout": "TitleBullets",
      "bullets": [
        "Green and grey infrastructure interact with weather and traffic-related air pollution.",
        "The Dublin case examined local urban development and park growth effects.",
        "Limitation: when measured effects are unavailable, frame health and ecosystem effects as open questions.",
        "Outlook: further evidence would sharpen these conclusions."
      ],
      "has_citation": false,
      "has_image": false
    }
  ]
}

User request:
Could you give slide 7 a sharper title? Keep the content as is.

```
