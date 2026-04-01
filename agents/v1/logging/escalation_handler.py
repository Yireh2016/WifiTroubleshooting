"""
Escalation handler for V1 agent.

Tracks inconclusive exchanges and triggers escalation after threshold (default: 3).
Logs escalation events to file for support review.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional


class EscalationHandler:
    """
    Manages escalation flow for inconclusive conversations.

    Tracks when user provides ambiguous/unclear responses.
    After N inconclusive exchanges, initiates graceful escalation to support.
    """

    INCONCLUSIVE_THRESHOLD = 3

    def __init__(self, request_id: str):
        """
        Initialize escalation handler.

        Args:
            request_id: Conversation request ID (for logging)
        """
        self.request_id = request_id
        self.inconclusive_count = 0
        self.escalation_triggered = False
        self.escalation_log_dir = Path(__file__).resolve().parent.parent / "logs" / "escalations"
        self.escalation_log_dir.mkdir(parents=True, exist_ok=True)

    def mark_inconclusive(self, reason: str):
        """
        Mark an exchange as inconclusive.

        Args:
            reason: Why this exchange was inconclusive (e.g., "ambiguous_answer", "no_answer")
        """
        self.inconclusive_count += 1

        # Check if we've hit threshold
        if self.inconclusive_count >= self.INCONCLUSIVE_THRESHOLD:
            self.escalation_triggered = True
            self._log_escalation(reason)

    def should_escalate(self) -> bool:
        """Check if escalation threshold has been reached."""
        return self.escalation_triggered

    def get_inconclusive_count(self) -> int:
        """Get current inconclusive exchange count."""
        return self.inconclusive_count

    def _log_escalation(self, final_reason: str):
        """
        Log escalation to file for support team review.

        Args:
            final_reason: The final reason for escalation
        """
        escalation_file = self.escalation_log_dir / f"{self.request_id}.json"

        escalation_data = {
            "request_id": self.request_id,
            "timestamp": datetime.utcnow().isoformat(),
            "escalation_threshold": self.INCONCLUSIVE_THRESHOLD,
            "inconclusive_count": self.inconclusive_count,
            "final_reason": final_reason,
            "status": "pending_human_review"
        }

        try:
            with open(escalation_file, "w") as f:
                json.dump(escalation_data, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to write escalation log: {e}")

    def get_escalation_message(self) -> str:
        """Get user-facing escalation message."""
        return (
            "I'm having difficulty understanding your issue precisely. "
            "Let me escalate you to our support team for more personalized help. "
            "They'll get back to you shortly."
        )

    @property
    def escalation_log_path(self) -> str:
        """Return path to escalation log file."""
        return str(self.escalation_log_dir / f"{self.request_id}.json")
