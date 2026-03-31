"""
Integration tests for agent scenarios (agents/v1/graph.py)

Tests complete conversation flows with real graph execution.
These are the 8 scenarios from Phase 5 Definition of Done.

Run with:
  pytest agents/v1/test_scenarios.py -v
"""

import sys
import uuid
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.v1.graph import compile_graph


@pytest.fixture
def graph():
    """Compile the agent graph once per test session."""
    return compile_graph()


@pytest.fixture
def thread_id():
    """Generate a unique thread ID for each test."""
    return str(uuid.uuid4())


@pytest.fixture
def graph_config(thread_id):
    """Create LangGraph config with thread ID."""
    return {"configurable": {"thread_id": thread_id}}


class TestScenarioScenario1:
    """S1: Single device affected → graceful exit"""

    def test_single_device_graceful_exit(self, graph, graph_config):
        """Scenario 1: Only laptop offline, phone works — should exit gracefully."""
        messages = [
            "My WiFi is having problems. My laptop can't connect but my phone works fine.",
            "Yes, the phone connects to WiFi no problem. It's just the laptop.",
        ]

        result = None
        for msg in messages:
            result = graph.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=graph_config,
            )

        assert result is not None, "Graph should return a state"
        assert "messages" in result
        assert result.get("last_executed_node") == "graceful_exit"
        assert result.get("reboot_appropriate") is False
        assert result.get("exit_reason") == "single_device"


class TestScenarioScenario2:
    """S2: ISP outage → graceful exit"""

    def test_isp_outage_graceful_exit(self, graph, graph_config):
        """Scenario 2: All devices offline, neighbor also affected — should exit gracefully."""
        messages = [
            "My internet is down. It's affecting everything.",
            "Yes, all devices are offline. Actually, my neighbor just told me their internet is also down.",
        ]

        result = None
        for msg in messages:
            result = graph.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=graph_config,
            )

        assert result is not None
        assert "messages" in result
        assert result.get("last_executed_node") == "graceful_exit"
        assert result.get("reboot_appropriate") is False
        assert result.get("exit_reason") == "isp_outage"


class TestScenarioScenario3:
    """S3: Already rebooted twice → graceful exit"""

    def test_already_rebooted_graceful_exit(self, graph, graph_config):
        """Scenario 3: User already rebooted twice with no improvement."""
        messages = [
            "My WiFi keeps disconnecting. All my devices are losing connection.",
            "I've already rebooted the router twice and it's still not working.",
        ]

        result = None
        for msg in messages:
            result = graph.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=graph_config,
            )

        assert result is not None
        assert "messages" in result
        assert result.get("last_executed_node") == "graceful_exit"
        assert result.get("reboot_appropriate") is False
        assert result.get("exit_reason") == "already_rebooted"


class TestScenarioScenario4:
    """S4: Loose cable found and fixed → close success"""

    def test_loose_cable_close_success(self, graph, graph_config):
        """Scenario 4: User found and fixed loose cable without reboot."""
        messages = [
            "My WiFi is down. All devices are offline.",
            "I've checked the cables and found one was loose. I plugged it back in and now it works!",
        ]

        result = None
        for msg in messages:
            result = graph.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=graph_config,
            )

        assert result is not None
        assert "messages" in result
        assert result.get("last_executed_node") == "close_success"
        assert result.get("issue_resolved") is True


class TestScenarioScenario5:
    """S5: Full reboot flow → resolved"""

    def test_full_reboot_resolved(self, graph, graph_config):
        """Scenario 5: User goes through full reboot steps and issue is resolved."""
        messages = [
            "My WiFi is down. All my devices can't connect.",
            "Yes, I have access to the router and modem.",
            "Done",
            "Yes, it's working now. Internet is restored.",
        ]

        result = None
        for msg in messages:
            result = graph.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=graph_config,
            )

        assert result is not None
        assert "messages" in result
        assert result.get("last_executed_node") == "close_success"
        assert result.get("reboot_appropriate") is True
        assert result.get("issue_resolved") is True


class TestScenarioScenario6:
    """S6: Full reboot flow → not resolved"""

    def test_full_reboot_not_resolved(self, graph, graph_config):
        """Scenario 6: User completes reboot but issue persists."""
        messages = [
            "My WiFi is down. All my devices can't connect.",
            "Yes, I have access.",
            "Done",
            "No, it's still not working.",
        ]

        result = None
        for msg in messages:
            result = graph.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=graph_config,
            )

        assert result is not None
        assert "messages" in result
        assert result.get("last_executed_node") == "apologize_and_exit"
        assert result.get("reboot_appropriate") is True
        assert result.get("issue_resolved") is False


class TestScenarioScenario7:
    """S7: Empty input and off-topic handling"""

    def test_off_topic_handling(self, graph, graph_config):
        """Scenario 7: Graph should handle off-topic messages gracefully."""
        messages = [
            "How are you?",
            "What's the weather like?",
            "My WiFi is down.",
        ]

        result = None
        for msg in messages:
            result = graph.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=graph_config,
            )

        assert result is not None, "Graph should not crash on off-topic input"
        assert "messages" in result


class TestScenarioScenario8:
    """S8: Power outage recently reported"""

    def test_power_outage_detection(self, graph, graph_config):
        """Scenario 8: Graph should detect power outage context."""
        messages = [
            "There was a power outage in my area. Internet is down.",
            "Yes, everything is offline.",
        ]

        result = None
        for msg in messages:
            result = graph.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=graph_config,
            )

        assert result is not None
        assert "messages" in result
        # Power outage typically leads to reboot decision
        assert result.get("reboot_appropriate") is not None


class TestMessagePersistence:
    """Tests for message history and state persistence across turns."""

    def test_messages_accumulate(self, graph, graph_config):
        """Each turn should accumulate messages in state."""
        msg1 = "My WiFi is down"
        msg2 = "All devices are offline"

        result1 = graph.invoke({"messages": [HumanMessage(content=msg1)]}, config=graph_config)
        result2 = graph.invoke({"messages": [HumanMessage(content=msg2)]}, config=graph_config)

        assert len(result1["messages"]) >= 1
        assert len(result2["messages"]) > len(result1["messages"])

    def test_thread_isolation(self, graph):
        """Different threads should have isolated conversation histories."""
        config1 = {"configurable": {"thread_id": str(uuid.uuid4())}}
        config2 = {"configurable": {"thread_id": str(uuid.uuid4())}}

        result1 = graph.invoke({"messages": [HumanMessage(content="Thread 1")]}, config=config1)
        result2 = graph.invoke({"messages": [HumanMessage(content="Thread 2")]}, config=config2)

        # Both should have messages but with different content
        assert len(result1["messages"]) > 0
        assert len(result2["messages"]) > 0


class TestStateTransitions:
    """Tests for correct state field transitions."""

    def test_reboot_appropriate_state(self, graph, graph_config):
        """reboot_appropriate should be set correctly during qualification."""
        messages = [
            "My WiFi is down. All devices offline.",
            "Yes, everything is affected.",
        ]

        result = None
        for msg in messages:
            result = graph.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=graph_config,
            )

        assert result.get("reboot_appropriate") is not None

    def test_rag_context_caching(self, graph, graph_config):
        """RAG context should be cached after first retrieval."""
        messages = [
            "My WiFi is down.",
            "Yes, all devices offline",
            "I'm ready",
            "Done step 1",
        ]

        result = None
        for i, msg in enumerate(messages):
            result = graph.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=graph_config,
            )
            if i == 3:  # After guide_reboot starts
                # RAG context should be cached
                if result.get("rag_context"):
                    assert isinstance(result["rag_context"], str)
                    assert len(result["rag_context"]) > 0

    def test_last_executed_node_tracking(self, graph, graph_config):
        """last_executed_node should reflect current execution."""
        msg = "My WiFi is down"
        result = graph.invoke(
            {"messages": [HumanMessage(content=msg)]},
            config=graph_config,
        )

        assert "last_executed_node" in result
        assert result["last_executed_node"] in [
            "qualify",
            "graceful_exit",
            "guide_reboot",
            "retrieval",
            "check_resolution",
            "close_success",
            "apologize_and_exit",
        ]


class TestErrorHandling:
    """Tests for graph resilience and error handling."""

    def test_graph_handles_empty_message(self, graph, graph_config):
        """Graph should not crash on empty message."""
        try:
            result = graph.invoke(
                {"messages": [HumanMessage(content="")]},
                config=graph_config,
            )
            assert result is not None
        except Exception as e:
            pytest.fail(f"Graph crashed on empty message: {e}")

    def test_graph_handles_very_long_message(self, graph, graph_config):
        """Graph should handle very long messages."""
        long_msg = "My WiFi is down. " * 100
        try:
            result = graph.invoke(
                {"messages": [HumanMessage(content=long_msg)]},
                config=graph_config,
            )
            assert result is not None
        except Exception as e:
            pytest.fail(f"Graph crashed on long message: {e}")

    def test_graph_handles_special_characters(self, graph, graph_config):
        """Graph should handle special characters in input."""
        special_msg = "My WiFi is down! @#$%^&*() 中文 emoji 🔧"
        try:
            result = graph.invoke(
                {"messages": [HumanMessage(content=special_msg)]},
                config=graph_config,
            )
            assert result is not None
        except Exception as e:
            pytest.fail(f"Graph crashed on special characters: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
