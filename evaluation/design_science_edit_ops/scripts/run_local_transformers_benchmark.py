#!/usr/bin/env python3
"""Run the edit-operation benchmark with a local Hugging Face causal LM.

The runner is deliberately a dry run unless ``--execute`` is supplied. Dry
runs load only the rendered JSONL and never import torch, Transformers, or
bitsandbytes. Execute mode is intended for the university JupyterHub GPU
environment, not for local setup or benchmark validation.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    from json_extraction import JsonExtractionError, extract_first_json_object
except ModuleNotFoundError:
    from evaluation.design_science_edit_ops.scripts.json_extraction import (
        JsonExtractionError,
        extract_first_json_object,
    )


BENCHMARK_ROOT = Path(__file__).resolve().parents[1]
PROVIDER = "local_transformers"
MANIFEST_FIELDS = [
    "task_id",
    "model_name",
    "model_id",
    "output_path",
    "raw_output_path",
    "skipped_existing",
    "extraction_success",
    "extraction_error",
    "latency_ms",
    "generated_chars",
    "error",
]


def positive_int(value: str) -> int:
    """Parse a strictly positive integer."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line options without importing model dependencies."""
    parser = argparse.ArgumentParser(
        description=(
            "Run a local Hugging Face Transformers edit-operation benchmark "
            "(dry-run by default)."
        )
    )
    parser.add_argument(
        "--rendered",
        type=Path,
        default=BENCHMARK_ROOT / "data" / "rendered_prompts_pilot.jsonl",
        help="Rendered benchmark prompt JSONL.",
    )
    parser.add_argument(
        "--model-id",
        help="Hugging Face model ID; required with --execute (for example Qwen/Qwen3-8B).",
    )
    parser.add_argument(
        "--model-name",
        required=True,
        help="Short name used for output directories and manifest files.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Clean output directory (default: outputs/<model_name>).",
    )
    parser.add_argument(
        "--raw-out-dir",
        type=Path,
        default=None,
        help="Raw diagnostics directory (default: outputs/<model_name>_raw).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Manifest CSV path (default: results/<model_name>_manifest.csv).",
    )
    parser.add_argument("--task-id", help="Run only the specified task ID.")
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=None,
        help="Run only the first N selected tasks.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=positive_int,
        default=512,
        help="Maximum new tokens to generate per task (default: 512).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature (used only with --do-sample; default: 0.0).",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=1.0,
        help="Nucleus-sampling probability (used only with --do-sample; default: 1.0).",
    )
    parser.add_argument(
        "--do-sample",
        action="store_true",
        help="Enable sampling. Generation is deterministic by default.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42).")
    quantization = parser.add_mutually_exclusive_group()
    quantization.add_argument(
        "--load-in-4bit",
        action="store_true",
        help="Load the model with bitsandbytes 4-bit quantization.",
    )
    quantization.add_argument(
        "--load-in-8bit",
        action="store_true",
        help="Load the model with bitsandbytes 8-bit quantization.",
    )
    parser.add_argument(
        "--dtype",
        choices=("auto", "bfloat16", "float16", "float32"),
        default="auto",
        help="Non-quantized model dtype (default: auto).",
    )
    parser.add_argument(
        "--device-map",
        default="auto",
        help="Transformers device map (default: auto).",
    )
    parser.add_argument(
        "--trust-remote-code",
        action="store_true",
        help="Allow model repository custom code. Disabled by default.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing task outputs instead of skipping them.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Load the model and run inference. Without this flag, perform a dry run.",
    )

    args = parser.parse_args(argv)
    args.model_name = args.model_name.strip()
    if not args.model_name:
        parser.error("--model-name must be a non-empty value")
    if args.out_dir is None:
        args.out_dir = BENCHMARK_ROOT / "outputs" / args.model_name
    if args.raw_out_dir is None:
        args.raw_out_dir = BENCHMARK_ROOT / "outputs" / f"{args.model_name}_raw"
    if args.manifest is None:
        args.manifest = BENCHMARK_ROOT / "results" / f"{args.model_name}_manifest.csv"
    return args


def load_rendered_prompts(path: Path) -> List[Dict[str, Any]]:
    """Load rendered prompts and validate the fields used by this runner."""
    if not path.exists():
        raise FileNotFoundError(f"rendered prompt file does not exist: {path}")

    records: List[Dict[str, Any]] = []
    seen_task_ids = set()
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")

            task_id = record.get("task_id")
            prompt = record.get("prompt")
            if not isinstance(task_id, str) or not task_id.strip():
                raise ValueError(f"{path}:{line_no}: task_id must be a non-empty string")
            if task_id in seen_task_ids:
                raise ValueError(f"{path}:{line_no}: duplicate task_id: {task_id}")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"{path}:{line_no}: prompt must be a non-empty string")

            messages = record.get("messages")
            if messages is not None and not isinstance(messages, list):
                raise ValueError(f"{path}:{line_no}: messages must be a list when present")

            seen_task_ids.add(task_id)
            records.append(record)

    if not records:
        raise ValueError(f"rendered prompt file contains no records: {path}")
    return records


def select_records(
    records: List[Dict[str, Any]], task_id: Optional[str], limit: Optional[int]
) -> List[Dict[str, Any]]:
    """Select one task by ID if requested, then apply an optional limit."""
    selected = records
    if task_id:
        selected = [record for record in records if record["task_id"] == task_id]
        if not selected:
            raise ValueError(f"task_id not found in rendered prompts: {task_id}")
    if limit is not None:
        selected = selected[:limit]
    return selected


def valid_messages(value: Any) -> Optional[List[Dict[str, Any]]]:
    """Return chat-template-ready messages, or None for malformed/empty input."""
    if not isinstance(value, list) or not value:
        return None
    messages: List[Dict[str, Any]] = []
    for message in value:
        if not isinstance(message, dict):
            return None
        if not isinstance(message.get("role"), str) or "content" not in message:
            return None
        messages.append(dict(message))
    return messages


def format_prompt(tokenizer: Any, record: Mapping[str, Any]) -> Tuple[str, Optional[str]]:
    """Prefer messages plus a chat template and fall back to the plain prompt."""
    prompt = str(record["prompt"])
    messages = valid_messages(record.get("messages"))
    apply_chat_template = getattr(tokenizer, "apply_chat_template", None)
    if messages is None or not callable(apply_chat_template):
        return prompt, None

    try:
        try:
            formatted = apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            formatted = apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        if not isinstance(formatted, str) or not formatted:
            raise ValueError("chat template returned an empty or non-string prompt")
        return formatted, None
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        return prompt, error


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write a JSON object with stable, readable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_manifest(path: Path, rows: List[Mapping[str, Any]]) -> None:
    """Write the local-model execution manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def manifest_row(
    *,
    args: argparse.Namespace,
    task_id: str,
    output_path: Path,
    raw_output_path: Path,
    skipped_existing: bool = False,
    extraction_success: bool = False,
    extraction_error: str = "",
    latency_ms: Any = "",
    generated_chars: Any = "",
    error: str = "",
) -> Dict[str, Any]:
    """Build one manifest row with normalized boolean values."""
    return {
        "task_id": task_id,
        "model_name": args.model_name,
        "model_id": args.model_id or "",
        "output_path": str(output_path),
        "raw_output_path": str(raw_output_path),
        "skipped_existing": str(skipped_existing).lower(),
        "extraction_success": str(extraction_success).lower(),
        "extraction_error": extraction_error,
        "latency_ms": latency_ms,
        "generated_chars": generated_chars,
        "error": error,
    }


def gpu_diagnostics(torch: Any) -> Dict[str, Any]:
    """Collect optional CUDA diagnostics without making task execution fragile."""
    diagnostics: Dict[str, Any] = {"cuda_available": False}
    try:
        available = bool(torch.cuda.is_available())
        diagnostics["cuda_available"] = available
        if not available:
            return diagnostics
        device = torch.cuda.current_device()
        diagnostics.update(
            {
                "gpu_name": torch.cuda.get_device_name(device),
                "gpu_memory_allocated_mb": round(
                    torch.cuda.memory_allocated(device) / (1024 * 1024), 2
                ),
                "gpu_memory_reserved_mb": round(
                    torch.cuda.memory_reserved(device) / (1024 * 1024), 2
                ),
            }
        )
    except Exception as exc:
        diagnostics["gpu_info_error"] = f"{type(exc).__name__}: {exc}"
    return diagnostics


def build_raw_record(
    *,
    args: argparse.Namespace,
    record: Mapping[str, Any],
    formatted_prompt: str,
    generated_text: str,
    extraction_success: bool,
    extraction_error: Optional[str],
    latency_ms: int,
    gpu_info: Mapping[str, Any],
    chat_template_error: Optional[str] = None,
    generation_error: Optional[str] = None,
) -> Dict[str, Any]:
    """Build one raw generation/debug record without any credentials."""
    raw: Dict[str, Any] = {
        "task_id": record["task_id"],
        "model_name": args.model_name,
        "model_id": args.model_id,
        "prompt": record["prompt"],
        "formatted_prompt": formatted_prompt,
        "generated_text": generated_text,
        "extraction_success": extraction_success,
        "extraction_error": extraction_error,
        "latency_ms": latency_ms,
        "max_new_tokens": args.max_new_tokens,
        "do_sample": args.do_sample,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "load_in_4bit": args.load_in_4bit,
        "load_in_8bit": args.load_in_8bit,
        "dtype": args.dtype,
        "device_map": args.device_map,
    }
    raw.update(gpu_info)
    if chat_template_error:
        raw["chat_template_error"] = chat_template_error
    if generation_error:
        raw["generation_error"] = generation_error
    return raw


def print_summary(
    *,
    args: argparse.Namespace,
    loaded: int,
    selected: int,
    outputs_written: int,
    raw_outputs_written: int,
    skipped_existing: int,
    extraction_success: int,
    errors: int,
    would_execute: int,
) -> None:
    """Print a stable operator-facing benchmark summary."""
    print(f"provider: {PROVIDER}")
    print(f"model_id: {args.model_id or ''}")
    print(f"model_name: {args.model_name}")
    print(f"rendered_prompts_loaded: {loaded}")
    print(f"tasks_selected: {selected}")
    print(f"execute: {str(args.execute).lower()}")
    if not args.execute:
        print(f"would_execute: {would_execute}")
    print(f"outputs_written: {outputs_written}")
    print(f"raw_outputs_written: {raw_outputs_written}")
    print(f"skipped_existing: {skipped_existing}")
    print(f"extraction_success: {extraction_success}")
    print(f"errors: {errors}")
    print(f"out_dir: {args.out_dir}")
    print(f"raw_out_dir: {args.raw_out_dir}")
    print(f"manifest_path: {args.manifest}")


def dry_run(
    args: argparse.Namespace,
    records: List[Dict[str, Any]],
    loaded_count: int,
) -> int:
    """Report selected work without importing model libraries or writing files."""
    skipped_existing = sum(
        1
        for record in records
        if (args.out_dir / f"{record['task_id']}.json").exists() and not args.overwrite
    )
    would_execute = len(records) - skipped_existing
    print(f"selected_task_ids: {','.join(record['task_id'] for record in records)}")
    print_summary(
        args=args,
        loaded=loaded_count,
        selected=len(records),
        outputs_written=0,
        raw_outputs_written=0,
        skipped_existing=skipped_existing,
        extraction_success=0,
        errors=0,
        would_execute=would_execute,
    )
    return 0


def resolve_torch_dtype(torch: Any, dtype: str) -> Any:
    """Map the CLI dtype name to a Transformers-compatible torch dtype."""
    if dtype == "auto":
        return "auto"
    return {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }[dtype]


def load_model_stack(args: argparse.Namespace) -> Tuple[Any, Any, Any]:
    """Lazily import dependencies and load the tokenizer/model for execute mode."""
    try:
        import torch
    except Exception as exc:
        raise RuntimeError(
            f"could not import PyTorch for --execute: {type(exc).__name__}: {exc}"
        ) from exc

    try:
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            set_seed,
        )
    except Exception as exc:
        raise RuntimeError(
            "could not import Hugging Face Transformers for --execute: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    if args.load_in_4bit or args.load_in_8bit:
        try:
            import bitsandbytes  # noqa: F401
        except Exception as exc:
            raise RuntimeError(
                "could not import bitsandbytes for quantized execution: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    random.seed(args.seed)
    set_seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    try:
        model_kwargs: Dict[str, Any] = {
            "device_map": args.device_map,
            "trust_remote_code": args.trust_remote_code,
        }
        if args.load_in_4bit:
            model_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True)
        elif args.load_in_8bit:
            model_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
        else:
            model_kwargs["torch_dtype"] = resolve_torch_dtype(torch, args.dtype)

        tokenizer = AutoTokenizer.from_pretrained(
            args.model_id,
            trust_remote_code=args.trust_remote_code,
        )
        model = AutoModelForCausalLM.from_pretrained(args.model_id, **model_kwargs)
        model.eval()
    except Exception as exc:
        raise RuntimeError(
            f"failed to load local model '{args.model_id}': {type(exc).__name__}: {exc}"
        ) from exc
    return torch, tokenizer, model


def synchronize_cuda(torch: Any) -> None:
    """Synchronize CUDA for useful latency measurements when it is available."""
    try:
        if torch.cuda.is_available():
            torch.cuda.synchronize()
    except Exception:
        pass


def generate_text(
    *,
    torch: Any,
    tokenizer: Any,
    model: Any,
    formatted_prompt: str,
    args: argparse.Namespace,
) -> str:
    """Generate and decode only tokens produced after the formatted prompt."""
    inputs = tokenizer(formatted_prompt, return_tensors="pt")
    inputs = inputs.to(model.device)
    prompt_length = inputs["input_ids"].shape[-1]

    generation_kwargs: Dict[str, Any] = {
        "max_new_tokens": args.max_new_tokens,
        "do_sample": args.do_sample,
    }
    if args.do_sample:
        generation_kwargs["temperature"] = args.temperature
        generation_kwargs["top_p"] = args.top_p

    pad_token_id = getattr(tokenizer, "pad_token_id", None)
    if pad_token_id is None:
        pad_token_id = getattr(tokenizer, "eos_token_id", None)
    if pad_token_id is not None:
        generation_kwargs["pad_token_id"] = pad_token_id

    with torch.no_grad():
        output_ids = model.generate(**inputs, **generation_kwargs)
    sequences = getattr(output_ids, "sequences", output_ids)
    generated_ids = sequences[0, prompt_length:]
    return tokenizer.decode(generated_ids, skip_special_tokens=True)


def execute_benchmark(
    args: argparse.Namespace,
    records: List[Dict[str, Any]],
    loaded_count: int,
) -> int:
    """Load one local model and execute all selected benchmark prompts."""
    if not args.model_id or not args.model_id.strip():
        raise RuntimeError("--execute requires --model-id")
    if args.do_sample and args.temperature <= 0:
        raise RuntimeError("--do-sample requires --temperature greater than 0")
    if args.do_sample and not 0 < args.top_p <= 1:
        raise RuntimeError("--do-sample requires --top-p in the interval (0, 1]")

    torch, tokenizer, model = load_model_stack(args)
    manifest_rows: List[Dict[str, Any]] = []
    outputs_written = 0
    raw_outputs_written = 0
    skipped_existing = 0
    extraction_success_count = 0
    error_count = 0

    for record in records:
        task_id = record["task_id"]
        output_path = args.out_dir / f"{task_id}.json"
        raw_output_path = args.raw_out_dir / f"{task_id}.json"

        if output_path.exists() and not args.overwrite:
            skipped_existing += 1
            manifest_rows.append(
                manifest_row(
                    args=args,
                    task_id=task_id,
                    output_path=output_path,
                    raw_output_path=raw_output_path,
                    skipped_existing=True,
                    error="skipped_existing",
                )
            )
            continue

        # A failed overwrite must not leave a stale clean output for validation.
        if args.overwrite and output_path.exists():
            output_path.unlink()

        formatted_prompt = str(record["prompt"])
        chat_template_error: Optional[str] = None
        generated_text = ""
        started = time.perf_counter()
        try:
            formatted_prompt, chat_template_error = format_prompt(tokenizer, record)
            synchronize_cuda(torch)
            started = time.perf_counter()
            generated_text = generate_text(
                torch=torch,
                tokenizer=tokenizer,
                model=model,
                formatted_prompt=formatted_prompt,
                args=args,
            )
            synchronize_cuda(torch)
            latency_ms = round((time.perf_counter() - started) * 1000)
            try:
                parsed = extract_first_json_object(generated_text)
                extraction_error = None
            except JsonExtractionError as exc:
                parsed = None
                extraction_error = str(exc)
            extraction_success = parsed is not None

            raw_record = build_raw_record(
                args=args,
                record=record,
                formatted_prompt=formatted_prompt,
                generated_text=generated_text,
                extraction_success=extraction_success,
                extraction_error=extraction_error,
                latency_ms=latency_ms,
                gpu_info=gpu_diagnostics(torch),
                chat_template_error=chat_template_error,
            )
            write_json(raw_output_path, raw_record)
            raw_outputs_written += 1

            if extraction_success and parsed is not None:
                write_json(output_path, parsed)
                outputs_written += 1
                extraction_success_count += 1
            else:
                error_count += 1

            manifest_rows.append(
                manifest_row(
                    args=args,
                    task_id=task_id,
                    output_path=output_path,
                    raw_output_path=raw_output_path,
                    extraction_success=extraction_success,
                    extraction_error=extraction_error or "",
                    latency_ms=latency_ms,
                    generated_chars=len(generated_text),
                )
            )
        except Exception as exc:
            synchronize_cuda(torch)
            latency_ms = round((time.perf_counter() - started) * 1000)
            error = f"{type(exc).__name__}: {exc}"
            error_count += 1
            raw_record = build_raw_record(
                args=args,
                record=record,
                formatted_prompt=formatted_prompt,
                generated_text=generated_text,
                extraction_success=False,
                extraction_error="generation failed before JSON extraction",
                latency_ms=latency_ms,
                gpu_info=gpu_diagnostics(torch),
                chat_template_error=chat_template_error,
                generation_error=error,
            )
            write_json(raw_output_path, raw_record)
            raw_outputs_written += 1
            manifest_rows.append(
                manifest_row(
                    args=args,
                    task_id=task_id,
                    output_path=output_path,
                    raw_output_path=raw_output_path,
                    extraction_error="generation failed before JSON extraction",
                    latency_ms=latency_ms,
                    generated_chars=len(generated_text),
                    error=error,
                )
            )

    write_manifest(args.manifest, manifest_rows)
    print_summary(
        args=args,
        loaded=loaded_count,
        selected=len(records),
        outputs_written=outputs_written,
        raw_outputs_written=raw_outputs_written,
        skipped_existing=skipped_existing,
        extraction_success=extraction_success_count,
        errors=error_count,
        would_execute=0,
    )
    return 0 if error_count == 0 else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    records = load_rendered_prompts(args.rendered)
    selected = select_records(records, args.task_id, args.limit)
    if not args.execute:
        return dry_run(args, selected, len(records))
    return execute_benchmark(args, selected, len(records))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise SystemExit(f"error: {exc}") from exc
