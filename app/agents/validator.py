from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config import MIN_FIELD_CONFIDENCE
from app.schemas import FIELD_NAMES, FieldName, ExtractionResult, FieldResult, ValidationResult


NormalizerName = Literal["text", "identifier", "hs_code", "weight"]


class RuleConfigurationError(ValueError):
    pass


class FieldRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected: str
    normalizer: NormalizerName = "text"
    aliases: list[str] = Field(default_factory=list)


class CustomerRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer: str
    fields: dict[FieldName, FieldRule]

    @model_validator(mode="after")
    def validate_coverage_and_expected_values(self) -> "CustomerRules":
        missing = set(FIELD_NAMES) - self.fields.keys()
        if missing:
            raise ValueError(f"rules are missing fields: {', '.join(sorted(missing))}")
        for field_name, rule in self.fields.items():
            values = [rule.expected, *rule.aliases]
            if any(_normalize(rule.normalizer, value) is None for value in values):
                raise ValueError(f"invalid expected value or alias for {field_name}")
        return self


def load_customer_rules(path: str | Path) -> CustomerRules:
    rules_path = Path(path)
    try:
        data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RuleConfigurationError(f"Could not load rules from {rules_path}: {exc}") from exc
    try:
        return CustomerRules.model_validate(data)
    except ValidationError as exc:
        raise RuleConfigurationError(f"Invalid customer rules in {rules_path}: {exc}") from exc


def validate_extraction(
    extraction: ExtractionResult,
    rules: CustomerRules,
    *,
    minimum_confidence: float = MIN_FIELD_CONFIDENCE,
) -> ValidationResult:
    if not 0 <= minimum_confidence <= 1:
        raise ValueError("minimum_confidence must be between 0 and 1")

    results: dict[FieldName, FieldResult] = {}
    for field_name, extracted in extraction.field_values().items():
        rule = rules.fields[field_name]
        expected = rule.expected

        if extracted.value is None:
            results[field_name] = FieldResult(
                status="uncertain",
                expected=expected,
                reason="No value was extracted; human verification is required.",
            )
            continue

        if extracted.confidence < minimum_confidence:
            results[field_name] = FieldResult(
                status="uncertain",
                found=extracted.value,
                expected=expected,
                reason=(
                    f"Confidence {extracted.confidence:.2f} is below the "
                    f"{minimum_confidence:.2f} threshold."
                ),
            )
            continue

        normalized_found = _normalize(rule.normalizer, extracted.value)
        if normalized_found is None:
            results[field_name] = FieldResult(
                status="uncertain",
                found=extracted.value,
                expected=expected,
                reason=f"Value does not have a valid {rule.normalizer} format.",
            )
            continue

        accepted_values = [rule.expected, *rule.aliases]
        if any(
            normalized_found == _normalize(rule.normalizer, accepted)
            for accepted in accepted_values
        ):
            results[field_name] = FieldResult(
                status="match",
                found=extracted.value,
                expected=expected,
                reason="Value matches the customer rule after normalization.",
            )
        else:
            results[field_name] = FieldResult(
                status="mismatch",
                found=extracted.value,
                expected=expected,
                reason="Value differs from the configured customer rule.",
            )

    return ValidationResult(fields=results)


def _normalize(normalizer: NormalizerName, value: str) -> str | None:
    if normalizer in {"text", "identifier"}:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        if normalizer == "text":
            spaced = "".join(character if character.isalnum() else " " for character in normalized)
            return " ".join(spaced.split()) or None
        return "".join(character for character in normalized if character.isalnum()) or None

    if normalizer == "hs_code":
        compact = re.sub(r"[\s.\-/]", "", value)
        if not re.fullmatch(r"\d{4,10}", compact):
            return None
        return compact

    return _normalize_weight(value)


def normalize_value(normalizer: NormalizerName, value: str) -> str | None:
    return _normalize(normalizer, value)


def _normalize_weight(value: str) -> str | None:
    match = re.fullmatch(
        r"\s*([+-]?[\d,]+(?:\.\d+)?)\s*([a-zA-Z]+)\s*",
        value,
    )
    if match is None:
        return None

    try:
        amount = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None

    unit = match.group(2).casefold()
    kilograms_per_unit = {
        "g": Decimal("0.001"),
        "gram": Decimal("0.001"),
        "grams": Decimal("0.001"),
        "kg": Decimal("1"),
        "kgs": Decimal("1"),
        "kilogram": Decimal("1"),
        "kilograms": Decimal("1"),
        "lb": Decimal("0.45359237"),
        "lbs": Decimal("0.45359237"),
        "pound": Decimal("0.45359237"),
        "pounds": Decimal("0.45359237"),
        "t": Decimal("1000"),
        "mt": Decimal("1000"),
        "ton": Decimal("1000"),
        "tons": Decimal("1000"),
        "tonne": Decimal("1000"),
        "tonnes": Decimal("1000"),
    }.get(unit)
    if kilograms_per_unit is None or amount <= 0:
        return None

    kilograms = (amount * kilograms_per_unit).quantize(Decimal("0.001"))
    return format(kilograms.normalize(), "f")