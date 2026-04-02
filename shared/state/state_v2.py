from typing import Optional, Literal, Annotated
from pydantic import BaseModel, Field
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage
from shared.state.state_v1 import ConversationState as ConversationStateV1


class ConversationState(ConversationStateV1):
    """V2 state: extends V1 with multi-model, mode, and manual-aware fields."""

    # Router model discovery
    router_model: Optional[str] = None  # e.g., "EA6350" (normalized UPPER)
    router_model_attempts: int = 0  # 0-3, gate at 3

    # Manual-aware qualifier caching
    manual_context: Optional[str] = None  # Retrieved at QUALIFY entry, cached

    # Reboot method
    reboot_method: Optional[Literal["physical", "app"]] = None

    # Conversation mode (set once at session start)
    conversation_mode: Literal["self_serve", "agent_assisted"] = "self_serve"

    # Connectivity gating for app reboot
    has_internet_on_other_device: Optional[bool] = None

    class Config:
        arbitrary_types_allowed = True
