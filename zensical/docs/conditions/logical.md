# Logical

!!! abstract "Summary"

    Combines other conditions with `and`, `or` and `not`. They can be nested as deeply as needed.

## Example

``` yaml
rules:
  # Match in December or January, but not on weekends, while VLC is running
  - name: "Winter weekday with VLC"
    conditions:
      and:
        - or: #(1)!
            - datetime:
                month:
                  - "December"
            - datetime:
                month:
                  - "January"
        - not:
            datetime:
              weekday:
                - "Saturday"
                - "Sunday"
        - process:
            name: "vlc" #(2)!
            exists: true
    actions:
      - run: "echo Winter weekday with VLC"
```

1.  Using `or` like this is a more elaborate way of writing:

    ``` yaml
    month: ["December", "January"]
    ```

    but you get the idea.

2.  Consider using `contains` or `regex` matching for different platforms.

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
