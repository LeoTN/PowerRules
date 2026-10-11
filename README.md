<div align="center">

[![PowerRules](https://raw.githubusercontent.com/LeoTN/PowerRules/main/assets/logo/readme_logo.svg)](https://github.com/LeoTN/PowerRules)

[![latest-version](https://img.shields.io/github/v/release/LeoTN/PowerRules?&filter=*.*.*&display_name=release&style=for-the-badge&logo=Rocket&logoColor=green&label=LATEST&color=green)](https://github.com/LeoTN/PowerRules/releases/latest)
[![latest-beta-version](https://img.shields.io/github/v/release/LeoTN/PowerRules?&include_prereleases&filter=*.*.*b*&display_name=release&style=for-the-badge&logo=Textpattern&logoColor=orange&label=LATEST%20BETA&color=orange)](https://github.com/LeoTN/PowerRules/releases)
[![license](https://img.shields.io/github/license/LeoTN/PowerRules?&style=for-the-badge&logo=Google%20Docs&logoColor=blue&label=License&color=blue)](https://github.com/LeoTN/PowerRules/blob/main/LICENSE)

<details>
  <summary><b>Table of Contents</b></summary>
  <a href="#about">About</a><br>
  <a href="#getting-started">Getting Started</a><br>
  <a href="#features">Features</a><br>
  <a href="#supported-platforms">Supported Platforms</a><br>
  <a href="#credits--license">Credits & License</a>
</details>

</div>

## About

Define rules which run commands on your computer when configurable conditions match, for example when a process is gone, a window is open or it is a certain time of day.

PowerRules started as a tool to shut down, reboot or suspend a computer at the right moment. Since actions are plain shell commands, it can now run any program or script.

Rules are evaluated from top to bottom. The first matching rule runs its actions in order.

## Getting Started

1\. Install via [pip](https://pypi.org/project/powerrules) (Python 3.11+) or download a [standalone binary](#supported-platforms):

```bash
pip install powerrules
```

2\. Create a policy file:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/LeoTN/PowerRules/main/assets/schema/powerrules_policy.schema.json

rules:
  # Shut down when no backup process is running and the current time is between 23:00 and 01:30
  - name: "Shutdown after nightly backup"
    enabled: true
    conditions:
      and:
        - process:
            name: "backup.exe"
            exists: false
        - datetime:
            between:
              start: "23"
              end: "1:30"
    actions:
      # Windows command
      - name: "Shutdown"
        run: "shutdown /s /t 0"
```

3\. Validate and evaluate the policy once. Use `--dry-run` to see what would happen:

```bash
pwru policy validate --policy my-policy.yaml
pwru policy run --once --policy my-policy.yaml --dry-run
```

> [!CAUTION]
> Without `--dry-run`, a matching rule ***runs*** its commands. The example above could shut down your computer.

> [!NOTE]
> `pwru` is installed by pip. When using a [standalone binary](#supported-platforms), call it by its file name instead.

## Features

### Process & Window Matching

Match rules based on processes and window titles.

```yaml
# Match if process "firefox.exe" is running
- process:
    name: "firefox.exe"
    exists: true

# Match if window with exact title "Firefox" exists
- window:
    title: "Firefox"
    exists: true
```

<details>
  <summary><b>Options reference</b></summary><br>

| Option | Applies to | Default | Description |
|--------|------------|---------|-------------|
| `name` | `process` | required | Name of the process to check. |
| `title` | `window` | required | Title of the window to check. |
| `exists` | both | required | Whether the process or window is expected to exist. |
| `match` | both | exact, case-sensitive | How the name or title is matched, see [Regex Matching](#regex-matching). |

</details>

### Regex Matching

Match process names and window titles using regular expressions with full-string matching.

```yaml
# Match if process name contains "fire"
- process:
    name: '.*fire.*'
    exists: true
    match:
      type: regex
      case_sensitive: true # This is the default behavior

# Match if window title starts with "firefox" (case insensitive)
- window:
    title: "Firefox.*"
    exists: true
    match:
      type: regex
      case_sensitive: false
```

<details>
  <summary><b>Options reference</b></summary><br>

Options of `match`:

| Option | Default | Description |
|--------|---------|-------------|
| `type` | `exact` | Matching mode: `exact` or `regex` (full-string match). |
| `case_sensitive` | `true` | Whether uppercase and lowercase letters should be treated differently. |

</details>

### Time-based Conditions

Match specific dates, time ranges, weekdays and months. If several of `between`, `weekday` and `month` are configured, all of them must match. The start of a range is inclusive, the end is exclusive.

```yaml
# Match every day from 23:00 until 1:30 the next morning
- datetime:
    between:
      start: "23"
      end: "1:30"

# Match on Mondays and Fridays
- datetime:
    weekday:
      - "Monday"
      - "Friday"

# Match in June, July and August
- datetime:
    month:
      - "June"
      - "July"
      - "August"

# Match on the whole days 2026-08-21 and 2026-08-22 (the end date 2026-08-23 is not included)
- datetime:
    between:
      start: "2026-08-21"
      end: "2026-08-23"

# Match from 2026-08-21 18:00 until 2026-08-23 6:00
- datetime:
    between:
      start: "2026-08-21 18:00"
      end: "2026-08-23 6:00"

# Match on Saturdays and Sundays from 2026-08-21 until the end of 2026
- datetime:
    between:
      start: "2026-08-21"
      end: "2027-01-01"
    weekday:
      - "Saturday"
      - "Sunday"

# Match on Saturday and Sunday nights in December from 22:00 until 6:00 the next morning
- datetime:
    between:
      start: "22"
      end: "6"
    weekday:
      - "Saturday"
      - "Sunday"
    month:
      - "December"
```

All values use the local time of the computer, timezones are not supported.

<details>
  <summary><b>Options reference</b></summary><br>

At least one of `between`, `weekday` and `month` is required.

| Option | Description |
|--------|-------------|
| `between` | Range during which the condition is satisfied. Both boundaries must be of the same kind (see below). |
| `weekday` | List of English weekday names (case-insensitive), e.g. `Monday`. |
| `month` | List of English month names (case-insensitive), e.g. `January`. |

`weekday` and `month`: If the time range crosses midnight, they refer to the day on which the range starts. For absolute ranges, they refer to the current day.

<br>

Kinds of `between`:

| Kind | Format | Example | Description |
|------|--------|---------|-------------|
| Time of day | `H`, `HH`, `H:MM`, `HH:MM`, `H:MM:SS` or `HH:MM:SS` | `"23"`, `"1:30"` | Repeats every day and may cross midnight. |
| Date | `YYYY-MM-DD` | `"2026-08-21"` | Covers whole days, from 0:00 of the start date until 0:00 of the end date. |
| Date with time | `YYYY-MM-DD` followed by a space or `T` and a time | `"2026-08-21 18:00"` | Absolute range without timezone. |

</details>

### Logical Conditions

Combine multiple conditions using `and`, `or`, and `not`.

```yaml
# Match if (condition_1 OR condition_2) AND NOT condition_3
- and:
    - or:
        - condition_1: ...
        - condition_2: ...
    - not:
        condition_3: ...
```

### Actions

When a rule matches, its actions run one after another as commands in a shell.

```yaml
actions:
  # A failing backup does not prevent the remaining actions
  - name: "Backup"
    run: "backup.sh"
    shell: bash
    working_directory: scripts # Relative to the policy file
    env:
      TARGET: "/mnt/backup"
    timeout: 600
    success_exit_codes: [0, 3]
    continue_on_error: true

  # Start a command in the background without waiting for it
  - run: "notify.sh"
    shell: bash
    wait: false

  # Shutting down may require additional permissions on Linux
  - name: "Shutdown"
    run: "systemctl poweroff"
```

<details>
  <summary><b>Options reference</b></summary><br>

| Option | Default | Description |
|--------|---------|-------------|
| `run` | required | Command to run. A command with several lines stops at the first failing line. |
| `name` | `Action N of M` | Name of the action, used in log messages. |
| `shell` | `powershell` on Windows, `sh` on Linux and macOS | One of `sh`, `bash`, `cmd`, `powershell` or `pwsh`. The shell has to be installed. |
| `working_directory` | directory of the policy file | Relative paths are resolved against the directory of the policy file. |
| `env` | none | Additional environment variables. Numbers and booleans are converted to strings. Names starting with `POWERRULES_` are reserved. |
| `timeout` | `60` | Maximum run time in seconds. Afterwards, the command and its child processes are terminated. `null` disables the limit. |
| `success_exit_codes` | `[0]` | Exit codes which count as success. |
| `wait` | `true` | `false` starts the command in the background. Cannot be combined with `timeout` or `success_exit_codes`. |
| `continue_on_error` | `false` | Whether the remaining actions still run if this action fails. |

</details>

Commands can read the name of their rule and action from the environment variables `POWERRULES_RULE_NAME` and `POWERRULES_ACTION_NAME`.

If an action fails (unexpected exit code, timeout or the command cannot be started), the remaining actions are skipped unless `continue_on_error` is set.

> [!WARNING]
> Commands run with the privileges of the user who started PowerRules, so treat policy files like scripts.

### Policy Evaluation

Evaluate a policy with `pwru policy run`. Without `--once`, the rules are evaluated every 10 seconds until PowerRules is stopped. A matching rule only runs its actions when it becomes the active match, not on every evaluation while it keeps matching.

```bash
# Evaluate continuously
pwru policy run

# Evaluate once and exit
pwru policy run --once

# Only report which rule would match without running any commands
pwru policy run --dry-run
```

The policy is loaded once at startup, so changes to the file require a restart. If a condition cannot be evaluated or an action fails, the evaluation stops.

<details>
  <summary><b>Options reference</b></summary><br>

| Option | Applies to | Default | Description |
|--------|------------|---------|-------------|
| `--policy`, `-p` | all `policy` commands | `powerrules.yaml` | Path to the PowerRules policy file. |
| `--once` | `policy run` | off | Evaluate the policy once and then exit. |
| `--stop-on-match` | `policy run` | off | Keep evaluating until the first rule matches, then stop. |
| `--dry-run` | `policy run` | off | Evaluate the policy without executing any matching action. |

</details>

### Logging

All `policy` commands accept the following logging options:

```bash
pwru policy run --log-level DEBUG --log-file my-log.log
```

Messages are shown on the console and written to a rotating log file. Commands of actions and their output are only logged on `DEBUG` level. The error output of a failed action is always logged as an error.

<details>
  <summary><b>Options reference</b></summary><br>

| Option | Default | Description |
|--------|---------|-------------|
| `--log-level` | `INFO` | Minimum log level shown on the console and written to the log file. One of `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
| `--log-file` | `powerrules.log` | Path to the rotating log file. |
| `--log-level-file` | value of `--log-level` | Minimum log level written to the log file. |

</details>

## Supported Platforms

| Platform | Standalone Binary | Notes |
|----------|-----------------------| ----- |
| Windows 10/11 | [powerrules-windows-x86_64.exe](https://github.com/LeoTN/PowerRules/releases/latest/download/powerrules-windows-x86_64.exe) | Window conditions only work when PowerRules runs in the logged-in user's session. |
| Linux | [powerrules-linux-x86_64](https://github.com/LeoTN/PowerRules/releases/latest/download/powerrules-linux-x86_64)<br>[powerrules-linux-arm64](https://github.com/LeoTN/PowerRules/releases/latest/download/powerrules-linux-arm64) | Window conditions require an X11 session (Wayland is currently not supported). |
| macOS | [powerrules-macos-arm64](https://github.com/LeoTN/PowerRules/releases/latest/download/powerrules-macos-arm64) | Window conditions require the screen recording permission. |

**Platform independent via pip:**
```bash
pip install powerrules
```

## Credits & License

* [Inkscape](https://inkscape.org) → program used to design the logo
* [Nuitka](https://github.com/nuitka/nuitka) → standalone binaries
* [psutil](https://github.com/giampaolo/psutil) → process information
* [Pydantic](https://github.com/pydantic/pydantic) → configuration validation
* [PyYAML](https://github.com/yaml/pyyaml) → YAML policy parsing
* [rich](https://github.com/textualize/rich) → console output formatting
* [Typer](https://github.com/fastapi/typer) → command-line interface

*This repository is licensed under the [MIT License](https://github.com/LeoTN/PowerRules/blob/main/LICENSE).*
