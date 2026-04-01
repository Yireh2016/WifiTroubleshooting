from typing import Optional, Annotated
from pydantic import BaseModel, Field
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage
from uuid import uuid4


class ConversationState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    reboot_appropriate: Optional[bool] = None
    issue_resolved: Optional[bool] = None
    next_node: str = "not_started"
    last_executed_node: str = "qualify"
    rag_context: Optional[str] = None
    exit_reason: Optional[str] = None
    # V1 Upgrades: Logging, guardrails, escalation
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    inconclusive_count: int = 0
    escalation_triggered: bool = False

    class Config:
        arbitrary_types_allowed = True
