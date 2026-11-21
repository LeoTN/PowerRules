# Match types

!!! abstract "Summary"

    Process names, window titles and command output can be matched exactly, with a regular expression or by a part of the text. Regular expressions use full-string matching.

## Example

``` yaml
# Match if the process name contains "fire"
- process:
    name: "fire"
    exists: true
    match:
      type: contains
      case_sensitive: true # This is the default

# Match if the window title starts with "firefox" (case-insensitive)
- window:
    title: "Firefox.*"
    exists: true
    match:
      type: regex
      case_sensitive: false
```

## Options

Options of `match`:

| Option           | Default | Description                                                                           |
| ---------------- | ------- | ------------------------------------------------------------------------------------- |
| `type`           | `exact` | Matching mode: `exact`, `regex` (full-string match) or `contains` (part of the text). |
| `case_sensitive` | `true`  | Whether uppercase and lowercase letters are treated differently.                      |

## Details

- Match types are available for the [process](../conditions/process.md) and [window](../conditions/window.md) conditions and for the `stdout` and `stderr` of [commands](command_options.md).
- A regular expression has to match the whole value. `fire` does not match `firefox`, but `fire.*` does.
- A `.` in a regular expression also matches line breaks, so patterns work on multi-line output.
- The output of a command is compared after leading and trailing whitespace was removed.
