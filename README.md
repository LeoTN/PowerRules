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

Define rules to control your computer's power state based on configurable conditions.

Rules are evaluated from top to bottom. The first matching rule executes its configured action.

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
    action:
      type: shutdown
```

3\. Validate and evaluate the policy once. Use `--dry-run` to see what would happen:

```bash
pwru policy validate --policy my-policy.yaml
pwru policy run --once --policy my-policy.yaml --dry-run
```

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

### Time-based Conditions

Match specific dates, time ranges, weekdays and months. If several of `between`, `weekday` and `month` are configured, all of them must match. The end of a range is always exclusive.

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

`start` and `end` must be of the same kind: both times, both dates or both dates with a time. All values use the local time of the computer, timezones are not supported.

If a time range crosses midnight, `weekday` and `month` refer to the day on which the range starts. For dates, they refer to the current day.

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

### Power Actions

Shutdown, sleep, hibernate, or reboot your computer.

```yaml
# Shutdown on match
- action:
    type: shutdown

# Reboot on match
- action:
    type: reboot
```

### Continuous Evaluation

Evaluate rules every 10 seconds. A matching rule is triggered only when it becomes the active match, avoiding repeated execution while the same rule remains matched.

```bash
pwru policy run
```

`--stop-on-match` can be used to stop the evaluation after the first match. The policy is loaded once at startup, so changes to the file require a restart.

## Supported Platforms

| Platform | Standalone Binary | Notes |
|----------|-----------------------| ----- |
| Windows 10/11 | [powerrules-windows-x86_64.exe](https://github.com/LeoTN/PowerRules/releases/latest/download/powerrules-windows-x86_64.exe) | Window conditions only work when PowerRules runs in the logged-in user's session. |
| Linux | [powerrules-linux-x86_64](https://github.com/LeoTN/PowerRules/releases/latest/download/powerrules-linux-x86_64)<br>[powerrules-linux-arm64](https://github.com/LeoTN/PowerRules/releases/latest/download/powerrules-linux-arm64) | Window conditions require an X11 session (Wayland is currently not supported). |
| macOS | [powerrules-macos-arm64](https://github.com/LeoTN/PowerRules/releases/latest/download/powerrules-macos-arm64) | Hibernation action is not supported. |

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
