import pytest

from powerrules.conditions.operators import AndCondition, NotCondition, OrCondition
from powerrules.engine.exceptions import ConditionEvaluationError
from tests.mocks import make_condition


def test_nested_conditions_are_evaluated_correctly() -> None:
    condition = AndCondition(
        conditions=(
            make_condition(True),
            NotCondition(
                condition=OrCondition(
                    conditions=(
                        make_condition(False),
                        make_condition(False),
                    )
                )
            ),
        )
    )

    assert condition.evaluate() is True


####################
# AndCondition tests
####################


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        ((True, True, True), True),
        ((True, False, True), False),
        ((False, True, True), False),
        ((True, True, False), False),
        ((False, False, False), False),
        ((True,), True),
        ((False,), False),
    ],
)
def test_and_condition_matches_only_when_all_conditions_match(
    results: tuple[bool, ...],
    expected: bool,
) -> None:
    condition = AndCondition(
        conditions=tuple(make_condition(result) for result in results)
    )

    assert condition.evaluate() is expected


# Not reachable through the configuration (it requires at least two conditions), but it documents the behavior
def test_and_condition_without_conditions_matches() -> None:
    assert AndCondition(conditions=()).evaluate() is True


def test_and_condition_stores_conditions_as_tuple() -> None:
    first_condition = make_condition(True)
    second_condition = make_condition(True)

    condition = AndCondition(conditions=[first_condition, second_condition])

    assert condition.conditions == (first_condition, second_condition)


# Does the evaluation stop after the first false condition is found?
def test_and_condition_short_circuits_after_first_false_condition() -> None:
    first_condition = make_condition(False)
    second_condition = make_condition(True)

    condition = AndCondition(
        conditions=(
            first_condition,
            second_condition,
        )
    )

    assert condition.evaluate() is False
    first_condition.evaluate.assert_called_once_with()
    second_condition.evaluate.assert_not_called()


def test_and_condition_propagates_condition_evaluation_error() -> None:
    condition = AndCondition(
        conditions=(
            make_condition(
                True, error=ConditionEvaluationError("Test condition failed")
            ),
        )
    )

    with pytest.raises(ConditionEvaluationError, match="Test condition failed"):
        condition.evaluate()


# The error is never raised, because the evaluation already stopped
def test_and_condition_does_not_evaluate_failing_condition_after_false_condition() -> (
    None
):
    failing_condition = make_condition(
        error=ConditionEvaluationError("Test condition failed")
    )

    condition = AndCondition(conditions=(make_condition(False), failing_condition))

    assert condition.evaluate() is False
    failing_condition.evaluate.assert_not_called()


###################
# OrCondition tests
###################


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        ((False, False, False), False),
        ((False, True, False), True),
        ((True, False, False), True),
        ((False, False, True), True),
        ((True, True, True), True),
        ((True,), True),
        ((False,), False),
    ],
)
def test_or_condition_matches_when_at_least_one_condition_matches(
    results: tuple[bool, ...],
    expected: bool,
) -> None:
    condition = OrCondition(
        conditions=tuple(make_condition(result) for result in results)
    )

    assert condition.evaluate() is expected


# Not reachable through the configuration (it requires at least two conditions), but it documents the behavior
def test_or_condition_without_conditions_does_not_match() -> None:
    assert OrCondition(conditions=()).evaluate() is False


def test_or_condition_stores_conditions_as_tuple() -> None:
    first_condition = make_condition(False)
    second_condition = make_condition(False)

    condition = OrCondition(conditions=[first_condition, second_condition])

    assert condition.conditions == (first_condition, second_condition)


# Does the evaluation stop after the first true condition is found?
def test_or_condition_short_circuits_after_first_true_condition() -> None:
    first_condition = make_condition(True)
    second_condition = make_condition(False)

    condition = OrCondition(
        conditions=(
            first_condition,
            second_condition,
        )
    )

    assert condition.evaluate() is True
    first_condition.evaluate.assert_called_once_with()
    second_condition.evaluate.assert_not_called()


def test_or_condition_propagates_condition_evaluation_error() -> None:
    condition = OrCondition(
        conditions=(
            make_condition(
                True, error=ConditionEvaluationError("Test condition failed")
            ),
        )
    )

    with pytest.raises(ConditionEvaluationError, match="Test condition failed"):
        condition.evaluate()


# The error is never raised, because the evaluation already stopped
def test_or_condition_does_not_evaluate_failing_condition_after_true_condition() -> (
    None
):
    failing_condition = make_condition(
        error=ConditionEvaluationError("Test condition failed")
    )

    condition = OrCondition(conditions=(make_condition(True), failing_condition))

    assert condition.evaluate() is True
    failing_condition.evaluate.assert_not_called()


####################
# NotCondition tests
####################


def test_not_condition_matches_when_child_does_not_match() -> None:
    condition = NotCondition(
        condition=make_condition(False),
    )

    assert condition.evaluate() is True


def test_not_condition_does_not_match_when_child_matches() -> None:
    condition = NotCondition(
        condition=make_condition(True),
    )

    assert condition.evaluate() is False


def test_not_condition_propagates_condition_evaluation_error() -> None:
    condition = NotCondition(
        condition=make_condition(
            True, error=ConditionEvaluationError("Test condition failed")
        ),
    )

    with pytest.raises(
        ConditionEvaluationError,
        match="Test condition failed",
    ):
        condition.evaluate()
