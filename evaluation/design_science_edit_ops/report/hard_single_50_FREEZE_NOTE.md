# HardSingleOp-50 Freeze Note

HardSingleOp-50 is frozen after successful benchmark construction, rendered-prompt generation, overlap checks, and gold validation.

Purpose:
Evaluate single executable LISA edit-operation generation under harder semantic targeting, relative positioning, citation-preservation, and preservation-constraint conditions.

Interpretation:
This is a validation-grounded hard stress benchmark. It uses held-out validation deck states, source examples, target slides, expected operations, and expected arguments, while deterministically rewriting user requests to increase difficulty.

Frozen files:
- data/benchmark_tasks_hard_single_50.jsonl
- data/rendered_prompts_hard_single_50.jsonl
- outputs/gold_hard_single_50/
- results/raw_results_hard_single_50_gold.csv
- results/hard_single_50_candidate_pool.csv
- results/hard_single_50_task_distribution.csv
- results/hard_single_50_complexity_distribution.csv
- report/hard_single_50_benchmark_audit.md

Quality gates:
- 50 selected tasks
- 50 rendered prompts
- 50/50 gold validation passed
- no final-50 source_example_id overlap
- validation split only
- supported executable operations only
- exactly one expected operation per task
- all seven executable edit operations represented
- 8 deck identities and 8 source packs represented

After this point, do not modify benchmark tasks, rendered prompts, schema, or prompt before model runs.
