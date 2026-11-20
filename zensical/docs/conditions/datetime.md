# Datetime

!!! abstract "Summary"

    Matches a time of day, an absolute date range, weekdays or months. All values use the local time of the computer.

## Example

``` yaml
rules:
  # Match on Saturday and Sunday nights in August from 22:00 until 6:00 the next morning
  - name: "Weekend night in August"
    conditions:
      datetime:
        between:
          start: "22"
          end: "6"
        weekday:
          - "Saturday"
          - "Sunday"
        month:
          - "August"
    actions:
      - run: "echo Weekend night in August"
```

More examples:

``` yaml
# Every day from 23:00 until 1:30 the next morning
- datetime:
    between:
      start: "23"
      end: "1:30"

# Mondays and Fridays
- datetime:
    weekday: ["Monday", "Friday"]

# The whole days 2026-08-21 and 2026-08-22
- datetime:
    between:
      start: "2026-08-21"
      end: "2026-08-23"

# From 2026-08-21 18:00 until 2026-08-23 6:00
- datetime:
    between:
      start: "2026-08-21 18:00"
      end: "2026-08-23 6:00"
```

## Options

At least one of `between`, `weekday` and `month` is required. If several are configured, all of them have to match.

| Option    | Default | Description                                                                                   |
| --------- | ------- | --------------------------------------------------------------------------------------------- |
| `between` | none    | Range in which the condition matches. `start` and `end` must be of the same kind (see below). |
| `weekday` | none    | List of English weekday names (case-insensitive), e.g. `Monday`.                              |
| `month`   | none    | List of English month names (case-insensitive), e.g. `January`.                               |

Kinds of `between`:

| Kind           | Format                                              | Example              | Description                                                                |
| -------------- | --------------------------------------------------- | -------------------- | -------------------------------------------------------------------------- |
| Time of day    | `H`, `HH`, `H:MM`, `HH:MM`, `H:MM:SS` or `HH:MM:SS` | `"23"`, `"1:30"`     | Repeats every day and may cross midnight.                                  |
| Date           | `YYYY-MM-DD`                                        | `"2026-08-21"`       | Covers whole days, from 0:00 of the start date until 0:00 of the end date. |
| Date with time | `YYYY-MM-DD` followed by a space or `T` and a time  | `"2026-08-21 18:00"` | Absolute range without timezone.                                           |

## Details

- The start of a range is inclusive, the end is exclusive.
- If a time range crosses midnight, `weekday` and `month` refer to the day on which the range starts. With `23` to `1:30` and `Monday`, the condition matches from Monday 23:00 until Tuesday 1:30.
- For absolute ranges, `weekday` and `month` refer to the current day. With `2026-08-21 18:00` to `2026-08-23 6:00` and `Friday`, the condition only matches on Friday from 18:00 until midnight, because the weekday changes to Saturday at 0:00.
- Timezones are not supported.

## Related

<div class="grid cards" markdown>

--8<-- "related_grid.md:sub1_policy_evaluation"

--8<-- "related_grid.md:sub1_actions"

--8<-- "related_grid.md:sub1_trust"

</div>
