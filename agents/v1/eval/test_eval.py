"""
Evaluation test runner for V1 agent.

Runs 10 golden scenarios against the agent.
Scores with LLM-as-judge on two metrics:
1. Qualification Accuracy (reboot decision)
2. Conversation Clarity (LLM subjective scoring)
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.v1.eval.golden_scenarios import GOLDEN_SCENARIOS
from agents.v1.eval.metrics import QualificationAccuracy, ConversationClarity
from agents.v1.eval.judge import ConversationJudge
from agents.v1.graph import compile_graph
from langchain_core.messages import HumanMessage


class EvaluationRunner:
    """Runs evaluation against golden scenarios."""

    def __init__(self):
        """Initialize graph and judge."""
        self.graph = compile_graph()
        self.judge = ConversationJudge()
        self.results = []

    def run_scenario(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a single golden scenario against the agent.

        Args:
            scenario: Golden scenario dict with conversation flow

        Returns:
            Dict with evaluation results
        """
        scenario_id = scenario["id"]
        scenario_name = scenario["name"]

        print(f"\n{'='*70}")
        print(f"Running: {scenario_id} - {scenario_name}")
        print(f"Type: {scenario['type']} | Difficulty: {scenario['difficulty']}")
        print(f"{'='*70}")

        # Simulate conversation with agent
        thread_id = f"eval_{scenario_id}"
        config = {"configurable": {"thread_id": thread_id}}

        # Extract user messages and simulate conversation
        conversation_turns = []
        agent_responses = []

        for turn in scenario["conversation"]:
            role = turn["role"]

            if role == "user":
                # Send user message to agent
                user_content = turn["content"]
                conversation_turns.append({"role": "user", "content": user_content})
                print(f"\n[USER]: {user_content}")

                try:
                    # Invoke graph
                    self.graph.invoke(
                        {"messages": [HumanMessage(content=user_content)]},
                        config=config
                    )

                    # Get state and extract last AI message
                    state = self.graph.get_state(config)
                    state_messages = state.values.get("messages", [])

                    agent_response = None
                    for msg in reversed(state_messages):
                        if hasattr(msg, 'type') and msg.type == "ai":
                            if hasattr(msg, 'content') and isinstance(msg.content, str) and msg.content.strip():
                                agent_response = msg.content
                                break

                    if agent_response:
                        agent_responses.append(agent_response)
                        conversation_turns.append({"role": "assistant", "content": agent_response})
                        print(f"[AGENT]: {agent_response[:100]}...")
                        state_dict = state.values
                    else:
                        print("[AGENT]: No response generated")
                        agent_responses.append("[No Response]")
                        state_dict = state.values

                except Exception as e:
                    print(f"[ERROR]: {str(e)}")
                    agent_responses.append(f"[Error: {str(e)}]")
                    state_dict = {}

        # Extract final state for evaluation
        final_reboot_decision = state_dict.get("reboot_appropriate")
        exit_reason = state_dict.get("exit_reason")

        print(f"\n[FINAL STATE]")
        print(f"  reboot_appropriate: {final_reboot_decision}")
        print(f"  exit_reason: {exit_reason}")

        # Metric 1: Qualification Accuracy
        expected_reboot = scenario["expected_outcome"].get("reboot_appropriate")
        qualification_result = QualificationAccuracy.evaluate(
            agent_decision=final_reboot_decision,
            expected_decision=expected_reboot
        )

        print(f"\n[METRIC 1: Qualification Accuracy]")
        print(f"  Expected: {expected_reboot}")
        print(f"  Agent Decision: {final_reboot_decision}")
        print(f"  Result: {qualification_result['reasoning']}")
        print(f"  Score: {qualification_result['score']}")

        # Metric 2: Conversation Clarity (LLM-as-judge)
        expected_clarity = scenario["expected_outcome"].get("clarity_score_expectations", "Medium")

        # Prepare data for judge
        clarity_eval_data = ConversationClarity.prepare_for_judge(
            conversation_turns=conversation_turns,
            agent_responses=agent_responses,
            expected_clarity_level=expected_clarity
        )

        # Score with judge
        clarity_result = self.judge.score_clarity(
            conversation_turns=conversation_turns,
            agent_responses=agent_responses,
            criteria=clarity_eval_data["evaluation_criteria"]
        )

        print(f"\n[METRIC 2: Conversation Clarity]")
        print(f"  Expected Level: {expected_clarity}")
        print(f"  Judge Score: {clarity_result['clarity_score']}")
        print(f"  Reasoning: {clarity_result['reasoning'][:200]}...")
        if clarity_result['strengths']:
            print(f"  Strengths: {', '.join(clarity_result['strengths'][:2])}")
        if clarity_result['weaknesses']:
            print(f"  Weaknesses: {', '.join(clarity_result['weaknesses'][:2])}")

        # Compile results
        result = {
            "scenario_id": scenario_id,
            "scenario_name": scenario_name,
            "type": scenario["type"],
            "difficulty": scenario["difficulty"],
            "qualification_accuracy": qualification_result,
            "conversation_clarity": clarity_result,
            "final_state": {
                "reboot_appropriate": final_reboot_decision,
                "exit_reason": exit_reason,
            }
        }

        return result

    def run_all(self) -> Dict[str, Any]:
        """Run all golden scenarios and compile report."""
        print("\n" + "="*70)
        print("STARTING EVALUATION PIPELINE - V1 AGENT")
        print("="*70)

        for scenario in GOLDEN_SCENARIOS:
            result = self.run_scenario(scenario)
            self.results.append(result)

        # Compile report
        report = self._compile_report()
        return report

    def _compile_report(self) -> Dict[str, Any]:
        """Compile evaluation report."""
        print("\n\n" + "="*70)
        print("EVALUATION REPORT")
        print("="*70)

        # Metric 1: Qualification Accuracy
        qual_accuracy_scores = [
            r["qualification_accuracy"]["score"] for r in self.results
        ]
        qual_accuracy_avg = sum(qual_accuracy_scores) / len(qual_accuracy_scores) if qual_accuracy_scores else 0

        # Metric 2: Conversation Clarity
        clarity_scores = [
            r["conversation_clarity"]["clarity_score"] for r in self.results
        ]
        clarity_avg = sum(clarity_scores) / len(clarity_scores) if clarity_scores else 0

        report = {
            "total_scenarios": len(GOLDEN_SCENARIOS),
            "total_passed": sum(1 for r in self.results if r["qualification_accuracy"]["passed"]),
            "metrics": {
                "qualification_accuracy": {
                    "average_score": round(qual_accuracy_avg, 3),
                    "scores": qual_accuracy_scores,
                    "description": "Percentage of correct reboot decisions"
                },
                "conversation_clarity": {
                    "average_score": round(clarity_avg, 3),
                    "scores": clarity_scores,
                    "description": "LLM-as-judge scoring (0.0-1.0)"
                }
            },
            "scenario_results": [
                {
                    "id": r["scenario_id"],
                    "name": r["scenario_name"],
                    "qualification_accuracy_passed": r["qualification_accuracy"]["passed"],
                    "clarity_score": r["conversation_clarity"]["clarity_score"]
                }
                for r in self.results
            ]
        }

        # Print report
        print(f"\nTotal Scenarios: {report['total_scenarios']}")
        print(f"Qualification Accuracy (Avg): {report['metrics']['qualification_accuracy']['average_score']}")
        print(f"Conversation Clarity (Avg): {report['metrics']['conversation_clarity']['average_score']}")

        print("\n--- Scenario Results ---")
        for sr in report["scenario_results"]:
            qual_status = "✓" if sr["qualification_accuracy_passed"] else "✗"
            print(f"{qual_status} {sr['id']}: {sr['name']} (clarity: {sr['clarity_score']})")

        return report

    def save_report(self, output_file: Path):
        """Save report to JSON file."""
        report = self._compile_report()
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n✓ Report saved to {output_file}")


if __name__ == "__main__":
    runner = EvaluationRunner()
    report = runner.run_all()

    # Save report
    output_file = Path(__file__).parent / "eval_report.json"
    runner.save_report(output_file)

    # Exit with success
    print("\n✓ Evaluation complete!")
    sys.exit(0)
