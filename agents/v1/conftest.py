"""
Pytest configuration and shared fixtures for agent tests.

This module provides:
- Mocked LLM responses for unit testing
- Sample state builders
- Fixtures for RAG context
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
from langchain_core.messages import AIMessage, HumanMessage

# Setup path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.state.state_v1 import ConversationState


@pytest.fixture
def mock_llm():
    """Mock LLM that returns structured JSON responses."""
    llm = Mock()

    def mock_invoke(messages):
        response = Mock()
        response.content = '{"reply": "mocked response", "decision": "reboot"}'
        return response

    llm.invoke = mock_invoke
    return llm


@pytest.fixture
def mock_vectorstore():
    """Mock Chroma vectorstore for RAG tests."""
    vs = Mock()

    def mock_similarity_search(query, k=1, filter=None):
        doc = Mock()
        doc.page_content = (
            "Step 1: Disconnect the power cable from the router.\n"
            "Step 2: Wait 30 seconds.\n"
            "Step 3: Reconnect the power cable.\n"
            "Step 4: Wait for the lights to stabilize."
        )
        doc.metadata = {"model_name": "EA6350", "language": "en", "section_tag": "troubleshooting"}
        return [doc]

    vs.similarity_search = mock_similarity_search
    return vs


@pytest.fixture
def sample_state():
    """Create a base ConversationState for testing."""
    return ConversationState(
        messages=[HumanMessage(content="My WiFi is down")],
        reboot_appropriate=None,
        issue_resolved=None,
        next_node="not_started",
        last_executed_node="qualify",
        rag_context=None,
        exit_reason=None,
    )


@pytest.fixture
def sample_messages():
    """Create a sample conversation history."""
    return [
        HumanMessage(content="My WiFi is down. All devices are offline."),
        AIMessage(content="I can help with that. Are all your devices affected?"),
        HumanMessage(content="Yes, everything is offline."),
        AIMessage(content="Have you tried rebooting the router?"),
        HumanMessage(content="No, not yet."),
    ]


@pytest.fixture
def rag_context():
    """Sample RAG context for reboot instructions."""
    return """
Step 1: Locate the power cable at the back of the Linksys EA6350 router.
Step 2: Disconnect the power cable from the router.
Step 3: Wait at least 30 seconds. This allows capacitors to discharge.
Step 4: Reconnect the power cable to the back of the router.
Step 5: Wait for the status lights to turn on and stabilize (usually 2-3 minutes).
Step 6: Test your internet connection on one device.
"""


@pytest.fixture
def patch_llm_module(mock_llm):
    """Patch the _get_llm function in nodes module."""
    with patch("agents.v1.nodes._get_llm", return_value=mock_llm):
        yield mock_llm


@pytest.fixture
def patch_vectorstore_module(mock_vectorstore):
    """Patch the _get_vectorstore function in nodes module."""
    with patch("agents.v1.nodes._get_vectorstore", return_value=mock_vectorstore):
        yield mock_vectorstore


@pytest.fixture
def json_response_factory():
    """Factory for creating mock JSON responses from nodes."""
    def create_response(node_type="qualify", **kwargs):
        responses = {
            "qualify": {
                "decision": "reboot",
                "exit_reason": None,
                "reply": "Let's get this fixed. Do you have access to the router?",
                **kwargs
            },
            "guide_reboot": {
                "reply": "First, let's disconnect the power cable.",
                "all_steps_done": False,
                **kwargs
            },
            "check_resolution": {
                "reply": "Is your internet working now?",
                "resolved": None,
                **kwargs
            },
            "graceful_exit": {
                "reply": "Thanks for explaining. Here's what I'd recommend...",
                **kwargs
            },
            "close_success": {
                "reply": "Glad I could help!",
                **kwargs
            },
            "apologize_and_exit": {
                "reply": "I'm sorry the reboot didn't resolve this. Please contact support.",
                **kwargs
            },
        }
        return responses.get(node_type, responses["qualify"])

    return create_response
