from pathlib import Path

from powerrules.config.loader import ConfigurationLoader
from powerrules.providers.clock import ClockProvider
from powerrules.trust.report import TrustReport, build_trust_report
from powerrules.trust.store import (
    TrustStore,
    compute_digest,
    compute_trusted_file_digests,
)


def trust_policy(
    policy_path: Path,
    trust_store: TrustStore,
    clock_provider: ClockProvider,
) -> TrustReport:
    """Trust the current content of a policy and of its trusted files.

    Args:
        policy_path: Path of the policy file.
        trust_store: Store in which the trust is saved.
        clock_provider: Provider for the time at which the policy is trusted.

    Returns:
        The trust report read back from the store, so it shows what was actually saved.

    Raises:
        OSError: If the policy cannot be read.
        yaml.YAMLError: If the YAML cannot be parsed.
        ValidationError: If the policy is invalid. An invalid policy must not be trusted.
        FileIntegrityError: If a trusted file cannot be read.
        TrustStoreError: If the trust store cannot be read or written.
    """
    # Resolve symbolic links once, so the validated, hashed and trusted file is the same one
    resolved_policy = policy_path.resolve()
    content = resolved_policy.read_bytes()
    configuration = ConfigurationLoader().parse(content)
    digest = compute_digest(content)
    trusted_files = compute_trusted_file_digests(
        resolved_policy.parent, configuration.get_trusted_files()
    )

    trust_store.trust(resolved_policy, digest, clock_provider.now(), trusted_files)

    return build_trust_report(
        resolved_policy,
        digest,
        trust_store.get_entry(resolved_policy),
        trusted_files,
    )
