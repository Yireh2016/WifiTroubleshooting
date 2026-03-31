#!/usr/bin/env python3
"""
Standalone test script for Phase 4: Agent Logic (LangGraph)

Tests:
1. Graph builds without errors
2. Graph compiles without errors
3. Graph has 7 nodes and correct structure
4. Node imports resolve
5. Routing logic validates state transitions
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.v1.graph import build_graph, compile_graph
from agents.v1.nodes import (
    qualify, graceful_exit, guide_reboot,
    check_resolution, close_success, apologize_and_exit,
    route_entry, route_after_qualify, route_after_guide, route_after_check,
)
from shared.state.state_v1 import ConversationState
from langchain_core.messages import HumanMessage, AIMessage

def test_graph_builds():
    """Test 1: Graph builds without errors."""
    try:
        graph = build_graph()
        print("✓ Test 1 PASSED: Graph builds successfully")
        return True
    except Exception as e:
        print(f"✗ Test 1 FAILED: Graph build error: {e}")
        return False

def test_graph_compiles():
    """Test 2: Graph compiles without errors."""
    try:
        app = compile_graph()
        print("✓ Test 2 PASSED: Graph compiles successfully")
        return True
    except Exception as e:
        print(f"✗ Test 2 FAILED: Graph compile error: {e}")
        return False

def test_graph_structure():
    """Test 3: Graph has 8 nodes and correct edge structure."""
    try:
        graph = build_graph()
        nodes = list(graph.nodes.keys())
        expected_nodes = {
            "router", "qualify", "graceful_exit", "guide_reboot", "retrieval", "check_resolution",
            "close_success", "apologize_and_exit"
        }

        if set(nodes) == expected_nodes and len(nodes) == 8:
            print(f"✓ Test 3 PASSED: Graph has 8 nodes: {sorted(nodes)}")
            return True
        else:
            print(f"✗ Test 3 FAILED: Expected 8 nodes {expected_nodes}, got {set(nodes)}")
            return False
    except Exception as e:
        print(f"✗ Test 3 FAILED: Structure check error: {e}")
        return False

def test_node_imports():
    """Test 4: All node imports resolve without errors."""
    try:
        # All imports should have succeeded if we got here
        functions = [
            qualify, graceful_exit, guide_reboot,
            check_resolution, close_success, apologize_and_exit,
            route_entry, route_after_qualify, route_after_guide, route_after_check,
        ]
        print(f"✓ Test 4 PASSED: All {len(functions)} node and routing functions imported")
        return True
    except Exception as e:
        print(f"✗ Test 4 FAILED: Import error: {e}")
        return False

def test_routing_logic():
    """Test 5: Routing logic validates state transitions."""
    try:
        # Test route_entry
        state_entry1 = ConversationState(
            messages=[HumanMessage(content="test")],
            reboot_appropriate=None
        )
        assert route_entry(state_entry1) == "qualify", "Entry should route to qualify when undecided"

        state_entry2 = ConversationState(
            messages=[HumanMessage(content="test")],
            reboot_appropriate=True, next_node="guide_reboot"
        )
        assert route_entry(state_entry2) == "guide_reboot", "Entry should route to guide_reboot when in progress"

        state_entry3 = ConversationState(
            messages=[HumanMessage(content="test")],
            reboot_appropriate=True, next_node="check_resolution", issue_resolved=None
        )
        assert route_entry(state_entry3) == "check_resolution", "Entry should route to check_resolution when done with reboot"

        # Test route_after_qualify
        state1 = ConversationState(
            messages=[HumanMessage(content="test")],
            reboot_appropriate=None
        )
        assert route_after_qualify(state1) == "__end__", "Should end (wait for user) on None"

        state2 = ConversationState(
            messages=[HumanMessage(content="test")],
            reboot_appropriate=True
        )
        assert route_after_qualify(state2) == "retrieval", "Should go to retrieval on True"

        state3 = ConversationState(
            messages=[HumanMessage(content="test")],
            reboot_appropriate=False,
            exit_reason="single_device"
        )
        assert route_after_qualify(state3) == "graceful_exit", "Should go to exit on False"

        # Test route_after_guide
        state4 = ConversationState(
            messages=[AIMessage(content="step 1")],
            next_node="guide_reboot"
        )
        assert route_after_guide(state4) == "__end__", "Should end (wait for user) while still guiding"

        state5 = ConversationState(
            messages=[AIMessage(content="all steps done")],
            next_node="check_resolution"
        )
        assert route_after_guide(state5) == "check_resolution", "Should move to check when all steps done"

        # Test route_after_check
        state6 = ConversationState(
            messages=[AIMessage(content="test")],
            issue_resolved=None
        )
        assert route_after_check(state6) == "__end__", "Should end (wait for user) on None"

        state7 = ConversationState(
            messages=[AIMessage(content="test")],
            issue_resolved=True
        )
        assert route_after_check(state7) == "close_success", "Should go to success on True"

        state8 = ConversationState(
            messages=[AIMessage(content="test")],
            issue_resolved=False
        )
        assert route_after_check(state8) == "apologize_and_exit", "Should go to exit on False"

        print("✓ Test 5 PASSED: All routing logic transitions validated")
        return True
    except AssertionError as e:
        print(f"✗ Test 5 FAILED: Routing assertion failed: {e}")
        return False
    except Exception as e:
        print(f"✗ Test 5 FAILED: Routing test error: {e}")
        return False

def main():
    print("=" * 70)
    print("Phase 4: Agent Logic (LangGraph) — Test Suite")
    print("=" * 70)
    print()

    results = [
        test_graph_builds(),
        test_graph_compiles(),
        test_graph_structure(),
        test_node_imports(),
        test_routing_logic(),
    ]

    print()
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 70)

    if passed == total:
        print("✓ All automated tests PASSED")
        return 0
    else:
        print(f"✗ {total - passed} test(s) FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
