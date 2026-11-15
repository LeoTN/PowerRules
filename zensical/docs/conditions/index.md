# Conditions

!!! abstract "Summary"

    Conditions decide whether a rule matches. They check processes, windows, the time or the result of a command and can be combined with `and`, `or` and `not`.

## Example

``` yaml
rules:
  # Match on weekends while no backup process is running
  - name: "Weekend without backup"
    conditions:
      and:
        - datetime:
            weekday:
              - "Saturday"
              - "Sunday"
        - process:
            name: "backup.exe"
            exists: false
    actions:
      - run: "echo No backup is running"
```

Every rule has exactly one `conditions` entry. To check several things, combine them with a [logical condition](logical.md).

## Condition types

| Condition                        | Matches when                                           | Notes                                |
| -------------------------------- | ------------------------------------------------------ | ------------------------------------ |
| [`process`](process.md)          | a process with the given name exists or does not exist |                                      |
| [`window`](window.md)            | a window with the given title exists or does not exist | Availability depends on the platform |
| [`datetime`](datetime.md)        | the current date, time, weekday or month fits          | Uses the local time of the computer  |
| [`command`](command.md)          | the exit code and the output of a command fit          | Also runs with `--dry-run`           |
| [`and`, `or`, `not`](logical.md) | the combination of other conditions fits               |                                      |

`process`, `window` and `command` compare text with [match types](../reference/match_types.md): exact, regular expression or contains.

## Details

- Conditions are [evaluated](../policy_evaluation.md) on every evaluation of the policy.
- `and` and `or` stop at the first decisive result, so the remaining conditions might not run.
- If a condition cannot be evaluated (e.g. a command exceeds its timeout or window conditions are not available on the platform), the evaluation stops.

## Related

<div class="grid cards" markdown>

--8<-- "related_grid.md:sub1_policy_evaluation"

--8<-- "related_grid.md:sub1_actions"

--8<-- "related_grid.md:sub1_trust"

</div>
