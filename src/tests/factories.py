"""Factories for objects which are shared by the tests.

Plain helper functions are defined in "tests.helpers", fixtures in the "conftest.py" files.
"""

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, create_autospec

from pydantic import BaseModel, ValidationError

from powerrules.actions.base import Action
from powerrules.actions.command import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    CommandAction,
    FilesVerifier,
)
from powerrules.application.runtime import PlatformProviders, PowerRulesRuntime
from powerrules.application.trust import trust_policy
from powerrules.commands.runner import CommandRunner
from powerrules.conditions.base import Condition
from powerrules.conditions.command import CommandCondition
from powerrules.conditions.datetime import DateTimeCondition, Month, Weekday
from powerrules.conditions.matcher import StringMatcher
from powerrules.config.builder import ConfigurationBuilder
from powerrules.config.loader import ConfigurationLoader
from powerrules.config.models import (
    ActionConfiguration,
    CommandConditionConfiguration,
    ConditionConfiguration,
    DateRangeConfiguration,
    DateTimeConditionConfiguration,
    DateTimeRangeConfiguration,
    MatchConfiguration,
    ProcessConditionConfiguration,
    RuleConfiguration,
    RuleSetConfiguration,
    TimeRangeConfiguration,
    WindowConditionConfiguration,
)
from powerrules.engine.models import Rule, RuleEvaluationResult
from powerrules.engine.rule_engine import RuleEngine
from powerrules.providers.clock import ClockProvider
from powerrules.providers.command import (
    CommandProvider,
    CommandRequest,
    CommandResult,
    Shell,
)
from powerrules.providers.process import ProcessProvider
from powerrules.providers.window import WindowProvider
from powerrules.trust.checker import PolicyTrustChecker
from powerrules.trust.report import TrustReport, TrustReportEntry
from powerrules.trust.store import (
    TrustedFileEntry,
    TrustEntry,
    TrustStatus,
    TrustStore,
    compute_file_digest,
    make_path_key,
)
from tests.helpers import (
    BACKUP_SCRIPT_RELATIVE_PATH,
    DEFAULT_BASE_DIRECTORY,
    DEFAULT_NOW_SATURDAY_NOON,
    DEFAULT_WORKING_DIRECTORY,
    TRUSTED_AT,
    modify_file,
    trust_policy_via_cli,
    write_policy,
    write_workspace_scripts,
)

# The kinds of "between" which a datetime condition configuration accepts
BetweenRangeConfiguration = (
    TimeRangeConfiguration | DateRangeConfiguration | DateTimeRangeConfiguration
)


############
# Conditions
############


def make_condition(
    result: bool = True,
    *,
    error: Exception | None = None,
) -> Mock:
    """Create a mocked condition.

    Args:
        result: Value returned by "evaluate()".
        error: Exception raised by "evaluate()" instead of returning the result.

    Returns:
        A mock which only allows the interface of "Condition".
    """
    condition = create_autospec(Condition, instance=True, spec_set=True)

    if error is not None:
        condition.evaluate.side_effect = error
    else:
        condition.evaluate.return_value = result

    return condition


#########
# Actions
#########


def make_action(
    name: str = "Test action",
    *,
    error: Exception | None = None,
) -> Mock:
    """Create a mocked action.

    Args:
        name: Value of the "name" property.
        error: Exception raised by "execute()".

    Returns:
        A mock which only allows the interface of "Action".
    """
    action = create_autospec(Action, instance=True, spec_set=True)
    action.name = name

    if error is not None:
        action.execute.side_effect = error

    return action


def make_command_action(
    command_provider: CommandProvider | None = None,
    *,
    command: str = "echo test",
    working_directory: Path = DEFAULT_WORKING_DIRECTORY,
    name: str = "Test action",
    rule_name: str = "Test rule",
    shell: Shell | None = None,
    environment: Mapping[str, str] | None = None,
    timeout: float | None = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    success_exit_codes: Collection[int] = (0,),
    wait: bool = True,
    continue_on_error: bool = False,
    trusted_files: Sequence[Path] = (),
    files_verifier: FilesVerifier | None = None,
    stdout_matcher: StringMatcher | None = None,
    stderr_matcher: StringMatcher | None = None,
) -> CommandAction:
    """Create a real command action with fixed names and the given options.

    Args:
        command_provider: Provider which runs the command. Defaults to a mocked one.
        command: Command to run.
        working_directory: Directory the command is run in.
        name: Name of the action.
        rule_name: Name of the rule the action belongs to.
        shell: Shell to run the command with.
        environment: Additional environment variables for the command.
        timeout: Maximum run time in seconds, None for no time limit.
        success_exit_codes: Exit codes which count as success.
        wait: Whether to wait for the command to finish.
        continue_on_error: Whether a failure is only logged instead of raised.
        trusted_files: Files the command depends on.
        files_verifier: Verifier which is called with the trusted files. None skips the verification.
        stdout_matcher: Expectation for stdout. None accepts any output.
        stderr_matcher: Expectation for stderr. None accepts any output.

    Returns:
        The action.
    """
    return CommandAction(
        command_provider if command_provider is not None else make_command_provider(),
        command,
        working_directory,
        name=name,
        rule_name=rule_name,
        shell=shell,
        environment=environment,
        timeout=timeout,
        success_exit_codes=success_exit_codes,
        wait=wait,
        continue_on_error=continue_on_error,
        trusted_files=trusted_files,
        files_verifier=files_verifier,
        stdout_matcher=stdout_matcher,
        stderr_matcher=stderr_matcher,
    )


def make_command_runner(
    command_provider: CommandProvider | None = None,
    *,
    command: str = "echo test",
    working_directory: Path = DEFAULT_WORKING_DIRECTORY,
    timeout: float | None = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    shell: Shell | None = None,
    environment: Mapping[str, str] | None = None,
    success_exit_codes: Collection[int] = (0,),
    wait: bool = True,
    stdout_matcher: StringMatcher | None = None,
    stderr_matcher: StringMatcher | None = None,
    trusted_files: Sequence[Path] = (),
    files_verifier: FilesVerifier | None = None,
) -> CommandRunner:
    """Create a real command runner with the given options.

    Args:
        command_provider: Provider which runs the command. Defaults to a mocked one.
        command: Command to run.
        working_directory: Directory the command is run in.
        timeout: Maximum run time in seconds, None for no time limit.
        shell: Shell to run the command with.
        environment: Additional environment variables for the command.
        success_exit_codes: Exit codes which count as success.
        wait: Whether to wait for the command to finish.
        stdout_matcher: Expectation for stdout. None accepts any output.
        stderr_matcher: Expectation for stderr. None accepts any output.
        trusted_files: Files the command depends on.
        files_verifier: Verifier which is called with the trusted files. None skips the verification.

    Returns:
        The runner.
    """
    return CommandRunner(
        command_provider if command_provider is not None else make_command_provider(),
        command,
        working_directory,
        timeout=timeout,
        shell=shell,
        environment=environment,
        success_exit_codes=success_exit_codes,
        wait=wait,
        stdout_matcher=stdout_matcher,
        stderr_matcher=stderr_matcher,
        trusted_files=trusted_files,
        files_verifier=files_verifier,
    )


def make_command_condition(
    command_provider: CommandProvider | None = None,
    *,
    command: str = "echo test",
    working_directory: Path = DEFAULT_WORKING_DIRECTORY,
    rule_name: str = "Test rule",
    timeout: float | None = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    shell: Shell | None = None,
    environment: Mapping[str, str] | None = None,
    success_exit_codes: Collection[int] = (0,),
    stdout_matcher: StringMatcher | None = None,
    stderr_matcher: StringMatcher | None = None,
    trusted_files: Sequence[Path] = (),
    files_verifier: FilesVerifier | None = None,
) -> CommandCondition:
    """Create a real command condition with the given options.

    Args:
        command_provider: Provider which runs the command. Defaults to a mocked one.
        command: Command to run.
        working_directory: Directory the command is run in.
        rule_name: Name of the rule where the command condition is located.
        timeout: Maximum run time in seconds, None for no time limit.
        shell: Shell to run the command with.
        environment: Additional environment variables for the command.
        success_exit_codes: Exit codes which count as success.
        stdout_matcher: Expectation for stdout. None accepts any output.
        stderr_matcher: Expectation for stderr. None accepts any output.
        trusted_files: Files the command depends on.
        files_verifier: Verifier which is called with the trusted files. None skips the verification.

    Returns:
        The condition.
    """
    return CommandCondition(
        command_provider if command_provider is not None else make_command_provider(),
        command,
        working_directory,
        rule_name=rule_name,
        timeout=timeout,
        shell=shell,
        environment=environment,
        success_exit_codes=success_exit_codes,
        stdout_matcher=stdout_matcher,
        stderr_matcher=stderr_matcher,
        trusted_files=trusted_files,
        files_verifier=files_verifier,
    )


def make_files_verifier(*, error: Exception | None = None) -> Mock:
    """Create a mocked files verifier, which is called with the trusted files before an action runs.

    Args:
        error: Exception raised by the verifier. None means that the files are accepted.

    Returns:
        A mock with the signature of "FilesVerifier", which only accepts a sequence of paths.
    """

    def verify_files(_files: Sequence[Path]) -> None:
        """Signature which the mock is built from."""

    files_verifier = create_autospec(verify_files, spec_set=True)

    if error is not None:
        files_verifier.side_effect = error

    return files_verifier


def make_action_configuration(**fields: object) -> ActionConfiguration:
    """Validate an action configuration which consists of a command and the given fields.

    Args:
        **fields: Raw fields which are added to the command or replace it.

    Returns:
        The validated configuration.

    Raises:
        ValidationError: If the fields are invalid.
    """
    return ActionConfiguration.model_validate({"run": "echo test", **fields})


#######
# Rules
#######


def make_rule(
    name: str = "Test rule",
    *,
    condition: Condition | None = None,
    actions: Sequence[Action] | None = None,
    enabled: bool = True,
) -> Rule:
    """Create a rule which consists of mocks by default.

    Only the name can be passed positionally. Everything else is keyword-only,
    so a condition and an action can never be mixed up.

    Args:
        name: Name of the rule.
        condition: Condition of the rule. Defaults to a mocked condition which matches.
        actions: Actions of the rule, always a sequence (also for a single action).
            Defaults to a single mocked action, an empty sequence means no actions.
        enabled: Whether the rule is enabled.

    Returns:
        The rule.
    """
    return Rule(
        name=name,
        condition=condition if condition is not None else make_condition(),
        actions=tuple(actions) if actions is not None else (make_action(),),
        enabled=enabled,
    )


def make_rule_with_actions(*action_names: str) -> Rule:
    """Create a matching rule with mocked actions of the given names.

    Args:
        *action_names: Names of the actions. Defaults to a single action named "Shutdown".

    Returns:
        The rule.
    """
    return make_rule(
        actions=[make_action(name) for name in action_names or ("Shutdown",)]
    )


def make_rule_engine(*rules: Rule) -> RuleEngine:
    """Create a real rule engine for the given rules.

    Use "make_rule_engine_mock()" for a mocked engine.

    Args:
        *rules: Rules in the order in which they are evaluated.

    Returns:
        The rule engine.
    """
    return RuleEngine(rules)


def make_rule_engine_mock(
    result: RuleEvaluationResult | None = None,
    *,
    results: Sequence[RuleEvaluationResult] | None = None,
    error: Exception | None = None,
) -> Mock:
    """Create a mocked rule engine.

    Args:
        result: Value returned by every call of "evaluate()". Defaults to a result without a match.
            Cannot be combined with "results".
        results: Values returned by the consecutive calls of "evaluate()", one per call.
        error: Exception raised by "evaluate()" instead of returning a result.

    Returns:
        A mock which only allows the interface of "RuleEngine".

    Raises:
        ValueError: If both "result" and "results" are given.
    """
    if result is not None and results is not None:
        raise ValueError("Only one of 'result' and 'results' can be given")

    rule_engine = create_autospec(RuleEngine, instance=True, spec_set=True)

    if error is not None:
        rule_engine.evaluate.side_effect = error
    elif results is not None:
        rule_engine.evaluate.side_effect = list(results)
    else:
        rule_engine.evaluate.return_value = (
            result if result is not None else RuleEvaluationResult(matched_rule=None)
        )

    return rule_engine


########################
# Providers and platform
########################


def make_clock_provider(now: datetime) -> Mock:
    """Create a mocked clock provider.

    The time can be changed later with "clock_provider.now.return_value".

    Args:
        now: Value returned by "now()".

    Returns:
        A mock which only allows the interface of "ClockProvider".
    """
    clock_provider = create_autospec(ClockProvider, instance=True, spec_set=True)
    clock_provider.now.return_value = now

    return clock_provider


def make_command_provider(
    result: CommandResult | None = None,
    *,
    error: Exception | None = None,
) -> Mock:
    """Create a mocked command provider.

    Args:
        result: Value returned by "run()". Defaults to a successful command (exit code 0).
        error: Exception raised by "run()" instead of returning the result.

    Returns:
        A mock which only allows the interface of "CommandProvider".
    """
    command_provider = create_autospec(CommandProvider, instance=True, spec_set=True)

    if error is not None:
        command_provider.run.side_effect = error
    else:
        command_provider.run.return_value = (
            result if result is not None else CommandResult(exit_code=0)
        )

    return command_provider


def make_command_request(
    working_directory: Path,
    command: str = "echo test",
    *,
    environment: Mapping[str, str] | None = None,
    timeout: float | None = None,
    wait: bool = True,
    shell: Shell | None = None,
) -> CommandRequest:
    """Create a command request with the given options.

    Args:
        working_directory: Directory the command is run in.
        command: Command to run.
        environment: Additional environment variables.
        timeout: Maximum run time in seconds, None for no time limit.
        wait: Whether to wait for the command to finish.
        shell: Shell to run the command with. None uses the default shell of the provider.

    Returns:
        The request.
    """
    return CommandRequest(
        command=command,
        working_directory=working_directory,
        environment=environment if environment is not None else {},
        timeout=timeout,
        wait=wait,
        shell=shell,
    )


def make_process_provider(
    process_names: Iterable[str] = (),
    *,
    error: Exception | None = None,
) -> Mock:
    """Create a mocked process provider.

    Args:
        process_names: Names returned by "get_process_names()".
        error: Exception raised by "get_process_names()" instead of returning the names.

    Returns:
        A mock which only allows the interface of "ProcessProvider".
    """
    process_provider = create_autospec(ProcessProvider, instance=True, spec_set=True)

    if error is not None:
        process_provider.get_process_names.side_effect = error
    else:
        process_provider.get_process_names.return_value = tuple(process_names)

    return process_provider


def make_window_provider(
    window_titles: Iterable[str] = (),
    *,
    available: bool = True,
    error: Exception | None = None,
) -> Mock:
    """Create a mocked window provider.

    Args:
        window_titles: Titles returned by "get_window_titles()".
        available: Value of the "is_available" property.
        error: Exception raised by "get_window_titles()" instead of returning the titles.

    Returns:
        A mock which only allows the interface of "WindowProvider".
    """
    window_provider = create_autospec(WindowProvider, instance=True, spec_set=True)
    window_provider.is_available = available

    if error is not None:
        window_provider.get_window_titles.side_effect = error
    else:
        window_provider.get_window_titles.return_value = tuple(window_titles)

    return window_provider


def make_platform_providers(
    now: datetime = DEFAULT_NOW_SATURDAY_NOON,
    *,
    process_names: Iterable[str] = (),
    window_titles: Iterable[str] = (),
    command_provider: CommandProvider | None = None,
) -> PlatformProviders:
    """Create platform providers which consist of mocks only.

    Args:
        now: Value returned by the clock provider.
        process_names: Names returned by the process provider.
        window_titles: Titles returned by the window provider.
        command_provider: Provider which runs the commands. Defaults to a mocked one.

    Returns:
        The providers, e.g. as the return value of a patched "get_platform_providers()".
    """
    return PlatformProviders(
        clock=make_clock_provider(now),
        process=make_process_provider(process_names),
        window=make_window_provider(window_titles),
        command=(
            command_provider
            if command_provider is not None
            else make_command_provider()
        ),
    )


#######
# Trust
#######


def make_trust_checker() -> Mock:
    """Create a mocked trust checker.

    Returns:
        A mock which only allows the interface of "PolicyTrustChecker".
    """
    return create_autospec(PolicyTrustChecker, instance=True, spec_set=True)


def make_trusted_file_entries(*files: Path) -> dict[str, TrustedFileEntry]:
    """Create the trusted file entries of the current content of the files.

    Args:
        *files: Existing files with all symbolic links resolved.

    Returns:
        The entries keyed by the normalized path of each file.
    """
    return {
        make_path_key(file): TrustedFileEntry(
            path=str(file), digest=compute_file_digest(file)
        )
        for file in files
    }


def make_trust_entry(
    policy: Path,
    *files: Path,
) -> TrustEntry:
    """Create the entry of a policy which is trusted with its current content.

    Args:
        policy: Existing policy file with all symbolic links resolved.
        *files: Existing trusted files of the policy.

    Returns:
        The entry.
    """
    return TrustEntry(
        path=str(policy),
        digest=compute_file_digest(policy),
        trusted_at=TRUSTED_AT,
        trusted_files=make_trusted_file_entries(*files),
    )


def make_trust_report(
    policy: str = "/policies/a.yaml",
    *statuses: TrustStatus,
    policy_status: TrustStatus = TrustStatus.TRUSTED,
    trusted_at: datetime | None = TRUSTED_AT,
) -> TrustReport:
    """Create a trust report of a policy and files with the given statuses.

    Args:
        policy: Path of the policy.
        *statuses: Statuses of the files, each file is named after the policy and its position.
        policy_status: Status of the policy.
        trusted_at: Time at which the policy was trusted, None if it never was.

    Returns:
        The report.
    """
    return TrustReport(
        (
            TrustReportEntry(
                Path(policy), policy_status, is_policy=True, trusted_at=trusted_at
            ),
            *(
                TrustReportEntry(Path(f"{policy}.file{index}"), status)
                for index, status in enumerate(statuses)
            ),
        )
    )


def trust_policy_with_fixed_time(
    trust_store: TrustStore,
    policy: Path,
    *,
    trusted_at: datetime = TRUSTED_AT,
) -> None:
    """Trust the current content of a policy and its trusted files at a fixed time.

    Args:
        trust_store: Store in which the trust is saved.
        policy: Path of the policy file.
        trusted_at: Time at which the policy is trusted.
    """
    trust_policy(policy, trust_store, make_clock_provider(trusted_at))


def trust_policies_with_each_status(tmp_path: Path) -> dict[str, Path]:
    """Trust three policies and then leave "a" unchanged, modify "b" and delete "c"."""
    policies = {
        name: write_backup_script_policy(tmp_path / name) for name in ("a", "b", "c")
    }

    for policy_file in policies.values():
        trust_policy_via_cli(policy_file)

    modify_file(policies["b"])
    policies["c"].unlink()

    return policies


######################################
# Configuration models and the builder
######################################


def make_process_condition_configuration(
    name: str = "backup.exe",
    *,
    exists: bool = False,
    match: MatchConfiguration | None = None,
) -> ConditionConfiguration:
    """Create the configuration of a process condition.

    Args:
        name: Name of the process.
        exists: Whether the process is expected to exist.
        match: Matching settings. Defaults to exact case-sensitive matching.

    Returns:
        The configuration.
    """
    return ConditionConfiguration(
        process=ProcessConditionConfiguration(
            name=name,
            exists=exists,
            match=match if match is not None else MatchConfiguration(),
        )
    )


def make_window_condition_configuration(
    title: str = "Test window title",
    *,
    exists: bool = True,
    match: MatchConfiguration | None = None,
) -> ConditionConfiguration:
    """Create the configuration of a window condition.

    Args:
        title: Title of the window.
        exists: Whether the window is expected to exist.
        match: Matching settings. Defaults to exact case-sensitive matching.

    Returns:
        The configuration.
    """
    return ConditionConfiguration(
        window=WindowConditionConfiguration(
            title=title,
            exists=exists,
            match=match if match is not None else MatchConfiguration(),
        )
    )


def make_datetime_condition_configuration(
    *,
    between: BetweenRangeConfiguration | None = None,
    weekday: list[Weekday] | None = None,
    month: list[Month] | None = None,
) -> ConditionConfiguration:
    """Create the configuration of a datetime condition.

    Args:
        between: Time, date or datetime range.
        weekday: Weekdays on which the condition matches.
        month: Months in which the condition matches.

    Returns:
        The configuration.
    """
    return ConditionConfiguration(
        datetime=DateTimeConditionConfiguration(
            between=between,
            weekday=weekday,
            month=month,
        )
    )


def make_command_condition_configuration(**fields: object) -> ConditionConfiguration:
    """Create the configuration of a command condition which consists of a command and the given fields.

    Args:
        **fields: Raw fields which are added to the command or replace it.

    Returns:
        The configuration.

    Raises:
        ValidationError: If the fields are invalid.
    """
    return ConditionConfiguration(
        command=CommandConditionConfiguration.model_validate(
            {"run": "echo test", **fields}
        )
    )


def make_rule_configuration(
    name: str = "Test rule",
    *,
    conditions: ConditionConfiguration | None = None,
    actions: list[ActionConfiguration] | None = None,
    enabled: bool = True,
) -> RuleConfiguration:
    """Create the configuration of a rule with a process condition and a command action by default.

    Args:
        name: Name of the rule.
        conditions: Condition configuration. Defaults to a process condition.
        actions: Action configurations. Defaults to a single command action.
        enabled: Whether the rule is enabled.

    Returns:
        The configuration.
    """
    return RuleConfiguration(
        name=name,
        enabled=enabled,
        conditions=(
            conditions
            if conditions is not None
            else make_process_condition_configuration()
        ),
        actions=(
            actions if actions is not None else [ActionConfiguration(run="echo test")]
        ),
    )


def make_configuration_builder(
    *,
    clock_provider: ClockProvider | None = None,
    process_provider: ProcessProvider | None = None,
    window_provider: WindowProvider | None = None,
    command_provider: CommandProvider | None = None,
    base_directory: Path = DEFAULT_BASE_DIRECTORY,
    files_verifier: FilesVerifier | None = None,
    condition_files_verifier: FilesVerifier | None = None,
) -> ConfigurationBuilder:
    """Create a configuration builder. Providers which are not given are replaced by mocks.

    Args:
        clock_provider: Provider for the current time. Defaults to a mocked one at "DEFAULT_NOW_SATURDAY_NOON".
        process_provider: Provider for the processes. Defaults to a mocked one without processes.
        window_provider: Provider for the windows. Defaults to a mocked one without windows.
        command_provider: Provider which runs the commands. Defaults to a mocked one.
        base_directory: Directory of the policy.
        files_verifier: Verifier for the trusted files of actions. None skips the verification.
        condition_files_verifier: Verifier for the trusted files of command conditions. None skips the verification.

    Returns:
        The builder.
    """
    return ConfigurationBuilder(
        clock_provider=(
            clock_provider
            if clock_provider is not None
            else make_clock_provider(DEFAULT_NOW_SATURDAY_NOON)
        ),
        process_provider=(
            process_provider
            if process_provider is not None
            else make_process_provider()
        ),
        command_provider=(
            command_provider
            if command_provider is not None
            else make_command_provider()
        ),
        window_provider=(
            window_provider if window_provider is not None else make_window_provider()
        ),
        base_directory=base_directory,
        files_verifier=files_verifier,
        condition_files_verifier=condition_files_verifier,
    )


def build_rule(
    conditions: ConditionConfiguration | None = None,
    *,
    actions: list[ActionConfiguration] | None = None,
    builder: ConfigurationBuilder | None = None,
) -> Rule:
    """Build a single rule from the given condition and action configurations.

    Args:
        conditions: Condition configuration. Defaults to a process condition.
        actions: Action configurations. Defaults to a single command action.
        builder: Builder which builds the rule. Defaults to a builder with mocked providers.

    Returns:
        The built rule.
    """
    builder = builder if builder is not None else make_configuration_builder()
    configuration = RuleSetConfiguration(
        rules=[make_rule_configuration(conditions=conditions, actions=actions)]
    )

    return builder.build(configuration).rules[0]


def build_command_action(
    action: ActionConfiguration | None = None,
    *,
    builder: ConfigurationBuilder | None = None,
) -> CommandAction:
    """Build a rule with a single action configuration and return its command action.

    Args:
        action: Action configuration. Defaults to a single command action.
        builder: Builder which builds the rule. Defaults to a builder with mocked providers.

    Returns:
        The built command action.
    """
    rule = build_rule(
        actions=[action] if action is not None else None,
        builder=builder,
    )
    built_action = rule.actions[0]

    assert isinstance(built_action, CommandAction)

    return built_action


def build_datetime_condition(
    clock_provider: ClockProvider,
    *,
    between: BetweenRangeConfiguration | None = None,
    weekday: list[Weekday] | None = None,
    month: list[Month] | None = None,
) -> DateTimeCondition:
    """Build a datetime condition which uses the given clock provider.

    Args:
        clock_provider: Provider for the current time.
        between: Time, date or datetime range.
        weekday: Weekdays on which the condition matches.
        month: Months in which the condition matches.

    Returns:
        The built condition.
    """
    rule = build_rule(
        make_datetime_condition_configuration(
            between=between, weekday=weekday, month=month
        ),
        builder=make_configuration_builder(clock_provider=clock_provider),
    )

    assert isinstance(rule.condition, DateTimeCondition)

    return rule.condition


def build_command_condition(
    conditions: ConditionConfiguration | None = None,
    *,
    builder: ConfigurationBuilder | None = None,
) -> CommandCondition:
    """Build a rule with a single command condition configuration and return its command condition.

    Args:
        conditions: Condition configuration. Defaults to a command condition.
        builder: Builder which builds the rule. Defaults to a builder with mocked providers.

    Returns:
        The built command condition.
    """
    rule = build_rule(
        conditions
        if conditions is not None
        else make_command_condition_configuration(),
        builder=builder,
    )

    assert isinstance(rule.condition, CommandCondition)

    return rule.condition


def build_rule_engine_from_policy(
    directory: Path,
    policy: str,
    *,
    now: datetime = DEFAULT_NOW_SATURDAY_NOON,
    process_names: tuple[str, ...] = (),
    process_error: Exception | None = None,
    window_titles: tuple[str, ...] = (),
    window_available: bool = True,
    command_provider: CommandProvider | None = None,
) -> RuleEngine:
    """Load a policy from a file and build an engine with mocked providers.

    Args:
        directory: Directory into which the policy is written. Commands run there by default.
        policy: YAML content of the policy.
        now: Time reported by the clock provider.
        process_names: Names reported by the process provider.
        process_error: Error raised by the process provider.
        window_titles: Titles reported by the window provider.
        window_available: Whether the window provider is available.
        command_provider: Provider which runs the commands. Defaults to a mocked one.

    Returns:
        The rule engine.
    """
    policy_file = write_policy(directory, policy)

    rule_set = make_configuration_builder(
        clock_provider=make_clock_provider(now),
        process_provider=make_process_provider(process_names, error=process_error),
        window_provider=make_window_provider(window_titles, available=window_available),
        command_provider=command_provider,
        base_directory=directory,
    ).build(ConfigurationLoader().load(policy_file))

    return RuleEngine(rule_set.rules)


def build_trusted_rule_engine(
    trust_store: TrustStore,
    policy: Path,
    *,
    require_trust_for_actions: bool = True,
    require_trust_for_conditions: bool = True,
) -> RuleEngine:
    """Build the engine of a policy with the real runtime and a trust checker.

    Args:
        trust_store: Store which knows the trusted policies.
        policy: Path of the policy file.
        require_trust_for_actions: Whether a policy or file which is not trusted is rejected because of its actions.
        require_trust_for_conditions: Whether a policy with a command condition which is not trusted is rejected.

    Returns:
        The rule engine.

    Raises:
        PolicyNotTrustedError: If trust is required and the policy or a trusted file is not trusted.
    """
    runtime = PowerRulesRuntime(
        trust_checker=PolicyTrustChecker(
            trust_store,
            require_trust_for_actions=require_trust_for_actions,
            require_trust_for_conditions=require_trust_for_conditions,
        )
    )

    return runtime._build_rule_engine(policy)


#############
# Policy data
#############


def make_policy_yaml(
    *,
    rule_name: str = "Test rule",
    command: str = "echo test",
    action_name: str | None = None,
    trusted_files: Sequence[str] = (),
) -> str:
    """Create a valid policy with a single rule and a single action.

    Args:
        rule_name: Name of the rule.
        command: Command of the action.
        action_name: Name of the action. Unnamed if None.
        trusted_files: Trusted files of the action.

    Returns:
        The YAML content of the policy.
    """
    lines = [
        "rules:",
        f'  - name: "{rule_name}"',
        "    conditions:",
        "      process:",
        '        name: "backup.exe"',
        "        exists: false",
        "    actions:",
        f'      - run: "{command}"',
    ]

    if action_name is not None:
        lines.append(f'        name: "{action_name}"')

    if trusted_files:
        lines.append("        trusted_files:")
        lines.extend(f"          - {file}" for file in trusted_files)

    return "\n".join(lines) + "\n"


# A valid policy whose only action trusts the script "backup.sh"
BACKUP_SCRIPT_POLICY = make_policy_yaml(
    action_name="Backup", trusted_files=[BACKUP_SCRIPT_RELATIVE_PATH]
)
# A valid policy whose condition runs a command which depends on the script "backup.sh"
COMMAND_CONDITION_POLICY = f"""
rules:
  - name: "Test rule"
    conditions:
      command:
        run: "check"
        trusted_files:
          - {BACKUP_SCRIPT_RELATIVE_PATH}
    actions:
      - run: "echo test"
"""


def make_rule_data(**overrides: object) -> dict[str, object]:
    """Create the raw data of a valid rule, as it is passed to the validation of the configuration.

    Args:
        **overrides: Fields which replace the defaults.

    Returns:
        The raw rule data.
    """
    rule: dict[str, object] = {
        "name": "Test rule",
        "conditions": {"process": {"name": "backup.exe", "exists": False}},
        "actions": [{"run": "echo test"}],
    }

    return {**rule, **overrides}


def make_trusted_files_rule_data(
    name: str,
    files: list[str],
    *,
    enabled: bool = True,
) -> dict[str, object]:
    """Create the raw data of a rule whose action has the given trusted files.

    Args:
        name: Name of the rule.
        files: Configured trusted files of the action.
        enabled: Whether the rule is enabled.

    Returns:
        The raw rule data.
    """
    return make_rule_data(
        name=name,
        enabled=enabled,
        actions=[{"run": "echo test", "trusted_files": files}],
    )


def write_backup_script_policy(
    directory: Path,
    *,
    create_script: bool = True,
) -> Path:
    """Write "BACKUP_SCRIPT_POLICY" and, optionally, the scripts which it trusts, into a directory.

    Args:
        directory: Directory of the policy and the scripts. It is created if it does not exist.
        create_script: Whether the trusted scripts are written as well.

    Returns:
        The path of the policy file.
    """
    policy_file = write_policy(directory, BACKUP_SCRIPT_POLICY)

    if create_script:
        write_workspace_scripts(directory)

    return policy_file


def write_command_condition_policy(
    directory: Path,
    *,
    create_script: bool = True,
) -> Path:
    """Write "COMMAND_CONDITION_POLICY" and, optionally, the scripts which it trusts, into a directory.

    Args:
        directory: Directory of the policy and the scripts. It is created if it does not exist.
        create_script: Whether the trusted scripts are written as well.

    Returns:
        The path of the policy file.
    """
    policy_file = write_policy(directory, COMMAND_CONDITION_POLICY)

    if create_script:
        write_workspace_scripts(directory)

    return policy_file


###############
# Other objects
###############


def make_validation_error() -> ValidationError:
    """Create the validation error of an invalid nested value ("inner.enabled").

    Returns:
        The error.
    """

    class Inner(BaseModel):
        enabled: bool

    class Outer(BaseModel):
        inner: Inner

    try:
        Outer.model_validate({"inner": {"enabled": "invalid"}})
    except ValidationError as error:
        return error

    raise AssertionError("The validation was expected to fail")


def make_monotonic_clock(*values: float) -> Callable[[], float]:
    """Create a replacement for "time.monotonic()" which returns the given values one after another.

    Args:
        *values: Values which are returned by the consecutive calls.
            The last value is returned again for every further call.

    Returns:
        The clock function.
    """
    remaining_values = list(values)

    def monotonic() -> float:
        if len(remaining_values) > 1:
            return remaining_values.pop(0)

        return remaining_values[0]

    return monotonic
