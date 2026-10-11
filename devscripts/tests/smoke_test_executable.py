"""Run smoke tests against a built PowerRules executable (called by build_executable.py, not pytest).

Every scenario only validates policies or uses "--dry-run", except the scenarios which are marked with
"executes_commands". Those only run harmless commands (echo, an exit code and a sleep).
"""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

SCENARIO_TIMEOUT_SECONDS = 120

# Placeholder for the path of the policy file in the arguments of a scenario
POLICY_PLACEHOLDER = "{policy}"

# Mirrors EXIT_RUNTIME_ERROR of powerrules.cli.errors
EXIT_RUNTIME_ERROR = 1

# Mirrors EXIT_POLICY_ERROR of powerrules.cli.errors, the executable is intentionally tested as a black box
EXIT_POLICY_ERROR = 2

# A healthy executable never prints these. They indicate a missing module or an unclassified error
FORBIDDEN_OUTPUT = (
    "Traceback",
    "ModuleNotFoundError",
    "ImportError",
    "Unexpected error",
)

# Matches on every day of the next centuries, so the result does not depend on when the test runs.
# The commands of this policy are never run, because every scenario which evaluates it uses "--dry-run"
MATCHING_POLICY = """
rules:
  - name: "Smoke test rule"
    conditions:
      and:
        - process:
            name: "powerrules-smoke-test-.*"
            exists: false
            match:
              type: regex
              case_sensitive: false
        - datetime:
            between:
              start: "2000-01-01"
              end: "2999-12-31"
            weekday: [Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday]
            month: [January, February, March, April, May, June, July, August, September, October, November, December]
    actions:
      - name: "Cleanup"
        run: "echo cleanup"
      - name: "Shutdown"
        run: "echo shutdown"
"""

# The window provider is usually not available on CI runners, so both a match and an evaluation error are fine
WINDOW_POLICY = """
rules:
  - name: "Smoke test window rule"
    conditions:
      window:
        title: "powerrules-smoke-test-window"
        exists: false
    actions:
      - run: "echo sleep"
"""

# The following policies run real commands. They behave the same in PowerShell and sh and never change the machine
REAL_COMMAND_POLICY = """
rules:
  - name: "Smoke test real command"
    conditions:
      datetime:
        between:
          start: "2000-01-01"
          end: "2999-12-31"
    actions:
      - name: "Echo"
        run: "echo powerrules-smoke-test"
"""

FAILING_COMMAND_POLICY = """
rules:
  - name: "Smoke test failing command"
    conditions:
      datetime:
        between:
          start: "2000-01-01"
          end: "2999-12-31"
    actions:
      - name: "Failing"
        run: "exit 3"
"""

# Exercises the termination of the process tree after the timeout
TIMEOUT_COMMAND_POLICY = """
rules:
  - name: "Smoke test command timeout"
    conditions:
      datetime:
        between:
          start: "2000-01-01"
          end: "2999-12-31"
    actions:
      - name: "Slow"
        run: "sleep 30"
        timeout: 1
"""

# The format of the actions before commands were introduced
FORMER_ACTION_POLICY = """
rules:
  - name: "Former action rule"
    conditions:
      process:
        name: "backup.exe"
        exists: false
    action:
      type: shutdown
"""

INVALID_YAML_POLICY = """
rules:
  - name: "Broken rule
"""

INVALID_POLICY = """
rules:
  - name: "Invalid rule"
    conditions:
      process:
        name: "backup.exe"
        exists: "not a boolean"
    actions:
      # Windows command
      - name: "Shutdown"
        run: "shutdown /s /t 0"
"""


@dataclass(frozen=True)
class SmokeScenario:
    """A single call of the executable and the result it has to produce.

    Args:
        name: Name of the scenario shown in the build output.
        arguments: Command line arguments. POLICY_PLACEHOLDER is replaced by the policy file path.
        policy: Content of the policy file. None means that no policy file exists.
        expected_exit_codes: Accepted exit codes of the executable.
        expected_output: Strings which have to be part of the combined stdout and stderr.
        executes_commands: Allows a policy run without "--dry-run". Only set it for policies with harmless commands.
    """

    name: str
    arguments: tuple[str, ...]
    policy: str | None = None
    expected_exit_codes: frozenset[int] = frozenset({0})
    expected_output: tuple[str, ...] = ()
    executes_commands: bool = False

    def __post_init__(self) -> None:
        # Safety net: a scenario must never be able to run commands on the machine without "--dry-run", except the scenario is explicitly marked as safe
        if (
            "run" in self.arguments
            and "--dry-run" not in self.arguments
            and not self.executes_commands
        ):
            raise ValueError(
                f"Scenario '{self.name}' runs a policy without '--dry-run'"
            )


SCENARIOS = (
    SmokeScenario(
        name="help",
        arguments=("--help",),
        expected_output=("A rule-based command automation tool",),
    ),
    SmokeScenario(
        name="validate valid policy",
        arguments=("policy", "validate", "--policy", POLICY_PLACEHOLDER),
        policy=MATCHING_POLICY,
        expected_output=("is valid",),
    ),
    SmokeScenario(
        name="show policy",
        arguments=("policy", "show", "--policy", POLICY_PLACEHOLDER),
        policy=MATCHING_POLICY,
        expected_output=("1. Smoke test rule",),
    ),
    SmokeScenario(
        name="run once dry run",
        arguments=(
            "policy",
            "run",
            "--once",
            "--dry-run",
            "--policy",
            POLICY_PLACEHOLDER,
        ),
        policy=MATCHING_POLICY,
        expected_output=(
            "[DRY RUN] Rule 'Smoke test rule' matched, would have executed actions: 'Cleanup', 'Shutdown'",
        ),
    ),
    SmokeScenario(
        name="run continuously dry run",
        arguments=(
            "policy",
            "run",
            "--dry-run",
            "--stop-on-match",
            "--policy",
            POLICY_PLACEHOLDER,
        ),
        policy=MATCHING_POLICY,
        expected_output=("Rule matched, stopping evaluation",),
    ),
    SmokeScenario(
        name="run once dry run with window condition",
        arguments=(
            "policy",
            "run",
            "--once",
            "--dry-run",
            "--policy",
            POLICY_PLACEHOLDER,
        ),
        policy=WINDOW_POLICY,
        expected_exit_codes=frozenset({0, 1}),
    ),
    SmokeScenario(
        name="run once with real command",
        arguments=("policy", "run", "--once", "--policy", POLICY_PLACEHOLDER),
        policy=REAL_COMMAND_POLICY,
        executes_commands=True,
        # This message is only logged after the command was started and finished
        expected_output=("Action 'Echo' finished with exit code 0",),
    ),
    SmokeScenario(
        name="run once with failing command",
        arguments=("policy", "run", "--once", "--policy", POLICY_PLACEHOLDER),
        policy=FAILING_COMMAND_POLICY,
        executes_commands=True,
        expected_exit_codes=frozenset({EXIT_RUNTIME_ERROR}),
        expected_output=("Action 'Failing' returned exit code 3, expected one of: 0",),
    ),
    SmokeScenario(
        name="run once with command timeout",
        arguments=("policy", "run", "--once", "--policy", POLICY_PLACEHOLDER),
        policy=TIMEOUT_COMMAND_POLICY,
        executes_commands=True,
        expected_exit_codes=frozenset({EXIT_RUNTIME_ERROR}),
        expected_output=("Action 'Slow' timed out after 1 seconds",),
    ),
    SmokeScenario(
        name="missing policy file",
        arguments=("policy", "validate", "--policy", POLICY_PLACEHOLDER),
        expected_exit_codes=frozenset({EXIT_POLICY_ERROR}),
        expected_output=("Policy file not found",),
    ),
    SmokeScenario(
        name="invalid yaml",
        arguments=("policy", "validate", "--policy", POLICY_PLACEHOLDER),
        policy=INVALID_YAML_POLICY,
        expected_exit_codes=frozenset({EXIT_POLICY_ERROR}),
        expected_output=("Failed to parse policy file",),
    ),
    SmokeScenario(
        name="invalid policy",
        arguments=("policy", "validate", "--policy", POLICY_PLACEHOLDER),
        policy=INVALID_POLICY,
        expected_exit_codes=frozenset({EXIT_POLICY_ERROR}),
        expected_output=("Policy validation failed",),
    ),
    SmokeScenario(
        name="former action format",
        arguments=("policy", "validate", "--policy", POLICY_PLACEHOLDER),
        policy=FORMER_ACTION_POLICY,
        expected_exit_codes=frozenset({EXIT_POLICY_ERROR}),
        expected_output=("Policy validation failed",),
    ),
)


def run_smoke_tests(executable: Path) -> list[str]:
    """Run all smoke test scenarios against the executable.

    Args:
        executable: Path to the built PowerRules executable.

    Returns:
        A description of every failed scenario. The list is empty if all scenarios passed.
    """
    # The scenarios run in a different working directory, so a relative path would no longer point to the executable
    executable = executable.resolve()

    failures: list[str] = []

    # An isolated directory keeps the log file and the policy files out of the repository
    with tempfile.TemporaryDirectory(prefix="powerrules-smoke-") as directory:
        working_directory = Path(directory)
        policy_path = working_directory / "powerrules.yaml"
        log_path = working_directory / "powerrules.log"

        for scenario in SCENARIOS:
            print(f"[INFO] Running smoke test '{scenario.name}'...")

            policy_path.unlink(missing_ok=True)

            if scenario.policy is not None:
                policy_path.write_text(scenario.policy, encoding="utf-8")

            failure = _run_scenario(
                executable, scenario, policy_path, log_path, working_directory
            )

            if failure is not None:
                failures.append(f"'{scenario.name}': {failure}")

    return failures


def _run_scenario(
    executable: Path,
    scenario: SmokeScenario,
    policy_path: Path,
    log_path: Path,
    working_directory: Path,
) -> str | None:
    """Run a single scenario.

    Returns:
        A description of the failure, or None if the scenario passed.
    """
    # The logging options belong to the "policy" commands, other scenarios (e.g. "--help") do not log
    log_arguments = (
        ("--log-file", str(log_path)) if scenario.arguments[:1] == ("policy",) else ()
    )

    command = [
        str(executable),
        *(
            argument.replace(POLICY_PLACEHOLDER, str(policy_path))
            for argument in scenario.arguments
        ),
        *log_arguments,
    ]

    try:
        result = subprocess.run(
            command,
            cwd=working_directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SCENARIO_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"timed out after {SCENARIO_TIMEOUT_SECONDS} seconds"

    output = result.stdout + result.stderr

    if result.returncode not in scenario.expected_exit_codes:
        return (
            f"unexpected exit code {result.returncode}, "
            f"expected one of {sorted(scenario.expected_exit_codes)}\n{output}"
        )

    for forbidden in FORBIDDEN_OUTPUT:
        if forbidden in output:
            return f"output contains '{forbidden}'\n{output}"

    for expected in scenario.expected_output:
        if expected not in output:
            return f"output does not contain '{expected}'\n{output}"

    return None
