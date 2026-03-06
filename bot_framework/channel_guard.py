"""Channel guard for enforcing human-only actions.

Actions in HUMAN_ONLY_ACTIONS can only be executed from Telegram (not API).
This prevents AI tools from performing sensitive operations autonomously.
"""

import logging

logger = logging.getLogger(__name__)

HUMAN_ONLY_ACTIONS = frozenset({
    "create_hours",
    "approve_change",
    "reject_change",
    "delete_task",
})


class ChannelGuard:
    """Validates that sensitive actions come from the right channel."""

    @staticmethod
    def check(action: str, channel: str) -> bool:
        """Return True if the action is allowed from this channel."""
        if action in HUMAN_ONLY_ACTIONS and channel != "telegram":
            logger.warning(
                "Blocked human-only action '%s' from channel '%s'",
                action, channel,
            )
            return False
        return True

    @staticmethod
    def require(action: str, channel: str) -> None:
        """Raise ValueError if the action is not allowed from this channel."""
        if not ChannelGuard.check(action, channel):
            raise ValueError(
                f"Action '{action}' can only be performed via Telegram (human)."
            )
