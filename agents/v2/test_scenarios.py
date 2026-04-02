import sys
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.v2.graph import compile_graph
from shared.state.state_v2 import ConversationState
from langchain_core.messages import HumanMessage


class TestHappyPathScenarios:
    """Tests for happy path end-to-end scenarios."""

    def test_happy_path_self_serve(self, patch_v2_llm, patch_v2_vectorstore, json_response_factory):
        """Full flow in self_serve mode: model -> qualify -> method -> reboot -> resolved."""
        compiled = compile_graph()
        config = {"configurable": {"thread_id": "test-1"}}

        # Mock responses for each step
        responses = [
            json.dumps(json_response_factory("welcome_with_model", extracted_model="EA6350")),
            json.dumps(json_response_factory("qualify_reboot")),
            json.dumps(json_response_factory("select_method", selected_method="physical")),
            json.dumps(json_response_factory("guide_reboot_done", all_steps_done=True)),
            json.dumps(json_response_factory("check_resolution_yes", resolved=True)),
            json.dumps(json_response_factory("close_success")),
        ]
        patch_v2_llm.invoke.side_effect = [Mock(content=r) for r in responses]

        # Invoke with mode
        state = compiled.invoke(
            {
                "messages": [],
                "conversation_mode": "self_serve",
            },
            config=config,
        )

        # Verify final state
        assert state["issue_resolved"] is True
        assert state["last_executed_node"] == "close_success"

    def test_happy_path_agent_assisted(self, patch_v2_llm, patch_v2_vectorstore, json_response_factory):
        """Full flow in agent_assisted mode."""
        compiled = compile_graph()
        config = {"configurable": {"thread_id": "test-2"}}

        responses = [
            json.dumps(json_response_factory("welcome_with_model", extracted_model="EA6350")),
            json.dumps(json_response_factory("qualify_reboot")),
            json.dumps(json_response_factory("select_method", selected_method="physical")),
            json.dumps(json_response_factory("guide_reboot_done", all_steps_done=True)),
            json.dumps(json_response_factory("check_resolution_yes", resolved=True)),
            json.dumps(json_response_factory("close_success")),
        ]
        patch_v2_llm.invoke.side_effect = [Mock(content=r) for r in responses]

        state = compiled.invoke(
            {
                "messages": [],
                "conversation_mode": "agent_assisted",
            },
            config=config,
        )

        assert state["issue_resolved"] is True
        assert state["conversation_mode"] == "agent_assisted"


class TestModelDiscoveryFailures:
    """Tests for model discovery failure scenarios."""

    def test_unknown_model_exits_after_3_retries(self, patch_v2_llm, patch_v2_vectorstore, json_response_factory):
        """User can't provide model -> exits after 3 retries."""
        compiled = compile_graph()
        config = {"configurable": {"thread_id": "test-3"}}

        # All attempts fail to find model
        responses = [
            json.dumps(json_response_factory("welcome")),  # No model
            json.dumps(json_response_factory("discover_model")),  # Still no model
            json.dumps(json_response_factory("discover_model")),  # Still no model
            json.dumps(json_response_factory("graceful_exit")),
        ]
        patch_v2_llm.invoke.side_effect = [Mock(content=r) for r in responses]

        state = compiled.invoke(
            {
                "messages": [HumanMessage(content="I don't know my model")],
                "conversation_mode": "self_serve",
            },
            config=config,
        )

        assert state["exit_reason"] == "unsupported_model"
        assert state["last_executed_node"] == "unsupported_model_exit"


class TestQualifyExitScenarios:
    """Tests for scenarios where qualify determines reboot isn't needed."""

    def test_qualify_exits_gracefully_single_device(self, patch_v2_llm, patch_v2_vectorstore, json_response_factory):
        """Single-device issue -> graceful exit."""
        compiled = compile_graph()
        config = {"configurable": {"thread_id": "test-4"}}

        responses = [
            json.dumps(json_response_factory("welcome_with_model", extracted_model="EA6350")),
            json.dumps(
                json_response_factory("qualify_exit", exit_reason="single_device")
            ),  # Not appropriate for reboot
            json.dumps(json_response_factory("graceful_exit")),
        ]
        patch_v2_llm.invoke.side_effect = [Mock(content=r) for r in responses]

        state = compiled.invoke(
            {
                "messages": [HumanMessage(content="My router is fine but one device can't connect")],
                "conversation_mode": "self_serve",
            },
            config=config,
        )

        assert state["reboot_appropriate"] is False
        assert state["exit_reason"] == "single_device"
        assert state["last_executed_node"] == "graceful_exit"

    def test_qualify_exits_isp_outage(self, patch_v2_llm, patch_v2_vectorstore, json_response_factory):
        """ISP outage detected -> graceful exit."""
        compiled = compile_graph()
        config = {"configurable": {"thread_id": "test-5"}}

        responses = [
            json.dumps(json_response_factory("welcome_with_model", extracted_model="EA6350")),
            json.dumps(json_response_factory("qualify_exit", exit_reason="isp_outage")),
            json.dumps(json_response_factory("graceful_exit")),
        ]
        patch_v2_llm.invoke.side_effect = [Mock(content=r) for r in responses]

        state = compiled.invoke(
            {
                "messages": [HumanMessage(content="No internet at all")],
                "conversation_mode": "self_serve",
            },
            config=config,
        )

        assert state["exit_reason"] == "isp_outage"


class TestRebootNotResolved:
    """Tests for scenarios where reboot doesn't fix the issue."""

    def test_reboot_not_resolved_apologize_and_exit(self, patch_v2_llm, patch_v2_vectorstore, json_response_factory):
        """Reboot doesn't fix -> apologize and exit."""
        compiled = compile_graph()
        config = {"configurable": {"thread_id": "test-6"}}

        responses = [
            json.dumps(json_response_factory("welcome_with_model", extracted_model="EA6350")),
            json.dumps(json_response_factory("qualify_reboot")),
            json.dumps(json_response_factory("select_method", selected_method="physical")),
            json.dumps(json_response_factory("guide_reboot_done", all_steps_done=True)),
            json.dumps(json_response_factory("check_resolution_no", resolved=False)),
            json.dumps(json_response_factory("apologize_and_exit")),
        ]
        patch_v2_llm.invoke.side_effect = [Mock(content=r) for r in responses]

        state = compiled.invoke(
            {
                "messages": [HumanMessage(content="Still not working after reboot")],
                "conversation_mode": "self_serve",
            },
            config=config,
        )

        assert state["issue_resolved"] is False
        assert state["last_executed_node"] == "apologize_and_exit"


class TestModeDifferences:
    """Tests to verify mode affects prompt behavior."""

    def test_self_serve_mode_persists(self, patch_v2_llm, patch_v2_vectorstore, json_response_factory):
        """Conversation mode (self_serve) persists throughout graph."""
        compiled = compile_graph()
        config = {"configurable": {"thread_id": "test-7"}}

        responses = [
            json.dumps(json_response_factory("welcome_with_model", extracted_model="EA6350")),
        ]
        patch_v2_llm.invoke.side_effect = [Mock(content=r) for r in responses]

        state = compiled.invoke(
            {
                "messages": [],
                "conversation_mode": "self_serve",
            },
            config=config,
        )

        assert state["conversation_mode"] == "self_serve"

    def test_agent_assisted_mode_persists(self, patch_v2_llm, patch_v2_vectorstore, json_response_factory):
        """Conversation mode (agent_assisted) persists throughout graph."""
        compiled = compile_graph()
        config = {"configurable": {"thread_id": "test-8"}}

        responses = [
            json.dumps(json_response_factory("welcome_with_model", extracted_model="EA6350")),
        ]
        patch_v2_llm.invoke.side_effect = [Mock(content=r) for r in responses]

        state = compiled.invoke(
            {
                "messages": [],
                "conversation_mode": "agent_assisted",
            },
            config=config,
        )

        assert state["conversation_mode"] == "agent_assisted"


class TestManualContextCaching:
    """Tests for manual context retrieval and caching."""

    def test_manual_context_cached_in_qualify(self, patch_v2_llm, patch_v2_vectorstore, json_response_factory):
        """Manual context is retrieved and cached in qualify node."""
        compiled = compile_graph()
        config = {"configurable": {"thread_id": "test-9"}}

        responses = [
            json.dumps(json_response_factory("welcome_with_model", extracted_model="EA6350")),
            json.dumps(json_response_factory("qualify_reboot")),
        ]
        patch_v2_llm.invoke.side_effect = [Mock(content=r) for r in responses]

        state = compiled.invoke(
            {
                "messages": [],
                "conversation_mode": "self_serve",
            },
            config=config,
        )

        # Manual context should be retrieved and cached
        assert state["manual_context"] is not None
        assert len(state["manual_context"]) > 0
