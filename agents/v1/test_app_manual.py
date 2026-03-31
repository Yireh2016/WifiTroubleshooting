"""
Manual verification test suite for Phase 5: Streamlit UI

This script tests the 8 scenarios from Phase 6 Definition of Done.
These tests verify graph behavior and message routing, simulating what
would be tested interactively through the Streamlit UI.

To run these tests:
  python3 agents/v1/test_app_manual.py

To run the interactive app and manually test scenarios:
  export STREAMLIT_SERVER_HEADLESS=true
  streamlit run agents/v1/app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage
from agents.v1.graph import compile_graph
import uuid

def run_scenario(scenario_name, user_messages, expected_terminal_node=None):
    """
    Run a conversation scenario and verify outcomes.

    Args:
        scenario_name: Name of the scenario
        user_messages: List of messages to send
        expected_terminal_node: Which terminal node should end the conversation
    """
    print(f"\n{'='*60}")
    print(f"Scenario: {scenario_name}")
    print(f"{'='*60}")

    graph = compile_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = None
        for i, message in enumerate(user_messages):
            print(f"\n[Turn {i+1}] User: {message[:80]}...")

            result = graph.invoke(
                {"messages": [HumanMessage(content=message)]},
                config=config,
            )

            state = result

            # Extract response
            if result and isinstance(result, dict) and "messages" in result:
                messages = result["messages"]
                ai_messages = [m for m in messages if hasattr(m, 'type') and m.type == "ai"]
                if ai_messages:
                    response = ai_messages[-1].content
                    print(f"[Bot]: {response[:120]}...")

        # Check final node
        if expected_terminal_node:
            last_executed_node = state.get("last_executed_node", "")
            if last_executed_node == expected_terminal_node:
                print(f"\n✓ PASS: Ended at {expected_terminal_node}")
                return True
            else:
                print(f"\n✗ FAIL: Expected {expected_terminal_node}, got {last_executed_node}")
                return False
        else:
            print(f"\n✓ PASS: Conversation completed (final node: {state.get('last_executed_node', 'unknown')})")
            return True

    except Exception as e:
        print(f"\n✗ FAIL: Exception occurred: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("Phase 5 Manual Verification Tests")
    print("Testing all 8 scenarios from Definition of Done\n")

    results = {}

    # Scenario 1: Single device affected
    results["S1"] = run_scenario(
        "Single device affected (graceful exit)",
        [
            "My WiFi is having problems. My laptop can't connect but my phone works fine.",
            "Yes, the phone connects to WiFi no problem. It's just the laptop."
        ],
        expected_terminal_node="graceful_exit"
    )

    # Scenario 2: ISP outage
    results["S2"] = run_scenario(
        "ISP outage (graceful exit)",
        [
            "My internet is down. It's affecting everything.",
            "Yes, all devices are offline. Actually, my neighbor just told me their internet is also down."
        ],
        expected_terminal_node="graceful_exit"
    )

    # Scenario 3: Already rebooted twice
    results["S3"] = run_scenario(
        "Already rebooted twice (graceful exit)",
        [
            "My WiFi keeps disconnecting. All my devices are losing connection.",
            "I've already rebooted the router twice and it's still not working."
        ],
        expected_terminal_node="graceful_exit"
    )

    # Scenario 4: Loose cable found and fixed
    results["S4"] = run_scenario(
        "Loose cable found and fixed (close success)",
        [
            "My WiFi is down. All devices are offline.",
            "I've checked the cables and found one was loose. I plugged it back in and now it works!"
        ],
        expected_terminal_node="close_success"
    )

    # Scenario 5: Full reboot flow → resolved
    results["S5"] = run_scenario(
        "Full reboot flow → resolved",
        [
            "My WiFi is down. All my devices can't connect.",
            "Yes, I have access to the router and modem.",
            "Done",
            "Yes, it's working now. Internet is restored."
        ],
        expected_terminal_node="close_success"
    )

    # Scenario 6: Full reboot flow → not resolved
    results["S6"] = run_scenario(
        "Full reboot flow → not resolved",
        [
            "My WiFi is down. All my devices can't connect.",
            "Yes, I have access.",
            "Done",
            "No, it's still not working."
        ],
        expected_terminal_node="apologize_and_exit"
    )

    # Scenario 7: Empty input / off-topic (should not crash, stay in qualify)
    results["S7"] = run_scenario(
        "Empty input and off-topic handling",
        [
            "How are you?",
            "What's the weather like?",
            "My WiFi is down."
        ]
    )

    # Scenario 8: Power outage fast-track
    results["S8"] = run_scenario(
        "Power outage recently reported",
        [
            "There was a power outage in my area. Internet is down.",
            "Yes, everything is offline."
        ]
    )

    # Summary
    print(f"\n\n{'='*60}")
    print("Test Summary")
    print(f"{'='*60}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for scenario, passed_flag in results.items():
        status = "✓ PASS" if passed_flag else "✗ FAIL"
        print(f"{scenario}: {status}")

    print(f"\nTotal: {passed}/{total} passed")

    if passed == total:
        print("\n✓ All scenarios passed!")
    else:
        print(f"\n✗ {total - passed} scenario(s) failed")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
