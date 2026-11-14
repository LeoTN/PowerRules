# Getting Started

Create, validate, trust and run your first policy.

## Installation

=== "pip"

    Requires Python 3.11 or newer.

    ``` bash
    pip install powerrules
    ```

=== "Standalone binary"

    Download the binary for your platform from the [latest release](https://github.com/LeoTN/PowerRules/releases/latest).

!!! note

    `pwru` is installed by pip. When using a standalone binary, call it by its file name instead.

Check the version:

``` bash
pwru --version
```

## Policy

### Creation

Create a file named `my-policy.yaml`:

``` yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/LeoTN/PowerRules/main/assets/schema/powerrules_policy.schema.json
# (1)!
rules:
  - name: "Demo rule"
    conditions:
      process:
        name: "powerrules-demo"
        exists: false
    actions:
      - name: "Say hello"
        run: "echo Hello from PowerRules"
```

1. Editors with YAML support can use this schema for validation and autocompletion.

The rule matches while no process named `powerrules-demo` is running.

### Validation

``` bash
pwru policy validate --policy my-policy.yaml
```

### Trust

Review the policy and trust it:

``` bash
pwru trust add --policy my-policy.yaml
```

PowerRules refuses to run policies which are not trusted or were modified since.  
[Learn more about trust](trust.md)

### Execution

Use `--once` to evaluate the policy a single time:

``` bash
pwru policy run --once --policy my-policy.yaml
```

``` { .pwsh .no-copy }
INFO     Running policy 'my-policy.yaml' once...
INFO     Policy '/path/to/my-policy.yaml' is trusted
INFO     Running action 'Say hello'
INFO     Action 'Say hello' finished with exit code 0
INFO     Rule 'Demo rule' matched, executed actions: 'Say hello'
```

## Related

<div class="grid cards" markdown>

--8<-- "related_grid.md:policy_evaluation"

--8<-- "related_grid.md:conditions"

--8<-- "related_grid.md:actions"

--8<-- "related_grid.md:trust"

</div>
