# Demo policy

!!! abstract "Summary"

    Rules for the example policies in the docs. The main example of a page is a complete policy.

## Example

``` yaml
# Complete policy which passes "pwru policy validate". Fragments only under "More examples"
rules:
  # Match <when the rule matches>
  - name: "<What the match means>" # E.g. "Firefox is running"
    conditions:
      # Portable: only datetime and "exists: false". Anything else needs content tabs (see below) or a note
      # Same names everywhere: firefox, vlc, scripts/my-check.sh (conditions), scripts/my-action.sh (actions)
      <condition>:
        <options>
    actions:
      # An echo, unless the page explains an option which needs something else
      # Scripts are started with a path (./my-check.sh, .\my-check.ps1) and listed in trusted_files
      - run: "echo <What the match means>"
```

Platform-specific policy, split with content tabs (`Windows`, `Linux`, `macOS`):

=== "Windows"

    ``` yaml
    rules: ...
    ```

=== "Linux & macOS"

    ``` yaml
    rules: ...
    ```
