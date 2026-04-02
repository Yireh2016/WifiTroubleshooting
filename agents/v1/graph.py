import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from shared.state.state_v1 import ConversationState
from agents.v1.nodes import (
    qualify, graceful_exit, guide_reboot, retrieval,
    check_resolution, close_success, apologize_and_exit,
    route_entry, route_after_qualify, route_after_guide, route_after_check,
)

def build_graph():
    graph = StateGraph(ConversationState)

    # Router node — no-op, just dispatches to the right node based on state
    graph.add_node("router", lambda state: {})
    graph.add_node("qualify", qualify)
    graph.add_node("graceful_exit", graceful_exit)
    graph.add_node("guide_reboot", guide_reboot)
    graph.add_node("retrieval", retrieval)
    graph.add_node("check_resolution", check_resolution)
    graph.add_node("close_success", close_success)
    graph.add_node("apologize_and_exit", apologize_and_exit)

    # Entry: always go through router to pick the right node
    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", route_entry, {
        "qualify": "qualify",
        "guide_reboot": "guide_reboot",
        "check_resolution": "check_resolution",
    })

    # After qualify: END (wait for user) or transition to next phase
    graph.add_conditional_edges("qualify", route_after_qualify, {
        END: END,
        "retrieval": "retrieval",
        "graceful_exit": "graceful_exit",
    })

    graph.add_edge("retrieval", "guide_reboot")

    # After guide: END (wait for user to confirm step) or move to resolution check
    graph.add_conditional_edges("guide_reboot", route_after_guide, {
        END: END,
        "check_resolution": "check_resolution",
    })

    # After check: END (wait for user answer) or terminal
    graph.add_conditional_edges("check_resolution", route_after_check, {
        END: END,
        "close_success": "close_success",
        "apologize_and_exit": "apologize_and_exit",
    })

    # Terminal nodes
    graph.add_edge("graceful_exit", END)
    graph.add_edge("close_success", END)
    graph.add_edge("apologize_and_exit", END)

    return graph

def compile_graph():
    graph = build_graph()
    checkpointer = MemorySaver()

    return graph.compile(
        checkpointer=checkpointer,
    )
