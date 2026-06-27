# Final 50 Benchmark Audit

## Provenance

- Benchmark version: `final_50_v1`
- Finalized export: `dataset/exports/finlized_combined_training_v1`
- Validation rows: `dataset/exports/finlized_combined_training_v1/combined_dialogues_validation.jsonl`
- Provenance statistics: `dataset/exports/finlized_combined_training_v1/combined_dialogues_api_call_statistics.jsonl`
- Verified healed deck root: `dataset/runs/v5/finalized_dataset_v1`
- Selection split: validation only; training rows are never a fallback.
- Deck states are reconstructed from verified healed source decks, not invented.

## Candidate filtering

- Validation examples loaded: 161
- Validation editing examples: 152
- Supported single-operation examples: 143
- Candidates excluded for pilot identifier overlap: 16
- Eligible candidates with recoverable compact deck states: 127
- Final tasks selected: 50

## Operation distribution

| Operation | Count |
|---|---:|
| edit_content | 12 |
| edit_slide | 8 |
| set_layout | 7 |
| move_slide | 7 |
| insert_slide_after | 6 |
| delete_slide | 5 |
| set_image | 5 |

## Difficulty distribution

| Difficulty | Count |
|---|---:|
| easy | 10 |
| medium | 25 |
| hard | 15 |

## Source coverage and leakage

- Unique source_pack_id values used: 8
- Unique deck_id values used: 8
- Unique deck_identity values used: 8
- Pilot source_pack_id values excluded: 1
- Pilot deck_id values excluded: 2
- Pilot deck_identity values excluded: 1
- Final/train source_pack_id overlap: 0
- Final/train deck_id overlap: 0
- Final/train deck_identity overlap: 0
- Leakage status: PASS

## Selected source scenarios

| Scenario | Count |
|---|---:|
| change_layout | 1 |
| compress_slide | 1 |
| delete_redundant_slide | 5 |
| expand_slide | 4 |
| improve_slide | 5 |
| insert_transition_slide | 6 |
| move_for_flow | 5 |
| move_slide | 2 |
| relayout_slide | 6 |
| retitle_slide | 5 |
| rewrite_slide_preserve_citation | 4 |
| rewrite_title | 1 |
| set_decorative_image | 5 |

## Construction notes

- The pilot deck and its inferred source pack/deck identity are excluded.
- Multi-operation examples and one-shot deck generation examples are excluded.
- Source requests are deterministically rewritten to be single-operation and unambiguous.
- Hard tasks refer to unique slide titles/roles where possible and retain explicit safety constraints.
- `ask_clarification` is not part of the operation vocabulary.
