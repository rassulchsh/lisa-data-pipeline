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

Use the university JupyterHub GPU server later only for local open-model inference.

## Planned Model Set

Current planned models:

- Qwen3-8B.
- Granite-4.1-8B or the newest compatible Granite 8B instruct model.
- Gemma-3-12B-IT if memory allows.
- Optional LFM2.5-8B-A1B.
- Optional API reference model.

## Benchmark Status

The folder contains the benchmark data, rendered prompts, API-reference and local-model runners, output validation, scoring, and aggregation scripts. Chart implementation remains future work.

## Phase 7A Local Transformers Runner

`scripts/run_local_transformers_benchmark.py` runs rendered prompts through a local Hugging Face causal language model. It is a dry run unless `--execute` is supplied, and dry runs do not import model libraries, download a model, or perform inference.

Dry-run one selected prompt locally:

```bash
python evaluation/design_science_edit_ops/scripts/run_local_transformers_benchmark.py \
  --model-id Qwen/Qwen3-8B \
  --model-name qwen3_8b \
  --limit 1
```

Start on JupyterHub with one quantized task:

```bash
python evaluation/design_science_edit_ops/scripts/run_local_transformers_benchmark.py \
  --model-id Qwen/Qwen3-8B \
  --model-name qwen3_8b \
  --max-new-tokens 512 \
  --limit 1 \
  --load-in-4bit \
  --execute \
  --overwrite
```

Validate that one-task run:

```bash
python evaluation/design_science_edit_ops/scripts/validate_outputs.py \
  --outputs evaluation/design_science_edit_ops/outputs/qwen3_8b \
  --model qwen3_8b \
  --out evaluation/design_science_edit_ops/results/raw_results_pilot_qwen3_8b_limit1.csv
```

After the one-task smoke test succeeds, run all ten pilot tasks:

```bash
python evaluation/design_science_edit_ops/scripts/run_local_transformers_benchmark.py \
  --model-id Qwen/Qwen3-8B \
  --model-name qwen3_8b \
  --max-new-tokens 512 \
  --load-in-4bit \
  --execute \
  --overwrite
```

Then validate the full output directory and aggregate its raw validation CSV with `validate_outputs.py` and `aggregate_results.py`. On JupyterHub, run one model at a time and always begin with `--limit 1` to verify model compatibility and GPU memory use.
