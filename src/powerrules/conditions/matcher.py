import re
from enum import StrEnum
from re import Pattern


class MatchType(StrEnum):
    """Supported string matching modes."""

    EXACT = "exact"
    REGEX = "regex"
    CONTAINS = "contains"


class StringMatcher:
    """Match strings using the configured matching settings. Defaults to exact case-sensitive matching."""

    def __init__(
        self,
        pattern: str,
        match_type: MatchType = MatchType.EXACT,
        case_sensitive: bool = True,
    ) -> None:
        self.pattern = pattern
        self.match_type = match_type
        self.case_sensitive = case_sensitive
        self._compiled_pattern = self._compile_pattern()

    def matches(self, value: str) -> bool:
        """Return whether the given value matches the configured pattern."""
        if self.match_type == MatchType.EXACT:
            if self.case_sensitive:
                return value == self.pattern

            return value.casefold() == self.pattern.casefold()

        if self.match_type == MatchType.CONTAINS:
            if self.case_sensitive:
                return self.pattern in value

            return self.pattern.casefold() in value.casefold()

        return (
            self._compiled_pattern is not None
            and self._compiled_pattern.fullmatch(value) is not None
        )

    def _compile_pattern(self) -> Pattern[str] | None:
        if self.match_type != MatchType.REGEX:
            return None

        # "." also matches line breaks, so a pattern like ".*error.*" works on multi-line command output
        flags = re.DOTALL

        # Ignore case if case_sensitive is False
        if not self.case_sensitive:
            flags |= re.IGNORECASE

        return re.compile(self.pattern, flags)
