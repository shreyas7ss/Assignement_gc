from app.schemas import AmendmentItem, Decision, ValidationResult


def route_validation(validation: ValidationResult) -> Decision:
    uncertain_fields = [
        name for name, result in validation.fields.items() if result.status == "uncertain"
    ]
    mismatches = [
        (name, result)
        for name, result in validation.fields.items()
        if result.status == "mismatch"
    ]

    if uncertain_fields:
        reason = (
            "Human review is required because these fields are uncertain: "
            f"{', '.join(uncertain_fields)}."
        )
        if mismatches:
            mismatch_names = ", ".join(name for name, _ in mismatches)
            reason += f" Mismatches also need review: {mismatch_names}."
        return Decision(outcome="human_review", reasoning=reason)

    if mismatches:
        amendment_draft = [
            AmendmentItem(
                field=name,
                found=result.found,
                expected=result.expected,
            )
            for name, result in mismatches
        ]
        details = "; ".join(
            f"{item.field}: found '{item.found}', expected '{item.expected}'"
            for item in amendment_draft
        )
        return Decision(
            outcome="amendment_request",
            reasoning=f"Request correction for mismatched fields: {details}.",
            amendment_draft=amendment_draft,
        )

    return Decision(
        outcome="auto_approve",
        reasoning=(
            "All required fields matched the customer rules with sufficient confidence."
        ),
    )