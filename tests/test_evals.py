import unittest

from app.config import OLLAMA_VISION_MODEL
from app.agents.router import route_validation
from app.agents.validator import CustomerRules, validate_extraction
from app.schemas import FIELD_NAMES, ExtractionResult, FieldValue
from evals.run_evals import EvaluationSample, _render_results, calculate_metrics


class EvaluationTests(unittest.TestCase):
    def test_default_vision_model_is_installed_gemma(self) -> None:
        self.assertEqual(OLLAMA_VISION_MODEL, "gemma3:4b")

    def test_calculates_accuracy_hallucination_caught_and_decision_metrics(self) -> None:
        rules = CustomerRules.model_validate(
            {
                "customer": "test",
                "fields": {
                    name: {
                        "expected": "847130" if name == "hs_code" else f"expected-{name}",
                        "normalizer": "hs_code" if name == "hs_code" else "text",
                    }
                    for name in FIELD_NAMES
                },
            }
        )
        expected_values = {
            name: "847130" if name == "hs_code" else f"expected-{name}"
            for name in FIELD_NAMES
        }
        values = dict(expected_values)
        values["invoice_number"] = "wrong-invoice"
        extraction = ExtractionResult.model_validate(
            {
                name: FieldValue(
                    value=values[name],
                    confidence=0.95,
                    source_quote=values[name],
                    page=1,
                )
                for name in FIELD_NAMES
            }
        )
        validation = validate_extraction(extraction, rules, minimum_confidence=0.8)
        decision = route_validation(validation)
        sample = EvaluationSample(
            sample_id="sample-1",
            ground_truth=expected_values,
            extracted=extraction,
            validation=validation,
            decision=decision,
            document_text=" ".join(expected_values.values()),
            expected_decision="amendment_request",
        )

        metrics = calculate_metrics([sample], rules)

        self.assertEqual(metrics["sample_count"], 1)
        self.assertEqual(metrics["hallucination_rate"], 1 / 8)
        self.assertEqual(metrics["caught_rate"], 1.0)
        self.assertEqual(metrics["decision_accuracy"], 1.0)
        self.assertEqual(metrics["field_metrics"]["invoice_number"]["exact_accuracy"], 0.0)
        self.assertEqual(metrics["decision_mix"]["amendment_request"], 1)
        self.assertEqual(metrics["decision_mix"]["auto_approve"], 0)

    def test_report_includes_model_and_dataset_limitations(self) -> None:
        report = _render_results(
            {
                "sample_count": 6,
                "field_metrics": {},
                "hallucination_rate": 0.0,
                "hallucination_fields": 0,
                "non_null_fields": 46,
                "caught_rate": None,
                "wrong_fields": 0,
                "caught_wrong_fields": 0,
                "decision_accuracy": 1.0,
                "correct_decisions": 6,
                "decision_mix": {
                    "auto_approve": 2,
                    "human_review": 2,
                    "amendment_request": 2,
                },
                "model": "gemma3:4b",
                "dataset_quality_counts": {"clean": 3, "messy_scanned": 3},
                "synthetic_documents": 6,
            }
        )

        self.assertIn("Extractor model: gemma3:4b", report)
        self.assertIn("3 clean, 3 messy_scanned", report)
        self.assertIn("2 auto_approve, 2 human_review, 2 amendment_request", report)
        self.assertIn("does not measure OCR on image-only documents", report)


if __name__ == "__main__":
    unittest.main()