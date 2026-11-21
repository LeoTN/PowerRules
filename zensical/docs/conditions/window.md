# Window

!!! abstract "Summary"

    Matches while a window with the given title exists or does not exist. Availability depends on the platform.

## Example

``` yaml
rules:
  # Match while a window title starts with "Firefox" (case-insensitive)
  - name: "Firefox window is open"
    conditions:
      window:
        title: "Firefox.*"
        exists: true
        match:
          type: regex
          case_sensitive: false
    actions:
      - run: "echo Firefox window is open"
```

## Options

| Option   | Default               | Description                                                               |
| -------- | --------------------- | ------------------------------------------------------------------------- |
| `title`  | required              | Title of the window to check.                                             |
| `exists` | required              | Whether the window is expected to exist (`true`) or not (`false`).        |
| `match`  | exact, case-sensitive | How the title is matched, see [Match Types](../reference/match_types.md). |

## Details

Only windows with a non-empty title are checked. Minimized windows are included.

| Platform | Requirement                                                                                                                                         |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Windows  | PowerRules has to run in the session of the logged-in user, not as a service. Windows on other virtual desktops and suspended UWP apps are skipped. |
| Linux    | An X11 session with a window manager which provides a window list. Wayland is not supported.                                                        |
| macOS    | The screen recording permission is required.                                                                                                        |

If a requirement is not met, window conditions may not be evaluated correctly and/or the evaluation stops.

## Related

<div class="grid cards" markdown>

--8<-- "related_grid.md:sub1_policy_evaluation"

--8<-- "related_grid.md:sub1_actions"

--8<-- "related_grid.md:sub1_trust"

</div>
