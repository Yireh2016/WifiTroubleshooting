# V1 Feature Additions Implementation Plan

**Date:** 2026-04-01  
**Status:** Ready for Execution  
**Branch:** evals_v1

## Overview

Adding four major feature sets to V1 agent to showcase production-readiness:
1. **Evaluation Pipeline** — LLM-as-judge scoring against golden dataset
2. **Guardrails** — Scope enforcement, hallucination prevention, prompt injection defense
3. **Structured Logging** — JSON logs with request IDs, latencies, payloads
4. **Human Escalation** — Graceful handoff after 3 inconclusive exchanges

## Requirements Summary

### Evaluation Pipeline
- **Scope:** 2 critical metrics (qualification accuracy, conversation clarity)
- **Dataset:** 10 synthetic test scenarios
- **Goal:** Showcase evaluation capability (not exhaustive coverage)

### Guardrails
- Graceful exit for out-of-scope queries
- Post-filter LLM outputs against RAG context for hallucination prevention
- Semantic prompt injection checking

### Structured Logging
- File-based JSON (git-ignored)
- Feature flag in `.env`
- Per-conversation: request ID, node execution trace, LLM payloads, latencies

### Human Escalation
- Trigger threshold: 3 inconclusive exchanges
- Output: Log file + UI notification
- Graceful handoff behavior

## Key Constraints

- V1 must run exactly as submitted (no breaking changes to existing behavior)
- All code in `agents/v1/` or `shared/` only
- No cross-version imports between V1, V2, V3
- Existing state schema (`shared/state/state_v1.py`) unchanged (extend via new fields)
- Existing RAG pipeline unchanged
- All existing tests must pass: `test_graph.py`, `test_app_manual.py`, `verify_retrieval.py`

## Phased Implementation

### Phase 1: Setup & Infrastructure
**Objective:** Create directory structure, add feature flags, prepare base utilities

**Tasks:**
- [ ] Update `.env.example` and `.env` with feature flags:
  - `EVAL_ENABLED=true/false`
  - `LOGGING_ENABLED=true/false`
  - `GUARDRAILS_ENABLED=true/false`
  - `ESCALATION_ENABLED=true/false`

- [ ] Create `agents/v1/eval/` directory:
  - `golden_scenarios.py` — 10 synthetic conversation scenarios covering:
    - WiFi qualification flows (reboot appropriate / not)
    - Various exit reasons (single_device, isp_outage, etc.)
    - Edge cases (ambiguous answers, conflicting info)
  - `metrics.py` — Define 2 critical metrics:
    - **Qualification Accuracy:** Did agent correctly identify if reboot is needed?
    - **Conversation Clarity:** Are step-by-step instructions understandable? (subjective, LLM-as-judge)
  - `judge.py` — LLM-as-judge implementation using OpenAI

- [ ] Create `agents/v1/logging/` directory:
  - `structured_logger.py` — JSON logger class with feature flag control
  - `escalation_handler.py` — Tracks inconclusive exchange count, triggers escalation
  - `logs/` directory (add to `.gitignore`)

### Phase 2: Guardrails
**Objective:** Implement safety checks (scope, hallucination, injection)

**Tasks:**
- [ ] Create `agents/v1/guardrails.py`:
  - **Scope Validator:** Detect out-of-scope queries (e.g., "what's 2+2", "make me a sandwich")
    - Use LLM lightweight classification or keyword matching
    - If out-of-scope: set exit_reason = "out_of_scope" and exit gracefully
  - **Hallucination Post-Filter:** After LLM generates response, verify it references only retrieved RAG chunks
    - Extract claims from LLM output
    - Semantic similarity check against cached RAG context
    - Flag/remove unsupported claims
  - **Prompt Injection Detector:** Semantic check for injection patterns in user input
    - Detect instructions to "ignore system prompt" or "pretend you're X"
    - Graceful exit with warning

- [ ] Integrate guardrails into `agents/v1/nodes.py`:
  - Call scope validator at start of conversation
  - Call hallucination filter after LLM response generation
  - Call injection detector on user messages

### Phase 3: Structured Logging
**Objective:** Implement comprehensive JSON logging with feature flag

**Tasks:**
- [ ] Implement `StructuredLogger` class:
  - Logs to `agents/v1/logs/{request_id}.json`
  - Auto-generates request_id at conversation start (UUID)
  - Captures:
    - Node entry/exit with timestamps
    - LLM prompt + response (if LOGGING_ENABLED)
    - Latencies for each node
    - User message, assistant response, state changes
  - Pretty-printed JSON for readability

- [ ] Add logging calls to `agents/v1/nodes.py`:
  - Log each node's input state, output state, duration
  - Log LLM payloads (system prompt, user message, response)

- [ ] Add to `.gitignore`:
  - `agents/v1/logs/`

### Phase 4: Human Escalation
**Objective:** Track inconclusive exchanges, trigger escalation at threshold

**Tasks:**
- [ ] Extend `ConversationState` in `shared/state/state_v1.py`:
  - Add `inconclusive_count: int` (default 0) — tracks unanswered/ambiguous user inputs
  - Add `escalation_triggered: bool` (default False)

- [ ] Implement escalation logic in `agents/v1/nodes.py`:
  - When agent response is "I don't understand" or "can you clarify" → increment counter
  - When counter reaches 3 → set `escalation_triggered = True`, log escalation event
  - Create graceful exit node with escalation message + file path to escalation log

- [ ] Update `agents/v1/app.py` (Streamlit):
  - Display escalation notification in UI when `escalation_triggered == True`
  - Show escalation log file path to user
  - Suggest user contact support via escalation queue

### Phase 5: Evaluation & Testing
**Objective:** Validate all features, ensure existing tests pass

**Tasks:**
- [ ] Run golden scenarios:
  - Create `agents/v1/test_eval.py`
  - Loop through 10 scenarios, collect agent responses
  - Score with LLM-as-judge against 2 metrics
  - Output evaluation report

- [ ] Verify existing tests still pass:
  - `python agents/v1/test_graph.py` → exit 0
  - `python agents/v1/test_app_manual.py` → exit 0
  - `python shared/rag/verify_retrieval.py` → exit 0

- [ ] Verify feature flags work:
  - Toggle each flag on/off, confirm behavior changes
  - Logging creates files only when enabled
  - Guardrails skip checks when disabled

## Success Criteria

- [ ] Evaluation pipeline runs against golden dataset, produces 2 metric scores
- [ ] Guardrails detect out-of-scope, hallucination, injection with graceful exits
- [ ] Structured logging creates readable JSON per conversation
- [ ] Escalation triggers after 3 inconclusive exchanges, shows UI notification
- [ ] All existing tests pass
- [ ] Feature flags control all new behavior
- [ ] No breaking changes to V1's core flow

## File Structure (After Implementation)

```
agents/v1/
├── app.py                    (updated: logging, escalation UI)
├── graph.py                  (updated: lazy load logging)
├── nodes.py                  (updated: guardrails, logging, escalation checks)
├── eval/
│   ├── golden_scenarios.py   (NEW: 10 test cases)
│   ├── metrics.py            (NEW: 2 critical metrics)
│   ├── judge.py              (NEW: LLM-as-judge)
│   └── test_eval.py          (NEW: evaluation runner)
├── logging/
│   ├── structured_logger.py  (NEW: JSON logger)
│   ├── escalation_handler.py (NEW: escalation tracker)
│   └── logs/                 (NEW: git-ignored log dir)
├── guardrails.py             (NEW: validators)
├── logs/                     (NEW: git-ignored)
└── [existing files]

shared/state/
└── state_v1.py               (updated: add inconclusive_count, escalation_triggered)
```

## Dependencies

- No new pip packages needed (use existing openai, langgraph, etc.)
- Feature flags read from `.env` (python-dotenv already in requirements)

## Notes for Execution

1. **State Extension:** Adding fields to ConversationState is backward-compatible (Pydantic defaults)
2. **Graceful Degradation:** If LOGGING_ENABLED=false, logger is no-op; if GUARDRAILS_ENABLED=false, checks are skipped
3. **LLM Cost:** Evaluation phase will call LLM for judge scoring — test with few scenarios first
4. **Testing:** Run `verify_retrieval.py` before eval to ensure RAG is working
