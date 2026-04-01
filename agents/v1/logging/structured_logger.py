"""
Structured logging for V1 agent.

Logs conversations to JSON with:
- Request ID (UUID per conversation)
- Node execution trace (entry, exit, duration)
- LLM payloads (if enabled)
- User messages and responses
- State changes
"""

import json
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import uuid4


class StructuredLogger:
    """
    JSON logger for V1 conversations.

    Logs to agents/v1/logs/{request_id}.json if LOGGING_ENABLED=true
    """

    def __init__(self, enabled: bool = True):
        """
        Initialize logger.

        Args:
            enabled: Whether logging is active (from LOGGING_ENABLED env var)
        """
        self.enabled = enabled
        self.request_id = str(uuid4())
        self.log_dir = Path(__file__).resolve().parent.parent / "logs"
        self.log_file = self.log_dir / f"{self.request_id}.json"
        self.log_data: Dict[str, Any] = {
            "request_id": self.request_id,
            "start_time": datetime.utcnow().isoformat(),
            "enabled": enabled,
            "events": []
        }

        if self.enabled:
            self.log_dir.mkdir(exist_ok=True)

    def log_node_entry(self, node_name: str, state: Dict[str, Any]):
        """Log when a node starts executing."""
        if not self.enabled:
            return

        self.log_data["events"].append({
            "type": "node_entry",
            "timestamp": datetime.utcnow().isoformat(),
            "node_name": node_name,
            "state_keys": list(state.keys()) if state else [],
            "messages_count": len(state.get("messages", [])) if state else 0
        })

    def log_node_exit(
        self,
        node_name: str,
        duration_ms: float,
        state_update: Optional[Dict[str, Any]] = None
    ):
        """Log when a node finishes executing."""
        if not self.enabled:
            return

        self.log_data["events"].append({
            "type": "node_exit",
            "timestamp": datetime.utcnow().isoformat(),
            "node_name": node_name,
            "duration_ms": round(duration_ms, 2),
            "state_update_keys": list(state_update.keys()) if state_update else []
        })

    def log_llm_call(
        self,
        node_name: str,
        system_prompt: str,
        user_message: str,
        response: str,
        duration_ms: float,
        model: str = "gpt-4"
    ):
        """Log LLM API call details."""
        if not self.enabled:
            return

        # Only log payloads if explicitly enabled (to avoid verbosity)
        log_payloads = os.getenv("LOGGING_PAYLOADS", "false").lower() == "true"

        self.log_data["events"].append({
            "type": "llm_call",
            "timestamp": datetime.utcnow().isoformat(),
            "node_name": node_name,
            "model": model,
            "duration_ms": round(duration_ms, 2),
            "system_prompt": system_prompt if log_payloads else "[redacted]",
            "user_message": user_message if log_payloads else "[redacted]",
            "response": response if log_payloads else "[redacted]"
        })

    def log_user_message(self, content: str):
        """Log a user message."""
        if not self.enabled:
            return

        self.log_data["events"].append({
            "type": "user_message",
            "timestamp": datetime.utcnow().isoformat(),
            "content": content[:200]  # Truncate for safety
        })

    def log_agent_response(self, content: str):
        """Log agent response."""
        if not self.enabled:
            return

        self.log_data["events"].append({
            "type": "agent_response",
            "timestamp": datetime.utcnow().isoformat(),
            "content": content[:200]
        })

    def log_guardrail_check(self, check_type: str, passed: bool, reason: str):
        """Log guardrail validation."""
        if not self.enabled:
            return

        self.log_data["events"].append({
            "type": "guardrail_check",
            "timestamp": datetime.utcnow().isoformat(),
            "check_type": check_type,
            "passed": passed,
            "reason": reason
        })

    def log_escalation(self, reason: str, inconclusive_count: int):
        """Log escalation trigger."""
        if not self.enabled:
            return

        self.log_data["events"].append({
            "type": "escalation",
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason,
            "inconclusive_count": inconclusive_count
        })

    def finalize(self, exit_reason: Optional[str] = None):
        """
        Finalize and write log file.

        Args:
            exit_reason: Why conversation ended (qualification, escalation, etc.)
        """
        if not self.enabled:
            return

        self.log_data["end_time"] = datetime.utcnow().isoformat()
        self.log_data["exit_reason"] = exit_reason

        try:
            with open(self.log_file, "w") as f:
                json.dump(self.log_data, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to write log file: {e}")

    @property
    def log_file_path(self) -> str:
        """Return path to log file for user reference."""
        return str(self.log_file)
