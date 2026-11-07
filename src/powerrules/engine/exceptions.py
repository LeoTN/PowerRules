class PowerRulesError(Exception):
    """Base exception for PowerRules errors."""


class ConditionEvaluationError(PowerRulesError):
    """Raised when a condition cannot be evaluated."""


class ConditionEvaluationProviderNotAvailableError(ConditionEvaluationError):
    """Raised when a condition cannot be evaluated because a provider is not available on the current platform.

    For example, the window provider is usually not available on headless systems."""


class ActionExecutionError(PowerRulesError):
    """Raised when an action cannot be executed."""


class ConfigurationError(PowerRulesError):
    """Raised when a configuration cannot be converted into a rule set."""


class PolicyNotTrustedError(PowerRulesError):
    """Raised when a policy has to be trusted, but is not trusted yet or was modified since it was trusted."""


class FileIntegrityError(PowerRulesError):
    """Raised when a trusted file cannot be read, is not trusted yet or was modified since it was trusted."""


class TrustStoreError(PowerRulesError):
    """Raised when the trust store cannot be read or written."""
