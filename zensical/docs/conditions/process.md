# Process

!!! abstract "Summary"

    Matches while a process with the given name exists or does not exist. The name is compared with a [match type](../reference/match_types.md).

## Example

=== "Windows"

    ``` yaml
    rules:
      # Match while Firefox is running
      - name: "Firefox is running"
        conditions:
          process:
            name: "firefox.exe"
            exists: true
        actions:
          - run: "echo Firefox is running"
    ```

=== "Linux & macOS"

    ``` yaml
    rules:
      # Match while Firefox is running
      - name: "Firefox is running"
        conditions:
          process:
            name: "firefox"
            exists: true
        actions:
          - run: "echo Firefox is running"
    ```

## Options

| Option   | Default               | Description                                                              |
| -------- | --------------------- | ------------------------------------------------------------------------ |
| `name`   | required              | Name of the process to check.                                            |
| `exists` | required              | Whether the process is expected to exist (`true`) or not (`false`).      |
| `match`  | exact, case-sensitive | How the name is matched, see [Match Types](../reference/match_types.md). |

## Details

- Process names usually differ between platforms (e.g. `firefox.exe` on Windows, `firefox` on Linux and macOS). Use a `contains` or `regex` match to write one policy for several platforms.

## Related

<div class="grid cards" markdown>

--8<-- "related_grid.md:sub1_policy_evaluation"

--8<-- "related_grid.md:sub1_actions"

--8<-- "related_grid.md:sub1_trust"

</div>
