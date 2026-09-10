<div align="center">

[![PowerRules](https://raw.githubusercontent.com/LeoTN/PowerRules/main/assets/logo/readme_logo.svg)](https://github.com/LeoTN/PowerRules)

[![latest-version](https://img.shields.io/github/v/release/LeoTN/PowerRules?&filter=*.*.*&display_name=release&style=for-the-badge&logo=Rocket&logoColor=green&label=LATEST&color=green)](https://github.com/LeoTN/PowerRules/releases/latest)
[![latest-beta-version](https://img.shields.io/github/v/release/LeoTN/PowerRules?&include_prereleases&filter=*.*.*b*&display_name=release&style=for-the-badge&logo=Textpattern&logoColor=orange&label=LATEST%20BETA&color=orange)](https://github.com/LeoTN/PowerRules/releases)
[![license](https://img.shields.io/github/license/LeoTN/PowerRules?&style=for-the-badge&logo=Google%20Docs&logoColor=blue&label=License&color=blue)](https://github.com/LeoTN/PowerRules/blob/main/LICENSE)

</div>

#

* [About](#about)
* [Getting Started](#getting-started)
* [Features](#features)
* [Supported Platforms](#supported-platforms)
* [Credits & License](#credits--license)

## About

PowerRules allows you to define rules that automatically control the power state of your computer based on configurable conditions.

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
  - name: "Shutdown after nightly weekend backup"
    conditions:
      and:
        - process:
            name: "backup.exe"
            exists: false
        - window:
            title: "Backup Completed"
            exists: true
        - datetime:
            between:
              start: "23"
              end: "1:30"
        - datetime:
            weekday: ["Saturday", "Sunday"]
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

**Run continuously:**

```bash
pwru policy run
```

Use a different policy file with `--policy` or `-p`:

```bash
pwru policy run --policy my-policy.yaml
```

## Features

| Feature | Description |
|---------|-------------|
| **Rule-based power management** | Define ordered rules with conditions and power actions |
| **Process conditions** | Match rules based on whether a process exists |
| **Time conditions** | Match time ranges and weekdays |
| **Window conditions** | Match window titles |
| **Logical conditions** | Combine conditions using `and`, `or`, and `not` |
| **Matching behavior** | How a value (process name, window title, etc.) should be matched. By default, an exact, case-sensitive match is used. |
| **Power actions** | Shutdown, sleep, hibernate, and reboot |
| **Continuous evaluation** | Evaluate policies repeatedly |
| **First-match execution** | Only the first matching rule executes once per match |

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
