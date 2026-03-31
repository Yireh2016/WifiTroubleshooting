"""
Unit tests for agent node functions (agents/v1/nodes.py)

Tests the logic and state mutations of each node in isolation,
using mocked LLM responses to avoid API calls.
"""

import sys
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.state.state_v1 import ConversationState
from agents.v1 import nodes


class TestQualifyNode:
    """Tests for the qualify node — determines if reboot is appropriate."""

    def test_qualify_asks_more_questions(self, patch_llm_module, json_response_factory):
        """Qualify should loop back when decision is 'ask_more'."""
        state = ConversationState(
            messages=[HumanMessage(content="My WiFi is slow")],
            reboot_appropriate=None,
        )

        # Mock LLM to return "ask_more"
        response = Mock()
        response.content = json.dumps(json_response_factory("qualify", decision="ask_more"))
        patch_llm_module.invoke.return_value = response

        result = nodes.qualify(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)
        assert "reboot_appropriate" not in result  # Should NOT be set
        assert "exit_reason" not in result

    def test_qualify_decides_reboot(self, patch_llm_module, json_response_factory):
        """Qualify should set reboot_appropriate=True when decision is 'reboot'."""
        state = ConversationState(
            messages=[
                HumanMessage(content="My WiFi is down"),
                AIMessage(content="Are all devices affected?"),
                HumanMessage(content="Yes, all devices"),
            ],
            reboot_appropriate=None,
        )

        response = Mock()
        response.content = json.dumps(
            json_response_factory("qualify", decision="reboot", reply="Let's reboot the router")
        )
        patch_llm_module.invoke.return_value = response

        result = nodes.qualify(state)

        assert result["reboot_appropriate"] is True
        assert "exit_reason" not in result

    def test_qualify_decides_exit(self, patch_llm_module, json_response_factory):
        """Qualify should set reboot_appropriate=False when decision is 'exit'."""
        state = ConversationState(
            messages=[
                HumanMessage(content="Only my laptop is affected"),
            ],
            reboot_appropriate=None,
        )

        response = Mock()
        response.content = json.dumps(
            json_response_factory(
                "qualify",
                decision="exit",
                exit_reason="single_device",
                reply="That suggests the issue is with the laptop, not the router.",
            )
        )
        patch_llm_module.invoke.return_value = response

        result = nodes.qualify(state)

        assert result["reboot_appropriate"] is False
        assert result["exit_reason"] == "single_device"

    def test_qualify_handles_missing_exit_reason(self, patch_llm_module, json_response_factory):
        """Qualify should use 'unknown' if exit_reason is missing."""
        state = ConversationState(
            messages=[HumanMessage(content="Something's wrong")],
            reboot_appropriate=None,
        )

        response = Mock()
        response.content = json.dumps(
            json_response_factory("qualify", decision="exit")
        )
        patch_llm_module.invoke.return_value = response

        result = nodes.qualify(state)

        assert result["reboot_appropriate"] is False
        assert result["exit_reason"] == "unknown"


class TestRetrievalNode:
    """Tests for the retrieval node — fetches RAG context."""

    def test_retrieval_caches_rag_context(self, patch_llm_module, patch_vectorstore_module, rag_context):
        """Retrieval should cache RAG context in state."""
        state = ConversationState(
            messages=[HumanMessage(content="Reboot the router")],
            reboot_appropriate=True,
            rag_context=None,  # Not yet cached
        )

        result = nodes.retrieval(state)

        assert "rag_context" in result
        assert result["rag_context"] is not None
        assert "Step 1" in result["rag_context"]
        assert result["next_node"] == "guide_reboot"

    def test_retrieval_reuses_cached_context(self, patch_llm_module):
        """Retrieval should skip RAG fetch if context is already cached."""
        cached_context = "Already cached reboot steps"
        state = ConversationState(
            messages=[HumanMessage(content="Next step?")],
            reboot_appropriate=True,
            rag_context=cached_context,
        )

        with patch("agents.v1.nodes._get_vectorstore") as mock_vs:
            result = nodes.retrieval(state)

            # Vectorstore should NOT be called (already cached)
            mock_vs.assert_not_called()
            assert result["rag_context"] == cached_context

    def test_retrieval_handles_empty_results(self, patch_llm_module, patch_vectorstore_module):
        """Retrieval should handle empty RAG results gracefully."""
        # Mock vectorstore to return empty
        with patch("agents.v1.nodes._get_vectorstore") as mock_vs:
            mock_vs.return_value.similarity_search.return_value = []

            state = ConversationState(
                messages=[HumanMessage(content="Reboot")],
                reboot_appropriate=True,
                rag_context=None,
            )

            result = nodes.retrieval(state)

            # Should return fallback message and exit
            assert "messages" in result
            assert "last_executed_node" in result
            assert result["last_executed_node"] == "apologize_and_exit"
            assert "trouble accessing" in result["messages"][0].content.lower()


class TestGuideRebootNode:
    """Tests for guide_reboot node — steps user through reboot."""

    def test_guide_reboot_presents_step(self, patch_llm_module, json_response_factory, rag_context):
        """Guide should present one step and wait for confirmation."""
        state = ConversationState(
            messages=[HumanMessage(content="Okay, let's reboot")],
            rag_context=rag_context,
            next_node="not_started",
        )

        response = Mock()
        response.content = json.dumps(
            json_response_factory(
                "guide_reboot",
                reply="First, disconnect the power cable. What do the lights look like?",
                all_steps_done=False,
            )
        )
        patch_llm_module.invoke.return_value = response

        result = nodes.guide_reboot(state)

        assert "messages" in result
        assert result["last_executed_node"] == "guide_reboot"
        assert "next_node" not in result  # Still guiding, not done

    def test_guide_reboot_marks_complete(self, patch_llm_module, json_response_factory, rag_context):
        """Guide should set next_node='check_resolution' when all steps done."""
        state = ConversationState(
            messages=[
                HumanMessage(content="Done with step 1"),
                HumanMessage(content="Done with step 2"),
                HumanMessage(content="Done with step 3"),
                HumanMessage(content="Done with step 4"),
            ],
            rag_context=rag_context,
            next_node="not_started",
        )

        response = Mock()
        response.content = json.dumps(
            json_response_factory(
                "guide_reboot",
                reply="Great! All steps complete. Let me check if it's working.",
                all_steps_done=True,
            )
        )
        patch_llm_module.invoke.return_value = response

        result = nodes.guide_reboot(state)

        assert result["next_node"] == "check_resolution"
        assert result["last_executed_node"] == "guide_reboot"

    def test_guide_reboot_injects_rag_context(self, patch_llm_module, json_response_factory, rag_context):
        """Guide should inject RAG context into the prompt."""
        state = ConversationState(
            messages=[HumanMessage(content="Start guiding")],
            rag_context=rag_context,
        )

        response = Mock()
        response.content = json.dumps(json_response_factory("guide_reboot"))
        patch_llm_module.invoke.return_value = response

        nodes.guide_reboot(state)

        # Verify the prompt includes RAG context
        call_args = patch_llm_module.invoke.call_args
        prompt = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("prompt")
        assert rag_context in prompt


class TestCheckResolutionNode:
    """Tests for check_resolution node — verifies if issue is fixed."""

    def test_check_asks_if_resolved(self, patch_llm_module, json_response_factory):
        """Check should ask user if issue is resolved."""
        state = ConversationState(
            messages=[HumanMessage(content="Reboot complete")],
            issue_resolved=None,
        )

        response = Mock()
        response.content = json.dumps(
            json_response_factory("check_resolution", reply="Is your internet working now?", resolved=None)
        )
        patch_llm_module.invoke.return_value = response

        result = nodes.check_resolution(state)

        assert "issue_resolved" not in result  # Stays None, waiting for user

    def test_check_records_resolved_true(self, patch_llm_module, json_response_factory):
        """Check should set issue_resolved=True."""
        state = ConversationState(
            messages=[HumanMessage(content="Yes, it works now!")],
            issue_resolved=None,
        )

        response = Mock()
        response.content = json.dumps(
            json_response_factory("check_resolution", reply="Excellent!", resolved=True)
        )
        patch_llm_module.invoke.return_value = response

        result = nodes.check_resolution(state)

        assert result["issue_resolved"] is True

    def test_check_records_resolved_false(self, patch_llm_module, json_response_factory):
        """Check should set issue_resolved=False."""
        state = ConversationState(
            messages=[HumanMessage(content="Still not working")],
            issue_resolved=None,
        )

        response = Mock()
        response.content = json.dumps(
            json_response_factory("check_resolution", reply="I'm sorry to hear that.", resolved=False)
        )
        patch_llm_module.invoke.return_value = response

        result = nodes.check_resolution(state)

        assert result["issue_resolved"] is False


class TestTerminalNodes:
    """Tests for terminal nodes — exit scenarios."""

    def test_graceful_exit_injects_reason(self, patch_llm_module, json_response_factory):
        """Graceful exit should inject the exit reason into prompt."""
        state = ConversationState(
            messages=[HumanMessage(content="Only my laptop affected")],
            reboot_appropriate=False,
            exit_reason="single_device",
        )

        response = Mock()
        response.content = json.dumps(
            json_response_factory("graceful_exit", reply="That's just the laptop, not a router issue.")
        )
        patch_llm_module.invoke.return_value = response

        result = nodes.graceful_exit(state)

        assert result["last_executed_node"] == "graceful_exit"
        assert "messages" in result

    def test_close_success(self, patch_llm_module, json_response_factory):
        """Close success should provide warm closing message."""
        state = ConversationState(
            messages=[HumanMessage(content="It works now, thanks!")],
            issue_resolved=True,
        )

        response = Mock()
        response.content = json.dumps(
            json_response_factory("close_success", reply="Glad I could help!")
        )
        patch_llm_module.invoke.return_value = response

        result = nodes.close_success(state)

        assert result["last_executed_node"] == "close_success"
        assert isinstance(result["messages"][0], AIMessage)

    def test_apologize_and_exit(self, patch_llm_module, json_response_factory):
        """Apologize exit should suggest contacting support."""
        state = ConversationState(
            messages=[HumanMessage(content="Still broken after reboot")],
            issue_resolved=False,
        )

        response = Mock()
        response.content = json.dumps(
            json_response_factory("apologize_and_exit", reply="Please contact support.")
        )
        patch_llm_module.invoke.return_value = response

        result = nodes.apologize_and_exit(state)

        assert result["last_executed_node"] == "apologize_and_exit"


class TestRouting:
    """Tests for routing functions — state-based decision logic."""

    def test_route_entry_to_qualify(self, sample_state):
        """Entry should route to qualify when undecided."""
        sample_state.reboot_appropriate = None
        result = nodes.route_entry(sample_state)
        assert result == "qualify"

    def test_route_entry_to_retrieval(self, sample_state):
        """Entry should route to retrieval when ready for reboot."""
        sample_state.reboot_appropriate = True
        sample_state.next_node = "not_started"
        result = nodes.route_entry(sample_state)
        assert result == "retrieval"

    def test_route_entry_to_guide_reboot(self, sample_state):
        """Entry should route to guide_reboot when in progress."""
        sample_state.reboot_appropriate = True
        sample_state.next_node = "guide_reboot"
        result = nodes.route_entry(sample_state)
        assert result == "guide_reboot"

    def test_route_entry_to_check_resolution(self, sample_state):
        """Entry should route to check_resolution when done guiding."""
        sample_state.reboot_appropriate = True
        sample_state.next_node = "check_resolution"
        sample_state.issue_resolved = None
        result = nodes.route_entry(sample_state)
        assert result == "check_resolution"

    def test_route_after_qualify_undecided(self, sample_state):
        """After qualify, should END if still undecided."""
        sample_state.reboot_appropriate = None
        result = nodes.route_after_qualify(sample_state)
        assert result == "__end__"

    def test_route_after_qualify_to_retrieval(self, sample_state):
        """After qualify, should route to retrieval if reboot needed."""
        sample_state.reboot_appropriate = True
        result = nodes.route_after_qualify(sample_state)
        assert result == "retrieval"

    def test_route_after_qualify_to_exit(self, sample_state):
        """After qualify, should route to exit if reboot not needed."""
        sample_state.reboot_appropriate = False
        result = nodes.route_after_qualify(sample_state)
        assert result == "graceful_exit"

    def test_route_after_guide_still_guiding(self, sample_state):
        """After guide, should END if still presenting steps."""
        sample_state.next_node = "guide_reboot"
        result = nodes.route_after_guide(sample_state)
        assert result == "__end__"

    def test_route_after_guide_done(self, sample_state):
        """After guide, should route to check_resolution when done."""
        sample_state.next_node = "check_resolution"
        result = nodes.route_after_guide(sample_state)
        assert result == "check_resolution"

    def test_route_after_check_unresolved(self, sample_state):
        """After check, should END if waiting for user answer."""
        sample_state.issue_resolved = None
        result = nodes.route_after_check(sample_state)
        assert result == "__end__"

    def test_route_after_check_resolved(self, sample_state):
        """After check, should route to success if resolved."""
        sample_state.issue_resolved = True
        result = nodes.route_after_check(sample_state)
        assert result == "close_success"

    def test_route_after_check_not_resolved(self, sample_state):
        """After check, should route to apologize if not resolved."""
        sample_state.issue_resolved = False
        result = nodes.route_after_check(sample_state)
        assert result == "apologize_and_exit"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
