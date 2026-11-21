# Exit codes

!!! abstract "Summary"

    `pwru` reports the result of a command via its exit code.

## Example

Validating a policy file which does not exist ends with exit code `2`:

=== "Linux and macOS (sh)"

    ``` bash
    pwru policy validate --policy missing.yaml
    echo $?
    ```

=== "Windows (PowerShell)"

    ``` powershell
    pwru policy validate --policy missing.yaml
    echo $LASTEXITCODE
    ```

``` { .text .no-copy }
ERROR    Policy file not found: /path/to/missing.yaml
2
```

## Exit codes

--8<-- "admonitions.md:contributions_welcome"

| Exit code | Meaning                        | Examples                                                                                                                                                                  |
| --------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `0`       | Success.                       | The policy is valid, was evaluated or no rule matched.                                                                                                                    |
| `1`       | Runtime error.                 | A condition cannot be evaluated, an action fails, the trust store cannot be read or written, an unexpected error occurred or a confirmation was declined (`trust prune`). |
| `2`       | Policy error or invalid usage. | The policy file was not found, contains invalid YAML or fails validation. Invalid command line options also use this code.                                                |
| `3`       | Trust error.                   | The policy or one of its `trusted_files` is not trusted, was modified or cannot be read, see [Trust](../trust.md).                                                        |
