# Actions

!!! abstract "Summary"

    Actions are commands which run one after another when a rule matches. If an action fails, the remaining actions are skipped unless `continue_on_error` is set.

## Example

=== "Windows"

    ``` yaml
    rules:
      # Match every night from 23:00 until 1:30
      - name: "Backup time"
        conditions:
          datetime:
            between:
              start: "23"
              end: "1:30"
        actions:
          # A failing backup does not prevent the remaining actions
          - name: "Backup"
            run: '.\my-action.ps1'
            working_directory: scripts # Relative to the policy file
            env:
              TARGET: 'D:\backup'
            timeout: 600
            success_exit_codes: [0, 3]
            continue_on_error: true
            trusted_files:
              - scripts/my-action.ps1 # Relative to the policy file (not to working_directory)

          # Fail if the output does not contain "Notification service is ready"
          - name: "Check"
            run: '.\my-check.ps1'
            working_directory: scripts
            stdout:
              value: "Notification service is ready"
              match:
                type: contains
            trusted_files:
              - scripts/my-check.ps1

          # Start a command in the background without waiting for it
          - run: '.\my-notification.ps1'
            working_directory: scripts
            wait: false
            trusted_files:
              - scripts/my-notification.ps1
    ```

=== "Linux & macOS"

    ``` yaml
    rules:
      # Match every night from 23:00 until 1:30
      - name: "Backup time"
        conditions:
          datetime:
            between:
              start: "23"
              end: "1:30"
        actions:
          # A failing backup does not prevent the remaining actions
          - name: "Backup"
            run: "./my-action.sh"
            working_directory: scripts # Relative to the policy file
            env:
              TARGET: "/mnt/backup"
            timeout: 600
            success_exit_codes: [0, 3]
            continue_on_error: true
            trusted_files:
              - scripts/my-action.sh # Relative to the policy file (not to working_directory)

          # Fail if the output does not contain "Notification service is ready"
          - name: "Check"
            run: "./my-check.sh"
            working_directory: scripts
            stdout:
              value: "Notification service is ready"
              match:
                type: contains
            trusted_files:
              - scripts/my-check.sh

          # Start a command in the background without waiting for it
          - run: "./my-notification.sh"
            working_directory: scripts
            wait: false
            trusted_files:
              - scripts/my-notification.sh
    ```

## Options

Actions use the [command options](reference/command_options.md). The options `name`, `wait` and `continue_on_error` are only available for actions.

## Details

!!! warning

    Commands run with the privileges of the user who started PowerRules, so treat policy files like scripts. Use [trust](trust.md) to detect modifications.

- Actions run in the order they are written, in the directory of the policy file by default.
- If an action fails (unexpected exit code/output, timeout or the command cannot be started), the remaining actions are skipped and the evaluation stops.
- With `continue_on_error: true`, a failed action is only logged as a warning and the remaining actions still run. This does not apply to a failed [trust](trust.md) check. A modified trusted file always stops the evaluation.
- With `wait: false`, the command is started in the background. There is no exit code, no output and no timeout, and the command keeps running if PowerRules ends.
- Commands can read the name of their rule and action from the environment variables `POWERRULES_RULE_NAME` and `POWERRULES_ACTION_NAME`.
- Actions are not executed with `--dry-run`.

## Related

<div class="grid cards" markdown>

--8<-- "related_grid.md:conditions"

--8<-- "related_grid.md:policy_evaluation"

--8<-- "related_grid.md:trust"

</div>
