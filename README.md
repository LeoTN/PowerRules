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

**Install with pip:**

```bash
pip install powerrules
```

**Create a policy file:**

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/LeoTN/PowerRules/main/assets/schema/powerrules_policy.schema.json

rules:
  # Shut down when no backup process is running, a matching backup window is open, and the current time is between 23:00 and 01:30
  - name: "Shutdown after nightly backup"
    conditions:
      and:
        - process:
            name: "backup.exe"
            exists: false
        - window:
            title: "Backup Nr. [0-9]+ Completed"
            exists: true
            match:
              type: regex
        - datetime:
            between:
              start: "23"
              end: "1:30"
    action:
      type: shutdown
```

**Validate the policy:**

```bash
pwru policy validate
```

**Show configured rules:**

```bash
pwru policy show
```

**Evaluate the policy once:**

```bash
pwru policy run --once
```

Use a different policy file with `--policy` or `-p`:

```bash
pwru policy run --policy my-policy.yaml
```

## Features

**Process & Window Matching**  
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
<br>

**Regex Matching**  
Match process names and window titles using regular expressions with full-string matching.

```yaml
# Match if process name ends with "firefox"
- process:
    name: ".*firefox.exe"
    match:
      type: regex
      # This is the default behavior
      case_sensitive: true

# Match if window title starts with "firefox" (case insensitive)
- window:
    title: "Firefox.*"
    match:
      type: regex
      case_sensitive: false
```
<br>

**Time-based Conditions**  
Match specific time ranges and weekdays.

```yaml
# Match if the current time is between 23:00 and 1:30
- datetime:
    between:
      start: "23"
      end: "1:30"

# Match on Monday or Friday
- datetime:
    weekdays:
      - "Monday"
      - "Friday"
```
<br>

**Logical Conditions**  
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
<br>

**Power Actions**  
Shutdown, sleep, hibernate, or reboot your computer.

```yaml
# Shutdown on match
- action:
    type: shutdown

# Reboot on match
- action:
    type: reboot
```
<br>

**Continuous Evaluation**  
Evaluate rules at a set interval.

```bash
pwru policy run
```

## Supported Platforms

| Platform | Status |
|----------|:------:|
| Windows 10/11 | ✅ |
| Linux | ✅ |
| macOS* | ✅ |

\* Hibernation is not supported on macOS.

## Credits & License

* [Pydantic](https://github.com/pydantic/pydantic) → configuration validation
* [PyYAML](https://github.com/yaml/pyyaml) → YAML policy parsing
* [Typer](https://github.com/fastapi/typer) → command-line interface
* [psutil](https://github.com/giampaolo/psutil) → process information
* [PyWinCtl](https://github.com/Kalmat/PyWinCtl) → window information
* [Inkscape](https://inkscape.org) → program used to design the logo

*This repository is licensed under the [MIT License](https://github.com/LeoTN/PowerRules/blob/main/LICENSE).*
