from pathlib import Path

import yaml

from powerrules.config.models import RuleSetConfiguration
from powerrules.trust.checker import PolicyTrustChecker


class ConfigurationLoader:
    """Load and validate PowerRules configuration files."""

    def __init__(self, trust_checker: PolicyTrustChecker | None = None) -> None:
        """Create a loader.

        Args:
            trust_checker: Checks whether a policy is trusted before it is parsed. None skips the check.
        """
        self.trust_checker = trust_checker

    def load(self, path: Path) -> RuleSetConfiguration:
        """Load and validate a PowerRules configuration file.

        The file is read exactly once, so the trust check and the parsing operate on identical bytes.
        Symbolic links are resolved once up front, so the trust check refers to the file which was actually read.
        The policy is parsed before the trust check, because its trusted files have to be known.
        Parsing only reads data, nothing of the policy is executed.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            Validated PowerRules configuration.

        Raises:
            OSError: If the configuration file cannot be read.
            PolicyNotTrustedError: If trust is required and the policy or a trusted file is not trusted.
            TrustStoreError: If trust is required and the trust store cannot be read.
            yaml.YAMLError: If the YAML cannot be parsed.
            ValidationError: If the configuration is invalid.
        """
        resolved_path = path.resolve()
        content = resolved_path.read_bytes()
        configuration = self.parse(content)

        if self.trust_checker is not None:
            # Relative paths are resolved against the directory of the policy
            self.trust_checker.verify(
                resolved_path,
                content,
                tuple(
                    resolved_path.parent / file
                    for file in configuration.get_trusted_files()
                ),
            )

        return configuration

    def parse(self, content: bytes) -> RuleSetConfiguration:
        """Parse and validate the content of a PowerRules configuration file.

        Args:
            content: Raw bytes of the YAML configuration file, encoded as UTF-8.

        Returns:
            Validated PowerRules configuration.

        Raises:
            yaml.YAMLError: If the YAML cannot be parsed.
            ValidationError: If the configuration is invalid.
        """
        data = yaml.safe_load(content.decode("utf-8"))

        return RuleSetConfiguration.model_validate(data)
