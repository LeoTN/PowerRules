# PowerRules

PowerRules is a rule-based command automation tool: when the conditions of a rule match, its commands run.

Originally built to shut down a computer at the right moment, it now runs any shell command.

```yaml
rules:
  # Shut down when no backup process is running between 23:00 and 01:30
  - name: "Shutdown after nightly backup"
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
      - run: "shutdown /s /t 0"
```

## How it works

- A **policy** is a YAML file with a list of rules.
- Each **rule** has conditions (processes, datetime, etc.) and actions (commands to run).
- Rules are evaluated from top to bottom. The first rule that matches runs its actions in order.
- A policy has to be [trusted](trust.md) first, so modifications of a policy or its scripts do not go unnoticed.

??? question "Why choose PowerRules over scheduled tasks or systemd timers?"
    You can build the same thing yourself: a scheduled task which runs every few
    seconds and starts a script containing all the logic. PowerRules is essentially
    that script partially written. You describe *what* should happen instead of
    *how* to check it.

    - **Declarative**: Combine conditions with `and`, `or` and `not` in a readable YAML file.
    - **Portable**: The same policy usually works on Windows, Linux and macOS.
    - **Debugging**: `--dry-run` shows what would happen and debug logs explain why a condition did or did not match.

    For a single fixed schedule on one system, the built-in tools are usually the
    simpler choice.

## Installation

=== "pip"

    Requires Python 3.11 or newer.

    ```bash
    pip install powerrules
    ```

=== "Standalone binary"

    Download the binary for your platform from the [latest release](https://github.com/LeoTN/PowerRules/releases/latest).

!!! note
    `pwru` is installed by pip. When using a standalone binary, call it by its file name instead.

Check the version:

```bash
pwru --version
```

## Next steps

<div class="grid cards" markdown>

-   **[Getting Started](getting_started.md)**

    ---

    Create, validate and trust your first policy.

-   **[Conditions](conditions/index.md)**

    ---

    Match processes, windows, time and command results.

-   **[Actions](actions.md)**

    ---

    Run commands when a rule matches.

-   **[Trust](trust.md)**

    ---

    Detect modifications of policies and scripts.

</div>