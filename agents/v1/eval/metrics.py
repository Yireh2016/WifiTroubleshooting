"""
Evaluation metrics for V1 agent.

Two critical metrics:
1. Qualification Accuracy: Did agent correctly identify if reboot is needed?
2. Conversation Clarity: Are step-by-step instructions understandable?
"""

from typing import Dict, Any, Literal


class QualificationAccuracy:
    """
    Metric 1: Qualification Accuracy

    Measures whether the agent correctly determined if a reboot is needed.
    - True Positive: Agent says reboot needed, should be needed
    - True Negative: Agent says reboot not needed, should not be needed
    - False Positive: Agent says reboot needed, but shouldn't be
    - False Negative: Agent says reboot not needed, but should be

    Score: (TP + TN) / Total
    """

    @staticmethod
    def evaluate(
        agent_decision: bool,
        expected_decision: bool
    ) -> Dict[str, Any]:
        """
        Compare agent's reboot decision against expected outcome.

        Args:
            agent_decision: Whether agent recommended reboot (True/False)
            expected_decision: Whether reboot should be recommended (True/False)

        Returns:
            Dict with pass/fail and reasoning
        """
        correct = agent_decision == expected_decision

        decision_type = "TP" if (agent_decision and expected_decision) else \
                       "TN" if (not agent_decision and not expected_decision) else \
                       "FP" if (agent_decision and not expected_decision) else "FN"

        return {
            "passed": correct,
            "score": 1.0 if correct else 0.0,
            "agent_decision": agent_decision,
            "expected_decision": expected_decision,
            "decision_type": decision_type,
            "reasoning": f"{'Correct' if correct else 'Incorrect'} reboot decision ({decision_type})"
        }


class ConversationClarity:
    """
    Metric 2: Conversation Clarity

    Measures whether the conversation flow is understandable and appropriately guided.
    Evaluated by LLM-as-judge scoring:
    - Clarity of questions (are they specific, not ambiguous?)
    - Appropriateness of responses (do they match the conversation context?)
    - Step-by-step guidance quality (if applicable)
    - Graceful exit handling (appropriate termination)

    Score: 0.0-1.0 (subjective, LLM-judged)
    """

    @staticmethod
    def prepare_for_judge(
        conversation_turns: list[Dict[str, str]],
        agent_responses: list[str],
        expected_clarity_level: Literal["Low", "Medium", "Medium-High", "High"]
    ) -> Dict[str, Any]:
        """
        Prepare conversation data for LLM-as-judge evaluation.

        Args:
            conversation_turns: Full conversation (user + agent messages)
            agent_responses: Agent's actual responses
            expected_clarity_level: Expected clarity level from golden scenario

        Returns:
            Dict ready for judge.py to evaluate
        """
        return {
            "conversation_turns": conversation_turns,
            "agent_responses": agent_responses,
            "expected_clarity_level": expected_clarity_level,
            "evaluation_criteria": [
                "Are agent questions specific and non-ambiguous?",
                "Does agent respond appropriately to user inputs?",
                "If providing steps, are they clear and actionable?",
                "Is the conversation flow logical?",
                "Are exits (scope, escalation) handled gracefully?"
            ]
        }
