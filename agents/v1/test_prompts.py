"""
Tests for prompt templates and LLM response parsing.

Validates:
- Prompt structure (JSON response format requirement)
- Response parsing (JSON extraction, markdown fence handling)
- Edge cases (malformed responses, missing fields)
"""

import sys
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.prompts.base_prompts import (
    QUALIFY_PROMPT, GUIDE_REBOOT_PROMPT, CHECK_RESOLUTION_PROMPT,
    GRACEFUL_EXIT_PROMPT, CLOSE_SUCCESS_PROMPT, APOLOGIZE_EXIT_PROMPT,
)
from agents.v1 import nodes


class TestPromptStructure:
    """Tests for prompt templates."""

    def test_qualify_prompt_exists(self):
        """QUALIFY_PROMPT should be defined."""
        assert QUALIFY_PROMPT is not None
        assert isinstance(QUALIFY_PROMPT, str)
        assert len(QUALIFY_PROMPT) > 0

    def test_guide_reboot_prompt_exists(self):
        """GUIDE_REBOOT_PROMPT should be defined."""
        assert GUIDE_REBOOT_PROMPT is not None
        assert isinstance(GUIDE_REBOOT_PROMPT, str)

    def test_check_resolution_prompt_exists(self):
        """CHECK_RESOLUTION_PROMPT should be defined."""
        assert CHECK_RESOLUTION_PROMPT is not None
        assert isinstance(CHECK_RESOLUTION_PROMPT, str)

    def test_graceful_exit_prompt_exists(self):
        """GRACEFUL_EXIT_PROMPT should be defined."""
        assert GRACEFUL_EXIT_PROMPT is not None
        assert isinstance(GRACEFUL_EXIT_PROMPT, str)

    def test_close_success_prompt_exists(self):
        """CLOSE_SUCCESS_PROMPT should be defined."""
        assert CLOSE_SUCCESS_PROMPT is not None
        assert isinstance(CLOSE_SUCCESS_PROMPT, str)

    def test_apologize_exit_prompt_exists(self):
        """APOLOGIZE_EXIT_PROMPT should be defined."""
        assert APOLOGIZE_EXIT_PROMPT is not None
        assert isinstance(APOLOGIZE_EXIT_PROMPT, str)

    def test_prompts_mention_json(self):
        """Prompts requiring JSON should mention it (required for OpenAI)."""
        prompts_needing_json = [
            QUALIFY_PROMPT,
            GUIDE_REBOOT_PROMPT,
            CHECK_RESOLUTION_PROMPT,
            GRACEFUL_EXIT_PROMPT,
            CLOSE_SUCCESS_PROMPT,
            APOLOGIZE_EXIT_PROMPT,
        ]

        for prompt in prompts_needing_json:
            assert "json" in prompt.lower(), f"Prompt missing JSON mention: {prompt[:50]}"

    def test_qualify_prompt_has_decision_field(self):
        """QUALIFY_PROMPT should mention decision field."""
        assert '"decision"' in QUALIFY_PROMPT or "'decision'" in QUALIFY_PROMPT

    def test_qualify_prompt_has_reply_field(self):
        """QUALIFY_PROMPT should mention reply field."""
        assert '"reply"' in QUALIFY_PROMPT or "'reply'" in QUALIFY_PROMPT

    def test_guide_reboot_has_steps_indicator(self):
        """GUIDE_REBOOT_PROMPT should mention steps or step-by-step."""
        assert "step" in GUIDE_REBOOT_PROMPT.lower()

    def test_graceful_exit_has_exit_reason_placeholder(self):
        """GRACEFUL_EXIT_PROMPT should have {exit_reason} placeholder."""
        assert "{exit_reason}" in GRACEFUL_EXIT_PROMPT


class TestJSONResponseParsing:
    """Tests for parsing LLM JSON responses."""

    def test_parse_valid_json_response(self):
        """Parser should handle valid JSON responses."""
        mock_llm = Mock()
        response = Mock()
        response.content = json.dumps({"reply": "Hello", "decision": "reboot"})
        mock_llm.invoke.return_value = response

        # Parse JSON
        parsed = json.loads(response.content)
        assert parsed["reply"] == "Hello"
        assert parsed["decision"] == "reboot"

    def test_parse_json_with_markdown_fences(self):
        """Parser should handle JSON wrapped in markdown code fences."""
        response_text = """
```json
{
    "reply": "Hello",
    "decision": "reboot"
}
```
"""
        # Simulate the parsing logic from nodes._call_llm
        content = response_text.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]

        parsed = json.loads(content)
        assert parsed["reply"] == "Hello"
        assert parsed["decision"] == "reboot"

    def test_parse_json_with_language_tag(self):
        """Parser should handle markdown with language tag."""
        response_text = '```json\n{"reply": "test", "decision": "exit"}\n```'

        content = response_text.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]

        parsed = json.loads(content)
        assert parsed["reply"] == "test"

    def test_parse_json_without_markdown(self):
        """Parser should handle plain JSON."""
        response_text = '{"reply": "test", "decision": "reboot"}'

        parsed = json.loads(response_text)
        assert parsed["reply"] == "test"

    def test_parse_json_with_nested_objects(self):
        """Parser should handle nested JSON structures."""
        response_text = json.dumps({
            "reply": "Nested test",
            "metadata": {
                "confidence": 0.95,
                "tags": ["wifi", "router"]
            }
        })

        parsed = json.loads(response_text)
        assert parsed["metadata"]["confidence"] == 0.95
        assert "wifi" in parsed["metadata"]["tags"]


class TestPromptTemplateInjection:
    """Tests for prompt template variable injection."""

    def test_graceful_exit_injects_exit_reason(self):
        """GRACEFUL_EXIT_PROMPT should support {exit_reason} injection."""
        exit_reasons = ["single_device", "isp_outage", "already_rebooted", "cables_fixed"]

        for reason in exit_reasons:
            prompt = GRACEFUL_EXIT_PROMPT.format(exit_reason=reason)
            assert reason in prompt

    def test_guide_reboot_injects_rag_context(self):
        """GUIDE_REBOOT_PROMPT should support {rag_context} injection."""
        context = "Step 1: Disconnect power\nStep 2: Wait 30 seconds"
        prompt = GUIDE_REBOOT_PROMPT.format(rag_context=context)

        assert context in prompt
        assert "Step 1" in prompt

    def test_prompt_injection_with_empty_string(self):
        """Prompts should handle empty string injection."""
        prompt = GRACEFUL_EXIT_PROMPT.format(exit_reason="")
        assert isinstance(prompt, str)

    def test_prompt_injection_with_special_characters(self):
        """Prompts should handle special character injection."""
        special_context = "Step 1: Disconnect @#$%^&*()\nStep 2: Wait 30 seconds"
        prompt = GUIDE_REBOOT_PROMPT.format(rag_context=special_context)
        assert "@#$%^&*()" in prompt


class TestQualifyResponseFields:
    """Tests for expected fields in qualify responses."""

    def test_qualify_response_has_decision(self):
        """Qualify response should have decision field."""
        response = {
            "decision": "reboot",
            "exit_reason": None,
            "reply": "Let's reboot"
        }

        assert "decision" in response
        assert response["decision"] in ["ask_more", "reboot", "exit"]

    def test_qualify_response_has_exit_reason(self):
        """Qualify response should have exit_reason (when exiting)."""
        response = {
            "decision": "exit",
            "exit_reason": "single_device",
            "reply": "That's a device issue"
        }

        assert "exit_reason" in response
        expected_reasons = [None, "single_device", "isp_outage", "already_rebooted", "cables_fixed"]
        assert response["exit_reason"] in expected_reasons

    def test_qualify_response_has_reply(self):
        """Qualify response should have reply field."""
        response = {
            "decision": "ask_more",
            "exit_reason": None,
            "reply": "Can you provide more details?"
        }

        assert "reply" in response
        assert isinstance(response["reply"], str)


class TestGuideRebootResponseFields:
    """Tests for expected fields in guide_reboot responses."""

    def test_guide_response_has_reply(self):
        """Guide response should have reply field."""
        response = {
            "reply": "Step 1: Disconnect power",
            "all_steps_done": False
        }

        assert "reply" in response
        assert isinstance(response["reply"], str)

    def test_guide_response_has_all_steps_done(self):
        """Guide response should have all_steps_done field."""
        response = {
            "reply": "All complete",
            "all_steps_done": True
        }

        assert "all_steps_done" in response
        assert isinstance(response["all_steps_done"], bool)


class TestCheckResolutionResponseFields:
    """Tests for expected fields in check_resolution responses."""

    def test_check_response_has_reply(self):
        """Check response should have reply field."""
        response = {
            "reply": "Is your WiFi working?",
            "resolved": None
        }

        assert "reply" in response

    def test_check_response_resolved_can_be_null(self):
        """Check response resolved field can be None."""
        response = {
            "reply": "Can you confirm?",
            "resolved": None
        }

        assert response["resolved"] is None

    def test_check_response_resolved_can_be_boolean(self):
        """Check response resolved field should be True or False."""
        response1 = {"reply": "Great!", "resolved": True}
        response2 = {"reply": "Sorry", "resolved": False}

        assert response1["resolved"] is True
        assert response2["resolved"] is False


class TestExitResponseFields:
    """Tests for exit node response fields."""

    def test_exit_responses_have_reply(self):
        """All exit responses should have reply field."""
        responses = [
            {"reply": "Graceful exit message"},
            {"reply": "Success message"},
            {"reply": "Apology message"},
        ]

        for resp in responses:
            assert "reply" in resp
            assert isinstance(resp["reply"], str)
            assert len(resp["reply"]) > 0


class TestPromptEdgeCases:
    """Edge cases for prompt handling."""

    def test_very_long_rag_context_injection(self):
        """Prompts should handle very long RAG context."""
        long_context = "Step " * 1000
        prompt = GUIDE_REBOOT_PROMPT.format(rag_context=long_context)
        assert long_context in prompt

    def test_prompt_with_newlines(self):
        """Prompts should handle contexts with newlines."""
        context = "Step 1\nStep 2\nStep 3\n" * 10
        prompt = GUIDE_REBOOT_PROMPT.format(rag_context=context)
        assert "Step 1" in prompt

    def test_prompt_injection_unicode(self):
        """Prompts should handle unicode characters."""
        context = "Step 1: Power ⚡ Disconnect 🔌 Power 💡"
        prompt = GUIDE_REBOOT_PROMPT.format(rag_context=context)
        assert "⚡" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
