from typing import Optional, Annotated
from pydantic import BaseModel, Field
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class ConversationState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    reboot_appropriate: Optional[bool] = None
    issue_resolved: Optional[bool] = None
    current_step: int = 0
    current_node: str = "qualify"
    rag_context: Optional[str] = None
    exit_reason: Optional[str] = None
    rag_context: str

    class Config:
        arbitrary_types_allowed = True
