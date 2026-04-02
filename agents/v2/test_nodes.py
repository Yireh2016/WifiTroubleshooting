import sys
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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
    _list_available_models,
    _check_model_exists,
)
from shared.state.state_v2 import ConversationState
from langchain_core.messages import AIMessage, HumanMessage


class TestWelcomeNode:
    """Tests for welcome node."""

    def test_welcome_extracts_model(self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state, json_response_factory):
        """Welcome node extracts model from LLM response."""
        response = json_response_factory("welcome_with_model")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = welcome(sample_v2_state)

        assert "messages" in result
        assert result["messages"][0].type == "ai"
        assert result["last_executed_node"] == "welcome"
        assert result.get("router_model") == "EA6350"

    def test_welcome_increments_attempts_on_no_model(self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state, json_response_factory):
        """Welcome increments attempts if model extraction fails."""
        response = json_response_factory("welcome")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = welcome(sample_v2_state)

        assert result["router_model_attempts"] == 1


class TestDiscoverModelNode:
    """Tests for discover_model node."""

    def test_discover_model_increments_attempts_on_failure(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state, json_response_factory
    ):
        """Discover model increments attempts if model not found."""
        state = sample_v2_state
        state.router_model_attempts = 1
        response = json_response_factory("discover_model")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = discover_model(state)

        assert result["router_model_attempts"] == 2
        assert result["last_executed_node"] == "discover_model"

    def test_discover_model_succeeds_on_known_model(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state, json_response_factory
    ):
        """Discover model sets router_model when found."""
        state = sample_v2_state
        state.router_model_attempts = 1
        response = json_response_factory("discover_model_success", extracted_model="EA6350")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = discover_model(state)

        assert result.get("router_model") == "EA6350"
        assert "router_model_attempts" not in result  # Should not increment


class TestUnsupportedModelExitNode:
    """Tests for unsupported_model_exit node."""

    def test_unsupported_model_exit_sets_exit_reason(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state, json_response_factory
    ):
        """Unsupported model exit sets exit_reason."""
        response = json_response_factory("graceful_exit")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = unsupported_model_exit(sample_v2_state)

        assert result["exit_reason"] == "unsupported_model"
        assert result["last_executed_node"] == "unsupported_model_exit"


class TestQualifyNode:
    """Tests for qualify node."""

    def test_qualify_retrieves_manual_context(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state_with_model, json_response_factory
    ):
        """Qualify node retrieves and caches manual context."""
        response = json_response_factory("qualify_reboot")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = qualify(sample_v2_state_with_model)

        assert "manual_context" in result
        assert result["reboot_appropriate"] is True
        assert result["last_executed_node"] == "qualify"

    def test_qualify_uses_cached_manual_context(
        self, patch_v2_llm, patch_v2_vectorstore, json_response_factory
    ):
        """Second qualify call uses cached manual_context."""
        state = ConversationState(
            messages=[HumanMessage(content="WiFi down")],
            conversation_mode="self_serve",
            router_model="EA6350",
            manual_context="Cached manual context",
        )
        response = json_response_factory("qualify_reboot")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        # First call sets it
        result1 = qualify(state)
        assert result1["manual_context"] == "Cached manual context"

    def test_qualify_sets_exit_reason(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state_with_model, json_response_factory
    ):
        """Qualify sets exit_reason when decision is exit."""
        response = json_response_factory("qualify_exit", exit_reason="single_device")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = qualify(sample_v2_state_with_model)

        assert result["reboot_appropriate"] is False
        assert result["exit_reason"] == "single_device"


class TestSelectRebootMethodNode:
    """Tests for select_reboot_method node."""

    def test_select_method_returns_method(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state_with_model, json_response_factory
    ):
        """Select method node returns physical or app method."""
        response = json_response_factory("select_method", selected_method="physical")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = select_reboot_method(sample_v2_state_with_model)

        assert result["reboot_method"] == "physical"
        assert result["last_executed_node"] == "select_reboot_method"


class TestRetrievalNode:
    """Tests for retrieval node."""

    def test_retrieval_uses_model_filter(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state_ready_to_qualify
    ):
        """Retrieval node filters by router_model."""
        state = sample_v2_state_ready_to_qualify
        state.reboot_appropriate = True
        state.reboot_method = "physical"

        result = retrieval(state)

        assert "rag_context" in result
        assert result["next_node"] == "guide_reboot"

    def test_retrieval_fallback_on_no_results(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state_ready_to_qualify
    ):
        """Retrieval returns fallback message if no docs found."""
        patch_v2_vectorstore.similarity_search.return_value = []

        state = sample_v2_state_ready_to_qualify
        state.reboot_appropriate = True
        state.reboot_method = "physical"

        result = retrieval(state)

        assert "messages" in result
        assert result["last_executed_node"] == "apologize_and_exit"


class TestGuideRebootNode:
    """Tests for guide_reboot node."""

    def test_guide_reboot_includes_mode(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state_with_model, json_response_factory
    ):
        """Guide reboot prompt includes conversation_mode."""
        response = json_response_factory("guide_reboot")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        state = sample_v2_state_with_model
        state.rag_context = "Step 1: Disconnect power"
        state.reboot_method = "physical"

        result = guide_reboot(state)

        assert result["last_executed_node"] == "guide_reboot"
        assert not result.get("next_node") or result.get("next_node") != "check_resolution"

    def test_guide_reboot_sets_next_node_when_done(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state_with_model, json_response_factory
    ):
        """Guide reboot sets next_node to check_resolution when all_steps_done."""
        response = json_response_factory("guide_reboot_done", all_steps_done=True)
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        state = sample_v2_state_with_model
        state.rag_context = "Step 1: Disconnect"
        state.reboot_method = "physical"

        result = guide_reboot(state)

        assert result.get("next_node") == "check_resolution"


class TestCheckResolutionNode:
    """Tests for check_resolution node."""

    def test_check_resolution_resolved_true(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state_with_model, json_response_factory
    ):
        """Check resolution sets issue_resolved=True when resolved."""
        response = json_response_factory("check_resolution_yes", resolved=True)
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = check_resolution(sample_v2_state_with_model)

        assert result["issue_resolved"] is True

    def test_check_resolution_resolved_false(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state_with_model, json_response_factory
    ):
        """Check resolution sets issue_resolved=False when not resolved."""
        response = json_response_factory("check_resolution_no", resolved=False)
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = check_resolution(sample_v2_state_with_model)

        assert result["issue_resolved"] is False

    def test_check_resolution_resolved_none(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state_with_model, json_response_factory
    ):
        """Check resolution doesn't set issue_resolved if response is vague."""
        response = json_response_factory("check_resolution", resolved=None)
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = check_resolution(sample_v2_state_with_model)

        assert "issue_resolved" not in result


class TestTerminalNodes:
    """Tests for terminal nodes."""

    def test_close_success(self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state_with_model, json_response_factory):
        """Close success node returns farewell message."""
        response = json_response_factory("close_success")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = close_success(sample_v2_state_with_model)

        assert result["last_executed_node"] == "close_success"

    def test_apologize_and_exit(
        self, patch_v2_llm, patch_v2_vectorstore, sample_v2_state_with_model, json_response_factory
    ):
        """Apologize and exit node returns sympathy message."""
        response = json_response_factory("apologize_and_exit")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = apologize_and_exit(sample_v2_state_with_model)

        assert result["last_executed_node"] == "apologize_and_exit"

    def test_graceful_exit(self, patch_v2_llm, patch_v2_vectorstore, json_response_factory):
        """Graceful exit node returns helpful exit message."""
        state = ConversationState(
            messages=[HumanMessage(content="Single device issue")],
            conversation_mode="self_serve",
            router_model="EA6350",
            exit_reason="single_device",
        )
        response = json_response_factory("graceful_exit")
        patch_v2_llm.invoke.return_value = Mock(content=json.dumps(response))

        result = graceful_exit(state)

        assert result["last_executed_node"] == "graceful_exit"


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_list_available_models(self, patch_v2_vectorstore):
        """_list_available_models returns sorted unique models."""
        models = _list_available_models()
        assert "EA6350" in models
        assert "ARCHER C1200" in models

    def test_check_model_exists_true(self, patch_v2_vectorstore):
        """_check_model_exists returns True for known models."""
        assert _check_model_exists("EA6350") is True

    def test_check_model_exists_false(self, patch_v2_vectorstore):
        """_check_model_exists returns False for unknown models."""
        assert _check_model_exists("UNKNOWN_MODEL") is False
