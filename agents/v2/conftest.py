import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.state.state_v2 import ConversationState


@pytest.fixture
def mock_llm():
    """Mock LLM that returns JSON responses."""
    llm = Mock()

    def mock_invoke(messages):
        response = Mock()
        response.content = '{"reply": "Test response", "decision": "ask_more"}'
        return response

    llm.invoke = mock_invoke
    return llm


@pytest.fixture
def mock_vectorstore():
    """Mock vectorstore with V2 metadata (includes brand, model filtering)."""
    vs = Mock()

    def mock_similarity_search(query, k=1, filter=None):
        doc = Mock()
        doc.page_content = "Step 1: Disconnect power cable for 30 seconds. Step 2: Reconnect power cable."
        doc.metadata = {
            "model_name": "EA6350",
            "language": "en",
            "section_tag": "troubleshooting",
            "brand": "LINKSYS",
        }
        return [doc] if filter is None or filter.get("$and", [{}])[0].get("model_name") == "EA6350" else []

    vs.similarity_search = mock_similarity_search

    def mock_get(where=None, limit=None):
        if where and where.get("model_name") == "EA6350":
            return {
                "ids": ["EA6350_en_troubleshooting"],
                "metadatas": [{"model_name": "EA6350", "brand": "LINKSYS"}],
            }
        elif where and where.get("model_name") == "ARCHER C1200":
            return {
                "ids": ["ARCHER C1200_en_overview"],
                "metadatas": [{"model_name": "ARCHER C1200", "brand": "TP-LINK"}],
            }
        # Default: return all models
        return {
            "ids": ["EA6350_en_troubleshooting", "ARCHER C1200_en_overview"],
            "metadatas": [
                {"model_name": "EA6350", "brand": "LINKSYS"},
                {"model_name": "ARCHER C1200", "brand": "TP-LINK"},
            ],
        }

    vs.get = mock_get
    return vs


@pytest.fixture
def sample_v2_state():
    """Sample V2 state with self-serve mode."""
    return ConversationState(
        messages=[HumanMessage(content="My WiFi is down")],
        conversation_mode="self_serve",
    )


@pytest.fixture
def sample_v2_state_agent_assisted():
    """Sample V2 state with agent-assisted mode."""
    return ConversationState(
        messages=[HumanMessage(content="WiFi not working")],
        conversation_mode="agent_assisted",
    )


@pytest.fixture
def sample_v2_state_with_model():
    """Sample V2 state with model already set."""
    return ConversationState(
        messages=[HumanMessage(content="My WiFi is down")],
        conversation_mode="self_serve",
        router_model="EA6350",
    )


@pytest.fixture
def sample_v2_state_ready_to_qualify():
    """Sample V2 state ready to enter qualify node."""
    return ConversationState(
        messages=[
            HumanMessage(content="My WiFi is down"),
            AIMessage(content="What's your router model?"),
            HumanMessage(content="Linksys EA6350"),
        ],
        conversation_mode="self_serve",
        router_model="EA6350",
    )


@pytest.fixture
def patch_v2_llm(mock_llm):
    """Patch _get_llm to return mock_llm."""
    with patch("agents.v2.nodes._get_llm", return_value=mock_llm):
        yield mock_llm


@pytest.fixture
def patch_v2_vectorstore(mock_vectorstore):
    """Patch _get_vectorstore to return mock_vectorstore."""
    with patch("agents.v2.nodes._get_vectorstore", return_value=mock_vectorstore):
        yield mock_vectorstore


@pytest.fixture
def json_response_factory():
    """Factory for V2 node JSON responses."""

    def create_response(node_type, **kwargs):
        responses = {
            "welcome": {
                "reply": "What router model do you have?",
                "extracted_model": None,
                "needs_guidance": False,
                **kwargs,
            },
            "welcome_with_model": {
                "reply": "Great! I found Linksys EA6350 in our system.",
                "extracted_model": "EA6350",
                "needs_guidance": False,
                **kwargs,
            },
            "discover_model": {
                "reply": "Could you check the sticker on the device?",
                "extracted_model": None,
                "needs_guidance": True,
                **kwargs,
            },
            "discover_model_success": {
                "reply": "Found it!",
                "extracted_model": "EA6350",
                "needs_guidance": False,
                **kwargs,
            },
            "qualify": {
                "decision": "ask_more",
                "exit_reason": None,
                "reply": "Let me ask you a few questions.",
                **kwargs,
            },
            "qualify_reboot": {
                "decision": "reboot",
                "exit_reason": None,
                "reply": "A reboot should fix this.",
                **kwargs,
            },
            "qualify_exit": {
                "decision": "exit",
                "exit_reason": "single_device",
                "reply": "Let's try a different approach.",
                **kwargs,
            },
            "select_method": {
                "reply": "Let's do a physical reboot.",
                "selected_method": "physical",
                "reasoning": "Your device is offline",
                **kwargs,
            },
            "guide_reboot": {
                "reply": "Disconnect the power cable for 30 seconds.",
                "all_steps_done": False,
                **kwargs,
            },
            "guide_reboot_done": {
                "reply": "You've completed all the steps!",
                "all_steps_done": True,
                **kwargs,
            },
            "check_resolution": {
                "reply": "Is your WiFi working now?",
                "resolved": None,
                **kwargs,
            },
            "check_resolution_yes": {
                "reply": "Great!",
                "resolved": True,
                **kwargs,
            },
            "check_resolution_no": {
                "reply": "I'm sorry to hear that.",
                "resolved": False,
                **kwargs,
            },
            "graceful_exit": {
                "reply": "Thank you for trying. Please contact support.",
                **kwargs,
            },
            "close_success": {
                "reply": "Happy to help! Goodbye.",
                **kwargs,
            },
            "apologize_and_exit": {
                "reply": "I'm sorry the reboot didn't resolve the issue.",
                **kwargs,
            },
        }
        return responses.get(node_type, responses["welcome"])

    return create_response
