import difflib
import re
from collections.abc import Sequence
from enum import StrEnum
from re import Pattern

# Longer values are cut off in explanations, so a debug message stays readable
_MAX_EXPLAINED_VALUE_LENGTH = 200
# Number of matching values which are listed in an explanation, the rest is only counted
_MAX_LISTED_VALUES = 5
# Number of similar values which are suggested if nothing matches
_MAX_SIMILAR_VALUES = 3


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

    def describe_matching(self) -> str:
        """Describe what a matching value looks like, e.g. "containing 'active' (ignoring case)".

        Returns:
            The description, which continues a sentence like "expected: a text ...".
        """
        if self.match_type == MatchType.EXACT:
            description = f"equal to {self.pattern!r}"
        elif self.match_type == MatchType.CONTAINS:
            description = f"containing {self.pattern!r}"
        else:
            description = f"matching the regular expression {self.pattern!r} completely"

        return description if self.case_sensitive else f"{description} (ignoring case)"

    def explain_expected_and_got(self, value: str) -> str:
        """Describe the expectation and the compared value in the style of "expected: ..., got: ...".

        This is meant for debug messages which make it easier to understand why a value does (not) match.

        Args:
            value: Value which was compared with the pattern.

        Returns:
            The explanation. A long value is shortened.
        """
        explanation = (
            f"expected: a text {self.describe_matching()}, got: {self._shorten(value)}"
        )

        # The most common mistake with a regular expression: It finds the text, but does not cover the whole value
        if (
            self._compiled_pattern is not None
            and self._compiled_pattern.fullmatch(value) is None
            and self._compiled_pattern.search(value) is not None
        ):
            explanation += " (the pattern matches a part of the value, but the whole value has to match)"

        return explanation

    def explain_existence(
        self, values: Sequence[str], subject: str, expected_exists: bool
    ) -> str:
        """Describe a search for a matching value among several values in the style of "expected: ..., got: ...".

        This is meant for debug messages of conditions which check whether something exists (e.g. a process).
        Only the matching values are listed, not all values, which keeps the message short and does not reveal unrelated values.

        Args:
            values: All values which were searched, e.g. the names of all processes.
            subject: Singular name of one value, used in the message (e.g. "process name"). The plural adds an "s".
            expected_exists: Whether a matching value is expected to exist.

        Returns:
            The explanation. If nothing matches although a match is expected, similar values are suggested.
        """
        plural_subject = f"{subject}s"
        existence = "to exist" if expected_exists else "not to exist"
        matching_values = [value for value in values if self.matches(value)]

        if matching_values:
            listed_values = ", ".join(
                self._shorten(value) for value in matching_values[:_MAX_LISTED_VALUES]
            )
            unlisted_count = len(matching_values) - _MAX_LISTED_VALUES
            unlisted_note = f" and {unlisted_count} more" if unlisted_count > 0 else ""
            found = f"{len(matching_values)} of {len(values)} {plural_subject} matching: {listed_values}{unlisted_note}"
        else:
            found = f"none of {len(values)} {plural_subject} matching"
            similar_values = (
                self._find_similar_values(values) if expected_exists else []
            )

            if similar_values:
                found += f" (similar: {', '.join(self._shorten(value) for value in similar_values)})"

        return f"expected: a {subject} {self.describe_matching()} {existence}, got: {found}"

    def _find_similar_values(self, values: Sequence[str]) -> list[str]:
        """Find values which are similar to the pattern, e.g. because they differ in their case or have a typo.

        Args:
            values: Values which are searched.

        Returns:
            The most similar values. A regular expression has no meaningful similarity, so nothing is returned for it.
        """
        if self.match_type == MatchType.REGEX:
            return []

        # The comparison ignores the case, so a value which only differs in its case is found
        values_by_folded_value = {value.casefold(): value for value in values}
        close_matches = difflib.get_close_matches(
            self.pattern.casefold(),
            list(values_by_folded_value),
            n=_MAX_SIMILAR_VALUES,
        )

        return [values_by_folded_value[match] for match in close_matches]

    @staticmethod
    def _shorten(value: str) -> str:
        """Return the representation of a value. A long value is cut off."""
        if len(value) <= _MAX_EXPLAINED_VALUE_LENGTH:
            return repr(value)

        omitted_length = len(value) - _MAX_EXPLAINED_VALUE_LENGTH

        return f"{value[:_MAX_EXPLAINED_VALUE_LENGTH]!r}... ({omitted_length} more characters)"

    def _compile_pattern(self) -> Pattern[str] | None:
        if self.match_type != MatchType.REGEX:
            return None

        # "." also matches line breaks, so a pattern like ".*error.*" works on multi-line command output
        flags = re.DOTALL

        # Ignore case if case_sensitive is False
        if not self.case_sensitive:
            flags |= re.IGNORECASE

        return re.compile(self.pattern, flags)
