from powerrules.conditions.matcher import MatchType, StringMatcher
from powerrules.engine.exceptions import (
    ConditionEvaluationError,
    ConditionEvaluationProviderNotAvailableError,
)
from powerrules.providers.window import WindowProvider


class WindowCondition:
    def __init__(
        self,
        window_title: str,
        expected_exists: bool,
        # Basically a wrapper object to interact with the OS to provide information about the existing windows
        window_provider: WindowProvider,
        match_type: MatchType = MatchType.EXACT,
        case_sensitive: bool = True,
    ):
        self.window_title = window_title
        self.expected_exists = expected_exists
        self.window_provider = window_provider
        self.matcher = StringMatcher(
            pattern=window_title,
            match_type=match_type,
            case_sensitive=case_sensitive,
        )

    def evaluate(self) -> bool:
        """Evaluate whether the configured window is in the expected state.

        Returns:
            True if the window state matches the expected state.

        Raises:
            ConditionEvaluationError: If the window state cannot be determined.
            ConditionEvaluationProviderNotAvailableError: If the window provider is not available on the current platform.
        """
        if not self.window_provider.is_available:
            raise ConditionEvaluationProviderNotAvailableError(
                f"Window provider is not available, cannot evaluate window condition for '{self.window_title}'"
            )

        try:
            window_titles = self.window_provider.get_window_titles()

            window_exists = any(self.matcher.matches(title) for title in window_titles)
        except Exception as e:
            raise ConditionEvaluationError(
                f"Failed to determine whether window '{self.window_title}' exists"
            ) from e

        return window_exists == self.expected_exists
