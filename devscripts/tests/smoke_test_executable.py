"""Run smoke tests against a built PowerRules executable (called by build_executable.py, not pytest).

Every scenario only validates policies or uses "--dry-run", so the power state of the machine is never changed.
"""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

SCENARIO_TIMEOUT_SECONDS = 120

# Placeholder for the path of the policy file in the arguments of a scenario
POLICY_PLACEHOLDER = "{policy}"

# Mirrors EXIT_POLICY_ERROR of powerrules.cli.errors, the executable is intentionally tested as a black box
EXIT_POLICY_ERROR = 2

# A healthy executable never prints these. They indicate a missing module or an unclassified error
FORBIDDEN_OUTPUT = (
    "Traceback",
    "ModuleNotFoundError",
    "ImportError",
    "Unexpected error",
)

# Matches on every day of the next centuries, so the result does not depend on when the test runs
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
    action:
      type: shutdown
"""

# The window provider is usually not available on CI runners, so both a match and an evaluation error are fine
WINDOW_POLICY = """
rules:
  - name: "Smoke test window rule"
    conditions:
      window:
        title: "powerrules-smoke-test-window"
        exists: false
    action:
      type: sleep
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
    action:
      type: shutdown
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
    """

    name: str
    arguments: tuple[str, ...]
    policy: str | None = None
    expected_exit_codes: frozenset[int] = frozenset({0})
    expected_output: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Safety net: a scenario must never be able to change the power state of the machine
        if "run" in self.arguments and "--dry-run" not in self.arguments:
            raise ValueError(
                f"Scenario '{self.name}' runs a policy without '--dry-run'"
            )


SCENARIOS = (
    SmokeScenario(
        name="help",
        arguments=("--help",),
        expected_output=("A rule-based computer power state management tool",),
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
            "[DRY RUN] Rule 'Smoke test rule' matched, would have executed action: shutdown",
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
    command = [
        str(executable),
        "--log-file",
        str(log_path),
        *(
            argument.replace(POLICY_PLACEHOLDER, str(policy_path))
            for argument in scenario.arguments
        ),
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
