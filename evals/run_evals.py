from __future__ import annotations

import argparse
import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.agents.extractor import extract_document, read_document_text
from app.agents.router import route_validation
from app.agents.validator import (
    CustomerRules,
    load_customer_rules,
    normalize_value,
    validate_extraction,
)
from app.config import OLLAMA_VISION_MODEL
from app.graph import DEFAULT_RULES_PATH
from app.schemas import FIELD_NAMES, Decision, ExtractionResult, ValidationResult


DEFAULT_DATASET_DIR = Path(__file__).parent / "dataset"
DEFAULT_RESULTS_PATH = Path(__file__).parent / "results.md"
DocumentReader = Callable[[str | Path], str]
Extractor = Callable[[str | Path], ExtractionResult]


@dataclass(frozen=True)
class EvaluationSample:
    sample_id: str
    ground_truth: dict[str, str | None]
    extracted: ExtractionResult
    validation: ValidationResult
    decision: Decision
    document_text: str
    expected_decision: str


def calculate_metrics(
    samples: list[EvaluationSample],
    rules: CustomerRules,
) -> dict[str, object]:
    if not samples:
        raise ValueError("at least one evaluation sample is required")

    field_metrics: dict[str, dict[str, int | float]] = {}
    wrong_fields = 0
    caught_wrong_fields = 0
    non_null_outputs = 0
    hallucinations = 0
    correct_decisions = 0
    decision_mix = {
        "auto_approve": 0,
        "human_review": 0,
        "amendment_request": 0,
    }

    for field_name in FIELD_NAMES:
        exact_correct = 0
        normalized_correct = 0
        for sample in samples:
            expected = sample.ground_truth[field_name]
            actual = getattr(sample.extracted, field_name).value
            if actual == expected:
                exact_correct += 1
            if _normalize_field(rules, field_name, actual) == _normalize_field(
                rules, field_name, expected
            ):
                normalized_correct += 1
        field_metrics[field_name] = {
            "exact_accuracy": exact_correct / len(samples),
            "normalized_accuracy": normalized_correct / len(samples),
        }

    for sample in samples:
        document_text = _normalize_evidence(sample.document_text)
        for field_name in FIELD_NAMES:
            expected = sample.ground_truth[field_name]
            field_value = getattr(sample.extracted, field_name)
            if field_value.value is not None:
                non_null_outputs += 1
                if _normalize_evidence(field_value.value) not in document_text:
                    hallucinations += 1

            is_wrong = _normalize_field(rules, field_name, field_value.value) != (
                _normalize_field(rules, field_name, expected)
            )
            if is_wrong:
                wrong_fields += 1
                if sample.validation.fields[field_name].status in {"uncertain", "mismatch"}:
                    caught_wrong_fields += 1

        if sample.decision.outcome == sample.expected_decision:
            correct_decisions += 1
        decision_mix[sample.decision.outcome] += 1

    return {
        "sample_count": len(samples),
        "field_metrics": field_metrics,
        "hallucination_rate": (
            hallucinations / non_null_outputs if non_null_outputs else 0.0
        ),
        "hallucination_fields": hallucinations,
        "non_null_fields": non_null_outputs,
        "caught_rate": caught_wrong_fields / wrong_fields if wrong_fields else None,
        "wrong_fields": wrong_fields,
        "caught_wrong_fields": caught_wrong_fields,
        "decision_accuracy": correct_decisions / len(samples),
        "correct_decisions": correct_decisions,
        "decision_mix": decision_mix,
    }


def run_evaluations(
    *,
    dataset_dir: str | Path = DEFAULT_DATASET_DIR,
    output_path: str | Path = DEFAULT_RESULTS_PATH,
    rules_path: str | Path = DEFAULT_RULES_PATH,
    extractor: Extractor = extract_document,
    document_reader: DocumentReader = read_document_text,
) -> dict[str, object]:
    dataset_root = Path(dataset_dir)
    files = sorted(dataset_root.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No labeled JSON documents found in {dataset_root}")

    rules = load_customer_rules(rules_path)
    samples: list[EvaluationSample] = []
    quality_counts: dict[str, int] = {}
    synthetic_documents = 0
    for label_path in files:
        label = json.loads(label_path.read_text(encoding="utf-8"))
        quality = label.get("quality", "unspecified")
        quality_counts[quality] = quality_counts.get(quality, 0) + 1
        synthetic_documents += bool(label.get("synthetic", False))
        document_path = (dataset_root / label["document"]).resolve()
        ground_truth = label["ground_truth"]
        missing = set(FIELD_NAMES) - ground_truth.keys()
        if missing:
            raise ValueError(f"{label_path} is missing labels: {', '.join(sorted(missing))}")

        extraction = extractor(document_path)
        validation = validate_extraction(extraction, rules)
        decision = route_validation(validation)
        samples.append(
            EvaluationSample(
                sample_id=label.get("sample_id", label_path.stem),
                ground_truth=ground_truth,
                extracted=extraction,
                validation=validation,
                decision=decision,
                document_text=document_reader(document_path),
                expected_decision=label["expected_decision"],
            )
        )

    metrics = calculate_metrics(samples, rules)
    metrics["model"] = OLLAMA_VISION_MODEL
    metrics["dataset_quality_counts"] = quality_counts
    metrics["synthetic_documents"] = synthetic_documents
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(_render_results(metrics), encoding="utf-8")
    return metrics


def _normalize_field(
    rules: CustomerRules,
    field_name: str,
    value: str | None,
) -> str | None:
    if value is None:
        return None
    return normalize_value(rules.fields[field_name].normalizer, value)


def _normalize_evidence(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def _render_results(metrics: dict[str, object]) -> str:
    field_metrics = metrics["field_metrics"]
    lines = [
        "# Evaluation Results",
        "",
        f"Documents evaluated: {metrics['sample_count']}",
        f"Extractor model: {metrics.get('model', 'not recorded')}",
        "Dataset profile: "
        + ", ".join(
            f"{count} {quality}"
            for quality, count in sorted(metrics.get("dataset_quality_counts", {}).items())
        ),
        f"Synthetic documents: {metrics.get('synthetic_documents', 0)}",
        f"Hallucination rate: {metrics['hallucination_rate']:.1%} "
        f"({metrics['hallucination_fields']}/{metrics['non_null_fields']} non-null fields)",
        "Caught rate: "
        + (
            f"{metrics['caught_rate']:.1%} "
            f"({metrics['caught_wrong_fields']}/{metrics['wrong_fields']} wrong fields)"
            if metrics["caught_rate"] is not None
            else "N/A (no wrong fields in the labeled set)"
        ),
        f"Decision accuracy: {metrics['decision_accuracy']:.1%} "
        f"({metrics['correct_decisions']}/{metrics['sample_count']})",
        "Decision mix: "
        + ", ".join(
            f"{count} {outcome}"
            for outcome, count in metrics["decision_mix"].items()
        ),
    ]
    if metrics.get("synthetic_documents"):
        lines.extend(
            [
                "",
                "Note: Messy samples are rasterized PDFs with an invisible searchable text layer "
                "for grounding checks. This run does not measure OCR on image-only documents.",
            ]
        )
    lines.extend(
        [
            "",
            "| Field | Exact accuracy | Normalized accuracy |",
            "| --- | ---: | ---: |",
        ]
    )
    for field_name, values in field_metrics.items():
        lines.append(
            f"| {field_name} | {values['exact_accuracy']:.1%} "
            f"| {values['normalized_accuracy']:.1%} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline trade-document evaluations")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    args = parser.parse_args()

    metrics = run_evaluations(
        dataset_dir=args.dataset,
        output_path=args.output,
        rules_path=args.rules,
    )
    print(_render_results(metrics))


if __name__ == "__main__":
    main()