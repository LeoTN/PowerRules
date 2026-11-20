# Policy evaluation

!!! abstract "Summary"

    A policy is evaluated continuously or once. Rules are checked from top to bottom, the first matching rule runs its actions, and only when it becomes the active match.

## Example

``` bash
# Evaluate continuously
pwru policy run

# Evaluate every 30 seconds
pwru policy run --interval 30

# Evaluate once and exit
pwru policy run --once

# Only report which rule would match without running any actions
pwru policy run --dry-run
```

## Evaluation flow

``` mermaid
flowchart TD
    A[Load policy once] --> B[Check enabled rules from top to bottom]
    B --> C{A rule matches?}
    C -- No --> F[Wait for the interval]
    C -- Yes --> D{Same rule as in the previous evaluation?}
    D -- Yes --> F
    D -- No --> E[Run actions in order]
    E --> F
    F --> B
```

## Options

| Option               | Default           | Description                                                                                           |
| -------------------- | ----------------- | ----------------------------------------------------------------------------------------------------- |
| `--policy`, `-p`     | `powerrules.yaml` | Path to the policy file.                                                                              |
| `--once`             | off               | Evaluate the policy once and then exit.                                                               |
| `--interval`         | `10`              | Seconds between the starts of two evaluations. Has no effect with `--once`.                           |
| `--stop-on-match`    | off               | Stop the evaluation after a rule has run its actions.                                                 |
| `--dry-run`          | off               | Evaluate the policy without running any action. Commands of command conditions still run.             |
| `--no-require-trust` | off               | Run the policy even if it is not trusted or was modified since it was trusted, see [Trust](trust.md). |

## Details

- A rule runs its actions when it becomes the active match, not on every evaluation while it keeps matching. If no rule matches in between, the rule runs its actions again the next time it matches.
- The interval is the time between the starts of two evaluations. If an evaluation takes longer, PowerRules logs a warning and starts the next one immediately.
- The policy is loaded once at startup, so changes to the file require a restart.
- Unless `--no-require-trust` is used, the policy has to be [trusted](trust.md). `--dry-run` only skips this if the policy has no [command condition](conditions/command.md), because the commands of command conditions run in a dry run as well.
- If a condition cannot be evaluated, an action fails or a trusted file was modified, the evaluation stops.

## Related

<div class="grid cards" markdown>

--8<-- "related_grid.md:conditions"

--8<-- "related_grid.md:actions"

--8<-- "related_grid.md:trust"

</div>
