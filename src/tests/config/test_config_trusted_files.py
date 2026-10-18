from datetime import datetime
from pathlib import Path
from typing import cast
from unittest.mock import Mock, create_autospec

import pytest
from pydantic import ValidationError

from powerrules.config.builder import ConfigurationBuilder
from powerrules.config.loader import ConfigurationLoader
from powerrules.config.models import ActionConfiguration, RuleSetConfiguration
from powerrules.engine.exceptions import PolicyNotTrustedError
from powerrules.trust.checker import PolicyTrustChecker
from tests.mocks import (
    make_clock_provider,
    make_command_provider,
    make_process_provider,
    make_window_provider,
)

BASE_DIRECTORY = Path("policies")


def _make_rule(
    name: str, files: list[str], *, enabled: bool = True
) -> dict[str, object]:
    return {
        "name": name,
        "enabled": enabled,
        "conditions": {"process": {"name": "backup.exe", "exists": False}},
        "actions": [{"run": "echo test", "trusted_files": files}],
    }


#########################################
# ActionConfiguration.trusted_files tests
#########################################


def test_action_configuration_has_no_trusted_files_by_default() -> None:
    assert ActionConfiguration.model_validate({"run": "echo test"}).trusted_files == []


def test_action_configuration_does_not_share_trusted_files_between_instances() -> None:
    first = ActionConfiguration.model_validate({"run": "echo test"})
    first.trusted_files.append(Path("a.sh"))

    assert ActionConfiguration.model_validate({"run": "echo test"}).trusted_files == []


def test_action_configuration_converts_trusted_files_to_paths() -> None:
    action = ActionConfiguration.model_validate(
        {"run": "echo test", "trusted_files": ["scripts/a.sh", "/opt/b.sh"]}
    )

    assert action.trusted_files == [Path("scripts/a.sh"), Path("/opt/b.sh")]


@pytest.mark.parametrize("files", [[""], ["   "], ["a.sh", ""], ["a.sh", " \t"]])
def test_action_configuration_rejects_blank_trusted_file(files: list[str]) -> None:
    with pytest.raises(
        ValidationError, match="'trusted_files' entries must not be blank"
    ):
        ActionConfiguration.model_validate({"run": "echo test", "trusted_files": files})


@pytest.mark.parametrize("files", ["a.sh", {"a": "b"}])
def test_action_configuration_rejects_trusted_files_which_are_not_a_list(
    files: object,
) -> None:
    with pytest.raises(ValidationError, match="valid list"):
        ActionConfiguration.model_validate({"run": "echo test", "trusted_files": files})


def test_rule_set_returns_trusted_files_of_all_rules_including_disabled_ones() -> None:
    configuration = RuleSetConfiguration.model_validate(
        {
            "rules": [
                _make_rule("First", ["a.sh", "b.sh"]),
                _make_rule("Disabled", ["b.sh", "c.sh"], enabled=False),
            ]
        }
    )

    # Duplicates are removed later by "resolve_trusted_files()"
    assert configuration.get_trusted_files() == (
        Path("a.sh"),
        Path("b.sh"),
        Path("b.sh"),
        Path("c.sh"),
    )


def test_rule_set_without_trusted_files_returns_empty_tuple() -> None:
    configuration = RuleSetConfiguration.model_validate(
        {"rules": [_make_rule("First", [])]}
    )

    assert configuration.get_trusted_files() == ()


###############
# Builder tests
###############


def _make_builder(files_verifier: object | None = None) -> ConfigurationBuilder:
    return ConfigurationBuilder(
        clock_provider=make_clock_provider(datetime(2026, 10, 17, 12, 0)),
        process_provider=make_process_provider(),
        command_provider=make_command_provider(),
        window_provider=make_window_provider(),
        base_directory=BASE_DIRECTORY,
        files_verifier=files_verifier,  # type: ignore[arg-type]
    )


def test_builder_joins_trusted_files_with_base_directory_without_resolving_them(
    tmp_path: Path,
) -> None:
    absolute_file = tmp_path / "absolute.sh"
    configuration = RuleSetConfiguration.model_validate(
        {"rules": [_make_rule("Test rule", ["scripts/a.sh", str(absolute_file)])]}
    )

    action = _make_builder().build(configuration).rules[0].actions[0]

    # Symbolic links are resolved by the verifier on every check, not once here
    assert action.trusted_files == (  # type: ignore[attr-defined]
        BASE_DIRECTORY / "scripts" / "a.sh",
        absolute_file,
    )


def test_builder_passes_files_verifier_to_actions() -> None:
    files_verifier = create_autospec(lambda files: None)
    configuration = RuleSetConfiguration.model_validate(
        {"rules": [_make_rule("Test rule", ["a.sh"])]}
    )

    action = _make_builder(files_verifier).build(configuration).rules[0].actions[0]

    assert action.files_verifier is files_verifier  # type: ignore[attr-defined]


def test_builder_builds_actions_without_trusted_files() -> None:
    configuration = RuleSetConfiguration.model_validate(
        {"rules": [_make_rule("Test rule", [])]}
    )

    action = _make_builder().build(configuration).rules[0].actions[0]

    assert action.trusted_files == ()  # type: ignore[attr-defined]


#################################
# ConfigurationLoader trust tests
#################################

POLICY_WITH_DUPLICATE_FILES = """
rules:
  - name: "Test rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    actions:
      - run: "first"
        trusted_files:
          - scripts/a.sh
      - run: "second"
        trusted_files:
          - ./scripts/a.sh
          - b.sh
"""


def _write_policy(directory: Path, content: str = POLICY_WITH_DUPLICATE_FILES) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    policy = directory / "powerrules.yaml"
    policy.write_text(content, encoding="utf-8")

    return policy


def _make_checker() -> PolicyTrustChecker:
    return create_autospec(PolicyTrustChecker, instance=True, spec_set=True)


def test_loader_verifies_policy_content_and_unique_resolved_files(
    tmp_path: Path,
) -> None:
    policy = _write_policy(tmp_path)
    checker = _make_checker()

    ConfigurationLoader(trust_checker=checker).load(policy)

    cast(Mock, checker.verify).assert_called_once_with(
        policy.resolve(),
        policy.read_bytes(),
        (tmp_path.resolve() / "scripts" / "a.sh", tmp_path.resolve() / "b.sh"),
    )


def test_loader_resolves_trusted_files_against_directory_of_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _write_policy(tmp_path / "policies")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    checker = _make_checker()

    ConfigurationLoader(trust_checker=checker).load(policy)

    files = cast(Mock, checker.verify).call_args.args[2]

    assert all(file.is_relative_to((tmp_path / "policies").resolve()) for file in files)


def test_loader_resolves_symbolic_link_of_policy_before_verifying(
    tmp_path: Path,
) -> None:
    policy = _write_policy(tmp_path / "real")
    link = tmp_path / "link.yaml"

    try:
        link.symlink_to(policy)
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are not available")

    checker = _make_checker()

    ConfigurationLoader(trust_checker=checker).load(link)

    assert cast(Mock, checker.verify).args[0] == policy.resolve()
    # The files belong to the directory of the real policy
    assert (
        cast(Mock, checker.verify).args[2][0].parent.parent
        == (tmp_path / "real").resolve()
    )


def test_loader_does_not_verify_invalid_policy(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path, 'rules:\n  - name: "Invalid"\n')
    checker = _make_checker()

    with pytest.raises(ValidationError):
        ConfigurationLoader(trust_checker=checker).load(policy)

    cast(Mock, checker.verify).assert_not_called()


def test_loader_propagates_trust_error(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path)
    checker = _make_checker()
    cast(Mock, checker.verify).side_effect = PolicyNotTrustedError(
        "Test policy is not trusted"
    )

    with pytest.raises(PolicyNotTrustedError, match="Test policy is not trusted"):
        ConfigurationLoader(trust_checker=checker).load(policy)


def test_loader_skips_trust_check_without_checker(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path)

    assert len(ConfigurationLoader().load(policy).rules) == 1
