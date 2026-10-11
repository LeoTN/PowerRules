"""Factories for mocked objects which are shared by the tests."""

from collections.abc import Iterable
from datetime import datetime
from unittest.mock import Mock, create_autospec

from powerrules.actions.base import Action
from powerrules.conditions.base import Condition
from powerrules.providers.clock import ClockProvider
from powerrules.providers.command import CommandProvider, CommandResult
from powerrules.providers.process import ProcessProvider
from powerrules.providers.window import WindowProvider


def make_condition(
    result: bool = True,
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


def make_action(
    name: str = "Test action",
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


def make_process_provider(
    process_names: Iterable[str] = (),
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
