import json
import sys
from pathlib import Path

from langgraph.graph import END

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage
from shared.state.state_v2 import ConversationState
from shared.prompts.v2_prompts import (
    WELCOME_DISCOVER_MODEL_PROMPT,
    DISCOVER_MODEL_RETRY_PROMPT,
    UNSUPPORTED_MODEL_EXIT_PROMPT,
    V2_QUALIFY_PROMPT,
    V2_GUIDE_REBOOT_PROMPT,
    V2_SELECT_REBOOT_METHOD_PROMPT,
    V2_CHECK_RESOLUTION_PROMPT,
    V2_GRACEFUL_EXIT_PROMPT,
    V2_CLOSE_SUCCESS_PROMPT,
    V2_APOLOGIZE_EXIT_PROMPT,
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
        VECTORSTORE = build_retriever(
            chroma_path=str(Path(__file__).resolve().parents[2] / "chroma_db" / "v2")
        )
    return VECTORSTORE


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


def _list_available_models() -> list[str]:
    """Return unique model names from Chroma collection."""
    vs = _get_vectorstore()
    all_docs = vs.get(limit=10000)
    models = set(
        m.get("model_name")
        for m in all_docs.get("metadatas", [])
        if m.get("model_name")
    )
    return sorted(list(models))


def _check_model_exists(model_name: str) -> bool:
    """Check if model has documents in collection."""
    vs = _get_vectorstore()
    results = vs.get(where={"model_name": model_name.upper()}, limit=1)
    return len(results.get("ids", [])) > 0


# --- Node 1: Welcome / Discover Model ---
def welcome(state: ConversationState) -> dict:
    """First interaction: ask user for router model."""
    prompt = WELCOME_DISCOVER_MODEL_PROMPT.format(
        conversation_mode=state.conversation_mode,
    )
    result = _call_llm(state.messages, prompt)
    updates = {
        "messages": [AIMessage(content=result["reply"])],
        "last_executed_node": "welcome",
    }

    extracted = result.get("extracted_model")
    if extracted:
        normalized = extracted.strip().upper()
        if _check_model_exists(normalized):
            updates["router_model"] = normalized
        else:
            updates["router_model_attempts"] = state.router_model_attempts + 1
    else:
        updates["router_model_attempts"] = state.router_model_attempts + 1

    return updates


# --- Node 2: Discover Model Retry ---
def discover_model(state: ConversationState) -> dict:
    """Retry model discovery. Max 3 attempts."""
    available = _list_available_models()
    prompt = DISCOVER_MODEL_RETRY_PROMPT.format(
        attempt_number=state.router_model_attempts,
        available_models=", ".join(available),
        conversation_mode=state.conversation_mode,
    )
    result = _call_llm(state.messages, prompt)
    updates = {
        "messages": [AIMessage(content=result["reply"])],
        "last_executed_node": "discover_model",
    }

    extracted = result.get("extracted_model")
    if extracted:
        normalized = extracted.strip().upper()
        if _check_model_exists(normalized):
            updates["router_model"] = normalized
            return updates

    updates["router_model_attempts"] = state.router_model_attempts + 1
    return updates


# --- Node 3: Unsupported Model Exit ---
def unsupported_model_exit(state: ConversationState) -> dict:
    """Exit after 3 failed model discovery attempts."""
    result = _call_llm(state.messages, UNSUPPORTED_MODEL_EXIT_PROMPT.format(
        conversation_mode=state.conversation_mode,
    ))
    return {
        "messages": [AIMessage(content=result["reply"])],
        "exit_reason": "unsupported_model",
        "last_executed_node": "unsupported_model_exit",
    }


# --- Node 4: Qualify (Manual-Aware) ---
def qualify(state: ConversationState) -> dict:
    """Qualify issue with manual context. Retrieves manual on first call, caches."""
    manual_ctx = state.manual_context
    if manual_ctx is None:
        vs = _get_vectorstore()
        results = retrieve(
            vs,
            query="router features capabilities overview troubleshooting",
            model_name=state.router_model,
            section_tag="troubleshooting",
            k=5,
        )
        manual_ctx = "\n\n".join([r.page_content for r in results]) if results else ""

    prompt = V2_QUALIFY_PROMPT.format(
        conversation_mode=state.conversation_mode,
        router_model=state.router_model,
        manual_context=manual_ctx,
    )
    result = _call_llm(state.messages, prompt)
    updates = {
        "messages": [AIMessage(content=result["reply"])],
        "manual_context": manual_ctx,
        "last_executed_node": "qualify",
    }

    if result["decision"] == "reboot":
        updates["reboot_appropriate"] = True
    elif result["decision"] == "exit":
        updates["reboot_appropriate"] = False
        updates["exit_reason"] = result.get("exit_reason", "unknown")

    return updates


# --- Node 5: Select Reboot Method ---
def select_reboot_method(state: ConversationState) -> dict:
    """LLM decides physical vs app reboot based on connectivity context."""
    prompt = V2_SELECT_REBOOT_METHOD_PROMPT.format(
        router_model=state.router_model,
        manual_context=state.manual_context or "",
        messages="(see conversation history)",
        conversation_mode=state.conversation_mode,
        has_internet_on_other_device=state.has_internet_on_other_device,
    )
    result = _call_llm(state.messages, prompt)
    return {
        "messages": [AIMessage(content=result["reply"])],
        "reboot_method": result.get("selected_method", "physical"),
        "last_executed_node": "select_reboot_method",
    }


# --- Node 6: Retrieval ---
def retrieval(state: ConversationState) -> dict:
    """Retrieve reboot steps for the user's specific router model."""
    vs = _get_vectorstore()
    method = state.reboot_method or "physical"
    query = (
        "reboot steps restart power cord"
        if method == "physical"
        else "app reboot web portal restart"
    )
    results = retrieve(
        vs,
        query=query,
        model_name=state.router_model,
        section_tag="troubleshooting",
        k=10,
    )
    rag_context = results[0].page_content if results else None

    if rag_context is None:
        return {
            "messages": [
                AIMessage(
                    content="I'm having trouble accessing the reboot instructions for your router. Please refer to your router's manual for reboot steps."
                )
            ],
            "last_executed_node": "apologize_and_exit",
        }
    return {"rag_context": rag_context, "next_node": "guide_reboot"}


# --- Node 7: Guide Reboot ---
def guide_reboot(state: ConversationState) -> dict:
    """Walk user through reboot steps from RAG context."""
    prompt = V2_GUIDE_REBOOT_PROMPT.format(
        conversation_mode=state.conversation_mode,
        router_model=state.router_model,
        reboot_method=state.reboot_method or "physical",
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


# --- Node 8: Check Resolution ---
def check_resolution(state: ConversationState) -> dict:
    """Ask if issue resolved after reboot."""
    prompt = V2_CHECK_RESOLUTION_PROMPT.format(
        conversation_mode=state.conversation_mode,
        router_model=state.router_model,
    )
    result = _call_llm(state.messages, prompt)
    updates = {
        "messages": [AIMessage(content=result["reply"])],
        "last_executed_node": "check_resolution",
    }
    if result.get("resolved") is True:
        updates["issue_resolved"] = True
    elif result.get("resolved") is False:
        updates["issue_resolved"] = False
    return updates


# --- Node 9a: Close Success ---
def close_success(state: ConversationState) -> dict:
    prompt = V2_CLOSE_SUCCESS_PROMPT.format(
        conversation_mode=state.conversation_mode,
        router_model=state.router_model,
    )
    result = _call_llm(state.messages, prompt)
    return {
        "messages": [AIMessage(content=result["reply"])],
        "last_executed_node": "close_success",
    }


# --- Node 9b: Apologize and Exit ---
def apologize_and_exit(state: ConversationState) -> dict:
    prompt = V2_APOLOGIZE_EXIT_PROMPT.format(
        router_model=state.router_model,
        conversation_mode=state.conversation_mode,
    )
    result = _call_llm(state.messages, prompt)
    return {
        "messages": [AIMessage(content=result["reply"])],
        "last_executed_node": "apologize_and_exit",
    }


# --- Node 9c: Graceful Exit ---
def graceful_exit(state: ConversationState) -> dict:
    prompt = V2_GRACEFUL_EXIT_PROMPT.format(
        exit_reason=state.exit_reason or "unknown",
        router_model=state.router_model or "unknown",
        conversation_mode=state.conversation_mode,
    )
    result = _call_llm(state.messages, prompt)
    return {
        "messages": [AIMessage(content=result["reply"])],
        "last_executed_node": "graceful_exit",
    }


# --- Routing Functions ---


def route_entry(state: ConversationState) -> str:
    """Main router: dispatch based on current state."""
    if state.router_model is None:
        if state.router_model_attempts >= 3:
            return "unsupported_model_exit"
        if state.router_model_attempts == 0:
            return "welcome"
        return "discover_model"
    if state.reboot_appropriate is None:
        return "qualify"
    if state.reboot_appropriate and state.reboot_method is None:
        return "select_reboot_method"
    if state.reboot_appropriate and state.next_node == "not_started":
        return "retrieval"
    if state.next_node == "guide_reboot":
        return "guide_reboot"
    if state.next_node == "check_resolution" and state.issue_resolved is None:
        return "check_resolution"
    return "welcome"  # fallback


def route_after_welcome(state: ConversationState) -> str:
    if state.router_model is not None:
        return "qualify"
    if state.router_model_attempts >= 3:
        return "unsupported_model_exit"
    return END  # wait for user input


def route_after_discover(state: ConversationState) -> str:
    if state.router_model is not None:
        return "qualify"
    if state.router_model_attempts >= 3:
        return "unsupported_model_exit"
    return END  # wait for user to retry


def route_after_qualify(state: ConversationState) -> str:
    if state.reboot_appropriate is None:
        return END
    if state.reboot_appropriate:
        return "select_reboot_method"
    return "graceful_exit"


def route_after_select_method(state: ConversationState) -> str:
    return "retrieval"


def route_after_guide(state: ConversationState) -> str:
    if state.next_node == "check_resolution":
        return "check_resolution"
    return END


def route_after_check(state: ConversationState) -> str:
    if state.issue_resolved is None:
        return END
    if state.issue_resolved:
        return "close_success"
    return "apologize_and_exit"
