# Design Science Edit-Operation Benchmark

This folder contains the Design Science technical evaluation benchmark for structured slide-edit operation generation in LISA.

The benchmark evaluates pre-fine-tuning inference behavior. It is not LoRA training and does not load or train any local model during scaffold/setup work.

The evaluated task is:

```text
existing deck state + user edit request + operation schema
    -> LLM inference
    -> structured slide-edit operation
    -> validator/scorer
```

The benchmark compares multiple LLMs on their ability to generate valid, local, reviewable slide-edit operations such as `edit_content`, `edit_slide`, `set_layout`, `move_slide`, `insert_slide_after`, `delete_slide`, and `set_image`.

The current benchmark intentionally excludes clarification/dialogue-control actions because the finalized dataset and current replayable operation vocabulary contain only executable slide-edit operations. Clarification handling is future scope and can be added later if the dataset and backend are extended.

Operation labels are intentionally strict. Benchmark task wording should make the expected operation unambiguous, especially when distinguishing content-only edits from whole-slide edits.

The same benchmark is intended to be reused later for pre/post LoRA evaluation: first measure the selected base model before fine-tuning, then rerun the same tasks after LoRA fine-tuning and compare results.

## Environment Split

Use the local LISA project in VS Code for:

- Benchmark task preparation.
- Prompt and schema maintenance.
- Output validation.
- Scoring and aggregation.
- Chart generation.
- Report drafting.


## Planned Model Set

Current planned models:

- Qwen3-8B.
- Granite-4.1-8B or the newest compatible Granite 8B instruct model.
- Gemma-3-12B-IT if memory allows.
- Optional LFM2.5-8B-A1B.
- Optional API reference model.

## Benchmark Status

The folder contains the benchmark data, rendered prompts, API-reference and local-model runners, output validation, scoring, and aggregation scripts. Chart implementation remains future work.


