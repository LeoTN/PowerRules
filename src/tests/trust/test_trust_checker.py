import logging
from pathlib import Path
from unittest.mock import Mock

import pytest

from powerrules.engine.exceptions import (
    FileIntegrityError,
    PolicyNotTrustedError,
    TrustStoreError,
)
from powerrules.trust.checker import PolicyTrustChecker
from powerrules.trust.store import TrustStore
from tests.helpers import (
    EMPTY_POLICY_CONTENT,
    corrupt_trust_store,
    create_symlink,
    get_log_messages,
    modify_file,
    trust_current_content,
    write_resolved_file,
)

LOGGER_NAME = "powerrules.trust.checker"


##############
# verify tests
##############


def test_checker_accepts_trusted_policy_and_files(
    trust_store: TrustStore,
    policy: Path,
    script: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    trust_current_content(trust_store, policy, script)
    reporter = Mock()

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        PolicyTrustChecker(trust_store, require_trust=True, reporter=reporter).verify(
            policy, EMPTY_POLICY_CONTENT, (script,)
        )

    reporter.assert_called_once()
    assert reporter.call_args.args[0].is_trusted is True
    assert get_log_messages(caplog, LOGGER_NAME, min_level=logging.WARNING) == []


def test_checker_rejects_policy_which_was_never_trusted(
    trust_store: TrustStore, policy: Path
) -> None:
    reporter = Mock()

    with pytest.raises(PolicyNotTrustedError, match="are not trusted"):
        PolicyTrustChecker(trust_store, require_trust=True, reporter=reporter).verify(
            policy, EMPTY_POLICY_CONTENT
        )

    # The report is shown even though the policy is rejected
    reporter.assert_called_once()
    assert reporter.call_args.args[0].is_trusted is False


def test_checker_rejects_modified_policy(trust_store: TrustStore, policy: Path) -> None:
    trust_current_content(trust_store, policy)

    with pytest.raises(PolicyNotTrustedError):
        PolicyTrustChecker(trust_store, require_trust=True).verify(
            policy, EMPTY_POLICY_CONTENT + b"# changed"
        )


def test_checker_rejects_modified_trusted_file(
    trust_store: TrustStore, policy: Path, script: Path
) -> None:
    trust_current_content(trust_store, policy, script)
    modify_file(script)

    with pytest.raises(PolicyNotTrustedError):
        PolicyTrustChecker(trust_store, require_trust=True).verify(
            policy, EMPTY_POLICY_CONTENT, (script,)
        )


def test_checker_rejects_trusted_file_which_was_added_later(
    trust_store: TrustStore, policy: Path, script: Path
) -> None:
    trust_current_content(trust_store, policy)

    with pytest.raises(PolicyNotTrustedError):
        PolicyTrustChecker(trust_store, require_trust=True).verify(
            policy, EMPTY_POLICY_CONTENT, (script,)
        )


def test_checker_reports_all_entries_even_if_the_policy_is_not_trusted(
    trust_store: TrustStore, policy: Path, script: Path
) -> None:
    reporter = Mock()

    with pytest.raises(PolicyNotTrustedError):
        PolicyTrustChecker(trust_store, require_trust=True, reporter=reporter).verify(
            policy, EMPTY_POLICY_CONTENT, (script,)
        )

    assert [entry.path for entry in reporter.call_args.args[0].entries] == [
        policy,
        script,
    ]


def test_checker_only_warns_if_trust_is_not_required(
    trust_store: TrustStore, policy: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        PolicyTrustChecker(trust_store, require_trust=False).verify(
            policy, EMPTY_POLICY_CONTENT
        )

    assert len(get_log_messages(caplog, LOGGER_NAME, min_level=logging.WARNING)) == 1
    assert (
        "are not trusted"
        in get_log_messages(caplog, LOGGER_NAME, min_level=logging.WARNING)[0]
    )


def test_checker_works_without_reporter(trust_store: TrustStore, policy: Path) -> None:
    trust_current_content(trust_store, policy)

    PolicyTrustChecker(trust_store, require_trust=True).verify(
        policy, EMPTY_POLICY_CONTENT
    )


def test_checker_shows_command_to_trust_the_policy(
    trust_store: TrustStore, policy: Path
) -> None:
    command_builder = Mock(return_value="pwru trust add --policy test.yaml")
    checker = PolicyTrustChecker(
        trust_store, require_trust=True, trust_command_builder=command_builder
    )

    with pytest.raises(
        PolicyNotTrustedError,
        match="run this command to trust them: pwru trust add --policy test.yaml",
    ):
        checker.verify(policy, EMPTY_POLICY_CONTENT)

    command_builder.assert_called_once_with(policy)


def test_checker_mentions_trust_command_without_command_builder(
    trust_store: TrustStore, policy: Path
) -> None:
    with pytest.raises(PolicyNotTrustedError, match="run 'trust add' to trust them"):
        PolicyTrustChecker(trust_store, require_trust=True).verify(
            policy, EMPTY_POLICY_CONTENT
        )


def test_checker_propagates_unusable_store_if_trust_is_required(
    trust_store: TrustStore, policy: Path
) -> None:
    corrupt_trust_store(trust_store)

    with pytest.raises(TrustStoreError):
        PolicyTrustChecker(trust_store, require_trust=True).verify(
            policy, EMPTY_POLICY_CONTENT
        )


def test_checker_treats_unusable_store_as_not_trusted_if_trust_is_not_required(
    trust_store: TrustStore, policy: Path, caplog: pytest.LogCaptureFixture
) -> None:
    corrupt_trust_store(trust_store)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        PolicyTrustChecker(trust_store, require_trust=False).verify(
            policy, EMPTY_POLICY_CONTENT
        )

    assert "treating the policy as not trusted" in caplog.text


####################
# verify_files tests
####################


def test_checker_verifies_unchanged_files(
    trust_store: TrustStore,
    policy: Path,
    script: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    trust_current_content(trust_store, policy, script)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        PolicyTrustChecker(trust_store, require_trust=True).verify_files(
            policy, (script,)
        )

    assert get_log_messages(caplog, LOGGER_NAME, min_level=logging.WARNING) == []


def test_checker_verifies_without_files(trust_store: TrustStore, policy: Path) -> None:
    PolicyTrustChecker(trust_store, require_trust=True).verify_files(policy, ())


def test_checker_rejects_file_which_was_modified_after_trusting(
    trust_store: TrustStore, policy: Path, script: Path
) -> None:
    trust_current_content(trust_store, policy, script)
    modify_file(script)

    with pytest.raises(FileIntegrityError, match="was modified since it was trusted"):
        PolicyTrustChecker(trust_store, require_trust=True).verify_files(
            policy, (script,)
        )


def test_checker_rejects_file_which_is_not_trusted(
    trust_store: TrustStore, policy: Path, script: Path
) -> None:
    trust_current_content(trust_store, policy)

    with pytest.raises(FileIntegrityError, match="is not trusted yet"):
        PolicyTrustChecker(trust_store, require_trust=True).verify_files(
            policy, (script,)
        )


def test_checker_rejects_files_of_policy_which_was_never_trusted(
    trust_store: TrustStore, policy: Path, script: Path
) -> None:
    with pytest.raises(FileIntegrityError, match="is not trusted yet"):
        PolicyTrustChecker(trust_store, require_trust=True).verify_files(
            policy, (script,)
        )


def test_checker_rejects_file_which_was_deleted(
    trust_store: TrustStore, policy: Path, script: Path
) -> None:
    trust_current_content(trust_store, policy, script)
    script.unlink()

    with pytest.raises(FileIntegrityError, match="cannot be read"):
        PolicyTrustChecker(trust_store, require_trust=True).verify_files(
            policy, (script,)
        )


def test_checker_reports_all_problematic_files_in_one_error(
    tmp_path: Path, trust_store: TrustStore, policy: Path, script: Path
) -> None:
    other = tmp_path / "other.sh"
    write_resolved_file(other, "other")
    trust_current_content(trust_store, policy, script, other)
    modify_file(script)
    modify_file(other)

    with pytest.raises(FileIntegrityError) as exc_info:
        PolicyTrustChecker(trust_store, require_trust=True).verify_files(
            policy, (script, other)
        )

    assert str(script) in str(exc_info.value)
    assert str(other) in str(exc_info.value)


def test_checker_shows_trust_command_when_files_are_rejected(
    trust_store: TrustStore, policy: Path, script: Path
) -> None:
    checker = PolicyTrustChecker(
        trust_store,
        require_trust=True,
        trust_command_builder=lambda path: f"pwru trust add --policy {path.name}",
    )

    with pytest.raises(FileIntegrityError, match="pwru trust add --policy"):
        checker.verify_files(policy, (script,))


def test_checker_only_warns_about_files_if_trust_is_not_required(
    trust_store: TrustStore,
    policy: Path,
    script: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    trust_current_content(trust_store, policy, script)
    modify_file(script)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        PolicyTrustChecker(trust_store, require_trust=False).verify_files(
            policy, (script,)
        )

    assert get_log_messages(caplog, LOGGER_NAME, min_level=logging.WARNING) == [
        f"File '{script}' was modified since it was trusted"
    ]


def test_checker_detects_link_which_was_pointed_to_another_file(
    tmp_path: Path, trust_store: TrustStore, policy: Path, script: Path
) -> None:
    other = tmp_path / "other.sh"
    write_resolved_file(other, "other")
    link = tmp_path / "link.sh"

    create_symlink(link, script)

    trust_current_content(trust_store, policy, link)
    link.unlink()
    link.symlink_to(other)

    with pytest.raises(FileIntegrityError, match="is not trusted yet"):
        PolicyTrustChecker(trust_store, require_trust=True).verify_files(
            policy, (link,)
        )


def test_checker_propagates_unusable_store_when_verifying_files(
    trust_store: TrustStore, policy: Path, script: Path
) -> None:
    corrupt_trust_store(trust_store)

    with pytest.raises(TrustStoreError):
        PolicyTrustChecker(trust_store, require_trust=True).verify_files(
            policy, (script,)
        )


def test_checker_treats_unusable_store_as_not_trusted_when_verifying_files(
    trust_store: TrustStore,
    policy: Path,
    script: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    corrupt_trust_store(trust_store)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        PolicyTrustChecker(trust_store, require_trust=False).verify_files(
            policy, (script,)
        )

    assert "treating the files as not trusted" in caplog.text
