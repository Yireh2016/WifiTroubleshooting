import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from shared.state.state_v2 import ConversationState
from agents.v2.nodes import (
    welcome,
    discover_model,
    unsupported_model_exit,
    qualify,
    select_reboot_method,
    retrieval,
    guide_reboot,
    check_resolution,
    close_success,
    apologize_and_exit,
    graceful_exit,
    route_entry,
    route_after_welcome,
    route_after_discover,
    route_after_qualify,
    route_after_select_method,
    route_after_guide,
    route_after_check,
)


def build_graph():
    """Build the V2 state machine with 9 nodes and conditional routing."""
    graph = StateGraph(ConversationState)

    # Router node (no-op dispatcher)
    graph.add_node("router", lambda state: {})

    # 9 functional nodes
    graph.add_node("welcome", welcome)
    graph.add_node("discover_model", discover_model)
    graph.add_node("unsupported_model_exit", unsupported_model_exit)
    graph.add_node("qualify", qualify)
    graph.add_node("select_reboot_method", select_reboot_method)
    graph.add_node("retrieval", retrieval)
    graph.add_node("guide_reboot", guide_reboot)
    graph.add_node("check_resolution", check_resolution)
    graph.add_node("close_success", close_success)
    graph.add_node("apologize_and_exit", apologize_and_exit)
    graph.add_node("graceful_exit", graceful_exit)

    # Entry: always go through router
    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        route_entry,
        {
            "welcome": "welcome",
            "discover_model": "discover_model",
            "unsupported_model_exit": "unsupported_model_exit",
            "qualify": "qualify",
            "select_reboot_method": "select_reboot_method",
            "retrieval": "retrieval",
            "guide_reboot": "guide_reboot",
            "check_resolution": "check_resolution",
        },
    )

    # After welcome
    graph.add_conditional_edges(
        "welcome",
        route_after_welcome,
        {
            "qualify": "qualify",
            "unsupported_model_exit": "unsupported_model_exit",
            END: END,
        },
    )

    # After discover_model
    graph.add_conditional_edges(
        "discover_model",
        route_after_discover,
        {
            "qualify": "qualify",
            "unsupported_model_exit": "unsupported_model_exit",
            END: END,
        },
    )

    # After qualify
    graph.add_conditional_edges(
        "qualify",
        route_after_qualify,
        {
            END: END,
            "select_reboot_method": "select_reboot_method",
            "graceful_exit": "graceful_exit",
        },
    )

    # After select_reboot_method -> always retrieval
    graph.add_edge("select_reboot_method", "retrieval")

    # After retrieval -> guide_reboot
    graph.add_edge("retrieval", "guide_reboot")

    # After guide_reboot
    graph.add_conditional_edges(
        "guide_reboot",
        route_after_guide,
        {
            END: END,
            "check_resolution": "check_resolution",
        },
    )

    # After check_resolution
    graph.add_conditional_edges(
        "check_resolution",
        route_after_check,
        {
            END: END,
            "close_success": "close_success",
            "apologize_and_exit": "apologize_and_exit",
        },
    )

    # Terminal nodes
    graph.add_edge("unsupported_model_exit", END)
    graph.add_edge("graceful_exit", END)
    graph.add_edge("close_success", END)
    graph.add_edge("apologize_and_exit", END)

    return graph


def compile_graph():
    """Compile the graph with memory checkpointer for conversation persistence."""
    graph = build_graph()
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
