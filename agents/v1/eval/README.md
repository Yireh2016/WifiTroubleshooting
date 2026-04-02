# WiFi Troubleshooting V1 - LangSmith Evaluations

Automated evaluation framework for the WiFi troubleshooting agent using LangSmith.

## Quick Start

```bash
python3 agents/v1/eval/run_eval_direct.py
```

This will:
1. Load your `.env` file (LANGSMITH_API_KEY, OPENAI_API_KEY)
2. Create/load the dataset `wifi_troubleshooting_golden_v1` in LangSmith
3. Run all 10 golden scenarios through your agent
4. Score with 4 evaluators:
   - **qualification_correctness** — Did agent decide reboot correctly?
   - **exit_reason_validity** — Did agent exit with correct reason?
   - **inconclusive_count_tracking** — Did agent track unclear exchanges?
   - **response_consistency** — Is conversation coherent?
5. Send results to LangSmith

**Runtime:** ~30-45 seconds

## Files in This Directory

| File | Purpose |
|------|---------|
| `run_eval_direct.py` | **Main entry point** — Run this to execute evaluations |
| `run_experiments.py` | **Core logic** — Dataset loading, evaluators, experiment execution |
| `golden_scenarios.jsonl` | **Dataset** — 10 golden scenarios in LangSmith format (JSONL) |
| `__init__.py` | Python package marker |

## Before Running

### 1. Environment Setup

Ensure your `.env` file has:
```bash
OPENAI_API_KEY=sk-...
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=Project_Name  # Your project name
```

### 2. Dependencies

All packages are in `agents/v1/requirements.txt`. Install once:
```bash
pip install -r agents/v1/requirements.txt
```

### 3. RAG Setup (One-Time)

Initialize Chroma vector store:
```bash
python shared/rag/ingest_v1.py
```

## Running Evaluations

### Simple Run
```bash
python3 agents/v1/eval/run_eval_direct.py
```

### Output
```
======================================================================
LangSmith Evaluation: WiFi Troubleshooting Agent V1
======================================================================

[Step 1] Loading dataset...
Using existing dataset: wifi_troubleshooting_golden_v1 (ID: ...)

[Step 2] Compiling agent graph...
[Step 3] Creating target function...
[Step 4] Running evaluation with 4 evaluators...
  - qualification_correctness: matches expected reboot decision
  - exit_reason_validity: matches expected exit reason
  - inconclusive_count_tracking: tracks inconclusive exchanges
  - response_consistency: maintains conversation coherence

[Progress: 10/10 scenarios completed in ~35 seconds]

======================================================================
Evaluation Complete!
======================================================================

Results Summary:
  Dataset: wifi_troubleshooting_golden_v1
  Project: Jainers_Interview
  Experiment Prefix: Jainers_Interview_v1_golden_scenarios

To see results in LangSmith:
  1. Go to https://smith.langchain.com
  2. Select 'Jainers_Interview' project (if not already selected)
  3. Click "Datasets & Experiments"
  4. Find "wifi_troubleshooting_golden_v1" dataset
  5. Click "Experiments" tab
  6. Look for experiments starting with "Jainers_Interview_v1_golden_scenarios"
```

## Understanding the Dataset

### Format: JSONL (Line-Delimited JSON)

Each line is one scenario:
```json
{
  "inputs": {
    "scenario_id": "scenario_001",
    "scenario_name": "Clear qualification: reboot needed",
    "chat_history": [
      {"role": "user", "content": "My WiFi is not working..."},
      {"role": "assistant", "content": "I'll help you troubleshoot..."},
      ...
    ]
  },
  "outputs": {
    "reboot_appropriate": true,
    "exit_reason": null,
    "clarity_score_expectations": "High - clear steps provided"
  },
  "metadata": {
    "scenario_type": "positive_reboot",
    "difficulty": "easy",
    "description": "User reports internet down, reboots help before, device count normal"
  }
}
```

### Scenario Types

| Type | Examples | Count |
|------|----------|-------|
| **positive_reboot** | Reboot is appropriate | 4 scenarios |
| **negative_isp** | ISP issue, outside scope | 1 scenario |
| **negative_single_device** | Only one device affected | 1 scenario |
| **hallucination_risk** | Agent may reference non-existent info | 1 scenario |
| **out_of_scope** | Unrelated question | 1 scenario |
| **injection_risk** | Prompt injection attempt | 1 scenario |
| **inconclusive** | User provides vague answers | 1 scenario |
| **escalation** | User consistently vague, needs support | 0 scenarios |

Total: 10 scenarios

## Understanding Evaluators

All evaluators are defined in `run_experiments.py`:

### 1. qualification_correctness
Compares agent's `reboot_appropriate` decision against expected.

```python
Score: 1.0 if match, 0.0 if mismatch
```

**What it measures:**
- Did agent correctly decide if router reboot is needed?
- Examples:
  - Expected: True, Actual: True → ✓ 1.0
  - Expected: False, Actual: False → ✓ 1.0
  - Expected: True, Actual: False → ✗ 0.0

### 2. exit_reason_validity
Compares agent's `exit_reason` against expected.

```python
Score: 1.0 (match), 0.5 (wrong reason), 0.0 (missing/extra)
```

**What it measures:**
- Did agent exit for the right reason?
- Examples:
  - Expected: "isp_outage", Actual: "isp_outage" → ✓ 1.0
  - Expected: "single_device", Actual: "isp_outage" → ⚠ 0.5
  - Expected: None, Actual: "isp_outage" → ✗ 0.0

**Valid exit reasons:**
- `None` — No exit, conversation continues
- `"isp_outage"` — ISP issue detected
- `"single_device"` — Only one device affected
- `"out_of_scope"` — Question outside WiFi troubleshooting
- `"escalation"` — User too vague, escalate to support

### 3. inconclusive_count_tracking
Checks if agent correctly tracks unclear exchanges.

```python
Score: 1.0 if match, 0.0 if mismatch
```

**What it measures:**
- Did agent count vague user responses correctly?
- Used to trigger escalation at `inconclusive_count >= 3`
- Examples:
  - Expected: 1, Actual: 1 → ✓ 1.0
  - Expected: 3, Actual: 2 → ✗ 0.0

### 4. response_consistency
Validates conversation coherence.

```python
Score: 1.0 (coherent), 0.5 (issues)
```

**What it measures:**
- Do messages alternate user ↔ assistant?
- Is the last message from assistant?
- Examples:
  - [User, Assistant, User, Assistant] → ✓ 1.0
  - [User, User, Assistant] → ⚠ 0.5
  - [Assistant, User] (odd ending) → ⚠ 0.5

## Viewing Results in LangSmith

### Navigate to Dataset
1. Go to https://smith.langchain.com
2. Click **Datasets** in left sidebar
3. Find **wifi_troubleshooting_golden_v1**
4. Click it

### View Experiments
1. Click **Experiments** tab
2. Look for experiments named:
   - `Jainers_Interview_v1_golden_scenarios-*`
3. Click any experiment to see detailed results

### Understanding the Results Table

| Column | What It Shows |
|--------|---------------|
| **scenario_id** | e.g., scenario_001 |
| **chat_history** | Full conversation (inputs) |
| **reboot_appropriate (expected)** | Ground truth from golden scenario |
| **reboot_appropriate (actual)** | Agent's prediction |
| **qualification_correctness** | Evaluator score (1.0 or 0.0) |
| **exit_reason_validity** | Evaluator score (1.0, 0.5, or 0.0) |
| **inconclusive_count_tracking** | Evaluator score (1.0 or 0.0) |
| **response_consistency** | Evaluator score (1.0 or 0.5) |

### Debugging a Failed Scenario

If a scenario has low scores:

1. **Click the scenario row** → See full trace
2. **Expand each node** to see:
   - Router decision
   - Qualification logic
   - RAG retrieval
   - Agent responses
   - State transitions
3. **Identify where it fails:**
   - Wrong node executed?
   - Incorrect state field?
   - LLM response unexpected?
4. **Fix the agent code** in `agents/v1/nodes.py` or prompts
5. **Re-run:** `python3 agents/v1/eval/run_eval_direct.py`

Results will be added as a **new experiment** (not overwriting old ones).

## Architecture Overview

### Data Flow
```
golden_scenarios.jsonl
    ↓ (loaded into LangSmith)
Dataset: wifi_troubleshooting_golden_v1
    ↓ (for each of 10 scenarios)
Agent Execution
    ├─ Convert scenario chat_history to LangGraph state
    ├─ Run compiled V1 graph
    └─ Return: messages, reboot_appropriate, exit_reason, inconclusive_count
    ↓
Evaluator Scoring
    ├─ qualification_correctness
    ├─ exit_reason_validity
    ├─ inconclusive_count_tracking
    └─ response_consistency
    ↓
Store Results in LangSmith
    └─ Experiment: Jainers_Interview_v1_golden_scenarios-{timestamp}
```

### Why Datasets Appear in "All Applications"

LangSmith has an architectural distinction:
- **Datasets** = Workspace-scoped resources (appear everywhere)
- **Experiments** = Project-scoped (linked through traces)
- **Traces** = Project-scoped (appear only in your Jainers_Interview project)

This is by design—datasets are meant to be reusable across projects. Your evaluation results are in the right project, but the dataset itself is at the workspace level.

## Troubleshooting

### Error: LANGSMITH_API_KEY not set
```
ERROR: LANGSMITH_API_KEY not set
```

**Fix:**
```bash
# Add to .env
echo "LANGSMITH_API_KEY=lsv2_..." >> .env

# Or export
export LANGSMITH_API_KEY=lsv2_...
python3 agents/v1/eval/run_eval_direct.py
```

### Error: Chroma database not found
```
FileNotFoundError: chroma_db/v1/ not found
```

**Fix:** Initialize the vector store once:
```bash
python shared/rag/ingest_v1.py
```

### Error: Module import fails
```
ModuleNotFoundError: No module named 'agents'
```

**Cause:** Python path not set correctly

**Fix:** Always run from project root:
```bash
cd /Users/jainer/Documents/routeThis
python3 agents/v1/eval/run_eval_direct.py
```

### Evaluation runs but results don't appear in LangSmith

1. Wait 30 seconds and refresh
2. Make sure you're in the right project: **Jainers_Interview**
3. Check you're looking at **Experiments** (not just Datasets)
4. Verify **LANGSMITH_API_KEY** is correct (copy-paste from https://smith.langchain.com)

### Want to delete and recreate the dataset

```bash
# In LangSmith UI:
# 1. Go to Datasets
# 2. Find wifi_troubleshooting_golden_v1 → Delete
# 3. Re-run: python3 agents/v1/eval/run_eval_direct.py
```

## Next Steps

1. **Run baseline:** `python3 agents/v1/eval/run_eval_direct.py`
2. **View results:** LangSmith UI → Datasets → Experiments
3. **Fix failures:** Modify agent code for failing scenarios
4. **Re-run:** Same command (creates new experiment)
5. **Compare:** Side-by-side view in LangSmith UI

## References

- **LangSmith Docs:** https://docs.langchain.com/langsmith
- **LangGraph Docs:** https://langgraph.js.org/
- **Evaluation Concepts:** https://docs.langchain.com/langsmith/evaluation-concepts
- **Agent Code:** `agents/v1/graph.py`, `agents/v1/nodes.py`
- **Shared State:** `shared/state/state_v1.py`
- **Prompts:** `shared/prompts/`
