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
- Gemma-4-12B-it if memory allows.
- Optional LFM2.5-8B-A1B.
- Optional API reference model.

## Benchmark Status

The folder contains the benchmark data, rendered prompts, API-reference and local-model runners, output validation, scoring, and aggregation scripts. Chart implementation remains future work.

## Final 50-task benchmark

The frozen 10-task pilot is an infrastructure sanity check. The final 50-task benchmark is the real model-comparison set: it is selected only from held-out validation examples and excludes pilot source identifiers and all source identifiers present in the training split. It uses only the seven executable editing operations; clarification/dialogue-control is excluded for now. Freeze the final task and rendered-prompt files before comparing any models.

The operation distribution is:

- `edit_content`: 12
- `edit_slide`: 8
- `set_layout`: 7
- `move_slide`: 7
- `insert_slide_after`: 6
- `delete_slide`: 5
- `set_image`: 5

Build and audit the deterministic final benchmark:

```bash
python evaluation/design_science_edit_ops/scripts/build_final_50_benchmark.py
```

Render model inputs without gold labels:

```bash
python evaluation/design_science_edit_ops/scripts/render_prompts.py \
  --tasks evaluation/design_science_edit_ops/data/benchmark_tasks_final_50.jsonl \
  --template evaluation/design_science_edit_ops/prompts/edit_operation_prompt.txt \
  --out-jsonl evaluation/design_science_edit_ops/data/rendered_prompts_final_50.jsonl \
  --out-preview evaluation/design_science_edit_ops/report/prompt_preview_final_50.md \
  --preview-count 5
```

Create deterministic gold outputs and verify validator compatibility:

```bash
python evaluation/design_science_edit_ops/scripts/build_gold_outputs_from_tasks.py

python evaluation/design_science_edit_ops/scripts/validate_outputs.py \
  --tasks evaluation/design_science_edit_ops/data/benchmark_tasks_final_50.jsonl \
  --outputs evaluation/design_science_edit_ops/outputs/gold_final_50 \
  --model gold_final_50 \
  --out evaluation/design_science_edit_ops/results/raw_results_final_50_gold.csv

python evaluation/design_science_edit_ops/scripts/aggregate_results.py \
  --raw evaluation/design_science_edit_ops/results/raw_results_final_50_gold.csv \
  --tasks evaluation/design_science_edit_ops/data/benchmark_tasks_final_50.jsonl \
  --out-model evaluation/design_science_edit_ops/results/summary_by_model_final_50_gold.csv \
  --out-api-call evaluation/design_science_edit_ops/results/summary_by_api_call_final_50_gold.csv
```

Run the API reference later:

```bash
python evaluation/design_science_edit_ops/scripts/run_api_benchmark.py \
  --rendered evaluation/design_science_edit_ops/data/rendered_prompts_final_50.jsonl \
  --model gpt-5.4-mini \
  --max-output-tokens 512 \
  --out-dir evaluation/design_science_edit_ops/outputs/api_reference_final_50 \
  --raw-out-dir evaluation/design_science_edit_ops/outputs/api_reference_final_50_raw \
  --manifest evaluation/design_science_edit_ops/results/api_reference_final_50_manifest.csv \
  --execute \
  --overwrite
```

Run Qwen3-8B later on JupyterHub:

```bash
python evaluation/design_science_edit_ops/scripts/run_local_transformers_benchmark.py \
  --rendered evaluation/design_science_edit_ops/data/rendered_prompts_final_50.jsonl \
  --model-id Qwen/Qwen3-8B \
  --model-name qwen3_8b_final_50 \
  --max-new-tokens 512 \
  --load-in-4bit \
  --execute \
  --overwrite
```

Run Granite-4.1-8B later on JupyterHub:

```bash
python evaluation/design_science_edit_ops/scripts/run_local_transformers_benchmark.py \
  --rendered evaluation/design_science_edit_ops/data/rendered_prompts_final_50.jsonl \
  --model-id ibm-granite/granite-4.1-8b \
  --model-name granite_4_1_8b_final_50 \
  --max-new-tokens 512 \
  --load-in-4bit \
  --execute \
  --overwrite
```

## Gemma 4 loader

Qwen, Granite, and LFM use the default `auto_causal_lm` loader. Gemma 4 uses
the processor-based `multimodal_lm` loader.

Run a one-task Gemma 4 compatibility test later on JupyterHub:

```bash
python evaluation/design_science_edit_ops/scripts/run_local_transformers_benchmark.py \
  --model-id google/gemma-4-12B-it \
  --model-name gemma_4_12b_it \
  --loader multimodal_lm \
  --max-new-tokens 512 \
  --limit 1 \
  --load-in-4bit \
  --execute \
  --overwrite
```

Validate the one-task output:

```bash
python evaluation/design_science_edit_ops/scripts/validate_outputs.py \
  --outputs evaluation/design_science_edit_ops/outputs/gemma_4_12b_it \
  --model gemma_4_12b_it \
  --out evaluation/design_science_edit_ops/results/raw_results_pilot_gemma_4_12b_it_limit1.csv
```

On JupyterHub, run one model at a time and add `--limit 1` for the first compatibility and GPU-memory smoke test.
