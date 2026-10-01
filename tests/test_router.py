import unittest

from app.schemas import FIELD_NAMES, FieldResult, ValidationResult
from app.agents.router import route_validation


class RouterTests(unittest.TestCase):
    def validation(
        self,
        statuses: dict[str, str],
    ) -> ValidationResult:
        fields = {}
        for name in FIELD_NAMES:
            status = statuses.get(name, "match")
            fields[name] = FieldResult(
                status=status,
                found="found value" if status == "mismatch" else None,
                expected="expected value" if status == "mismatch" else None,
                reason="hand-built test result",
            )
        return ValidationResult(fields=fields)

    def test_all_matches_auto_approve(self) -> None:
        decision = route_validation(self.validation({}))

        self.assertEqual(decision.outcome, "auto_approve")
        self.assertTrue(decision.reasoning)
        self.assertEqual(decision.amendment_draft, [])

    def test_mismatch_requests_amendment_with_field_details(self) -> None:
        decision = route_validation(
            self.validation({"invoice_number": "mismatch"})
        )

        self.assertEqual(decision.outcome, "amendment_request")
        self.assertEqual(
            [item.model_dump() for item in decision.amendment_draft],
            [{
                "field": "invoice_number",
                "found": "found value",
                "expected": "expected value",
            }],
        )

    def test_uncertain_field_requires_human_review(self) -> None:
        decision = route_validation(
            self.validation({"gross_weight": "uncertain"})
        )

        self.assertEqual(decision.outcome, "human_review")
        self.assertIn("gross_weight", decision.reasoning)
        self.assertEqual(decision.amendment_draft, [])

    def test_uncertain_takes_precedence_over_mismatch(self) -> None:
        decision = route_validation(
            self.validation(
                {
                    "invoice_number": "mismatch",
                    "gross_weight": "uncertain",
                }
            )
        )

        self.assertEqual(decision.outcome, "human_review")
        self.assertEqual(decision.amendment_draft, [])


if __name__ == "__main__":
    unittest.main()