"""Unified permission guard: action x group x channel.

Controls which actions are allowed based on the combination of
user group (admin/dev/freela) and channel (telegram/api).

Admin users can do everything from any channel (including API).
Dev/freela users have restricted actions that require Telegram (human).
"""

import logging

logger = logging.getLogger(__name__)

# Actions that require Telegram for non-admin users.
# Admin users can perform these from any channel (API included).
SENSITIVE_ACTIONS = frozenset({
    "create_hours",
    "approve_change",
    "reject_change",
    "delete_task",
})

# Actions restricted to admin group regardless of channel.
ADMIN_ONLY_ACTIONS = frozenset({
    "approve_change",
    "reject_change",
})

# Permission matrix: (group, channel) → set of blocked actions
# If an action is NOT in the blocked set, it's allowed.
_BLOCKED: dict[tuple[str, str], frozenset[str]] = {
    # Admin via Telegram: everything allowed
    ("admin", "telegram"): frozenset(),
    # Admin via API: everything allowed (key feature — admin's AI tools work fully)
    ("admin", "api"): frozenset(),
    # Dev via Telegram: can do everything except admin-only
    ("dev", "telegram"): ADMIN_ONLY_ACTIONS,
    # Dev via API: sensitive actions blocked
    ("dev", "api"): SENSITIVE_ACTIONS,
    # Freela via Telegram: can do everything except admin-only
    ("freela", "telegram"): ADMIN_ONLY_ACTIONS,
    # Freela via API: sensitive actions blocked
    ("freela", "api"): SENSITIVE_ACTIONS,
}


class ChannelGuard:
    """Validates actions against the unified permission matrix."""

    @staticmethod
    def check(action: str, channel: str, group: str = "freela") -> bool:
        """Return True if the action is allowed for this group+channel."""
        blocked = _BLOCKED.get((group, channel), SENSITIVE_ACTIONS)
        if action in blocked:
            logger.warning(
                "Blocked action '%s' for group='%s' channel='%s'",
                action, group, channel,
            )
            return False
        return True

    @staticmethod
    def require(action: str, channel: str, group: str = "freela") -> None:
        """Raise ValueError if the action is not allowed."""
        if not ChannelGuard.check(action, channel, group):
            if action in ADMIN_ONLY_ACTIONS and group != "admin":
                raise ValueError(
                    f"Action '{action}' requires admin permission."
                )
            raise ValueError(
                f"Action '{action}' requires Telegram for group '{group}'."
            )
