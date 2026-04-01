"""
LLM-as-judge evaluation system.

Uses OpenAI to score conversation clarity against criteria.
"""

import json
from typing import Dict, Any
import os
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _get_judge_llm():
    """Lazy-load OpenAI client (avoid requiring .env at import time)."""
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in .env")
    return OpenAI(api_key=api_key)


class ConversationJudge:
    """
    LLM-as-judge for evaluating conversation clarity.

    Prompts GPT-4 to score a conversation on clarity and appropriateness.
    """

    @staticmethod
    def score_clarity(
        conversation_turns: list[Dict[str, str]],
        agent_responses: list[str],
        criteria: list[str]
    ) -> Dict[str, Any]:
        """
        Use LLM to score conversation clarity.

        Args:
            conversation_turns: Full conversation history
            agent_responses: Agent's specific responses
            criteria: List of evaluation criteria

        Returns:
            Dict with clarity_score (0.0-1.0) and reasoning
        """
        client = _get_judge_llm()

        # Build conversation text for judge
        conversation_text = "\n".join([
            f"{turn['role'].upper()}: {turn['content']}"
            for turn in conversation_turns
        ])

        criteria_text = "\n".join([f"- {c}" for c in criteria])

        system_prompt = """You are an expert evaluator of WiFi troubleshooting conversations.
Your job is to score a conversation on clarity and appropriateness.

You MUST respond in JSON format with this structure:
{
    "clarity_score": 0.0-1.0,
    "reasoning": "explanation",
    "strengths": ["list", "of", "strengths"],
    "weaknesses": ["list", "of", "weaknesses"]
}
"""

        user_prompt = f"""Evaluate this WiFi troubleshooting conversation on clarity and appropriateness.

CONVERSATION:
{conversation_text}

EVALUATION CRITERIA:
{criteria_text}

Score the conversation 0.0-1.0 where:
- 1.0: Excellent clarity, appropriate responses, clear guidance
- 0.75: Good clarity with minor issues
- 0.5: Moderate clarity with some confusing points
- 0.25: Poor clarity, confusing or inappropriate responses
- 0.0: Very poor clarity, incoherent or unhelpful

Respond ONLY with JSON."""

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.5
        )

        try:
            result = json.loads(response.choices[0].message.content)
            return {
                "clarity_score": result.get("clarity_score", 0.5),
                "reasoning": result.get("reasoning", "No reasoning provided"),
                "strengths": result.get("strengths", []),
                "weaknesses": result.get("weaknesses", [])
            }
        except (json.JSONDecodeError, KeyError) as e:
            return {
                "clarity_score": 0.5,
                "reasoning": f"Judge failed to parse response: {str(e)}",
                "strengths": [],
                "weaknesses": ["Judge response parsing failed"]
            }
