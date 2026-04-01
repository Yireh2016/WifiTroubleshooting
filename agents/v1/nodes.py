import json
import sys
import os
import time
from pathlib import Path

from langgraph.graph import END

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from shared.state.state_v1 import ConversationState
from shared.prompts.base_prompts import (
    QUALIFY_PROMPT, GUIDE_REBOOT_PROMPT,
    CHECK_RESOLUTION_PROMPT, GRACEFUL_EXIT_PROMPT,
    CLOSE_SUCCESS_PROMPT, APOLOGIZE_EXIT_PROMPT,
)
from shared.rag.retriever import build_retriever, retrieve
from agents.v1.guardrails import GuardrailsManager
from agents.v1.logging.structured_logger import StructuredLogger
from agents.v1.logging.escalation_handler import EscalationHandler

LLM = None  # Lazy-loaded on first call
VECTORSTORE = None  # Lazy-loaded on first RAG call
LOGGER = None  # Lazy-loaded on first node execution
GUARDRAILS = None  # Lazy-loaded on first node execution
ESCALATION = None  # Lazy-loaded on first node execution

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

def _get_logger(request_id: str):
    """Lazy-load structured logger for conversation."""
    global LOGGER
    if LOGGER is None:
        enabled = os.getenv("LOGGING_ENABLED", "false").lower() == "true"
        LOGGER = StructuredLogger(enabled=enabled)
        LOGGER.request_id = request_id  # Override with conversation request_id
    return LOGGER

def _get_guardrails():
    """Lazy-load guardrails manager."""
    global GUARDRAILS
    if GUARDRAILS is None:
        GUARDRAILS = GuardrailsManager()
    return GUARDRAILS

def _get_escalation(request_id: str):
    """Lazy-load escalation handler for conversation."""
    global ESCALATION
    if ESCALATION is None:
        ESCALATION = EscalationHandler(request_id=request_id)
    return ESCALATION

def _call_llm(messages: list, prompt: str) -> dict:
    """Call LLM with conversation history + prompt, parse JSON response."""
    llm = _get_llm()
    llm_messages = [
        SystemMessage(content=prompt),
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
    """Qualify whether reboot is needed. Checks guardrails first."""
    start_time = time.time()
    logger = _get_logger(state.request_id)
    guardrails = _get_guardrails()

    logger.log_node_entry("qualify", state.dict())

    # Extract last user message
    user_message = None
    for msg in reversed(state.messages):
        if hasattr(msg, 'type') and msg.type == "human":
            user_message = msg.content
            break

    # Guardrails check: scope + injection
    if user_message and guardrails.enabled:
        is_safe, reason = guardrails.check_user_input(user_message)
        logger.log_guardrail_check("scope_and_injection", is_safe, reason)

        if not is_safe:
            logger.log_node_exit("qualify", time.time() - start_time, {"exit_reason": "out_of_scope"})
            return {
                "messages": [AIMessage(content=(
                    "I'm here to help with WiFi troubleshooting on your Linksys EA6350 router. "
                    f"Your question is outside my scope. {reason}"
                ))],
                "reboot_appropriate": False,
                "exit_reason": "out_of_scope"
            }

    # Normal qualification flow
    result = _call_llm(state.messages, QUALIFY_PROMPT)
    llm_duration = time.time() - start_time
    logger.log_llm_call("qualify", QUALIFY_PROMPT, user_message or "", result.get("reply", ""), llm_duration)

    updates = {"messages": [AIMessage(content=result["reply"])]}

    if result["decision"] == "reboot":
        updates["reboot_appropriate"] = True
    elif result["decision"] == "exit":
        updates["reboot_appropriate"] = False
        updates["exit_reason"] = result.get("exit_reason", "unknown")
    # "ask_more" → reboot_appropriate stays None, loops back

    logger.log_node_exit("qualify", time.time() - start_time, updates)
    return updates

def graceful_exit(state: ConversationState) -> dict:
    logger = _get_logger(state.request_id)
    prompt = GRACEFUL_EXIT_PROMPT.format(exit_reason=state.exit_reason or "unknown")
    result = _call_llm(state.messages, prompt)
    logger.finalize(exit_reason=state.exit_reason)
    return {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "graceful_exit"}

def retrieval(state: ConversationState) ->dict:
    # Retrieve RAG context once, cache in state
    rag_context = state.rag_context
    if rag_context is None:
        vs = _get_vectorstore()
        results = retrieve(vectorstore=vs, query= "router reboot steps power cord disconnect",k=10)
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
    """Guide user through reboot steps. Post-filter for hallucinations."""
    start_time = time.time()
    logger = _get_logger(state.request_id)
    guardrails = _get_guardrails()

    logger.log_node_entry("guide_reboot", state.dict())

    prompt = GUIDE_REBOOT_PROMPT.format(
        rag_context=state.rag_context,
    )
    result = _call_llm(state.messages, prompt)
    llm_duration = time.time() - start_time
    logger.log_llm_call("guide_reboot", prompt, "", result.get("reply", ""), llm_duration)

    # Post-filter for hallucinations
    response = result["reply"]
    if guardrails.enabled:
        filtered_response, passed_filter = guardrails.filter_agent_response(
            response, state.rag_context
        )
        logger.log_guardrail_check("hallucination_filter", passed_filter, "Post-filter check")
        response = filtered_response

    updates = {
        "messages": [AIMessage(content=response)],
        "last_executed_node": "guide_reboot",
    }
    if result.get("all_steps_done"):
        updates["next_node"] = "check_resolution"

    logger.log_node_exit("guide_reboot", time.time() - start_time, updates)
    return updates

def check_resolution(state: ConversationState) -> dict:
    """Check if issue is resolved. Track inconclusive exchanges for escalation."""
    start_time = time.time()
    logger = _get_logger(state.request_id)
    escalation = _get_escalation(state.request_id)

    logger.log_node_entry("check_resolution", state.dict())

    result = _call_llm(state.messages, CHECK_RESOLUTION_PROMPT)
    llm_duration = time.time() - start_time
    logger.log_llm_call("check_resolution", CHECK_RESOLUTION_PROMPT, "", result.get("reply", ""), llm_duration)

    updates = {
        "messages": [AIMessage(content=result["reply"])],
        "last_executed_node": "check_resolution",
    }

    # Track resolution status
    if result.get("resolved") is True:
        updates["issue_resolved"] = True
    elif result.get("resolved") is False:
        updates["issue_resolved"] = False
    else:
        # Inconclusive response — mark for escalation tracking
        if os.getenv("ESCALATION_ENABLED", "false").lower() == "true":
            escalation.mark_inconclusive("ambiguous_resolution_response")
            updates["inconclusive_count"] = escalation.get_inconclusive_count()

            logger.log_escalation("inconclusive_exchange", escalation.get_inconclusive_count())

            # Check if we've hit escalation threshold
            if escalation.should_escalate():
                updates["escalation_triggered"] = True
                updates["next_node"] = "escalation_notice"

    logger.log_node_exit("check_resolution", time.time() - start_time, updates)
    return updates

def close_success(state: ConversationState) -> dict:
    logger = _get_logger(state.request_id)
    result = _call_llm(state.messages, CLOSE_SUCCESS_PROMPT)
    logger.finalize(exit_reason="issue_resolved")
    return {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "close_success"}

def apologize_and_exit(state: ConversationState) -> dict:
    result = _call_llm(state.messages, APOLOGIZE_EXIT_PROMPT)
    logger = _get_logger(state.request_id)
    logger.finalize(exit_reason="reboot_failed")
    return {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "apologize_and_exit"}

def escalation_notice(state: ConversationState) -> dict:
    """Notify user of escalation and log for support team."""
    logger = _get_logger(state.request_id)
    escalation = _get_escalation(state.request_id)

    escalation_msg = escalation.get_escalation_message()
    logger.log_escalation(
        "escalation_triggered_after_threshold",
        escalation.get_inconclusive_count()
    )
    logger.finalize(exit_reason="escalation")

    return {
        "messages": [AIMessage(content=escalation_msg)],
        "last_executed_node": "escalation_notice",
        "escalation_triggered": True,
        "exit_reason": "escalation"
    }

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
    if state.escalation_triggered:
        return "escalation_notice"
    if state.issue_resolved is None:
        return END  # Return to user for answer
    if state.issue_resolved:
        return "close_success"
    return "apologize_and_exit"
