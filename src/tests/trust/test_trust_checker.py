import logging
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from powerrules.engine.exceptions import (
    FileIntegrityError,
    PolicyNotTrustedError,
    TrustStoreError,
)
from powerrules.trust.checker import PolicyTrustChecker
from powerrules.trust.store import (
    TrustStore,
    compute_digest,
    compute_trusted_file_digests,
)

LOGGER_NAME = "powerrules.trust.checker"
TRUSTED_AT = datetime(2026, 10, 17, 14, 3)
POLICY_CONTENT = b"rules: []\n"


@pytest.fixture
def store(tmp_path: Path) -> TrustStore:
    return TrustStore(tmp_path / "store" / "trust.json")


@pytest.fixture
def policy(tmp_path: Path) -> Path:
    path = tmp_path / "powerrules.yaml"
    path.write_bytes(POLICY_CONTENT)

    return path.resolve()


@pytest.fixture
def script(tmp_path: Path) -> Path:
    path = tmp_path / "backup.sh"
    path.write_text("echo backup", encoding="utf-8")

    return path.resolve()


def _trust(store: TrustStore, policy: Path, *files: Path) -> None:
    """Trust the current content of the policy and the files."""
    store.trust(
        policy,
        compute_digest(policy.read_bytes()),
        TRUSTED_AT,
        compute_trusted_file_digests(policy.parent, files),
    )


def _get_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == LOGGER_NAME and record.levelno >= logging.WARNING
    ]


def _corrupt(store: TrustStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("not json", encoding="utf-8")


##############
# verify tests
##############


def test_checker_accepts_trusted_policy_and_files(
    store: TrustStore,
    policy: Path,
    script: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _trust(store, policy, script)
    reporter = Mock()

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        PolicyTrustChecker(store, require_trust=True, reporter=reporter).verify(
            policy, POLICY_CONTENT, (script,)
        )

    reporter.assert_called_once()
    assert reporter.call_args.args[0].is_trusted is True
    assert _get_warnings(caplog) == []


def test_checker_rejects_policy_which_was_never_trusted(
    store: TrustStore, policy: Path
) -> None:
    reporter = Mock()

    with pytest.raises(PolicyNotTrustedError, match="are not trusted"):
        PolicyTrustChecker(store, require_trust=True, reporter=reporter).verify(
            policy, POLICY_CONTENT
        )

    # The report is shown even though the policy is rejected
    reporter.assert_called_once()
    assert reporter.call_args.args[0].is_trusted is False


def test_checker_rejects_modified_policy(store: TrustStore, policy: Path) -> None:
    _trust(store, policy)

    with pytest.raises(PolicyNotTrustedError):
        PolicyTrustChecker(store, require_trust=True).verify(
            policy, POLICY_CONTENT + b"# changed"
        )


def test_checker_rejects_modified_trusted_file(
    store: TrustStore, policy: Path, script: Path
) -> None:
    _trust(store, policy, script)
    script.write_text("echo changed", encoding="utf-8")

    with pytest.raises(PolicyNotTrustedError):
        PolicyTrustChecker(store, require_trust=True).verify(
            policy, POLICY_CONTENT, (script,)
        )


def test_checker_rejects_trusted_file_which_was_added_later(
    store: TrustStore, policy: Path, script: Path
) -> None:
    _trust(store, policy)

    with pytest.raises(PolicyNotTrustedError):
        PolicyTrustChecker(store, require_trust=True).verify(
            policy, POLICY_CONTENT, (script,)
        )


def test_checker_reports_all_entries_even_if_the_policy_is_not_trusted(
    store: TrustStore, policy: Path, script: Path
) -> None:
    reporter = Mock()

    with pytest.raises(PolicyNotTrustedError):
        PolicyTrustChecker(store, require_trust=True, reporter=reporter).verify(
            policy, POLICY_CONTENT, (script,)
        )

    assert [entry.path for entry in reporter.call_args.args[0].entries] == [
        policy,
        script,
    ]


def test_checker_only_warns_if_trust_is_not_required(
    store: TrustStore, policy: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        PolicyTrustChecker(store, require_trust=False).verify(policy, POLICY_CONTENT)

    assert len(_get_warnings(caplog)) == 1
    assert "are not trusted" in _get_warnings(caplog)[0]


def test_checker_works_without_reporter(store: TrustStore, policy: Path) -> None:
    _trust(store, policy)

    PolicyTrustChecker(store, require_trust=True).verify(policy, POLICY_CONTENT)


def test_checker_shows_command_to_trust_the_policy(
    store: TrustStore, policy: Path
) -> None:
    command_builder = Mock(return_value="pwru trust add --policy test.yaml")
    checker = PolicyTrustChecker(
        store, require_trust=True, trust_command_builder=command_builder
    )

    with pytest.raises(
        PolicyNotTrustedError,
        match="run this command to trust them: pwru trust add --policy test.yaml",
    ):
        checker.verify(policy, POLICY_CONTENT)

    command_builder.assert_called_once_with(policy)


def test_checker_mentions_trust_command_without_command_builder(
    store: TrustStore, policy: Path
) -> None:
    with pytest.raises(PolicyNotTrustedError, match="run 'trust add' to trust them"):
        PolicyTrustChecker(store, require_trust=True).verify(policy, POLICY_CONTENT)


def test_checker_propagates_unusable_store_if_trust_is_required(
    store: TrustStore, policy: Path
) -> None:
    _corrupt(store)

    with pytest.raises(TrustStoreError):
        PolicyTrustChecker(store, require_trust=True).verify(policy, POLICY_CONTENT)


def test_checker_treats_unusable_store_as_not_trusted_if_trust_is_not_required(
    store: TrustStore, policy: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _corrupt(store)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        PolicyTrustChecker(store, require_trust=False).verify(policy, POLICY_CONTENT)

    assert "treating the policy as not trusted" in caplog.text


####################
# verify_files tests
####################


def test_checker_verifies_unchanged_files(
    store: TrustStore,
    policy: Path,
    script: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _trust(store, policy, script)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        PolicyTrustChecker(store, require_trust=True).verify_files(policy, (script,))

    assert _get_warnings(caplog) == []


def test_checker_verifies_without_files(store: TrustStore, policy: Path) -> None:
    PolicyTrustChecker(store, require_trust=True).verify_files(policy, ())


def test_checker_rejects_file_which_was_modified_after_trusting(
    store: TrustStore, policy: Path, script: Path
) -> None:
    _trust(store, policy, script)
    script.write_text("echo changed", encoding="utf-8")

    with pytest.raises(FileIntegrityError, match="was modified since it was trusted"):
        PolicyTrustChecker(store, require_trust=True).verify_files(policy, (script,))


def test_checker_rejects_file_which_is_not_trusted(
    store: TrustStore, policy: Path, script: Path
) -> None:
    _trust(store, policy)

    with pytest.raises(FileIntegrityError, match="is not trusted yet"):
        PolicyTrustChecker(store, require_trust=True).verify_files(policy, (script,))


def test_checker_rejects_files_of_policy_which_was_never_trusted(
    store: TrustStore, policy: Path, script: Path
) -> None:
    with pytest.raises(FileIntegrityError, match="is not trusted yet"):
        PolicyTrustChecker(store, require_trust=True).verify_files(policy, (script,))


def test_checker_rejects_file_which_was_deleted(
    store: TrustStore, policy: Path, script: Path
) -> None:
    _trust(store, policy, script)
    script.unlink()

    with pytest.raises(FileIntegrityError, match="cannot be read"):
        PolicyTrustChecker(store, require_trust=True).verify_files(policy, (script,))


def test_checker_reports_all_problematic_files_in_one_error(
    tmp_path: Path, store: TrustStore, policy: Path, script: Path
) -> None:
    other = tmp_path / "other.sh"
    other.write_text("echo other", encoding="utf-8")
    other = other.resolve()
    _trust(store, policy, script, other)
    script.write_text("echo changed", encoding="utf-8")
    other.write_text("echo changed", encoding="utf-8")

    with pytest.raises(FileIntegrityError) as exc_info:
        PolicyTrustChecker(store, require_trust=True).verify_files(
            policy, (script, other)
        )

    assert str(script) in str(exc_info.value)
    assert str(other) in str(exc_info.value)


def test_checker_shows_trust_command_when_files_are_rejected(
    store: TrustStore, policy: Path, script: Path
) -> None:
    checker = PolicyTrustChecker(
        store,
        require_trust=True,
        trust_command_builder=lambda path: f"pwru trust add --policy {path.name}",
    )

    with pytest.raises(FileIntegrityError, match="pwru trust add --policy"):
        checker.verify_files(policy, (script,))


def test_checker_only_warns_about_files_if_trust_is_not_required(
    store: TrustStore,
    policy: Path,
    script: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _trust(store, policy, script)
    script.write_text("echo changed", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        PolicyTrustChecker(store, require_trust=False).verify_files(policy, (script,))

    assert _get_warnings(caplog) == [
        f"File '{script}' was modified since it was trusted"
    ]


def test_checker_detects_link_which_was_pointed_to_another_file(
    tmp_path: Path, store: TrustStore, policy: Path, script: Path
) -> None:
    other = tmp_path / "other.sh"
    other.write_text("echo other", encoding="utf-8")
    link = tmp_path / "link.sh"

    try:
        link.symlink_to(script)
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are not available")

    _trust(store, policy, link)
    link.unlink()
    link.symlink_to(other)

    with pytest.raises(FileIntegrityError, match="is not trusted yet"):
        PolicyTrustChecker(store, require_trust=True).verify_files(policy, (link,))


def test_checker_propagates_unusable_store_when_verifying_files(
    store: TrustStore, policy: Path, script: Path
) -> None:
    _corrupt(store)

    with pytest.raises(TrustStoreError):
        PolicyTrustChecker(store, require_trust=True).verify_files(policy, (script,))


def test_checker_treats_unusable_store_as_not_trusted_when_verifying_files(
    store: TrustStore,
    policy: Path,
    script: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _corrupt(store)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        PolicyTrustChecker(store, require_trust=False).verify_files(policy, (script,))

    assert "treating the files as not trusted" in caplog.text
