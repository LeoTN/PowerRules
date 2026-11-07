from typing import Protocol


class Condition(Protocol):
    def evaluate(self) -> bool:
        """Evaluate the condition.

        Returns:
            True if the condition matches, otherwise False.

        Raises:
            ConditionEvaluationError: If the condition cannot be evaluated.
            FileIntegrityError: If trust is required and a trusted file of a command condition cannot be read,
                is not trusted yet or was modified.
        """
        ...
