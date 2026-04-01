# V2 WiFi Troubleshooting Agent -- Implementation Plan

## Context

This plan implements the V2 WiFi troubleshooting agent as specified in `agents/v2/spec.md` and informed by `agents/v2/research.md`. V2 extends V1's single-model MVP into a multi-router, multi-mode agent with LLM-driven literacy detection, router model discovery (3-retry gate), conversation mode selection, and manual-aware qualification. V2 is a standalone agent that never modifies V1 code or V1 shared modules. New shared components are added alongside originals in `shared/`.

**Key V2 architectural decisions:**
- Single Chroma collection (`chroma_db/v2/`) with metadata-based multi-model filtering
- Router model discovery gate: welcome asks model, 3 retries with guidance, graceful exit
- LLM-driven literacy detection (self-serve only, dynamic, no static mapping)
- Conversation mode: Streamlit radio at start, then LLM handles adaptation
- Manual-aware qualifier: retrieves manual context before asking questions
- Generic reboot queries (not linksys-specific)
- App reboot method: LLM-driven connectivity gating decision
- No local admin edge case in V2
- No `prompt_config.py` -- LLM handles all adaptation via system prompt
- V2 NEVER modifies V1 code or V1 shared modules

---

## Dependency Graph

```
Phase 1: State Schema
    |
    v
Phase 2: Ingest Pipeline ----+
    |                         |
    v                         v
Phase 3: Prompts         (chroma_db/v2/ ready)
    |                         |
    +----------+--------------+
               |
               v
         Phase 4: Nodes
               |
               v
         Phase 5: Graph
               |
               v
         Phase 6: Streamlit App
               |
               v
         Phase 7: Tests
               |
               v
         Phase 8: Documentation
```

---

## Critical Files Table

| File | Action | Phase | Purpose |
|------|--------|-------|---------|
| `shared/state/state_v2.py` | Create | 1 | Extended Pydantic state with router_model, mode, manual_context |
| `shared/rag/ingest_v2.py` | Create | 2 | CLI-driven multi-model ingest with langdetect |
| `shared/prompts/v2_prompts.py` | Create | 3 | All V2 prompt templates (welcome, qualify, guide, etc.) |
| `agents/v2/nodes.py` | Create | 4 | 9 node functions + 5 routing functions |
| `agents/v2/graph.py` | Create | 5 | 9-node LangGraph state machine |
| `agents/v2/app.py` | Create | 6 | Streamlit UI with mode selector + model welcome |
| `agents/v2/conftest.py` | Create | 7 | Test fixtures for V2 state, mocks |
| `agents/v2/requirements.txt` | Create | 8 | V2 dependencies (superset of V1 + langdetect) |
| `agents/v2/README.md` | Create | 8 | V2-specific documentation |

---

## Phase 1: State Schema

**Goal:** Define the extended Pydantic state schema for V2 that inherits from V1.
**Depends on:** None
**Complexity:** Low

### Files
- Create: `shared/state/state_v2.py`

### Implementation Details

```python
# shared/state/state_v2.py
from typing import Optional, Literal, Annotated
from pydantic import BaseModel, Field
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage
from shared.state.state_v1 import ConversationState as ConversationStateV1


class ConversationState(ConversationStateV1):
    """V2 state: extends V1 with multi-model, mode, and manual-aware fields."""

    # Router model discovery
    router_model: Optional[str] = None           # e.g., "EA6350" (normalized UPPER)
    router_model_attempts: int = 0               # 0-3, gate at 3

    # Manual-aware qualifier caching
    manual_context: Optional[str] = None         # Retrieved at QUALIFY entry, cached

    # Reboot method
    reboot_method: Optional[Literal["physical", "app"]] = None

    # Conversation mode (set once at session start)
    conversation_mode: Literal["self_serve", "agent_assisted"] = "self_serve"

    # Connectivity gating for app reboot
    has_internet_on_other_device: Optional[bool] = None
```

Key design notes:
- Inherits from `ConversationStateV1` (messages, reboot_appropriate, issue_resolved, next_node, last_executed_node, rag_context, exit_reason)
- `router_model_attempts` tracks the 3-retry discovery gate
- `manual_context` caches retrieved manual sections for the qualify node (separate from `rag_context` which caches reboot steps)
- No `detected_literacy_level` field -- LLM handles this implicitly; if logging is desired later, add it then
- `conversation_mode` is a Literal type, defaults to "self_serve"

### Success Criteria
- [ ] `shared/state/state_v2.py` exists and imports cleanly
- [ ] `ConversationState` inherits all V1 fields
- [ ] V2-specific fields: `router_model`, `router_model_attempts`, `manual_context`, `reboot_method`, `conversation_mode`, `has_internet_on_other_device`
- [ ] `shared/state/state_v1.py` is NOT modified
- [ ] `from shared.state.state_v2 import ConversationState` works from repo root

---

### Gate 1 to 2: State Schema Validation

**Verification steps:**
```bash
cd /Users/jainer/Documents/WifiTroubleshooting
python -c "
from shared.state.state_v2 import ConversationState
s = ConversationState()
# V1 fields present
assert hasattr(s, 'messages')
assert hasattr(s, 'reboot_appropriate')
assert hasattr(s, 'issue_resolved')
assert hasattr(s, 'next_node')
assert hasattr(s, 'last_executed_node')
assert hasattr(s, 'rag_context')
assert hasattr(s, 'exit_reason')
# V2 fields present with defaults
assert s.router_model is None
assert s.router_model_attempts == 0
assert s.manual_context is None
assert s.reboot_method is None
assert s.conversation_mode == 'self_serve'
assert s.has_internet_on_other_device is None
print('GATE 1 PASSED: State schema valid')
"

# Verify V1 is untouched
python -c "
from shared.state.state_v1 import ConversationState
s = ConversationState()
assert not hasattr(s, 'router_model'), 'V1 state was modified!'
print('V1 state untouched: PASS')
"
```
**Pass criteria:** Both commands print PASS with no errors.
**Fail action:** Fix the state schema. Ensure inheritance from `ConversationStateV1` works and no fields conflict.

---

## Phase 2: Ingest Pipeline

**Goal:** Create `ingest_v2.py` with CLI args, per-page langdetect, and multi-model support writing to `chroma_db/v2/`.
**Depends on:** Phase 1 (state schema for metadata understanding)
**Complexity:** Medium

### Files
- Create: `shared/rag/ingest_v2.py`

### Implementation Details

```python
# shared/rag/ingest_v2.py
import argparse
import json
import sys
from pathlib import Path
from langdetect import detect
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.documents import Document

load_dotenv()

CANONICAL_TAGS = ["overview", "setup", "features", "troubleshooting", "specifications", "other"]
CHROMA_PATH = Path(__file__).resolve().parents[2] / "chroma_db" / "v2"
SUPPORTED_LANGUAGES = {"en", "fr", "es", "de", "pt", "it"}


def detect_page_language(page_text: str) -> str:
    """Detect language of a PDF page. Returns ISO 639-1 code or 'unknown'."""
    ...

def load_english_pages(pdf_path: str) -> list:
    """Load PDF, detect language per page with langdetect, keep only English."""
    ...

def segment_document_with_llm(full_text: str, model_name: str) -> list[dict]:
    """Use LLM to segment manual into canonical sections. Same pattern as V1."""
    ...

def build_documents(sections: list[dict], model_name: str, brand: str) -> tuple[list[Document], list[str]]:
    """Create Documents with V2 metadata schema (model_name, brand, language, section_tag, chunk_id, source_file)."""
    ...

def is_already_indexed(vectorstore, model_name: str) -> bool:
    """Check if model already exists in collection."""
    ...

def ingest(model_name: str, brand: str, pdf_path: str, chroma_path: str = None):
    """Main ingest: load PDF -> langdetect filter -> LLM segment -> embed -> store."""
    ...

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest router manual into V2 Chroma collection")
    parser.add_argument("--pdf", required=True, help="Path to router manual PDF")
    parser.add_argument("--model", required=True, help="Router model name (e.g., EA6350)")
    parser.add_argument("--brand", required=True, help="Router brand (e.g., Linksys)")
    args = parser.parse_args()
    ingest(model_name=args.model, brand=args.brand, pdf_path=args.pdf)
```

Key differences from `ingest_v1.py`:
- Uses `langdetect` per-page instead of hardcoded page-range filter
- Accepts `--pdf`, `--model`, `--brand` CLI args
- Writes to `chroma_db/v2/` (separate from V1)
- `brand` field in metadata
- `chunk_id` format: `{MODEL}_{lang}_{section_tag}_{counter}`
- Reuses same `segment_document_with_llm` pattern as V1 (same canonical tags)

### Success Criteria
- [ ] `python shared/rag/ingest_v2.py --pdf shared/data/user_guide_EA6350.pdf --model EA6350 --brand Linksys` runs without error
- [ ] `chroma_db/v2/` directory created with data
- [ ] All stored documents have `language: "en"` metadata
- [ ] All stored documents have `model_name: "EA6350"` metadata
- [ ] No Spanish/French content in the collection
- [ ] `shared/rag/ingest_v1.py` is NOT modified
- [ ] Deduplication works (running twice does not duplicate)

---

### Gate 2 to 3: Ingest + Retrieval Validation

**Verification steps:**
```bash
cd /Users/jainer/Documents/WifiTroubleshooting

# Step 1: Run ingest
python shared/rag/ingest_v2.py \
    --pdf shared/data/user_guide_EA6350.pdf \
    --model EA6350 \
    --brand Linksys

# Step 2: Verify retrieval with existing verify script
python shared/rag/verify_retrieval.py --version v2

# Step 3: Verify metadata structure
python -c "
from shared.rag.retriever import build_retriever
vs = build_retriever(chroma_path='chroma_db/v2')
results = vs.get(where={'model_name': 'EA6350'}, limit=5)
print(f'Documents found: {len(results[\"ids\"])}')
for m in results['metadatas']:
    assert m['language'] == 'en', f'Non-English doc: {m}'
    assert m['model_name'] == 'EA6350', f'Wrong model: {m}'
    assert 'brand' in m, f'Missing brand: {m}'
    print(f'  tag={m[\"section_tag\"]}, brand={m.get(\"brand\")}, lang={m[\"language\"]}')
print('GATE 2 PASSED: Ingest metadata valid')
"

# Step 4: Verify V1 ingest is untouched
python -c "
import shared.rag.ingest_v1 as v1
print(f'V1 CHROMA_PATH: {v1.CHROMA_PATH}')
assert 'v1' in str(v1.CHROMA_PATH), 'V1 path changed!'
print('V1 ingest untouched: PASS')
"
```
**Pass criteria:** All 4 steps pass. `verify_retrieval.py --version v2` prints "All verification checks passed for v2." Metadata assertions pass.
**Fail action:** If langdetect misclassifies pages, add a `min_text_length` threshold (skip pages with < 50 chars). If retrieval fails, check collection name matches ("router_manuals"). If V1 path assertion fails, undo accidental V1 modification.

---

## Phase 3: Prompts

**Goal:** Create all V2 prompt templates with placeholders for mode, manual context, and router model.
**Depends on:** Phase 1 (state fields referenced in placeholders)
**Complexity:** Medium

### Files
- Create: `shared/prompts/v2_prompts.py`

### Implementation Details

All prompts follow the V1 pattern from `base_prompts.py`: uppercase constant strings with `{placeholder}` substitution, expecting JSON responses.

```python
# shared/prompts/v2_prompts.py

WELCOME_DISCOVER_MODEL_PROMPT = """You are a WiFi troubleshooting assistant...
- Conversation mode: {conversation_mode}
- Ask the user for their router model
- If mode is self_serve: warm, patient tone
- If mode is agent_assisted: concise, technical tone
- If user doesn't know, provide guidance (sticker on device, manual, admin page)
- Extract model name from user input if possible

Respond with JSON:
{{
    "reply": "your welcome message asking for router model",
    "extracted_model": null | "MODEL_NAME",
    "needs_guidance": true | false
}}"""

DISCOVER_MODEL_RETRY_PROMPT = """...
- Attempt {attempt_number} of 3
- Available models in system: {available_models}
- Previous messages: {messages}
- Guide user to find model (sticker, manual, etc.)
- If user says something that could be a model, try to match

Respond with JSON:
{{
    "reply": "...",
    "extracted_model": null | "MODEL_NAME",
    "needs_guidance": true | false
}}"""

UNSUPPORTED_MODEL_EXIT_PROMPT = """...
- User's router model could not be identified after 3 attempts
- Provide helpful exit: suggest checking manufacturer website, contacting ISP
- Mention they can return once they have their model info

Respond with JSON:
{{
    "reply": "your farewell message"
}}"""

V2_QUALIFY_PROMPT = """You are a Senior WiFi Technician Specialist...
- Conversation mode: {conversation_mode}
- Router model: {router_model}
- Router manual context: {manual_context}

If mode is "self_serve":
  - Analyze user vocabulary and infer literacy dynamically
  - Adapt language complexity (plain for non-technical, technical for technical)
  - Do NOT ask meta-questions about tech level

If mode is "agent_assisted":
  - Use technical language throughout
  - Skip analogies, be concise

Ask ONE question at a time about observable signs.
Reference the manual when relevant to the user's specific router.
Keep the interview to 3-4 questions max, then decide.

Respond with JSON:
{{
    "decision": "ask_more" | "reboot" | "exit",
    "exit_reason": null | "single_device" | "isp_outage" | "already_rebooted" | "cables_fixed",
    "reply": "your message to the user"
}}"""

V2_GUIDE_REBOOT_PROMPT = """You are a Senior WiFi Technician Specialist...
- Conversation mode: {conversation_mode}
- Router model: {router_model}
- Reboot method: {reboot_method}

Use ONLY the following instructions from the manual:
{rag_context}

If mode is "self_serve":
  - Adapt language to user's apparent literacy level
  - One step at a time, ask for observable confirmations
  - Use plain language ("lights", "blinking") for non-technical users

If mode is "agent_assisted":
  - Can batch steps, use technical terms ("WAN LED", "status indicator")
  - Concise instructions

Respond with JSON:
{{
    "reply": "your message to the user",
    "all_steps_done": true | false
}}"""

V2_SELECT_REBOOT_METHOD_PROMPT = """...
- Router model: {router_model}
- Manual context: {manual_context}
- User's issue summary so far: {messages}
- Conversation mode: {conversation_mode}

Decide which reboot method(s) to offer:
- "physical": Always available (power cord disconnect)
- "app": Only if user has internet on another device AND manual mentions app/web reboot

If user has no internet at all -> physical only
If intermittent/partial -> LLM may offer app as faster alternative

Respond with JSON:
{{
    "reply": "your message offering method(s)",
    "selected_method": "physical" | "app",
    "reasoning": "why this method"
}}"""

V2_CHECK_RESOLUTION_PROMPT = """...(same as V1 CHECK_RESOLUTION_PROMPT but with mode awareness)
- Conversation mode: {conversation_mode}
...

Respond with JSON:
{{
    "reply": "your message to the user",
    "resolved": true | false | null
}}"""

V2_GRACEFUL_EXIT_PROMPT = """...
- Exit reason: {exit_reason}
- Router model: {router_model}
- Conversation mode: {conversation_mode}
- Do NOT reference Linksys-specific URLs -- use generic guidance based on router_model

Respond with JSON:
{{
    "reply": "your farewell message"
}}"""

V2_CLOSE_SUCCESS_PROMPT = """...(same as V1 but mode-aware, generic not linksys-specific)
- Conversation mode: {conversation_mode}
- Router model: {router_model}

Respond with JSON:
{{
    "reply": "your closing message"
}}"""

V2_APOLOGIZE_EXIT_PROMPT = """...
- Router model: {router_model}
- Conversation mode: {conversation_mode}
- Suggest contacting router manufacturer support (generic, not Linksys-specific)

Respond with JSON:
{{
    "reply": "your message"
}}"""
```

### Success Criteria
- [ ] `shared/prompts/v2_prompts.py` exists with all 9 prompt constants
- [ ] All prompts use `{conversation_mode}` and `{router_model}` placeholders
- [ ] V2_QUALIFY_PROMPT includes `{manual_context}` placeholder
- [ ] V2_GUIDE_REBOOT_PROMPT includes `{rag_context}` and `{reboot_method}` placeholders
- [ ] All prompts request JSON responses with documented schemas
- [ ] No hardcoded "Linksys" or "EA6350" references (generic for any model)
- [ ] `shared/prompts/base_prompts.py` is NOT modified

---

### Gate 3 to 4: Prompt Template Validation

**Verification steps:**
```bash
cd /Users/jainer/Documents/WifiTroubleshooting

python -c "
from shared.prompts.v2_prompts import (
    WELCOME_DISCOVER_MODEL_PROMPT,
    DISCOVER_MODEL_RETRY_PROMPT,
    UNSUPPORTED_MODEL_EXIT_PROMPT,
    V2_QUALIFY_PROMPT,
    V2_GUIDE_REBOOT_PROMPT,
    V2_SELECT_REBOOT_METHOD_PROMPT,
    V2_CHECK_RESOLUTION_PROMPT,
    V2_GRACEFUL_EXIT_PROMPT,
    V2_CLOSE_SUCCESS_PROMPT,
    V2_APOLOGIZE_EXIT_PROMPT,
)

# Verify placeholders exist in key prompts
assert '{conversation_mode}' in V2_QUALIFY_PROMPT
assert '{router_model}' in V2_QUALIFY_PROMPT
assert '{manual_context}' in V2_QUALIFY_PROMPT
assert '{rag_context}' in V2_GUIDE_REBOOT_PROMPT
assert '{reboot_method}' in V2_GUIDE_REBOOT_PROMPT
assert '{exit_reason}' in V2_GRACEFUL_EXIT_PROMPT
assert '{available_models}' in DISCOVER_MODEL_RETRY_PROMPT
assert '{attempt_number}' in DISCOVER_MODEL_RETRY_PROMPT

# Verify no hardcoded model references
for prompt in [V2_QUALIFY_PROMPT, V2_GUIDE_REBOOT_PROMPT, V2_GRACEFUL_EXIT_PROMPT, V2_APOLOGIZE_EXIT_PROMPT]:
    assert 'linksys.com/support/EA6350' not in prompt.lower(), 'Hardcoded Linksys URL found!'

print('GATE 3 PASSED: All prompts importable with correct placeholders')
"

# Verify V1 prompts untouched
python -c "
from shared.prompts.base_prompts import QUALIFY_PROMPT, GUIDE_REBOOT_PROMPT
assert 'Linksys' in GUIDE_REBOOT_PROMPT or '{rag_context}' in GUIDE_REBOOT_PROMPT
print('V1 prompts untouched: PASS')
"
```
**Pass criteria:** All imports succeed, placeholder assertions pass, no hardcoded model URLs.
**Fail action:** Fix missing placeholders or add missing prompt constants. Ensure `__init__.py` in `shared/prompts/` exists.

---

## Phase 4: Nodes

**Goal:** Implement all V2 node functions and routing functions following V1 patterns.
**Depends on:** Phase 1 (state), Phase 2 (ingest/retriever), Phase 3 (prompts)
**Complexity:** High

### Files
- Create: `agents/v2/nodes.py`

### Implementation Details

Follows V1 node pattern: lazy-loaded LLM/vectorstore, `_call_llm` helper, JSON response parsing. All nodes take `ConversationState` (V2) and return a dict of state updates.

**9 Node Functions:**

```python
# agents/v2/nodes.py
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.graph import END
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from shared.state.state_v2 import ConversationState
from shared.prompts.v2_prompts import (
    WELCOME_DISCOVER_MODEL_PROMPT, DISCOVER_MODEL_RETRY_PROMPT,
    UNSUPPORTED_MODEL_EXIT_PROMPT, V2_QUALIFY_PROMPT,
    V2_GUIDE_REBOOT_PROMPT, V2_SELECT_REBOOT_METHOD_PROMPT,
    V2_CHECK_RESOLUTION_PROMPT, V2_GRACEFUL_EXIT_PROMPT,
    V2_CLOSE_SUCCESS_PROMPT, V2_APOLOGIZE_EXIT_PROMPT,
)
from shared.rag.retriever import build_retriever, retrieve

LLM = None
VECTORSTORE = None

def _get_llm(): ...       # Same lazy pattern as V1
def _get_vectorstore():   # Points to chroma_db/v2/
    global VECTORSTORE
    if VECTORSTORE is None:
        VECTORSTORE = build_retriever(chroma_path=str(Path(__file__).resolve().parents[2] / "chroma_db" / "v2"))
    return VECTORSTORE

def _call_llm(messages: list, prompt: str) -> dict: ...  # Same as V1

def _list_available_models() -> list[str]:
    """Return unique model names from Chroma collection."""
    vs = _get_vectorstore()
    all_docs = vs.get(limit=10000)
    models = set(m.get("model_name") for m in all_docs.get("metadatas", []) if m.get("model_name"))
    return sorted(list(models))

def _check_model_exists(model_name: str) -> bool:
    """Check if model has documents in collection."""
    vs = _get_vectorstore()
    results = vs.get(where={"model_name": model_name.upper()}, limit=1)
    return len(results.get("ids", [])) > 0

# --- Node 1: Welcome / Discover Model ---
def welcome(state: ConversationState) -> dict:
    """First interaction: ask user for router model. Uses WELCOME_DISCOVER_MODEL_PROMPT."""
    prompt = WELCOME_DISCOVER_MODEL_PROMPT.format(
        conversation_mode=state.conversation_mode,
    )
    result = _call_llm(state.messages, prompt)
    updates = {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "welcome"}

    extracted = result.get("extracted_model")
    if extracted:
        normalized = extracted.strip().upper()
        if _check_model_exists(normalized):
            updates["router_model"] = normalized
        else:
            updates["router_model_attempts"] = state.router_model_attempts + 1
    else:
        updates["router_model_attempts"] = state.router_model_attempts + 1

    return updates

# --- Node 2: Discover Model Retry ---
def discover_model(state: ConversationState) -> dict:
    """Retry model discovery. Max 3 attempts."""
    available = _list_available_models()
    prompt = DISCOVER_MODEL_RETRY_PROMPT.format(
        attempt_number=state.router_model_attempts,
        available_models=", ".join(available),
        messages="(see conversation history)",
        conversation_mode=state.conversation_mode,
    )
    result = _call_llm(state.messages, prompt)
    updates = {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "discover_model"}

    extracted = result.get("extracted_model")
    if extracted:
        normalized = extracted.strip().upper()
        if _check_model_exists(normalized):
            updates["router_model"] = normalized
            return updates

    updates["router_model_attempts"] = state.router_model_attempts + 1
    return updates

# --- Node 3: Unsupported Model Exit ---
def unsupported_model_exit(state: ConversationState) -> dict:
    """Exit after 3 failed model discovery attempts."""
    result = _call_llm(state.messages, UNSUPPORTED_MODEL_EXIT_PROMPT)
    return {
        "messages": [AIMessage(content=result["reply"])],
        "exit_reason": "unsupported_model",
        "last_executed_node": "unsupported_model_exit",
    }

# --- Node 4: Qualify (Manual-Aware) ---
def qualify(state: ConversationState) -> dict:
    """Qualify issue with manual context. Retrieves manual on first call, caches."""
    manual_ctx = state.manual_context
    if manual_ctx is None:
        vs = _get_vectorstore()
        results = retrieve(vs, query="router features capabilities overview troubleshooting",
                          model_name=state.router_model, section_tag="troubleshooting", k=5)
        manual_ctx = "\n\n".join([r.page_content for r in results]) if results else ""

    prompt = V2_QUALIFY_PROMPT.format(
        conversation_mode=state.conversation_mode,
        router_model=state.router_model,
        manual_context=manual_ctx,
    )
    result = _call_llm(state.messages, prompt)
    updates = {
        "messages": [AIMessage(content=result["reply"])],
        "manual_context": manual_ctx,
        "last_executed_node": "qualify",
    }

    if result["decision"] == "reboot":
        updates["reboot_appropriate"] = True
    elif result["decision"] == "exit":
        updates["reboot_appropriate"] = False
        updates["exit_reason"] = result.get("exit_reason", "unknown")

    return updates

# --- Node 5: Select Reboot Method ---
def select_reboot_method(state: ConversationState) -> dict:
    """LLM decides physical vs app reboot based on connectivity context."""
    prompt = V2_SELECT_REBOOT_METHOD_PROMPT.format(
        router_model=state.router_model,
        manual_context=state.manual_context or "",
        messages="(see conversation history)",
        conversation_mode=state.conversation_mode,
    )
    result = _call_llm(state.messages, prompt)
    return {
        "messages": [AIMessage(content=result["reply"])],
        "reboot_method": result.get("selected_method", "physical"),
        "last_executed_node": "select_reboot_method",
    }

# --- Node 6: Retrieval ---
def retrieval(state: ConversationState) -> dict:
    """Retrieve reboot steps for the user's specific router model."""
    vs = _get_vectorstore()
    method = state.reboot_method or "physical"
    query = "reboot steps restart power cord" if method == "physical" else "app reboot web portal restart"
    results = retrieve(vs, query=query, model_name=state.router_model,
                      section_tag="troubleshooting", k=10)
    rag_context = results[0].page_content if results else None

    if rag_context is None:
        return {
            "messages": [AIMessage(content="I'm having trouble accessing the reboot instructions for your router. Please refer to your router's manual for reboot steps.")],
            "last_executed_node": "apologize_and_exit",
        }
    return {"rag_context": rag_context, "next_node": "guide_reboot"}

# --- Node 7: Guide Reboot ---
def guide_reboot(state: ConversationState) -> dict:
    """Walk user through reboot steps from RAG context."""
    prompt = V2_GUIDE_REBOOT_PROMPT.format(
        conversation_mode=state.conversation_mode,
        router_model=state.router_model,
        reboot_method=state.reboot_method or "physical",
        rag_context=state.rag_context,
    )
    result = _call_llm(state.messages, prompt)
    updates = {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "guide_reboot"}
    if result.get("all_steps_done"):
        updates["next_node"] = "check_resolution"
    return updates

# --- Node 8: Check Resolution ---
def check_resolution(state: ConversationState) -> dict:
    """Ask if issue resolved after reboot."""
    prompt = V2_CHECK_RESOLUTION_PROMPT.format(
        conversation_mode=state.conversation_mode,
    )
    result = _call_llm(state.messages, prompt)
    updates = {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "check_resolution"}
    if result.get("resolved") is True:
        updates["issue_resolved"] = True
    elif result.get("resolved") is False:
        updates["issue_resolved"] = False
    return updates

# --- Node 9a: Close Success ---
def close_success(state: ConversationState) -> dict:
    prompt = V2_CLOSE_SUCCESS_PROMPT.format(
        conversation_mode=state.conversation_mode,
        router_model=state.router_model,
    )
    result = _call_llm(state.messages, prompt)
    return {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "close_success"}

# --- Node 9b: Apologize and Exit ---
def apologize_and_exit(state: ConversationState) -> dict:
    prompt = V2_APOLOGIZE_EXIT_PROMPT.format(
        router_model=state.router_model,
        conversation_mode=state.conversation_mode,
    )
    result = _call_llm(state.messages, prompt)
    return {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "apologize_and_exit"}

# --- Node 9c: Graceful Exit ---
def graceful_exit(state: ConversationState) -> dict:
    prompt = V2_GRACEFUL_EXIT_PROMPT.format(
        exit_reason=state.exit_reason or "unknown",
        router_model=state.router_model or "unknown",
        conversation_mode=state.conversation_mode,
    )
    result = _call_llm(state.messages, prompt)
    return {"messages": [AIMessage(content=result["reply"])], "last_executed_node": "graceful_exit"}
```

**5 Routing Functions:**

```python
def route_entry(state: ConversationState) -> str:
    """Main router: dispatch based on current state."""
    if state.router_model is None:
        if state.router_model_attempts >= 3:
            return "unsupported_model_exit"
        if state.router_model_attempts == 0:
            return "welcome"
        return "discover_model"
    if state.reboot_appropriate is None:
        return "qualify"
    if state.reboot_appropriate and state.reboot_method is None:
        return "select_reboot_method"
    if state.reboot_appropriate and state.next_node == "not_started":
        return "retrieval"
    if state.next_node == "guide_reboot":
        return "guide_reboot"
    if state.next_node == "check_resolution" and state.issue_resolved is None:
        return "check_resolution"
    return "welcome"  # fallback

def route_after_welcome(state: ConversationState) -> str:
    if state.router_model is not None:
        return "qualify"
    if state.router_model_attempts >= 3:
        return "unsupported_model_exit"
    return END  # wait for user input

def route_after_discover(state: ConversationState) -> str:
    if state.router_model is not None:
        return "qualify"
    if state.router_model_attempts >= 3:
        return "unsupported_model_exit"
    return END  # wait for user to retry

def route_after_qualify(state: ConversationState) -> str:
    if state.reboot_appropriate is None:
        return END
    if state.reboot_appropriate:
        return "select_reboot_method"
    return "graceful_exit"

def route_after_select_method(state: ConversationState) -> str:
    return "retrieval"

def route_after_guide(state: ConversationState) -> str:
    if state.next_node == "check_resolution":
        return "check_resolution"
    return END

def route_after_check(state: ConversationState) -> str:
    if state.issue_resolved is None:
        return END
    if state.issue_resolved:
        return "close_success"
    return "apologize_and_exit"
```

### Success Criteria
- [ ] All 9 node functions + routing functions importable
- [ ] `welcome` extracts model and validates against collection
- [ ] `discover_model` increments attempts and lists available models
- [ ] `qualify` retrieves manual context and caches in state
- [ ] `select_reboot_method` uses LLM to decide physical vs app
- [ ] `retrieval` uses generic query with model filter
- [ ] `guide_reboot` includes mode and method in prompt
- [ ] All routing functions handle state transitions correctly
- [ ] Vectorstore points to `chroma_db/v2/`
- [ ] No hardcoded "Linksys" or "EA6350" in node logic

---

### Gate 4 to 5: Node Unit Tests

**Verification steps:**
```bash
cd /Users/jainer/Documents/WifiTroubleshooting

python -c "
from agents.v2.nodes import (
    welcome, discover_model, unsupported_model_exit,
    qualify, select_reboot_method, retrieval,
    guide_reboot, check_resolution,
    close_success, apologize_and_exit, graceful_exit,
    route_entry, route_after_welcome, route_after_discover,
    route_after_qualify, route_after_select_method,
    route_after_guide, route_after_check,
)
print('GATE 4 PASSED: All node and routing functions importable')
"

# Verify routing logic (no LLM needed)
python -c "
from shared.state.state_v2 import ConversationState
from agents.v2.nodes import route_entry

# No model yet -> welcome
s = ConversationState()
assert route_entry(s) == 'welcome', f'Expected welcome, got {route_entry(s)}'

# Model attempts >= 3 -> unsupported_model_exit
s2 = ConversationState(router_model_attempts=3)
assert route_entry(s2) == 'unsupported_model_exit'

# Model set, no qualify decision -> qualify
s3 = ConversationState(router_model='EA6350')
assert route_entry(s3) == 'qualify'

# Reboot appropriate, no method -> select_reboot_method
s4 = ConversationState(router_model='EA6350', reboot_appropriate=True)
assert route_entry(s4) == 'select_reboot_method'

print('GATE 4 PASSED: Routing logic correct')
"
```
**Pass criteria:** All imports succeed. Routing logic returns correct node names for each state.
**Fail action:** Fix import errors (check `sys.path` setup). Fix routing logic to match the 9-node state machine.

---

## Phase 5: Graph

**Goal:** Wire the 9-node state machine with conditional edges following V1 graph pattern.
**Depends on:** Phase 4 (nodes)
**Complexity:** Medium

### Files
- Create: `agents/v2/graph.py`

### Implementation Details

```python
# agents/v2/graph.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from shared.state.state_v2 import ConversationState
from agents.v2.nodes import (
    welcome, discover_model, unsupported_model_exit,
    qualify, select_reboot_method, retrieval,
    guide_reboot, check_resolution,
    close_success, apologize_and_exit, graceful_exit,
    route_entry, route_after_welcome, route_after_discover,
    route_after_qualify, route_after_select_method,
    route_after_guide, route_after_check,
)


def build_graph():
    graph = StateGraph(ConversationState)

    # Router node (no-op dispatcher)
    graph.add_node("router", lambda state: {})

    # 9 functional nodes
    graph.add_node("welcome", welcome)
    graph.add_node("discover_model", discover_model)
    graph.add_node("unsupported_model_exit", unsupported_model_exit)
    graph.add_node("qualify", qualify)
    graph.add_node("select_reboot_method", select_reboot_method)
    graph.add_node("retrieval", retrieval)
    graph.add_node("guide_reboot", guide_reboot)
    graph.add_node("check_resolution", check_resolution)
    graph.add_node("close_success", close_success)
    graph.add_node("apologize_and_exit", apologize_and_exit)
    graph.add_node("graceful_exit", graceful_exit)

    # Entry: always go through router
    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", route_entry, {
        "welcome": "welcome",
        "discover_model": "discover_model",
        "unsupported_model_exit": "unsupported_model_exit",
        "qualify": "qualify",
        "select_reboot_method": "select_reboot_method",
        "retrieval": "retrieval",
        "guide_reboot": "guide_reboot",
        "check_resolution": "check_resolution",
    })

    # After welcome
    graph.add_conditional_edges("welcome", route_after_welcome, {
        "qualify": "qualify",
        "unsupported_model_exit": "unsupported_model_exit",
        END: END,
    })

    # After discover_model
    graph.add_conditional_edges("discover_model", route_after_discover, {
        "qualify": "qualify",
        "unsupported_model_exit": "unsupported_model_exit",
        END: END,
    })

    # After qualify
    graph.add_conditional_edges("qualify", route_after_qualify, {
        END: END,
        "select_reboot_method": "select_reboot_method",
        "graceful_exit": "graceful_exit",
    })

    # After select_reboot_method -> always retrieval
    graph.add_edge("select_reboot_method", "retrieval")

    # After retrieval -> guide_reboot
    graph.add_edge("retrieval", "guide_reboot")

    # After guide_reboot
    graph.add_conditional_edges("guide_reboot", route_after_guide, {
        END: END,
        "check_resolution": "check_resolution",
    })

    # After check_resolution
    graph.add_conditional_edges("check_resolution", route_after_check, {
        END: END,
        "close_success": "close_success",
        "apologize_and_exit": "apologize_and_exit",
    })

    # Terminal nodes
    graph.add_edge("unsupported_model_exit", END)
    graph.add_edge("graceful_exit", END)
    graph.add_edge("close_success", END)
    graph.add_edge("apologize_and_exit", END)

    return graph


def compile_graph():
    graph = build_graph()
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
```

**State machine diagram:**
```
[START]
   |
[ROUTER] ---- route_entry dispatches based on state
   |
   +---> [WELCOME] ---> model found? ---> [QUALIFY]
   |        |                              |
   |        +---> retry? ---> END (wait)   +---> reboot? ---> [SELECT_METHOD] -> [RETRIEVAL] -> [GUIDE_REBOOT]
   |        |                              |                                                      |
   |        +---> 3 fails ---> [UNSUPPORTED_MODEL_EXIT]                                          +---> done? ---> [CHECK_RESOLUTION]
   |                           |                                                                 |                  |
   +---> [DISCOVER_MODEL] ----+      +---> not appropriate ---> [GRACEFUL_EXIT]                  +---> END (wait)  +---> resolved? ---> [CLOSE_SUCCESS]
                                     |                                                                             |
                                     +---> ask_more ---> END (wait for user)                                       +---> not resolved ---> [APOLOGIZE_AND_EXIT]
```

### Success Criteria
- [ ] `build_graph()` returns a valid `StateGraph`
- [ ] `compile_graph()` returns a compiled graph with checkpointer
- [ ] 11 nodes registered (router + 10 functional)
- [ ] All conditional edges map to valid node names
- [ ] No edges reference nodes that don't exist
- [ ] Graph compiles without errors

---

### Gate 5 to 6: Graph Compilation

**Verification steps:**
```bash
cd /Users/jainer/Documents/WifiTroubleshooting

python -c "
from agents.v2.graph import build_graph, compile_graph

# Test build
g = build_graph()
print(f'Nodes: {list(g.nodes.keys())}')
assert len(g.nodes) >= 11, f'Expected 11+ nodes, got {len(g.nodes)}'

# Test compile (will fail if edges are invalid)
compiled = compile_graph()
print(f'Compiled graph type: {type(compiled)}')
print('GATE 5 PASSED: Graph compiles successfully')
"
```
**Pass criteria:** Graph compiles with no errors. 11+ nodes present.
**Fail action:** If compilation fails, check that all routing functions return node names that exist in the graph. Verify all `add_conditional_edges` mappings include all possible return values.

---

## Phase 6: Streamlit App

**Goal:** Build the V2 Streamlit UI with mode selector radio button and model welcome flow.
**Depends on:** Phase 5 (graph)
**Complexity:** Medium

### Files
- Create: `agents/v2/app.py`

### Implementation Details

```python
# agents/v2/app.py
import sys, uuid, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import streamlit as st
from langchain_core.messages import HumanMessage
from agents.v2.graph import compile_graph

st.set_page_config(page_title="WiFi Troubleshooting Assistant V2", page_icon="📶", layout="centered")
st.title("WiFi Troubleshooting Assistant V2")

TERMINAL_NODES = ("graceful_exit", "close_success", "apologize_and_exit", "unsupported_model_exit")

# --- Mode Selection (before graph starts) ---
if "conversation_mode" not in st.session_state:
    st.subheader("How would you like to troubleshoot?")
    mode = st.radio(
        "Select conversation mode:",
        options=["self_serve", "agent_assisted"],
        format_func=lambda x: "I'll troubleshoot on my own" if x == "self_serve" else "An agent will help me",
        horizontal=True,
    )
    if st.button("Start"):
        st.session_state.conversation_mode = mode
        st.rerun()
    st.stop()

# --- Session State Init ---
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_ended" not in st.session_state:
    st.session_state.conversation_ended = False
if "graph" not in st.session_state:
    st.session_state.graph = compile_graph()

graph = st.session_state.graph
config = {
    "configurable": {"thread_id": st.session_state.thread_id},
    "run_name": "wifi-troubleshoot-v2",
}

# --- Initial welcome invocation (no user input needed) ---
if not st.session_state.messages:
    # Invoke graph with mode but no user message to trigger welcome node
    graph.invoke(
        {"messages": [], "conversation_mode": st.session_state.conversation_mode},
        config=config,
    )
    state = graph.get_state(config)
    state_messages = state.values.get("messages", [])
    for msg in reversed(state_messages):
        if hasattr(msg, 'type') and msg.type == "ai":
            welcome_text = msg.content
            st.session_state.messages.append({"role": "assistant", "content": welcome_text})
            break

# --- Render chat history ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Chat input loop (same pattern as V1) ---
if not st.session_state.conversation_ended:
    if prompt := st.chat_input("Type your message..."):
        # (same invoke/state-check/terminal-check pattern as V1 app.py)
        ...
else:
    st.info("Conversation ended. Refresh to start a new session.")
    if st.button("Start New Conversation"):
        st.session_state.clear()
        st.rerun()
```

Key differences from V1 `app.py`:
- Mode selector radio button before graph starts (blocks with `st.stop()`)
- Mode stored in `st.session_state.conversation_mode` and passed to graph
- Welcome invocation happens automatically after mode selection (no user input needed)
- `TERMINAL_NODES` includes `unsupported_model_exit`
- Chat input placeholder is generic ("Type your message...")

### Success Criteria
- [ ] Mode selector radio appears before conversation starts
- [ ] Mode is locked for the session after selection
- [ ] Welcome message appears automatically after mode selection (asks for router model)
- [ ] Chat loop follows V1 pattern (invoke, get_state, extract AI message, check terminal)
- [ ] Terminal nodes include `unsupported_model_exit`
- [ ] "Start New Conversation" button clears all session state
- [ ] `agents/v1/app.py` is NOT modified

---

### Gate 6 to 7: App Smoke Test

**Verification steps:**
```bash
cd /Users/jainer/Documents/WifiTroubleshooting

# Verify app imports without error
python -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
# Just test imports, not Streamlit runtime
from agents.v2.graph import compile_graph
from shared.state.state_v2 import ConversationState
print('GATE 6 PASSED: App dependencies importable')
"

# Manual smoke test (requires running app)
echo "Manual verification required:"
echo "  1. streamlit run agents/v2/app.py"
echo "  2. Verify mode selector appears"
echo "  3. Select 'self_serve', click Start"
echo "  4. Verify welcome message asks for router model"
echo "  5. Type 'Linksys EA6350' - verify model is recognized"
echo "  6. Answer qualify questions - verify manual-aware questions"
echo "  7. Complete reboot flow - verify resolution check"
```
**Pass criteria:** App launches. Mode selector works. Welcome asks for model. Full conversation flow completes without crash.
**Fail action:** If welcome doesn't trigger, check that graph handles empty `messages` list in initial invocation. If mode isn't passed, verify `conversation_mode` is included in `graph.invoke()` input dict.

---

## Phase 7: Tests

**Goal:** Create comprehensive test suite covering nodes, graph, and end-to-end scenarios.
**Depends on:** Phase 4 (nodes), Phase 5 (graph)
**Complexity:** High

### Files
- Create: `agents/v2/conftest.py`
- Create: `agents/v2/test_nodes.py`
- Create: `agents/v2/test_graph.py`
- Create: `agents/v2/test_scenarios.py`

### Implementation Details

**conftest.py** -- extends V1 pattern with V2 state and mocks:

```python
# agents/v2/conftest.py
import sys, pytest
from pathlib import Path
from unittest.mock import Mock, patch
from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.state.state_v2 import ConversationState

@pytest.fixture
def mock_llm(): ...  # Same as V1

@pytest.fixture
def mock_vectorstore():
    """Mock vectorstore with V2 metadata (includes brand, model filtering)."""
    vs = Mock()
    def mock_similarity_search(query, k=1, filter=None):
        doc = Mock()
        doc.page_content = "Step 1: Disconnect power cable..."
        doc.metadata = {"model_name": "EA6350", "language": "en",
                       "section_tag": "troubleshooting", "brand": "Linksys"}
        return [doc]
    vs.similarity_search = mock_similarity_search

    def mock_get(where=None, limit=None):
        if where and where.get("model_name") == "EA6350":
            return {"ids": ["EA6350_en_troubleshooting"], "metadatas": [{"model_name": "EA6350", "brand": "Linksys"}]}
        return {"ids": [], "metadatas": []}
    vs.get = mock_get
    return vs

@pytest.fixture
def sample_v2_state():
    return ConversationState(
        messages=[HumanMessage(content="My WiFi is down")],
        conversation_mode="self_serve",
    )

@pytest.fixture
def sample_v2_state_with_model():
    return ConversationState(
        messages=[HumanMessage(content="My WiFi is down")],
        conversation_mode="self_serve",
        router_model="EA6350",
    )

@pytest.fixture
def patch_v2_llm(mock_llm):
    with patch("agents.v2.nodes._get_llm", return_value=mock_llm):
        yield mock_llm

@pytest.fixture
def patch_v2_vectorstore(mock_vectorstore):
    with patch("agents.v2.nodes._get_vectorstore", return_value=mock_vectorstore):
        yield mock_vectorstore

@pytest.fixture
def json_response_factory():
    """Factory for V2 node JSON responses."""
    def create_response(node_type, **kwargs):
        responses = {
            "welcome": {"reply": "What router model do you have?", "extracted_model": None, "needs_guidance": False, **kwargs},
            "discover_model": {"reply": "Could you check the sticker?", "extracted_model": None, "needs_guidance": True, **kwargs},
            "qualify": {"decision": "reboot", "exit_reason": None, "reply": "Let's reboot.", **kwargs},
            "select_method": {"reply": "Let's do a physical reboot.", "selected_method": "physical", "reasoning": "No internet", **kwargs},
            "guide_reboot": {"reply": "Disconnect the power cable.", "all_steps_done": False, **kwargs},
            "check_resolution": {"reply": "Is it working?", "resolved": None, **kwargs},
            ...
        }
        return responses.get(node_type, responses["welcome"])
    return create_response
```

**test_nodes.py** -- unit tests for each node:

```python
# Key tests:
def test_welcome_extracts_model(patch_v2_llm, patch_v2_vectorstore, sample_v2_state, mock_llm):
    """Welcome node extracts model from LLM response and validates against collection."""
    ...

def test_discover_model_increments_attempts(patch_v2_llm, patch_v2_vectorstore):
    """Discover model increments router_model_attempts on failure."""
    ...

def test_discover_model_succeeds_on_known_model(patch_v2_llm, patch_v2_vectorstore):
    """Discover model sets router_model when model exists in collection."""
    ...

def test_qualify_retrieves_manual_context(patch_v2_llm, patch_v2_vectorstore, sample_v2_state_with_model):
    """Qualify node retrieves and caches manual context."""
    ...

def test_qualify_uses_cached_manual_context(patch_v2_llm, patch_v2_vectorstore):
    """Second qualify call uses cached manual_context, doesn't re-retrieve."""
    ...

def test_select_reboot_method_returns_method(patch_v2_llm, patch_v2_vectorstore):
    """Select method node returns physical or app."""
    ...

def test_retrieval_uses_model_filter(patch_v2_llm, patch_v2_vectorstore):
    """Retrieval node filters by state.router_model."""
    ...

def test_guide_reboot_includes_mode(patch_v2_llm, patch_v2_vectorstore):
    """Guide reboot prompt includes conversation_mode."""
    ...
```

**test_graph.py** -- graph structure and routing tests:

```python
def test_graph_has_all_nodes():
    """Graph contains all 11 nodes (router + 10 functional)."""
    ...

def test_graph_compiles():
    """Graph compiles with checkpointer."""
    ...

def test_route_entry_dispatches_correctly():
    """route_entry returns correct node for each state combination."""
    ...

def test_model_discovery_gate_exits_after_3():
    """After 3 failed attempts, route_entry returns unsupported_model_exit."""
    ...
```

**test_scenarios.py** -- end-to-end conversation flows:

```python
def test_happy_path_self_serve(patch_v2_llm, patch_v2_vectorstore):
    """Full flow: mode -> model -> qualify -> method -> reboot -> resolved."""
    ...

def test_happy_path_agent_assisted(patch_v2_llm, patch_v2_vectorstore):
    """Full flow in agent-assisted mode."""
    ...

def test_unknown_model_exits_after_3_retries(patch_v2_llm, patch_v2_vectorstore):
    """User can't provide model -> exits after 3 retries."""
    ...

def test_qualify_exits_gracefully(patch_v2_llm, patch_v2_vectorstore):
    """Single-device issue -> graceful exit."""
    ...

def test_reboot_not_resolved(patch_v2_llm, patch_v2_vectorstore):
    """Reboot doesn't fix -> apologize and exit."""
    ...
```

### Success Criteria
- [ ] `pytest agents/v2/ -v` runs with no import errors
- [ ] All unit tests pass with mocked LLM and vectorstore
- [ ] Model discovery 3-retry gate tested explicitly
- [ ] Routing logic tested for all state combinations
- [ ] At least 5 end-to-end scenarios covered
- [ ] No tests require actual OpenAI API calls

---

### Gate 7 to 8: Test Suite Green

**Verification steps:**
```bash
cd /Users/jainer/Documents/WifiTroubleshooting

# Run all V2 tests
pytest agents/v2/ -v --tb=short 2>&1 | tail -20

# Verify V1 tests still pass (no regressions)
pytest agents/v1/ -v --tb=short 2>&1 | tail -20

# Check test count
pytest agents/v2/ --co -q 2>&1 | tail -5
```
**Pass criteria:** All V2 tests pass. All V1 tests still pass. At least 15 test functions exist.
**Fail action:** Fix failing tests. If V1 tests break, check that no shared modules were accidentally modified. If import errors, verify `sys.path` setup in conftest.py.

---

## Phase 8: Documentation

**Goal:** Create README, requirements.txt, and verify all run instructions work.
**Depends on:** Phase 6 (app), Phase 7 (tests)
**Complexity:** Low

### Files
- Create: `agents/v2/README.md`
- Create: `agents/v2/requirements.txt`

### Implementation Details

**requirements.txt:**
```
langchain-community>=0.2
langchain-openai>=0.3
langchain-chroma>=0.2
langchain-core>=0.3
langgraph>=0.2
chromadb>=0.5
pypdf>=4.0
pydantic>=2.0
streamlit>=1.30
python-dotenv>=1.0
openai>=1.0
langdetect>=1.0
pytest>=7.0
pytest-cov>=4.0
```

**README.md structure:**
```markdown
# V2 WiFi Troubleshooting Agent

## What's New in V2
- Multi-router model support (metadata-based Chroma filtering)
- Router model discovery with 3-retry gate
- Conversation mode selector (self-serve / agent-assisted)
- LLM-driven literacy detection (self-serve only)
- Manual-aware qualifier (retrieves manual before questioning)
- App/browser reboot method (LLM-driven connectivity gating)
- Generic reboot queries (model-agnostic)

## How to Run
...

## Architecture
### State Machine (9-node graph)
### State Schema
### Prompts

## Design Decisions
- Why single Chroma collection
- Why LLM-driven literacy (not static)
- Why no prompt_config.py
- Why manual-aware qualifier

## Known Limitations
- No local admin edge case
- Single language (English only)
- No evaluation pipeline (deferred to V3)
```

### Success Criteria
- [ ] `agents/v2/README.md` exists with all sections
- [ ] `agents/v2/requirements.txt` includes `langdetect>=1.0`
- [ ] Run instructions work from clean state:
  - `pip install -r agents/v2/requirements.txt`
  - `python shared/rag/ingest_v2.py --pdf shared/data/user_guide_EA6350.pdf --model EA6350 --brand Linksys`
  - `python shared/rag/verify_retrieval.py --version v2`
  - `streamlit run agents/v2/app.py`
- [ ] README documents all V2 design decisions

---

### Gate 8: Final Documentation Check

**Verification steps:**
```bash
cd /Users/jainer/Documents/WifiTroubleshooting

# Verify files exist
test -f agents/v2/README.md && echo "README: EXISTS" || echo "README: MISSING"
test -f agents/v2/requirements.txt && echo "requirements.txt: EXISTS" || echo "requirements.txt: MISSING"

# Verify langdetect in requirements
grep -q "langdetect" agents/v2/requirements.txt && echo "langdetect: PRESENT" || echo "langdetect: MISSING"

# Verify README has key sections
grep -q "How to Run" agents/v2/README.md && echo "Run section: PRESENT" || echo "Run section: MISSING"
grep -q "Design Decisions" agents/v2/README.md && echo "Design section: PRESENT" || echo "Design section: MISSING"
```
**Pass criteria:** All files exist. langdetect present. Key README sections present.
**Fail action:** Create missing files or sections.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `langdetect` misclassifies short pages (< 50 chars) | Medium | Low | Add `min_text_length` threshold; skip pages with too little text |
| LLM fails to extract model name from natural language input | Medium | Medium | Use structured examples in prompt; fallback to "did you mean [X]?" with available models |
| V2 Chroma collection conflicts with V1 | Low | High | Separate paths (`chroma_db/v1/` vs `chroma_db/v2/`); never share collections |
| Router model normalization mismatches (e.g., "EA-6350" vs "EA6350") | Medium | Medium | Normalize aggressively at ingest AND discovery: strip hyphens, uppercase, strip whitespace |
| LLM hallucates reboot steps instead of using RAG context | Low | High | Prompt explicitly says "Use ONLY the following instructions"; V3 adds hallucination guardrail |
| Streamlit mode selector resets on page rerun | Low | Medium | Store mode in `st.session_state` and guard with `st.stop()` before graph init |
| `select_reboot_method` node adds latency without clear value for physical-only manuals | Medium | Low | If manual has no app reboot section, LLM defaults to physical quickly; consider skipping node if only one method available |
| V1 shared modules accidentally modified | Low | Critical | Gate checks verify V1 imports still work; CI could diff `shared/state/state_v1.py` and `shared/rag/ingest_v1.py` against known checksums |

---

## End-to-End Verification Procedure

Run this after all phases are complete to validate the full system:

```bash
cd /Users/jainer/Documents/WifiTroubleshooting

echo "=== Step 1: Verify V1 is untouched ==="
python -c "
from shared.state.state_v1 import ConversationState
s = ConversationState()
assert not hasattr(s, 'router_model'), 'V1 state modified!'
print('V1 state: OK')
"
python -c "
from shared.prompts.base_prompts import QUALIFY_PROMPT
print('V1 prompts: OK')
"
python -c "
import shared.rag.ingest_v1 as v1
assert 'v1' in str(v1.CHROMA_PATH)
print('V1 ingest: OK')
"

echo "=== Step 2: Run V2 ingest ==="
python shared/rag/ingest_v2.py \
    --pdf shared/data/user_guide_EA6350.pdf \
    --model EA6350 \
    --brand Linksys

echo "=== Step 3: Verify V2 retrieval ==="
python shared/rag/verify_retrieval.py --version v2

echo "=== Step 4: Run V2 unit tests ==="
pytest agents/v2/ -v --tb=short

echo "=== Step 5: Run V1 tests (regression check) ==="
pytest agents/v1/ -v --tb=short

echo "=== Step 6: Verify graph compilation ==="
python -c "
from agents.v2.graph import compile_graph
g = compile_graph()
print(f'V2 graph compiled: {type(g)}')
print('Graph compilation: OK')
"

echo "=== Step 7: Verify state schema ==="
python -c "
from shared.state.state_v2 import ConversationState
s = ConversationState(conversation_mode='agent_assisted', router_model='EA6350')
assert s.router_model == 'EA6350'
assert s.conversation_mode == 'agent_assisted'
assert s.router_model_attempts == 0
assert s.reboot_appropriate is None
print('V2 state schema: OK')
"

echo "=== Step 8: Manual app test ==="
echo "Run: streamlit run agents/v2/app.py"
echo "Test scenarios:"
echo "  1. Self-serve + EA6350 + WiFi down + reboot resolves -> close_success"
echo "  2. Agent-assisted + EA6350 + single device issue -> graceful_exit"
echo "  3. Self-serve + unknown model x3 -> unsupported_model_exit"
echo "  4. Self-serve + EA6350 + reboot fails -> apologize_and_exit"

echo "=== All automated checks complete ==="
```

---

### Critical Files for Implementation
- `/Users/jainer/Documents/WifiTroubleshooting/shared/state/state_v2.py`
- `/Users/jainer/Documents/WifiTroubleshooting/shared/rag/ingest_v2.py`
- `/Users/jainer/Documents/WifiTroubleshooting/shared/prompts/v2_prompts.py`
- `/Users/jainer/Documents/WifiTroubleshooting/agents/v2/nodes.py`
- `/Users/jainer/Documents/WifiTroubleshooting/agents/v2/graph.py`
