# Trust

!!! abstract "Summary"

    PowerRules remembers which policies you trust. Every modification of a policy or of its `trusted_files` makes it untrusted until you and trust it again.

## Example

``` bash
# Trust the current content of a policy and its trusted files
pwru trust add --policy my-policy.yaml

# Show all trusted policies and their current status
pwru trust list

# Remove the trust of a policy
pwru trust remove --policy my-policy.yaml

# Remove trusted policies whose policy file no longer exists
pwru trust prune
```

Scripts and other files which commands depend on are not detected automatically. List them in `trusted_files`:

``` yaml
actions:
  - run: "./backup.sh"
    working_directory: scripts
    trusted_files:
      - scripts/backup.sh # Relative to the policy file (not to working_directory)
```

## Options

| Command        | Options                                | Description                                                                                                                               |
| -------------- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `trust add`    | `--policy`                             | Trust the current content of the policy and its trusted files. An invalid policy or an unreadable file cannot be trusted.                 |
| `trust remove` | `--policy`                             | Remove the trust of the policy.                                                                                                           |
| `trust list`   | `--trusted`, `--modified`, `--missing` | List all trusted policies and their current status. Several filters can be combined, a policy is shown if it matches at least one.        |
| `trust prune`  | `--dry-run`, `--yes`, `-y`             | Remove trusted policies whose policy file no longer exists. `--dry-run` only shows what would be removed, `--yes` skips the confirmation. |

## Details

!!! warning

    Trust only covers the policy and its `trusted_files`. Programs started by commands are not checked and the trust store is only protected by the permissions of your user account.

- A policy is identified by its path and trusted by its content (SHA-256 hash).
- `pwru policy run` refuses to run untrusted policies by default. `--no-require-trust` overrides this.
- The policy and its trusted files are checked when the policy is loaded. Right before an action or a command condition runs, its `trusted_files` are checked again.
- A policy only counts as trusted if the policy and all of its trusted files are trusted.
- The trust store is saved in `~/.powerrules/trust.json`.

### Trust status of the policy and its files

| Status     | Description                                    |
| ---------- | ---------------------------------------------- |
| `trusted`  | The content is unchanged since it was trusted. |
| `unknown`  | The policy or file was never trusted.          |
| `modified` | The content changed since it was trusted.      |
| `missing`  | The file cannot be read.                       |

## Related

<div class="grid cards" markdown>

--8<-- "related_grid.md:getting_started"

--8<-- "related_grid.md:policy_evaluation"

--8<-- "related_grid.md:actions"

</div>
