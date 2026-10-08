"""Pure causal-validity classification for the F01 verifier."""

VALIDITY_CLASSES = {
    "valid_model_outcome",
    "external_infra_invalid",
    "task_invalid",
    "indeterminate_integrity",
}


def classify_causal_validity(
    reason: str | None,
    *,
    candidate_execution_started: bool,
    override: str | None = None,
) -> str:
    """Classify without inventing a pre-start cause after candidate action."""

    if override is not None:
        if override not in VALIDITY_CLASSES:
            raise ValueError(f"unknown causal-validity override: {override}")
        return override
    if reason == "verifier_selfcheck_failed":
        return "task_invalid"
    if reason in {
        "indeterminate_integrity",
        "database_mutation",
        "tampered_hidden_db",
    }:
        return "indeterminate_integrity"
    if reason == "external_infra_invalid":
        return "external_infra_invalid"
    if reason in {
        "verifier_error",
        "verifier_isolation_failed",
        "verifier_budget_exhausted",
    }:
        return (
            "indeterminate_integrity"
            if candidate_execution_started
            else "external_infra_invalid"
        )
    return "valid_model_outcome"
