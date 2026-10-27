import logging

from powerrules.conditions.matcher import MatchType, StringMatcher
from powerrules.engine.exceptions import ConditionEvaluationError
from powerrules.providers.process import ProcessProvider

logger = logging.getLogger(__name__)


class ProcessCondition:
    def __init__(
        self,
        process_name: str,
        expected_exists: bool,
        # Basically a wrapper object to interact with the OS to provide information about the existing processes
        process_provider: ProcessProvider,
        match_type: MatchType = MatchType.EXACT,
        case_sensitive: bool = True,
    ):
        self.process_name = process_name
        self.expected_exists = expected_exists
        self.process_provider = process_provider
        self.matcher = StringMatcher(process_name, match_type, case_sensitive)

    def evaluate(self) -> bool:
        """Evaluate whether the configured process is in the expected state.

        Returns:
            True if the process state matches the expected state.

        Raises:
            ConditionEvaluationError: If the process state cannot be determined.
        """
        try:
            process_names = self.process_provider.get_process_names()

            is_existing = any(
                self.matcher.matches(process_name) for process_name in process_names
            )
        except Exception as e:
            raise ConditionEvaluationError(
                f"Failed to determine whether process '{self.process_name}' exists"
            ) from e

        is_met = is_existing == self.expected_exists

        # The explanation needs a second pass over all names, so it is only built if the message is going to be logged
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"Process condition {'met' if is_met else 'not met'}, "
                f"{self.matcher.explain_existence(process_names, 'process name', self.expected_exists)}"
            )

        return is_met
