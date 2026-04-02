"""
Run LangSmith evaluations on golden scenarios dataset.

This script:
1. Loads the golden_scenarios.jsonl dataset into LangSmith
2. Defines evaluators for qualification, exit reasons, and clarity
3. Runs experiments with the V1 agent
4. Sends results to LangSmith for visualization
"""

import sys
import json
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file to ensure LANGSMITH_PROJECT and other vars are set
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langsmith import Client, evaluate
from langsmith.evaluation import run_evaluator, EvaluationResult
from langchain_core.messages import HumanMessage, AIMessage
from agents.v1.graph import compile_graph


# ============================================================================
# 1. Dataset Setup
# ============================================================================

def load_or_create_dataset():
    """Load golden_scenarios.jsonl into LangSmith."""
    client = Client()
    dataset_name = "wifi_troubleshooting_golden_v1"

    # Check if dataset already exists
    datasets = list(client.list_datasets(dataset_name=dataset_name))
    if datasets:
        dataset = datasets[0]
        print(f"Using existing dataset: {dataset.name} (ID: {dataset.id})")
        return dataset

    # Create new dataset with metadata to tag it to the project
    print(f"Creating new dataset: {dataset_name}")
    project_name = os.getenv("LANGSMITH_PROJECT", "default")
    dataset = client.create_dataset(
        dataset_name,
        metadata={"project": project_name, "purpose": "evaluation"}
    )

    # Load JSONL file
    jsonl_path = Path(__file__).parent / "golden_scenarios.jsonl"
    with open(jsonl_path, "r") as f:
        for line_num, line in enumerate(f, 1):
            data = json.loads(line)
            client.create_example(
                inputs=data["inputs"],
                outputs=data["outputs"],
                metadata=data.get("metadata", {}),
                dataset_id=dataset.id
            )
            print(f"  Added example {line_num}: {data['inputs']['scenario_id']}")

    return dataset


# ============================================================================
# 2. Target Function: Convert JSONL to Graph Input
# ============================================================================

def example_to_graph_input(inputs: dict) -> dict:
    """
    Convert dataset example inputs to LangGraph state format.

    Input: {
        "scenario_id": "scenario_001",
        "scenario_name": "...",
        "chat_history": [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."},
            ...
        ]
    }

    Output: ConversationState compatible dict with messages
    """
    chat_history = inputs.get("chat_history", [])

    # Convert to LangChain messages
    messages = []
    for msg in chat_history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    return {
        "messages": messages,
        # Store scenario info in state for reference
        "scenario_id": inputs.get("scenario_id"),
    }


# ============================================================================
# 3. Evaluators
# ============================================================================

@run_evaluator
def qualification_correctness(run, example) -> EvaluationResult:
    """
    Check if reboot_appropriate matches expected value.

    Scores:
    - 1: Correct prediction
    - 0: Incorrect prediction
    """
    expected_reboot = example.outputs.get("reboot_appropriate")
    predicted_reboot = run.outputs.get("reboot_appropriate")

    # Handle None values gracefully
    match = expected_reboot == predicted_reboot
    score = 1 if match else 0

    return EvaluationResult(
        key="qualification_correctness",
        score=score,
    )


@run_evaluator
def exit_reason_validity(run, example) -> EvaluationResult:
    """
    Check if exit_reason matches expected value.

    Scores:
    - 1: Correct exit reason (or both None)
    - 0.5: Exit triggered but reason differs
    - 0: Missing exit when expected, or vice versa
    """
    expected_reason = example.outputs.get("exit_reason")
    predicted_reason = run.outputs.get("exit_reason")

    if expected_reason == predicted_reason:
        score = 1.0
    elif expected_reason is None and predicted_reason is not None:
        # Expected to continue but agent exited
        score = 0.0
    elif expected_reason is not None and predicted_reason is None:
        # Expected exit but agent didn't exit
        score = 0.0
    else:
        # Both exited but with different reasons
        score = 0.5

    return EvaluationResult(
        key="exit_reason_validity",
        score=score,
    )


@run_evaluator
def inconclusive_count_tracking(run, example) -> EvaluationResult:
    """
    Check if inconclusive_count is tracked correctly.

    Expected field in outputs: "inconclusive_count" (optional)
    """
    expected_count = example.outputs.get("inconclusive_count")
    predicted_count = run.outputs.get("inconclusive_count", 0)

    if expected_count is None:
        # No expectation set, just verify it's not negative
        score = 1.0 if predicted_count >= 0 else 0.0
    else:
        match = expected_count == predicted_count
        score = 1.0 if match else 0.0

    return EvaluationResult(
        key="inconclusive_count_tracking",
        score=score,
    )


@run_evaluator
def response_consistency(run, example) -> EvaluationResult:
    """
    Check if agent maintains conversation coherence.

    Basic checks:
    - Last message is from assistant (not user)
    - All messages alternate between user and assistant
    - No critical errors in response
    """
    messages = run.outputs.get("messages", [])

    # Check message alternation
    if len(messages) < 2:
        return EvaluationResult(key="response_consistency", score=0.5)

    consistent = True
    last_role = None
    for msg in messages:
        role = getattr(msg, "type", None)  # "human" or "ai"
        if last_role is not None:
            if (last_role == "human" and role != "ai") or \
               (last_role == "ai" and role != "human"):
                consistent = False
                break
        last_role = role

    # Last message should be from assistant (AI)
    last_is_assistant = messages[-1].type == "ai" if messages else False

    score = 1.0 if (consistent and last_is_assistant) else 0.5

    return EvaluationResult(
        key="response_consistency",
        score=score,
    )


# ============================================================================
# 4. Main Evaluation
# ============================================================================

def run_evaluation():
    """Run LangSmith evaluation on golden scenarios."""
    import os

    # Ensure environment is set up
    if not os.getenv("LANGSMITH_API_KEY"):
        print("ERROR: LANGSMITH_API_KEY not set. Please configure your environment.")
        return

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set. Please configure your environment.")
        return

    print("\n" + "="*70)
    print("LangSmith Evaluation: WiFi Troubleshooting Agent V1")
    print("="*70)

    # Step 1: Load/Create dataset
    print("\n[Step 1] Loading dataset...")
    dataset = load_or_create_dataset()

    # Step 2: Compile agent graph
    print("\n[Step 2] Compiling agent graph...")
    app = compile_graph()

    # Step 3: Create target function (dataset input → graph execution)
    print("[Step 3] Creating target function...")
    def target(inputs: dict) -> dict:
        """Execute graph on dataset inputs."""
        graph_inputs = example_to_graph_input(inputs)
        result = app.invoke(graph_inputs, config={"thread_id": inputs.get("scenario_id")})
        return result

    # Step 4: Run evaluation
    print("[Step 4] Running evaluation with 4 evaluators...")
    print("  - qualification_correctness: matches expected reboot decision")
    print("  - exit_reason_validity: matches expected exit reason")
    print("  - inconclusive_count_tracking: tracks inconclusive exchanges")
    print("  - response_consistency: maintains conversation coherence")

    # Get project name from environment
    project_name = os.getenv("LANGSMITH_PROJECT", "default")

    results = evaluate(
        target,
        data=dataset.name,
        evaluators=[
            qualification_correctness,
            exit_reason_validity,
            inconclusive_count_tracking,
            response_consistency,
        ],
        experiment_prefix=f"{project_name}_v1_golden_scenarios",
        max_concurrency=1,  # Sequential for debugging; increase for parallel
    )

    # Step 5: Print summary
    print("\n" + "="*70)
    print("Evaluation Complete!")
    print("="*70)
    print(f"\nResults Summary:")
    print(f"  Dataset: {dataset.name}")
    print(f"  Project: {project_name}")
    print(f"  Experiment Prefix: {project_name}_v1_golden_scenarios")
    print(f"\nTo see results in LangSmith:")
    print(f"  1. Go to https://smith.langchain.com")
    print(f"  2. Select '{project_name}' project (if not already selected)")
    print(f"  3. Look for experiments starting with '{project_name}_v1_golden_scenarios'")
    print(f"  4. Click any experiment to see detailed evaluation results")
    print("\n" + "="*70)

    return results


if __name__ == "__main__":
    run_evaluation()
