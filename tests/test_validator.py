import unittest
from pathlib import Path

from app.agents.validator import CustomerRules, load_customer_rules, validate_extraction
from app.schemas import FIELD_NAMES, ExtractionResult, FieldValue


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = {
            "consignee_name": "ACME Corporation Ltd",
            "hs_code": "847130",
            "port_of_loading": "Shanghai",
            "port_of_discharge": "Los Angeles",
            "incoterms": "FOB",
            "goods_description": "Portable computers",
            "gross_weight": "1200 kg",
            "invoice_number": "ACME-INV-2026-001",
        }
        self.rules = CustomerRules.model_validate(
            {
                "customer": "acme",
                "fields": {
                    name: {
                        "expected": value,
                        "normalizer": "weight" if name == "gross_weight" else (
                            "hs_code" if name == "hs_code" else (
                                "identifier" if name == "invoice_number" else "text"
                            )
                        ),
                    }
                    for name, value in self.expected.items()
                },
            }
        )

    def make_extraction(self, overrides: dict[str, FieldValue] | None = None) -> ExtractionResult:
        values = {
            name: FieldValue(
                value=value,
                confidence=0.95,
                source_quote=value,
                page=1,
            )
            for name, value in self.expected.items()
        }
        if overrides:
            values.update(overrides)
        return ExtractionResult.model_validate(values)

    def test_normalized_equivalent_values_match(self) -> None:
        extraction = self.make_extraction(
            {
                "gross_weight": FieldValue(
                    value="1.2 tonnes",
                    confidence=0.95,
                    source_quote="1.2 tonnes",
                    page=1,
                )
            }
        )

        result = validate_extraction(extraction, self.rules, minimum_confidence=0.8)

        self.assertEqual(result.fields["gross_weight"].status, "match")
        self.assertEqual(result.fields["gross_weight"].found, "1.2 tonnes")
        self.assertEqual(result.fields["gross_weight"].expected, "1200 kg")

    def test_null_and_low_confidence_are_uncertain(self) -> None:
        extraction = self.make_extraction(
            {
                "invoice_number": FieldValue(
                    value=None,
                    confidence=0.0,
                    source_quote=None,
                    page=None,
                ),
                "hs_code": FieldValue(
                    value="847130",
                    confidence=0.4,
                    source_quote="847130",
                    page=1,
                ),
            }
        )

        result = validate_extraction(extraction, self.rules, minimum_confidence=0.8)

        self.assertEqual(result.fields["invoice_number"].status, "uncertain")
        self.assertEqual(result.fields["hs_code"].status, "uncertain")

    def test_different_value_is_mismatch_with_both_values(self) -> None:
        extraction = self.make_extraction(
            {
                "invoice_number": FieldValue(
                    value="ACME-INV-2026-999",
                    confidence=0.95,
                    source_quote="ACME-INV-2026-999",
                    page=1,
                )
            }
        )

        result = validate_extraction(extraction, self.rules, minimum_confidence=0.8)

        invoice_result = result.fields["invoice_number"]
        self.assertEqual(invoice_result.status, "mismatch")
        self.assertEqual(invoice_result.found, "ACME-INV-2026-999")
        self.assertEqual(invoice_result.expected, "ACME-INV-2026-001")

    def test_invalid_weight_format_is_uncertain(self) -> None:
        extraction = self.make_extraction(
            {
                "gross_weight": FieldValue(
                    value="about twelve hundred",
                    confidence=0.95,
                    source_quote="about twelve hundred",
                    page=1,
                )
            }
        )

        result = validate_extraction(extraction, self.rules, minimum_confidence=0.8)

        self.assertEqual(result.fields["gross_weight"].status, "uncertain")

    def test_text_normalization_preserves_word_boundaries(self) -> None:
        extraction = self.make_extraction(
            {
                "consignee_name": FieldValue(
                    value="ACMECorporation Ltd",
                    confidence=0.95,
                    source_quote="ACMECorporation Ltd",
                    page=1,
                )
            }
        )

        result = validate_extraction(extraction, self.rules, minimum_confidence=0.8)

        self.assertEqual(result.fields["consignee_name"].status, "mismatch")

    def test_rounded_pound_conversion_matches_kilogram_rule(self) -> None:
        rules_data = self.rules.model_dump()
        rules_data["fields"]["gross_weight"]["expected"] = "1 kg"
        rules = CustomerRules.model_validate(rules_data)
        extraction = self.make_extraction(
            {
                "gross_weight": FieldValue(
                    value="2.20462 lbs",
                    confidence=0.95,
                    source_quote="2.20462 lbs",
                    page=1,
                )
            }
        )

        result = validate_extraction(extraction, rules, minimum_confidence=0.8)

        self.assertEqual(result.fields["gross_weight"].status, "match")

    def test_customer_acme_yaml_defines_every_field(self) -> None:
        rules_path = Path(__file__).parents[1] / "app" / "rules" / "customer_acme.yaml"

        loaded = load_customer_rules(rules_path)

        self.assertEqual(loaded.customer, "acme_demo")
        self.assertEqual(set(loaded.fields), set(FIELD_NAMES))


if __name__ == "__main__":
    unittest.main()