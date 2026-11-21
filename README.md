<div align="center">
  <!-- The whitespace below is required for proper rendering -->
  
  [![PowerRules](https://raw.githubusercontent.com/LeoTN/PowerRules/main/assets/logo/readme_logo.svg)](https://github.com/LeoTN/PowerRules)

  [![latest-version](https://img.shields.io/github/v/release/LeoTN/PowerRules?&filter=*.*.*&display_name=release&style=for-the-badge&logo=Rocket&logoColor=green&label=LATEST&color=green)](https://github.com/LeoTN/PowerRules/releases/latest)
  [![latest-beta-version](https://img.shields.io/github/v/release/LeoTN/PowerRules?&include_prereleases&filter=*.*.*b*&display_name=release&style=for-the-badge&logo=Textpattern&logoColor=orange&label=LATEST%20BETA&color=orange)](https://github.com/LeoTN/PowerRules/releases)
  [![license](https://img.shields.io/github/license/LeoTN/PowerRules?&style=for-the-badge&logo=Google%20Docs&logoColor=blue&label=License&color=blue)](https://github.com/LeoTN/PowerRules/blob/main/LICENSE)

  [**Documentation**](https://leotn.github.io/PowerRules/latest/) · [**Getting started**](https://leotn.github.io/PowerRules/latest/getting_started/)
</div>

## About

PowerRules is a rule-based command automation tool: when the conditions of a rule match, its commands run.

``` yaml
rules:
  # Match when no backup process is running between 23:00 and 01:30
  - name: "Shutdown when no backup is running at night"
    conditions:
      and:
        - process:
            name: "backup"
            exists: false
        - datetime:
            between:
              start: "23"
              end: "1:30"
    actions:
      - run: "shutdown -h now"
```

## Credits & License

- [Inkscape](https://inkscape.org) → program used to design the logo
- [Nuitka](https://github.com/nuitka/nuitka) → standalone binaries
- [psutil](https://github.com/giampaolo/psutil) → process information
- [Pydantic](https://github.com/pydantic/pydantic) → configuration validation
- [PyYAML](https://github.com/yaml/pyyaml) → YAML policy parsing
- [rich](https://github.com/textualize/rich) → console output formatting
- [Typer](https://github.com/fastapi/typer) → command-line interface
- [Zensical](https://github.com/zensical/zensical) → documentation

_This repository is licensed under the [MIT License](https://github.com/LeoTN/PowerRules/blob/main/LICENSE)._
