"""
Format mappers for Codex App Server JSON-RPC protocol.

The Codex App Server uses kebab-case for enum values in its JSON-RPC API.
This module provides mapping utilities to normalize values from various
input formats (camelCase, kebab-case) to the expected kebab-case format.
"""

from typing import Dict

# Sandbox mode mapping to kebab-case
SANDBOX_MAP: Dict[str, str] = {
    # kebab-case (canonical)
    "danger-full-access": "danger-full-access",
    "workspace-write": "workspace-write",
    "read-only": "read-only",
    # camelCase variants
    "dangerFullAccess": "danger-full-access",
    "workspaceWrite": "workspace-write",
    "readOnly": "read-only",
}

# Approval policy mapping to kebab-case
APPROVAL_POLICY_MAP: Dict[str, str] = {
    # kebab-case (canonical)
    "never": "never",
    "on-request": "on-request",
    "on-failure": "on-failure",
    "untrusted": "untrusted",
    # camelCase variants
    "onRequest": "on-request",
    "onFailure": "on-failure",
}

# Default values
DEFAULT_SANDBOX = "danger-full-access"
DEFAULT_APPROVAL_POLICY = "never"


def map_sandbox(value: str) -> str:
    """Map sandbox value to kebab-case format.

    Args:
        value: Sandbox value in any format (kebab-case or camelCase)

    Returns:
        Kebab-case sandbox value for Codex App Server API
    """
    return SANDBOX_MAP.get(value, DEFAULT_SANDBOX)


def map_approval_policy(value: str) -> str:
    """Map approval policy value to kebab-case format.

    Args:
        value: Approval policy in any format (kebab-case or camelCase)

    Returns:
        Kebab-case approval policy for Codex App Server API
    """
    return APPROVAL_POLICY_MAP.get(value, DEFAULT_APPROVAL_POLICY)
