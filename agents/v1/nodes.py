import json
import sys
from pathlib import Path

from langgraph.graph import END

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from shared.state.state_v1 import ConversationState
from shared.prompts.base_prompts import (
    SYSTEM_PROMPT, QUALIFY_PROMPT, GUIDE_REBOOT_PROMPT,
    CHECK_RESOLUTION_PROMPT, GRACEFUL_EXIT_PROMPT,
    CLOSE_SUCCESS_PROMPT, APOLOGIZE_EXIT_PROMPT,
)
from shared.rag.retriever import build_retriever, retrieve

LLM = None  # Lazy-loaded on first call
VECTORSTORE = None  # Lazy-loaded on first RAG call

def _get_llm():
    global LLM
    if LLM is None:
        LLM = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.2,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    return LLM

def _get_vectorstore():
    global VECTORSTORE
    if VECTORSTORE is None:
        VECTORSTORE = build_retriever()
    return VECTORSTORE

def _call_llm(messages: list, prompt: str) -> dict:
    """Call LLM with conversation history + prompt, parse JSON response."""
    llm = _get_llm()
    llm_messages = [
        SystemMessage(content=prompt),
        # SystemMessage(content=SYSTEM_PROMPT),
        *messages,
    ]
    response = llm.invoke(llm_messages)
    # Parse JSON from response, handling markdown fences
    content = response.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(content)

# --- Node Functions ---

def qualify(state: ConversationState) -> dict:
    result = _call_llm(state.messages, QUALIFY_PROMPT)
    updates = {"messages": [AIMessage(content=result["reply"])]}

    if result["decision"] == "reboot":
        updates["reboot_appropriate"] = True
    elif result["decision"] == "exit":
        updates["reboot_appropriate"] = False
        updates["exit_reason"] = result.get("exit_reason", "unknown")
    # "ask_more" → reboot_appropriate stays None, loops back

    return updates

def graceful_exit(state: ConversationState) -> dict:
    prompt = GRACEFUL_EXIT_PROMPT.format(exit_reason=state.exit_reason or "unknown")
    result = _call_llm(state.messages, prompt)
    return {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "graceful_exit"}

def retrieval(state: ConversationState) ->dict:
    # Retrieve RAG context once, cache in state
    rag_context = state.rag_context
    if rag_context is None:
        vs = _get_vectorstore()
        results = retrieve(vs, "router reboot steps power cord disconnect")
        rag_context = results[0].page_content if results else None

    if rag_context is None:
        # Fallback — retrieval failed
        return {
            "messages": [AIMessage(content=(
                "I'm having trouble accessing the specific reboot instructions. "
                "Please refer to your router's manual for reboot instructions, "
                "or visit Linksys.com/support/EA6350 for help."
            ))],
            "last_executed_node": "apologize_and_exit",
        }
    return {
        "rag_context": rag_context,
        "next_node": "guide_reboot",
    }

def guide_reboot(state: ConversationState) -> dict:
    prompt = GUIDE_REBOOT_PROMPT.format(
        rag_context=state.rag_context,
    )
    result = _call_llm(state.messages, prompt)

    updates = {
        "messages": [AIMessage(content=result["reply"])],
        "last_executed_node": "guide_reboot",
    }
    if result.get("all_steps_done"):
        updates["next_node"] = "check_resolution"

    return updates

def check_resolution(state: ConversationState) -> dict:
    result = _call_llm(state.messages, CHECK_RESOLUTION_PROMPT)
    updates = {
        "messages": [AIMessage(content=result["reply"])],
        "last_executed_node": "check_resolution",
    }
    if result.get("resolved") is True:
        updates["issue_resolved"] = True
    elif result.get("resolved") is False:
        updates["issue_resolved"] = False
    # None → keep asking
    return updates

def close_success(state: ConversationState) -> dict:
    result = _call_llm(state.messages, CLOSE_SUCCESS_PROMPT)
    return {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "close_success"}

def apologize_and_exit(state: ConversationState) -> dict:
    result = _call_llm(state.messages, APOLOGIZE_EXIT_PROMPT)
    return {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "apologize_and_exit"}

# --- Routing Functions ---

def route_entry(state: ConversationState) -> str:
    """Route to the correct node based on current state.
    Called on every graph invocation to resume at the right point."""
    if state.reboot_appropriate is None:
        return "qualify"
    if state.reboot_appropriate and state.next_node == "not_started":
        return "retrieval"
    if state.next_node == "guide_reboot":
        return "guide_reboot"
    if state.next_node == "check_resolution" and state.issue_resolved is None:
        return "check_resolution"
    # Fallback (shouldn't happen in normal flow)
    return "qualify"

def route_after_qualify(state: ConversationState) -> str:
    if state.reboot_appropriate is None:
        return END  # Return to user for more info
    if state.reboot_appropriate:
        return "retrieval"
    return "graceful_exit"

def route_after_guide(state: ConversationState) -> str:
    if state.next_node == "check_resolution":
        return "check_resolution"
    return END  # Return to user to confirm step

def route_after_check(state: ConversationState) -> str:
    if state.issue_resolved is None:
        return END  # Return to user for answer
    if state.issue_resolved:
        return "close_success"
    return "apologize_and_exit"
