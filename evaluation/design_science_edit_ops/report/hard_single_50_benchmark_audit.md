# HardSingleOp-50 Benchmark Audit

## Source files used

- Benchmark version: `hard_single_50_v1`
- Validation dialogues: `dataset/exports/finlized_combined_training_v1/combined_dialogues_validation.jsonl`
- Split/provenance statistics: `dataset/exports/finlized_combined_training_v1/combined_dialogues_api_call_statistics.jsonl`
- Verified healed deck root: `dataset/runs/v5/finalized_dataset_v1`
- Frozen final-50 exclusions: `evaluation/design_science_edit_ops/data/benchmark_tasks_final_50.jsonl`
- Pilot exclusions: `evaluation/design_science_edit_ops/data/benchmark_tasks_pilot.jsonl`
- Training data was used only as an identifier exclusion set; no training dialogue was a candidate.

## Candidate loading and exclusions

- Validation rows loaded: 161
- Eligible clean single-operation candidates: 77
- Selected tasks: 50
- Confirmation-gated selected dialogues using the initiating request: 24

| Exclusion reason | Count |
|---|---:|
| final_50_source_example_overlap | 50 |
| not_deck_editing | 9 |
| pilot_source_identifier_overlap | 17 |
| unsupported_or_multi_operation_signature | 8 |

## Operation distribution

| Operation | Requested target | Selected | Deviation |
|---|---:|---:|---:|
| edit_content | 10 | 7 | -3 |
| edit_slide | 8 | 9 | 1 |
| set_layout | 7 | 7 | 0 |
| move_slide | 7 | 8 | 1 |
| insert_slide_after | 7 | 8 | 1 |
| delete_slide | 5 | 5 | 0 |
| set_image | 6 | 6 | 0 |

The unused clean pool contains only 7 `edit_content` examples after final-50 and pilot exclusions. The three-task deficit is redistributed deterministically to the highest-hardness operations, with at most one extra task per operation before any broader fallback.

## Difficulty distribution

| Difficulty | Count |
|---|---:|
| easy | 5 |
| hard | 23 |
| medium | 22 |

## Hardness tag distribution

| Hardness tag | Count |
|---|---:|
| citation_preservation | 45 |
| content_transformation | 7 |
| long_deck | 50 |
| relative_position | 16 |
| semantic_title_destination | 16 |
| semantic_title_target | 42 |
| similar_title_distractor | 24 |
| trivial_operation_penalty | 12 |

## Rewrite type distribution

| Rewrite type | Count |
|---|---:|
| content_edit_wording_strengthened | 7 |
| destination_number_to_unique_title | 16 |
| limited_title_agenda_distractor | 24 |
| preservation_constraints_added | 45 |
| target_number_to_unique_title | 42 |

## Deck and source-pack diversity

- Unique source packs: 8
- Unique decks: 8
- Unique deck identities: 8
- Deck lengths: 9–11 slides

## Overlap and quality-gate checks

- Final-50 task-ID overlap: 0 — PASS
- Final-50 source-example overlap: 0 — PASS
- Pilot task-ID overlap: 0 — PASS
- Pilot source-example overlap: 0 — PASS
- Pilot source-identifier overlap: 0 — PASS
- Train source-identifier overlap: 0 — PASS
- Unsupported operation count: 0 — PASS
- `ask_clarification` count: 0 — PASS
- Selected examples with expected backend tool-call count other than one: 0 — PASS
- Final-50 deck-identity reuse: 8
- Final-50 source-pack reuse: 8

Deck/source-pack reuse is expected and is not source-example leakage: final-50 already occupies eight validation decks and the pilot occupies the ninth. HardSingleOp therefore isolates unused validation dialogues/source examples while conservatively excluding the entire pilot deck. A deck-level exclusion against both prior suites would leave no candidates.

## Examples of selected hard tasks

### hard_single_004 — `move_slide`

- Hardness: 12 (semantic_title_target, semantic_title_destination, relative_position, citation_preservation, long_deck, similar_title_distractor)
- Request: Move the slide titled “Fiscal Costs and Distributional Impacts of Carbon Pricing” so it appears directly after the slide titled “Economic Stakes of Carbon Pricing Policies in OECD Countries”. Keep the moved slide's title, content, and layout unchanged. Preserve all citation and source references exactly as they are. Do not edit or move any other slide. Use the case study slide—not the agenda or title slide.
- Expected target: slide 7

### hard_single_011 — `move_slide`

- Hardness: 12 (semantic_title_target, semantic_title_destination, relative_position, citation_preservation, long_deck, similar_title_distractor)
- Request: Move the slide titled “What Evaluating Remote Learning Effectiveness Means for Future Practice” so it appears directly after the slide titled “The problem: why evaluating the effectiveness of remote learning strategies in public k-12 education matters”. Keep the moved slide's title, content, and layout unchanged. Preserve all citation and source references exactly as they are. Do not edit or move any other slide. Use the synthesis slide—not the agenda or title slide.
- Expected target: slide 11

### hard_single_018 — `move_slide`

- Hardness: 12 (semantic_title_target, semantic_title_destination, relative_position, citation_preservation, long_deck, similar_title_distractor)
- Request: Move the slide titled “Fiscal Cost and Distributional Consequences” so it appears directly after the slide titled “The Policy Stakes of Universal Basic Income Pilots in OECD Countries”. Keep the moved slide's title, content, and layout unchanged. Preserve all citation and source references exactly as they are. Do not edit or move any other slide. Use the case study slide—not the agenda or title slide.
- Expected target: slide 7

### hard_single_025 — `move_slide`

- Hardness: 12 (semantic_title_target, semantic_title_destination, relative_position, citation_preservation, long_deck, similar_title_distractor)
- Request: Move the slide titled “Synthesis and Implications: Making Informed Decisions on Early Childhood Education” so it appears directly after the slide titled “The problem: why evaluating the impact of early childhood education on long-term cognitive development matters”. Keep the moved slide's title, content, and layout unchanged. Preserve all citation and source references exactly as they are. Do not edit or move any other slide. Use the synthesis slide—not the agenda or title slide.
- Expected target: slide 11

### hard_single_048 — `move_slide`

- Hardness: 12 (semantic_title_target, semantic_title_destination, relative_position, citation_preservation, long_deck, similar_title_distractor)
- Request: Move the slide titled “Policy Recommendations and Future Research Directions” so it appears directly after the slide titled “The Policy Stakes of Universal Basic Income Pilots in OECD Countries”. Keep the moved slide's title, content, and layout unchanged. Preserve all citation and source references exactly as they are. Do not edit or move any other slide. Use the synthesis slide—not the agenda or title slide.
- Expected target: slide 9

## Limitations

- Validation provenance contains only nine source decks, so task-level diversity is stronger than deck-level diversity.
- The requested `edit_content` quota cannot be met without reusing final-50 examples or the pilot deck; the benchmark records the three-task redistribution instead.
- Semantic title targeting is deterministic only when the compact recovered deck contains a unique title; otherwise the builder retains an explicit numbered fallback and applies the score penalty.
- Gold validation checks schema, operation, target, minimum argument completeness, and replay proxy compatibility; it is not a live PowerPoint execution test.

## Freeze statement

- Status: **FROZEN — PASS**
- Gold validation: all 50 selected tasks passed.
- Gold validation file: `evaluation/design_science_edit_ops/results/raw_results_hard_single_50_gold.csv`
- Frozen task SHA-256: `bd9e21e23ab307dfec59fbaaddb7cd14d60367c2c7ab02774e3b233acf140af7`
- Any future task-content change requires a new benchmark version and fresh gold validation.
