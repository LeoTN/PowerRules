# Command

!!! abstract "Summary"

    Matches if a command finishes with a successful exit code and the configured output. Command conditions also run with `--dry-run`.

## Example

``` yaml
rules:
  # Match if the script exits with 0 or 2 and prints "successful" (case-insensitive)
  - name: "Service is successful"
    conditions:
      command:
        run: "check.sh"
        shell: bash
        working_directory: scripts # Relative to the policy file
        success_exit_codes: [0, 2]
        stdout:
          value: "successful"
          match:
            type: contains
            case_sensitive: false
        trusted_files:
          - scripts/check.sh # Relative to the policy file (not to working_directory)
    actions:
      - run: "echo Service is successful"
```

## Options

Command conditions use the [command options](../reference/command_options.md).

## Details

!!! warning

    Command conditions run on every evaluation, **even with `--dry-run`**. Use [trust](../trust.md) to detect modifications.

- The condition matches if the exit code and all configured outputs match. A different exit code or output is no error, the condition simply does not match.
- If the command cannot be started or exceeds its `timeout`, the condition cannot be evaluated and the evaluation stops.
- Unlike actions, conditions do not receive the `POWERRULES_*` environment variables.
- Commands and their output are only logged on `DEBUG` level.
- [`and` and `or`](logical.md) stop at the first decisive result. Put cheap conditions first, so the command only runs when needed.

See [Actions vs. command conditions](../reference/command_options.md#actions-vs-command-conditions) for the differences to the commands of actions.

## Related

<div class="grid cards" markdown>

--8<-- "related_grid.md:sub1_policy_evaluation"

--8<-- "related_grid.md:sub1_actions"

--8<-- "related_grid.md:sub1_trust"

</div>
