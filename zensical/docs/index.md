# PowerRules

PowerRules is a rule-based command automation tool: when the conditions of a rule match, its commands run.

Originally built to shut down a computer at the right moment, it now runs any shell command.

=== "Windows"

    ``` yaml
    rules:
      # Match when no backup process is running between 23:00 and 01:30
      - name: "Shutdown when no backup is running at night"
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

=== "Linux & macOS"

    ``` yaml
    rules:
      # Match when no backup process is running between 23:00 and 01:30
      - name: "Shutdown when no backup is running at night"
        conditions:
          and:
            - process:
                name: "backup"
                exists: false
            - datetime:
                between:
                  start: "23"
                  end: "1:30"
        actions:
          - run: "shutdown -h now"
    ```

## How it works

- A **policy** is a YAML file with a list of rules.
- Each **rule** has conditions (processes, datetime, etc.) and actions (commands to run).
- Rules are evaluated from top to bottom. The first rule that matches runs its actions in order.
- A policy has to be [trusted](trust.md) first, so modifications of a policy or its scripts do not go unnoticed.

??? question "Why choose PowerRules over scheduled tasks or systemd timers?"

    You can build the same thing yourself: a scheduled task which runs every few
    seconds and starts a script containing all the logic. PowerRules is essentially
    that script partially written. You describe _what_ should happen instead of
    _how_ to check it.

    - **Declarative**: Combine conditions with `and`, `or` and `not` in a readable YAML file.
    - **Portable**: The same policy usually works on Windows, Linux and macOS.
    - **Debugging**: `--dry-run` shows what would happen and debug logs explain why a condition did or did not match.

    For a single fixed schedule on one system, the built-in tools are usually the
    simpler choice.

## Related

<div class="grid cards" markdown>

--8<-- "related_grid.md:getting_started"

--8<-- "related_grid.md:conditions"

--8<-- "related_grid.md:actions"

--8<-- "related_grid.md:trust"

</div>
