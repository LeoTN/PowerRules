# Logging

!!! abstract "Summary"

    Messages are shown on the console and written to a rotating log file. Commands of actions and command conditions and their output are only logged on `DEBUG` level.

## Example

``` bash
pwru policy run --log-level DEBUG --log-file my-log.log
```

## Options

All `policy` and `trust` commands accept these options:

| Option             | Default                | Description                                                                                                       |
| ------------------ | ---------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `--log-level`      | `INFO`                 | Minimum log level shown on the console and written to the log file. One of `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
| `--log-file`       | `powerrules.log`       | Path to the rotating log file.                                                                                    |
| `--log-level-file` | value of `--log-level` | Minimum log level written to the log file.                                                                        |

## Details

- Messages below `WARNING` are written to stdout, `WARNING` and `ERROR` to stderr.
- The log file is rotated at 10 MB and five backups are kept.
- Use `--log-level DEBUG` to find out why a condition did or did not match.
