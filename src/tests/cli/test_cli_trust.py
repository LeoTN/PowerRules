import re
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from powerrules.cli.app import app
from powerrules.cli.errors import EXIT_POLICY_ERROR, EXIT_POLICY_TRUST_ERROR
from powerrules.trust.store import (
    TRUST_STORE_DIRECTORY_NAME,
    TRUST_STORE_FILE_NAME,
    TrustStore,
)
from tests.factories import trust_policies_with_each_status, write_backup_script_policy
from tests.helpers import (
    BACKUP_SCRIPT_RELATIVE_PATH,
    get_plain_output,
    get_table_row,
    modify_file,
    read_log_file,
    trust_policy_via_cli,
)

runner = CliRunner()


#############
# Group tests
#############


def test_cli_trust_displays_help() -> None:
    result = runner.invoke(app, ["trust", "--help"])

    assert result.exit_code == 0
    assert "Manage which policies are trusted." in get_plain_output(result)

    for command in ("add", "remove", "list"):
        assert command in get_plain_output(result)


#################
# trust add tests
#################


def test_cli_trust_add_trusts_policy_and_shows_table(tmp_path: Path) -> None:
    policy_file = write_backup_script_policy(tmp_path)

    result = runner.invoke(app, ["trust", "add", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert f"Policy '{policy_file}' is now trusted" in get_plain_output(result)
    assert "Trust status" in get_plain_output(result)
    assert "Trusted at" in get_plain_output(result)
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", result.stdout)
    assert str(policy_file.resolve()) in get_plain_output(result)
    assert str((tmp_path / BACKUP_SCRIPT_RELATIVE_PATH).resolve()) in get_plain_output(
        result
    )
    assert TrustStore().get_entry(policy_file) is not None


def test_cli_trust_add_writes_status_only_to_the_log_file(tmp_path: Path) -> None:
    policy_file = write_backup_script_policy(tmp_path)

    result = runner.invoke(app, ["trust", "add", "--policy", str(policy_file)])

    message = f"Policy '{policy_file.resolve()}' is trusted"

    assert message not in result.output
    assert message in read_log_file(tmp_path)


def test_cli_trust_add_uses_default_policy_in_current_directory(
    tmp_path: Path,
) -> None:
    write_backup_script_policy(tmp_path)

    result = runner.invoke(app, ["trust", "add"])

    assert result.exit_code == 0
    assert TrustStore().get_entry(tmp_path / "powerrules.yaml") is not None


def test_cli_trust_add_trusts_the_current_content_again(tmp_path: Path) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    script = tmp_path / BACKUP_SCRIPT_RELATIVE_PATH
    modify_file(script)

    result = runner.invoke(app, ["trust", "add", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert "modified" not in get_plain_output(result)


def test_cli_trust_add_rejects_missing_policy(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["trust", "add", "--policy", str(tmp_path / "missing.yaml")]
    )

    assert result.exit_code == EXIT_POLICY_ERROR
    assert "Policy file not found" in result.output


def test_cli_trust_add_does_not_trust_invalid_policy(tmp_path: Path) -> None:
    policy_file = tmp_path / "powerrules.yaml"
    policy_file.write_text('rules:\n  - name: "Invalid"\n', encoding="utf-8")

    result = runner.invoke(app, ["trust", "add", "--policy", str(policy_file)])

    assert result.exit_code == EXIT_POLICY_ERROR
    assert "Policy validation failed" in result.output
    assert TrustStore().get_entry(policy_file) is None


def test_cli_trust_add_does_not_trust_policy_with_missing_file(tmp_path: Path) -> None:
    policy_file = write_backup_script_policy(tmp_path, create_script=False)

    result = runner.invoke(app, ["trust", "add", "--policy", str(policy_file)])

    assert result.exit_code == EXIT_POLICY_TRUST_ERROR
    assert "cannot be read" in result.output
    assert TrustStore().get_entry(policy_file) is None


####################
# trust remove tests
####################


def test_cli_trust_remove_removes_trust(tmp_path: Path) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)

    result = runner.invoke(app, ["trust", "remove", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert f"Policy '{policy_file}' is no longer trusted" in get_plain_output(result)
    assert TrustStore().get_entry(policy_file) is None


def test_cli_trust_remove_reports_policy_which_was_not_trusted(tmp_path: Path) -> None:
    policy_file = write_backup_script_policy(tmp_path)

    result = runner.invoke(app, ["trust", "remove", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert f"Policy '{policy_file}' was not trusted" in get_plain_output(result)


def test_cli_trust_remove_works_for_deleted_policy(tmp_path: Path) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    policy_file.unlink()

    result = runner.invoke(app, ["trust", "remove", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert "is no longer trusted" in get_plain_output(result)


##################
# trust list tests
##################


def test_cli_trust_list_reports_empty_store() -> None:
    result = runner.invoke(app, ["trust", "list"])

    assert result.exit_code == 0
    assert "No policies are trusted" in get_plain_output(result)
    assert "Trust status" not in get_plain_output(result)


def test_cli_trust_list_shows_current_status_of_every_policy(tmp_path: Path) -> None:
    unchanged = write_backup_script_policy(tmp_path / "a")
    modified = write_backup_script_policy(tmp_path / "b")
    deleted = write_backup_script_policy(tmp_path / "c")

    for policy_file in (unchanged, modified, deleted):
        trust_policy_via_cli(policy_file)

    # The trust list has to show the status which is valid now, not the one of the time of trusting
    modify_file(modified)
    deleted.unlink()

    result = runner.invoke(app, ["trust", "list"])

    assert result.exit_code == 0
    assert "Trusted at" in get_plain_output(result)

    assert "trusted" in get_table_row(result.stdout, unchanged.resolve())
    assert "modified" in get_table_row(result.stdout, modified.resolve())
    assert "missing" in get_table_row(result.stdout, deleted.resolve())
    # The files are listed below their policy
    assert "trusted" in get_table_row(
        result.stdout, (tmp_path / "a" / BACKUP_SCRIPT_RELATIVE_PATH).resolve()
    )


def test_cli_trust_list_shows_policies_sorted_by_path(tmp_path: Path) -> None:
    second = write_backup_script_policy(tmp_path / "b")
    first = write_backup_script_policy(tmp_path / "a")
    trust_policy_via_cli(second)
    trust_policy_via_cli(first)

    output = runner.invoke(app, ["trust", "list"]).stdout

    assert output.index(str(first.resolve())) < output.index(str(second.resolve()))


def test_cli_trust_list_reports_modified_file_below_trusted_policy(
    tmp_path: Path,
) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    modify_file(tmp_path / BACKUP_SCRIPT_RELATIVE_PATH)

    result = runner.invoke(app, ["trust", "list"])

    assert "trusted" in get_table_row(result.stdout, policy_file.resolve())
    assert "modified" in get_table_row(
        result.stdout, (tmp_path / BACKUP_SCRIPT_RELATIVE_PATH).resolve()
    )


def test_cli_trust_list_reports_unusable_trust_store(isolated_home: Path) -> None:
    store_file = isolated_home / TRUST_STORE_DIRECTORY_NAME / TRUST_STORE_FILE_NAME
    store_file.parent.mkdir()
    store_file.write_text("not json", encoding="utf-8")

    result = runner.invoke(app, ["trust", "list"])

    assert result.exit_code == 1
    assert "corrupted or has an unsupported format" in result.output


###############################
# policy validate and run tests
###############################


def test_cli_policy_validate_shows_table_once_with_unknown_status(
    tmp_path: Path,
) -> None:
    policy_file = write_backup_script_policy(tmp_path)

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert "Trust status" in get_plain_output(result)
    assert "unknown" in get_plain_output(result)
    assert "trust add --policy" in result.output
    # The messages of the single entries are only written to the log file
    assert "is not trusted yet" not in result.output
    assert "is not trusted yet" in read_log_file(tmp_path)


def test_cli_policy_validate_shows_trusted_status(tmp_path: Path) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert "Trust status" in get_plain_output(result)
    assert "unknown" not in get_plain_output(result)
    assert "modified" not in get_plain_output(result)
    assert "is valid" in get_plain_output(result)


def test_cli_policy_validate_reports_modified_policy(tmp_path: Path) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    modify_file(policy_file)

    result = runner.invoke(app, ["policy", "validate", "--policy", str(policy_file)])

    assert result.exit_code == 0
    assert "modified" in get_table_row(result.stdout, policy_file.resolve())


def test_cli_policy_run_rejects_untrusted_policy(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = write_backup_script_policy(tmp_path)

    result = runner.invoke(
        app, ["policy", "run", "--once", "--policy", str(policy_file)]
    )

    assert result.exit_code == EXIT_POLICY_TRUST_ERROR
    assert "trust add --policy" in result.output
    command_provider.run.assert_not_called()


def test_cli_policy_run_runs_trusted_policy(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)

    result = runner.invoke(
        app, ["policy", "run", "--once", "--policy", str(policy_file)]
    )

    assert result.exit_code == 0
    command_provider.run.assert_called_once()


def test_cli_policy_run_rejects_modified_policy(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    modify_file(policy_file)

    result = runner.invoke(
        app, ["policy", "run", "--once", "--policy", str(policy_file)]
    )

    assert result.exit_code == EXIT_POLICY_TRUST_ERROR
    assert "modified" in get_plain_output(result)
    command_provider.run.assert_not_called()


def test_cli_policy_run_rejects_modified_trusted_file(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    modify_file(tmp_path / BACKUP_SCRIPT_RELATIVE_PATH)

    result = runner.invoke(
        app, ["policy", "run", "--once", "--policy", str(policy_file)]
    )

    assert result.exit_code == EXIT_POLICY_TRUST_ERROR
    assert "modified" in get_table_row(
        result.stdout, (tmp_path / BACKUP_SCRIPT_RELATIVE_PATH).resolve()
    )
    command_provider.run.assert_not_called()


def test_cli_policy_run_can_skip_trust_requirement(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = write_backup_script_policy(tmp_path)

    result = runner.invoke(
        app,
        ["policy", "run", "--once", "--no-require-trust", "--policy", str(policy_file)],
    )

    assert result.exit_code == 0
    assert "are not trusted" in result.output
    command_provider.run.assert_called_once()


def test_cli_policy_run_dry_run_does_not_require_trust(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = write_backup_script_policy(tmp_path)

    result = runner.invoke(
        app, ["policy", "run", "--once", "--dry-run", "--policy", str(policy_file)]
    )

    assert result.exit_code == 0
    assert "[DRY RUN] Rule 'Test rule' matched" in get_plain_output(result)
    assert "Trust status" in get_plain_output(result)
    command_provider.run.assert_not_called()


def test_cli_policy_run_does_not_run_policy_after_trust_was_removed(
    tmp_path: Path, command_provider: Mock
) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    runner.invoke(app, ["trust", "remove", "--policy", str(policy_file)])

    result = runner.invoke(
        app, ["policy", "run", "--once", "--policy", str(policy_file)]
    )

    assert result.exit_code == EXIT_POLICY_TRUST_ERROR
    command_provider.run.assert_not_called()


###################
# trust prune tests
###################


def test_cli_trust_prune_removes_stale_policy_without_confirmation(
    tmp_path: Path,
) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    policy_file.unlink()

    result = runner.invoke(app, ["trust", "prune", "--yes"])

    assert result.exit_code == 0
    assert "Removed 1 policy from the trust store" in get_plain_output(result)
    assert TrustStore().get_entry(policy_file) is None


def test_cli_trust_prune_shows_the_policies_which_are_removed(tmp_path: Path) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    policy_file.unlink()

    result = runner.invoke(app, ["trust", "prune", "--yes"])

    assert "missing" in get_table_row(result.stdout, policy_file.resolve())


def test_cli_trust_prune_keeps_existing_policies_and_uses_plural(
    tmp_path: Path,
) -> None:
    policies = trust_policies_with_each_status(tmp_path)
    second_deleted = write_backup_script_policy(tmp_path / "d")
    trust_policy_via_cli(second_deleted)
    second_deleted.unlink()

    result = runner.invoke(app, ["trust", "prune", "--yes"])

    assert result.exit_code == 0
    assert "Removed 2 policies from the trust store" in get_plain_output(result)
    assert TrustStore().get_entry(policies["a"]) is not None
    # A modified policy still exists, so it is not pruned
    assert TrustStore().get_entry(policies["b"]) is not None
    assert TrustStore().get_entry(policies["c"]) is None
    assert TrustStore().get_entry(second_deleted) is None


def test_cli_trust_prune_reports_nothing_to_prune_for_empty_store() -> None:
    result = runner.invoke(app, ["trust", "prune"])

    assert result.exit_code == 0
    assert "Nothing to prune" in get_plain_output(result)


def test_cli_trust_prune_reports_nothing_to_prune_if_all_policies_exist(
    tmp_path: Path,
) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)

    result = runner.invoke(app, ["trust", "prune"])

    assert result.exit_code == 0
    assert "Nothing to prune" in get_plain_output(result)
    assert TrustStore().get_entry(policy_file) is not None


def test_cli_trust_prune_dry_run_keeps_policies_and_does_not_ask(
    tmp_path: Path,
) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    policy_file.unlink()

    # No input is given, so a confirmation prompt would abort the command
    result = runner.invoke(app, ["trust", "prune", "--dry-run"])

    assert result.exit_code == 0
    assert "[DRY RUN] Would remove 1 policy" in get_plain_output(result)
    assert "Removed" not in get_plain_output(result)
    assert TrustStore().get_entry(policy_file) is not None


def test_cli_trust_prune_removes_policy_after_confirmation(tmp_path: Path) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    policy_file.unlink()

    result = runner.invoke(app, ["trust", "prune"], input="y\n")

    assert result.exit_code == 0
    assert "Remove 1 policy from the trust store?" in get_plain_output(result)
    assert TrustStore().get_entry(policy_file) is None


@pytest.mark.parametrize("answer", ["n\n", ""], ids=["declined", "no-input"])
def test_cli_trust_prune_keeps_policy_if_not_confirmed(
    tmp_path: Path, answer: str
) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    policy_file.unlink()

    result = runner.invoke(app, ["trust", "prune"], input=answer)

    assert result.exit_code == 1
    assert "Aborted" in result.output
    # An abort is no unexpected error
    assert "Unexpected error" not in result.output
    assert TrustStore().get_entry(policy_file) is not None


def test_cli_trust_prune_reports_unusable_trust_store(isolated_home: Path) -> None:
    store_file = isolated_home / TRUST_STORE_DIRECTORY_NAME / TRUST_STORE_FILE_NAME
    store_file.parent.mkdir()
    store_file.write_text("not json", encoding="utf-8")

    result = runner.invoke(app, ["trust", "prune", "--yes"])

    assert result.exit_code == 1
    assert "corrupted or has an unsupported format" in result.output


#########################
# trust list filter tests
#########################


@pytest.mark.parametrize(
    ("flags", "expected_names"),
    [
        (["--trusted"], {"a"}),
        (["--modified"], {"b"}),
        (["--missing"], {"c"}),
        (["--trusted", "--modified"], {"a", "b"}),
        (["--modified", "--missing"], {"b", "c"}),
        (["--trusted", "--modified", "--missing"], {"a", "b", "c"}),
    ],
)
def test_cli_trust_list_filters_policies_by_status(
    tmp_path: Path,
    flags: list[str],
    expected_names: set[str],
) -> None:
    policies = trust_policies_with_each_status(tmp_path)

    result = runner.invoke(app, ["trust", "list", *flags])

    assert result.exit_code == 0

    for name, policy_file in policies.items():
        assert (str(policy_file.resolve()) in get_plain_output(result)) is (
            name in expected_names
        )


def test_cli_trust_list_filter_matches_policy_with_modified_trusted_file(
    tmp_path: Path,
) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)
    script = (tmp_path / BACKUP_SCRIPT_RELATIVE_PATH).resolve()
    modify_file(script)

    modified_result = runner.invoke(app, ["trust", "list", "--modified"])
    trusted_result = runner.invoke(app, ["trust", "list", "--trusted"])

    # The policy itself is unchanged, but it is only trusted if its files are as well
    assert "trusted" in get_table_row(modified_result.stdout, policy_file.resolve())
    assert "modified" in get_table_row(modified_result.stdout, script)
    assert str(policy_file.resolve()) not in get_plain_output(trusted_result)


def test_cli_trust_list_reports_no_match_without_table(tmp_path: Path) -> None:
    policy_file = write_backup_script_policy(tmp_path)
    trust_policy_via_cli(policy_file)

    result = runner.invoke(app, ["trust", "list", "--missing"])

    assert result.exit_code == 0
    assert "No trusted policies match the selected filters" in get_plain_output(result)
    assert "Trust status" not in get_plain_output(result)


def test_cli_trust_list_with_filter_reports_empty_store() -> None:
    result = runner.invoke(app, ["trust", "list", "--modified"])

    assert result.exit_code == 0
    assert "No policies are trusted" in get_plain_output(result)
