import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.v2.graph import build_graph, compile_graph
from agents.v2.nodes import (
    route_entry,
    route_after_welcome,
    route_after_discover,
    route_after_qualify,
    route_after_select_method,
    route_after_guide,
    route_after_check,
)
from shared.state.state_v2 import ConversationState
from langgraph.graph import END


class TestGraphStructure:
    """Tests for graph structure and compilation."""

    def test_graph_has_all_nodes(self):
        """Graph contains all 11 nodes (router + 10 functional)."""
        graph = build_graph()
        nodes = list(graph.nodes.keys())

        expected_nodes = [
            "router",
            "welcome",
            "discover_model",
            "unsupported_model_exit",
            "qualify",
            "select_reboot_method",
            "retrieval",
            "guide_reboot",
            "check_resolution",
            "close_success",
            "apologize_and_exit",
            "graceful_exit",
        ]

        for node in expected_nodes:
            assert node in nodes, f"Missing node: {node}"

    def test_graph_compiles(self):
        """Graph compiles with checkpointer."""
        compiled = compile_graph()
        assert compiled is not None
        assert hasattr(compiled, "invoke")
        assert hasattr(compiled, "get_state")

    def test_build_graph_returns_stategraph(self):
        """build_graph returns a StateGraph instance."""
        graph = build_graph()
        assert hasattr(graph, "nodes")
        assert hasattr(graph, "edges")


class TestRouteEntry:
    """Tests for route_entry routing function."""

    def test_route_entry_initial_state_to_welcome(self):
        """Route entry dispatches to welcome for initial state."""
        state = ConversationState()
        assert route_entry(state) == "welcome"

    def test_route_entry_after_first_attempt_to_discover(self):
        """Route entry dispatches to discover_model after 1 failed attempt."""
        state = ConversationState(router_model_attempts=1)
        assert route_entry(state) == "discover_model"

    def test_route_entry_after_three_attempts_to_unsupported_exit(self):
        """Route entry dispatches to unsupported_model_exit after 3 failed attempts."""
        state = ConversationState(router_model_attempts=3)
        assert route_entry(state) == "unsupported_model_exit"

    def test_route_entry_with_model_to_qualify(self):
        """Route entry dispatches to qualify when model is set."""
        state = ConversationState(router_model="EA6350")
        assert route_entry(state) == "qualify"

    def test_route_entry_after_qualify_decision_true_to_select_method(self):
        """Route entry dispatches to select_reboot_method when reboot appropriate."""
        state = ConversationState(router_model="EA6350", reboot_appropriate=True)
        assert route_entry(state) == "select_reboot_method"

    def test_route_entry_to_retrieval_when_ready(self):
        """Route entry dispatches to retrieval when ready."""
        state = ConversationState(
            router_model="EA6350",
            reboot_appropriate=True,
            reboot_method="physical",
            next_node="not_started",
        )
        assert route_entry(state) == "retrieval"

    def test_route_entry_to_guide_reboot_when_next_node_set(self):
        """Route entry dispatches to guide_reboot when next_node is set."""
        state = ConversationState(
            router_model="EA6350",
            reboot_appropriate=True,
            next_node="guide_reboot",
        )
        assert route_entry(state) == "guide_reboot"


class TestRouteAfterWelcome:
    """Tests for route_after_welcome routing function."""

    def test_route_after_welcome_with_model_to_qualify(self):
        """After welcome, route to qualify if model found."""
        state = ConversationState(router_model="EA6350")
        assert route_after_welcome(state) == "qualify"

    def test_route_after_welcome_three_attempts_to_exit(self):
        """After welcome, route to unsupported_model_exit if 3 attempts."""
        state = ConversationState(router_model_attempts=3)
        assert route_after_welcome(state) == "unsupported_model_exit"

    def test_route_after_welcome_wait_for_input(self):
        """After welcome, return END to wait for user input if no model."""
        state = ConversationState(router_model_attempts=1)
        assert route_after_welcome(state) == END


class TestRouteAfterDiscover:
    """Tests for route_after_discover routing function."""

    def test_route_after_discover_with_model_to_qualify(self):
        """After discover, route to qualify if model found."""
        state = ConversationState(router_model="EA6350")
        assert route_after_discover(state) == "qualify"

    def test_route_after_discover_three_attempts_to_exit(self):
        """After discover, route to unsupported_model_exit if 3 attempts."""
        state = ConversationState(router_model_attempts=3)
        assert route_after_discover(state) == "unsupported_model_exit"

    def test_route_after_discover_wait_for_input(self):
        """After discover, return END to wait for retry if no model."""
        state = ConversationState(router_model_attempts=2)
        assert route_after_discover(state) == END


class TestRouteAfterQualify:
    """Tests for route_after_qualify routing function."""

    def test_route_after_qualify_ask_more_to_end(self):
        """After qualify, return END if reboot_appropriate is None (ask_more)."""
        state = ConversationState(reboot_appropriate=None)
        assert route_after_qualify(state) == END

    def test_route_after_qualify_reboot_true_to_select_method(self):
        """After qualify, route to select_reboot_method if reboot appropriate."""
        state = ConversationState(reboot_appropriate=True)
        assert route_after_qualify(state) == "select_reboot_method"

    def test_route_after_qualify_reboot_false_to_graceful_exit(self):
        """After qualify, route to graceful_exit if reboot not appropriate."""
        state = ConversationState(reboot_appropriate=False)
        assert route_after_qualify(state) == "graceful_exit"


class TestRouteAfterSelectMethod:
    """Tests for route_after_select_method routing function."""

    def test_route_after_select_method_to_retrieval(self):
        """After select_reboot_method, always route to retrieval."""
        state = ConversationState(reboot_method="physical")
        assert route_after_select_method(state) == "retrieval"


class TestRouteAfterGuide:
    """Tests for route_after_guide routing function."""

    def test_route_after_guide_all_done_to_check_resolution(self):
        """After guide_reboot, route to check_resolution if all steps done."""
        state = ConversationState(next_node="check_resolution")
        assert route_after_guide(state) == "check_resolution"

    def test_route_after_guide_wait_for_input(self):
        """After guide_reboot, return END to wait if not all steps done."""
        state = ConversationState(next_node="not_started")
        assert route_after_guide(state) == END


class TestRouteAfterCheck:
    """Tests for route_after_check routing function."""

    def test_route_after_check_vague_answer_to_end(self):
        """After check_resolution, return END if response is vague."""
        state = ConversationState(issue_resolved=None)
        assert route_after_check(state) == END

    def test_route_after_check_resolved_true_to_close_success(self):
        """After check_resolution, route to close_success if resolved."""
        state = ConversationState(issue_resolved=True)
        assert route_after_check(state) == "close_success"

    def test_route_after_check_resolved_false_to_apologize_exit(self):
        """After check_resolution, route to apologize_and_exit if not resolved."""
        state = ConversationState(issue_resolved=False)
        assert route_after_check(state) == "apologize_and_exit"


class TestModelDiscoveryGate:
    """Tests for model discovery 3-retry gate."""

    def test_model_discovery_gate_exits_after_3_attempts(self):
        """Model discovery gate exits after 3 failed attempts."""
        # Simulate 3 failed attempts
        state = ConversationState(router_model_attempts=0)
        assert route_entry(state) == "welcome"

        state.router_model_attempts = 1
        assert route_entry(state) == "discover_model"

        state.router_model_attempts = 2
        assert route_entry(state) == "discover_model"

        state.router_model_attempts = 3
        assert route_entry(state) == "unsupported_model_exit"

    def test_model_discovery_gate_allows_earlier_exit_with_model(self):
        """Model discovery can exit earlier if model is found."""
        state = ConversationState(router_model_attempts=2, router_model="EA6350")
        assert route_entry(state) == "qualify"  # Skips unsupported_model_exit
