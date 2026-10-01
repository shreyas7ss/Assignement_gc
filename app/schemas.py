from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


FieldName = Literal[
    "consignee_name",
    "hs_code",
    "port_of_loading",
    "port_of_discharge",
    "incoterms",
    "goods_description",
    "gross_weight",
    "invoice_number",
]

FIELD_NAMES: tuple[FieldName, ...] = (
    "consignee_name",
    "hs_code",
    "port_of_loading",
    "port_of_discharge",
    "incoterms",
    "goods_description",
    "gross_weight",
    "invoice_number",
)


class FieldValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None
    confidence: float = Field(ge=0, le=1)
    source_quote: str | None
    page: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_grounding_for_value(self) -> "FieldValue":
        if self.value is not None and not self.source_quote:
            raise ValueError("non-null values require a source_quote")
        return self


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consignee_name: FieldValue
    hs_code: FieldValue
    port_of_loading: FieldValue
    port_of_discharge: FieldValue
    incoterms: FieldValue
    goods_description: FieldValue
    gross_weight: FieldValue
    invoice_number: FieldValue

    def field_values(self) -> dict[FieldName, FieldValue]:
        return {name: getattr(self, name) for name in FIELD_NAMES}


class FieldResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["match", "mismatch", "uncertain"]
    found: str | None = None
    expected: str | None = None
    reason: str

    @model_validator(mode="after")
    def require_comparison_values_for_mismatch(self) -> "FieldResult":
        if self.status == "mismatch" and (self.found is None or self.expected is None):
            raise ValueError("mismatches require both found and expected values")
        return self


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: dict[FieldName, FieldResult]

    @model_validator(mode="after")
    def require_all_fields(self) -> "ValidationResult":
        missing = set(FIELD_NAMES) - self.fields.keys()
        if missing:
            raise ValueError(f"validation is missing fields: {', '.join(sorted(missing))}")
        return self


class AmendmentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: FieldName
    found: str
    expected: str


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["auto_approve", "human_review", "amendment_request"]
    reasoning: str = Field(min_length=1)
    amendment_draft: list[AmendmentItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_amendments_only_for_amendment_request(self) -> "Decision":
        if self.outcome == "amendment_request" and not self.amendment_draft:
            raise ValueError("amendment_request requires at least one amendment item")
        if self.outcome != "amendment_request" and self.amendment_draft:
            raise ValueError("amendment_draft is only valid for amendment_request")
        return self