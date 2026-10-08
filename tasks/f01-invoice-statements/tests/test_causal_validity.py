import pytest

from causal_validity import classify_causal_validity


def test_generic_verifier_failure_is_external_only_before_candidate_start():
    assert classify_causal_validity(
        "verifier_error", candidate_execution_started=False
    ) == "external_infra_invalid"
    assert classify_causal_validity(
        "verifier_error", candidate_execution_started=True
    ) == "indeterminate_integrity"


def test_verifier_budget_exhaustion_is_phase_aware():
    assert classify_causal_validity(
        "verifier_budget_exhausted", candidate_execution_started=False
    ) == "external_infra_invalid"
    assert classify_causal_validity(
        "verifier_budget_exhausted", candidate_execution_started=True
    ) == "indeterminate_integrity"


def test_known_causal_classes_do_not_depend_on_phase():
    assert classify_causal_validity(
        "verifier_selfcheck_failed", candidate_execution_started=True
    ) == "task_invalid"
    assert classify_causal_validity(
        "external_infra_invalid", candidate_execution_started=True
    ) == "external_infra_invalid"
    assert classify_causal_validity(
        "database_mutation", candidate_execution_started=False
    ) == "indeterminate_integrity"
    assert classify_causal_validity(
        "task_timeout", candidate_execution_started=True
    ) == "valid_model_outcome"


def test_explicit_override_is_validated():
    assert classify_causal_validity(
        "verifier_error",
        candidate_execution_started=True,
        override="task_invalid",
    ) == "task_invalid"
    with pytest.raises(ValueError, match="unknown causal-validity override"):
        classify_causal_validity(
            "verifier_error",
            candidate_execution_started=False,
            override="made_up",
        )
