from powerrules.conditions.matcher import MatchType, StringMatcher


def test_string_matcher_matches_exact_string_case_sensitive() -> None:
    matcher = StringMatcher(
        pattern="test", match_type=MatchType.EXACT, case_sensitive=True
    )
    assert matcher.matches("test") is True
    assert matcher.matches("TEST") is False


def test_string_matcher_matches_exact_string_case_insensitive() -> None:
    matcher = StringMatcher(
        pattern="test", match_type=MatchType.EXACT, case_sensitive=False
    )
    assert matcher.matches("test") is True
    assert matcher.matches("TEST") is True


def test_string_matcher_matches_regex_case_sensitive() -> None:
    matcher = StringMatcher(
        pattern="test", match_type=MatchType.REGEX, case_sensitive=True
    )
    assert matcher.matches("test") is True
    assert matcher.matches("TEST") is False


def test_string_matcher_matches_regex_case_insensitive() -> None:
    matcher = StringMatcher(
        pattern="test", match_type=MatchType.REGEX, case_sensitive=False
    )
    assert matcher.matches("test") is True
    assert matcher.matches("TEST") is True


def test_string_matcher_matches_regex_with_string_in_full_match_format_case_sensitive() -> (
    None
):
    matcher = StringMatcher(
        pattern="^test$", match_type=MatchType.REGEX, case_sensitive=True
    )
    assert matcher.matches("test") is True
    assert matcher.matches("TEST") is False


def test_string_matcher_matches_regex_with_string_in_full_match_format_case_insensitive() -> (
    None
):
    matcher = StringMatcher(
        pattern="^test$", match_type=MatchType.REGEX, case_sensitive=False
    )
    assert matcher.matches("test") is True
    assert matcher.matches("TEST") is True
