# Logical

!!! abstract "Summary"

    Combines other conditions with `and`, `or` and `not`. They can be nested as deeply as needed.

## Example

``` yaml
rules:
  # Match if (Firefox OR Chrome is running) AND NOT a backup is running
  - name: "Browser without backup"
    conditions:
      and:
        - or:
            - process:
                name: "firefox.exe"
                exists: true
            - process:
                name: "chrome.exe"
                exists: true
        - not:
            process:
              name: "backup.exe"
              exists: true
    actions:
      - run: "echo Browser is running without a backup"
```

## Options

| Option | Takes                           | Matches when                    |
| ------ | ------------------------------- | ------------------------------- |
| `and`  | list of at least two conditions | all conditions match.           |
| `or`   | list of at least two conditions | at least one condition matches. |
| `not`  | exactly one condition           | the condition does not match.   |

## Details

- A condition defines exactly one of `and`, `or`, `not` or a single condition type.
- `and` and `or` evaluate their conditions in order and stop at the first decisive result. In other words, if an `and` condition finds a non-matching condition, it stops and returns `false`. If an `or` condition finds a matching condition, it stops and returns `true`.
- `not` only negates the result. If the inner condition cannot be evaluated, the evaluation still stops.

## Related

<div class="grid cards" markdown>

--8<-- "related_grid.md:sub1_policy_evaluation"

--8<-- "related_grid.md:sub1_actions"

--8<-- "related_grid.md:sub1_trust"

</div>
