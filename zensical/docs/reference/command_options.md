# Command Options

!!! abstract "Summary"

    Options which [actions](../actions.md) and [command conditions](../conditions/command.md) have in common. They define which command runs, how it runs and what counts as success.

## Options

Options without a label apply to [actions](../actions.md) and [command conditions](../conditions/command.md). <span class="option-tag">Actions only</span> marks options which command conditions do not have.

| Option                                                           | Default                                          | Description                                                                                                                                            |
| ---------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `run`                                                            | required                                         | Command to run. A command with several lines stops at the first failing line.                                                                          |
| `name` <span class="option-tag">Actions only</span>              | `Action N of M`                                  | Name of the action, used in log messages.                                                                                                              |
| `shell`                                                          | `powershell` on Windows, `sh` on Linux and macOS | One of `sh`, `bash`, `cmd`, `powershell` or `pwsh`. The shell has to be installed.                                                                     |
| `working_directory`                                              | directory of the policy file                     | Relative paths are resolved against the directory of the policy file.                                                                                  |
| `env`                                                            | none                                             | Additional environment variables. Numbers and booleans are converted to strings. Names starting with `POWERRULES_` are reserved.                       |
| `timeout`                                                        | `60`                                             | Maximum run time in seconds. Afterwards, the command and its child processes are terminated. `null` or `.inf` disables the limit.                      |
| `success_exit_codes`                                             | `[0]`                                            | Exit codes which count as success.                                                                                                                     |
| `stdout`, `stderr`                                               | none                                             | Expected output of the command. A different output counts as unsuccessful (see below).                                                                 |
| `wait` <span class="option-tag">Actions only</span>              | `true`                                           | `false` starts the command in the background. Cannot be combined with `timeout`, `success_exit_codes`, `stdout` or `stderr`.                           |
| `continue_on_error` <span class="option-tag">Actions only</span> | `false`                                          | Whether the remaining actions still run if this action fails.                                                                                          |
| `trusted_files`                                                  | none                                             | Files (e.g. scripts) the command depends on. They are verified before every run. Relative paths are resolved against the directory of the policy file. |

Options of `stdout` and `stderr`:

| Option  | Default               | Description                                                   |
| ------- | --------------------- | ------------------------------------------------------------- |
| `value` | required              | Text or regular expression the output is compared with.       |
| `match` | exact, case-sensitive | How the output is matched, see [Match Types](match_types.md). |

## Details

- The output is compared after leading and trailing whitespace was removed.
- The shell `cmd` only supports a single line. Chain commands with `&&` instead.
- `trusted_files` are relative to the policy file, not to `working_directory`. See [Trust](../trust.md).

### Actions vs. command conditions

| Situation                                        | [Action](../actions.md)                                                                   | [Command condition](../conditions/command.md) |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------- | --------------------------------------------- |
| Unexpected exit code or output                   | The action fails and the remaining actions are skipped unless `continue_on_error` is set. | The condition does not match.                 |
| Command cannot be started or times out           | The action fails.                                                                         | The evaluation stops.                         |
| `POWERRULES_RULE_NAME`, `POWERRULES_ACTION_NAME` | Set.                                                                                      | Not set.                                      |
| `--dry-run`                                      | Not executed.                                                                             | Executed.                                     |
