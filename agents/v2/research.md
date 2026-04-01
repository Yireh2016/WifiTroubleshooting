# RouteThis V2 WiFi Assistant — Research & Design Analysis

**Date**: 2026-04-01  
**Status**: Production Research Document  
**Scope**: V2 technical architecture — multi-model support, router discovery, literacy detection, conversation modes, and LLM-driven decision logic

---

## Executive Summary

V2 extends V1's MVP with **multi-router support, dynamic literacy detection, and conversation mode flexibility**. The design removes all static configuration injection (prompt_config.py) in favor of **LLM-driven decisions made dynamically during conversation**. A Streamlit mode selector (at app start) establishes conversation context, but all language complexity, method selection, and decision trees are handled by the LLM in real-time.

**Key architectural principle:** *Shift from hardcoded decision trees to LLM-driven, context-aware reasoning.*

---

## 1. Multi-Model Router Support Architecture

### Core Design Principle

V2 supports multiple router models (Linksys EA6350, TP-Link Archer C80, Netgear Nighthawk, etc.) using a **single Chroma collection with metadata-based filtering**. This eliminates per-model code paths while preserving retrieval accuracy.

### Single Collection Strategy

**One Chroma collection (`chroma_db/v2/`) for all models:**

| Benefit | Rationale |
|---------|-----------|
| **Operational simplicity** | Single vector store to deploy and maintain |
| **Fast filtering** | Metadata filters in Chroma are O(1) lookups |
| **Extensibility** | Add new models via ingest CLI without touching code |
| **Cross-model search** | Same retriever works for all models; filter by metadata |

### Metadata Schema

All ingested chunks carry this metadata:

```python
metadata = {
    # Primary filter keys (exact-match, case-sensitive)
    "model_name": "EA6350",                # UPPERCASE, normalized
    "brand": "Linksys",                    # For context/logging
    "language": "en",                      # ISO 639-1 code (lowercase)
    "section_tag": "troubleshooting",      # Canonical section (lowercase)
    
    # Secondary metadata (for observability)
    "model_aliases": ["LINKSYS EA6350", "EA6350"],  # Alternative names user might say
    "section_title": "Troubleshooting WiFi Issues",  # Original heading
    "source_file": "user_guide_EA6350.pdf",         # PDF source
    "page_range": "15-18",                          # Physical page numbers
    
    # Deduplication/versioning
    "chunk_id": "EA6350_en_troubleshooting_001",  # Unique per model-lang-section-chunk
    "ingest_version": "2026-04-01",               # Ingest timestamp for versioning
}
```

### Normalization Rules

Chroma uses **exact-string matching** on metadata — no fuzzy matching:

```python
# Ingest time: normalize to canonical form
def normalize_for_metadata(model_name: str, language: str) -> dict:
    return {
        "model_name": model_name.strip().upper(),     # "ea6350" → "EA6350"
        "language": language.strip().lower(),         # "EN" → "en"
        "section_tag": "troubleshooting",             # Always lowercase
    }

# Retrieval time: exact match
filter_dict = {
    "$and": [
        {"model_name": state.router_model},  # Must match exactly
        {"language": "en"},
        {"section_tag": "troubleshooting"}
    ]
}
```

### Retrieval Pattern

```python
def retrieve_for_model(query: str, model_name: str, vectorstore) -> list:
    """
    Generic retrieval for any model in collection.
    
    Args:
        query: User question (e.g., "how do I reboot?")
        model_name: Router model (e.g., "EA6350")
        vectorstore: Chroma instance
    
    Returns:
        List of relevant chunks with model metadata
    """
    results = vectorstore.similarity_search_with_score(
        query=query,
        k=5,  # Top 5 chunks
        filter={
            "$and": [
                {"model_name": model_name},
                {"language": "en"},
                {"section_tag": "troubleshooting"}
            ]
        }
    )
    # Filter returns (Document, score) tuples
    return [(doc, score) for doc, score in results if score > 0.5]
```

---

## 2. Router Model Discovery Flow (3-Retry Gate)

V2 begins by discovering the user's router model with graceful fallback. This is a **critical gate** — if model is not found after 3 retries, the agent exits with a helpful message.

### Discovery Conversation Flow

```
┌─ Streamlit starts (mode selected)
├─ Welcome node: "What router model do you have?"
├─ User says: "Linksys EA6350" or "I don't know"
├─ Qualifier node: 
│  ├─ Parse model from speech/text (heuristic + LLM)
│  ├─ Query Chroma: does model exist in collection?
│  ├─ If found: store in state.router_model, continue
│  └─ If not found: ask clarifying question (retry 1, 2, 3)
├─ After 3 failed retries: exit with "unsupported_model"
└─ Continue to troubleshooting flow
```

### Implementation Pattern

**State extension (in `shared/state/state_v2.py`):**

```python
class RouterModelState(ConversationState):
    # Inherited from V1
    messages: Annotated[list, add_messages]
    
    # V2 additions
    router_model: Optional[str] = None      # e.g., "EA6350" (normalized)
    router_brand: Optional[str] = None      # e.g., "Linksys"
    mode: str = "self_serve"                # "self_serve" or "agent_assisted"
    model_discovery_attempts: int = 0       # Counter for retry gate
```

**Qualifier node with model validation:**

```python
def qualify_and_discover_model(state: RouterModelState, vectorstore):
    """
    Discover router model and validate it exists in collection.
    Implements 3-retry gate.
    """
    state.model_discovery_attempts += 1
    
    # Extract model from last user message
    user_input = state.messages[-1].content
    model_name = extract_model_name(user_input)  # LLM-based heuristic
    
    # Normalize and check collection
    if model_name:
        normalized = model_name.strip().upper()
        exists = check_model_in_collection(normalized, vectorstore)
        
        if exists:
            state.router_model = normalized
            state.router_brand = get_brand_for_model(normalized)
            # Continue to troubleshooting
            return state, "model_discovered"
    
    # Model not found or not provided
    if state.model_discovery_attempts < 3:
        # Ask clarifying question (include model examples from collection)
        available_models = list_available_models(vectorstore)
        msg = (f"I couldn't find that model. Here are supported routers: "
               f"{', '.join(available_models[:5])}. Could you check your manual?")
        return state, ("clarify_model", msg)
    else:
        # Exit after 3 retries
        state.exit_reason = "unsupported_model"
        return state, "exit"
```

**Chroma helper (in `shared/rag/retriever.py`):**

```python
def check_model_in_collection(model_name: str, vectorstore) -> bool:
    """Check if model has any documents in Chroma."""
    results = vectorstore.get(
        where={"model_name": model_name.upper()},
        limit=1
    )
    return len(results.get("ids", [])) > 0

def list_available_models(vectorstore) -> list[str]:
    """Return all unique model_names in collection."""
    # Chroma doesn't have native DISTINCT, so we fetch and deduplicate
    all_docs = vectorstore.get(limit=10000)
    models = set(
        doc.get("model_name") 
        for doc in all_docs.get("metadatas", [])
    )
    return sorted(list(models))
```

---

## 3. Language Detection and Filtering

V2 ingest pipeline automatically detects language per page using `langdetect`, stores it in metadata, and filters at retrieval time.

### Page-Level Language Detection

**At ingest time (in `shared/rag/ingest_v2.py`):**

```python
from langdetect import detect

def detect_page_language(page_text: str) -> str:
    """
    Detect language of a PDF page.
    Returns ISO 639-1 code (e.g., "en", "fr", "es").
    Fallback to "unknown" if detection fails.
    """
    try:
        lang = detect(page_text)
        return lang if lang in SUPPORTED_LANGUAGES else "unknown"
    except Exception:
        return "unknown"

def ingest_multi_language_pdf(pdf_path: str, model_name: str, brand: str):
    """
    Ingest entire PDF, detect language per page, store in metadata.
    """
    doc = load_pdf(pdf_path)
    
    for page_num, page_text in enumerate(doc.pages):
        language = detect_page_language(page_text)
        
        # Only ingest English pages (language == "en")
        if language != "en":
            logger.info(f"Skipping page {page_num} (language: {language})")
            continue
        
        # Segment and ingest with language metadata
        segments = segment_with_llm(page_text)
        for segment in segments:
            metadata = {
                "model_name": model_name.upper(),
                "language": language,
                "page_number": page_num,
                "section_tag": infer_section_tag(segment),
                # ... other metadata
            }
            vectorstore.add_documents([segment], metadatas=[metadata])
```

### Filtering at Retrieval

```python
def retrieve_english_only(query: str, model: str, vectorstore):
    """Retrieve only English pages for the user's model."""
    return vectorstore.similarity_search(
        query=query,
        k=5,
        filter={
            "$and": [
                {"model_name": model},
                {"language": "en"},  # Explicit English filter
            ]
        }
    )
```

### Multilingual Support (Future)

To add French support later:

```python
# At app startup, user selects language (or app detects from browser locale)
state.preferred_language = "fr"

# At retrieval time, swap filter
filter_dict = {
    "$and": [
        {"model_name": state.router_model},
        {"language": state.preferred_language},  # Dynamic language filter
    ]
}
```

---

## 4. Conversation Mode System

V2 introduces two conversation modes, selected **once at app start** via Streamlit UI. This choice affects literacy detection and language complexity throughout the conversation.

### Mode Definitions

| Mode | Literacy Detection | Language Style | Manual Retrieval | Use Case |
|------|-------------------|-----------------|------------------|----------|
| **Self-Serve** | LLM-driven, dynamic | Adaptive (plain language when needed) | User manual queried and offered | Users troubleshooting independently |
| **Agent-Assisted** | Disabled (assume technical) | Always technical | Retrieved for agent context only | Tech-savvy users, agents assisting users |

### Streamlit Mode Selector (Entry Point)

```python
# agents/v2/app.py
import streamlit as st

# At app start (before graph initialization)
col1, col2 = st.columns(2)
with col1:
    if st.button("I'll troubleshoot on my own", use_container_width=True):
        st.session_state.conversation_mode = "self_serve"
with col2:
    if st.button("An agent will help me", use_container_width=True):
        st.session_state.conversation_mode = "agent_assisted"

if "conversation_mode" not in st.session_state:
    st.info("Select a conversation mode above to begin.")
    st.stop()

# Mode is now locked for this session
mode = st.session_state.conversation_mode
state.mode = mode
```

### State Extension

```python
class ConversationMode(ConversationState):
    mode: str  # "self_serve" or "agent_assisted"
    
    # Literacy metadata (self-serve only; ignored in agent-assisted)
    detected_literacy_level: Optional[str] = None  # "high", "medium", "low" (dynamic)
    should_use_plain_language: bool = False        # Inferred from conversation flow
```

---

## 5. LLM-Driven Literacy Detection (Self-Serve Only)

V2 removes static literacy classification in favor of **dynamic, conversation-based detection**. The LLM observes user language, questions, and technical vocabulary to adapt explanations on-the-fly.

### Detection Strategy

Literacy detection is **implicit and ongoing**, not a upfront quiz:

```
User asks: "How do I restart the WiFi?"
↓
LLM observes: simple vocabulary, not technical
↓
LLM infers: likely non-technical user (low literacy)
↓
LLM responds: plain language, step-by-step with analogies

---

User asks: "Can you walk through a factory reset to clear wlan config?"
↓
LLM observes: technical terms (factory reset, wlan config)
↓
LLM infers: technical user (high literacy)
↓
LLM responds: technical detail, less handholding
```

### Implementation in Prompt Template

**Prompt template (in `shared/prompts/v2_qualifier.md`):**

```markdown
## Context
- Mode: {mode}
- Router Manual: {manual_excerpt}
- Conversation History: {messages}

## Instructions
1. **If mode is "self_serve":**
   - Analyze user's language: vocabulary, technical terms, clarity of questions
   - Infer literacy level implicitly (don't ask "what's your technical level?")
   - Adapt explanations: use plain language if user seems non-technical
   - Examples: "restart" = "turn off, wait 30 seconds, turn on" (plain)
   - vs. "reboot" = "cycle power" (technical user won't need step-by-step)

2. **If mode is "agent_assisted":**
   - Assume user is technical (don't simplify)
   - Use technical language and router terminology
   - Skip analogies and basic explanations

3. **Do not:**
   - Explicitly classify user's literacy level
   - Ask meta-questions ("Are you comfortable with tech?")
   - Toggle between literacy levels mid-conversation (be consistent once inferred)

## Output (JSON)
{
  "next_message": "...",
  "literacy_level_observed": "high|medium|low",  // For logging only
  "detected_mode_mismatch": false  // If user seems agent-assisted but selected self-serve
}
```

### Code-Level Implementation

```python
def qualifier_node(state: ConversationMode):
    """
    Qualify issue and dynamically detect literacy (self-serve) or assume technical (agent-assisted).
    Literacy detection is passive (inferred from user input), not active (no questions).
    """
    
    # Build prompt with context
    prompt = load_prompt("shared/prompts/v2_qualifier.md")
    prompt_text = prompt.format(
        mode=state.mode,
        manual_excerpt=retrieve_manual_excerpt(state.router_model),
        messages=format_messages(state.messages)
    )
    
    # LLM makes decision
    response = get_llm().invoke([
        SystemMessage(content=prompt_text),
        HumanMessage(content=state.messages[-1].content)
    ])
    
    # Parse JSON response
    output = json.loads(response.content)
    
    # Store observed literacy (for logging, NOT for changing LLM behavior)
    if state.mode == "self_serve":
        state.detected_literacy_level = output["literacy_level_observed"]
    
    # Continue with qualifications
    return state, output["next_message"]
```

**Key principle:** Literacy detection is **read-only observation for logging**; the LLM's adaptive language happens naturally in prompts and responses, not via explicit branches.

---

## 6. Manual-Aware Qualifier Node

The qualifier node **retrieves the user's router manual** and formulates questions **in relation to the manual's reboot steps**. This ensures questions are grounded in the actual device capabilities.

### Retrieval Pattern

```python
def retrieve_manual_for_model(model_name: str, vectorstore):
    """
    Retrieve the full router manual (troubleshooting section) for a model.
    Used to inform qualifier questions and context.
    """
    results = vectorstore.similarity_search(
        query="restart reboot reset troubleshooting steps",
        k=10,  # Retrieve more chunks to build full context
        filter={
            "$and": [
                {"model_name": model_name},
                {"language": "en"},
                {"section_tag": "troubleshooting"}
            ]
        }
    )
    return results

def build_manual_context(chunks: list) -> str:
    """Concatenate chunks into a coherent manual excerpt."""
    return "\n\n".join([doc.page_content for doc in chunks])
```

### Prompt Integration

**In `shared/prompts/v2_qualifier.md`:**

```markdown
## Router Manual (for {router_model})
{manual_excerpt}

## Your Role
- Ask clarifying questions about the user's WiFi issue
- Reference manual sections when relevant (e.g., "Does your router have a reset button? Yours (EA6350) has one on the back...")
- Determine if a reboot is appropriate based on the issue
- If reboot is not appropriate, offer graceful exit (e.g., "This sounds like an ISP issue, not router-related")

## Questions to Ask (in order)
1. "Is WiFi completely down, or just slow?"
2. "Have you tried restarting your router before? If so, what happened?"
3. [Custom question based on manual content and issue type]

## Output (JSON)
{
  "reboot_appropriate": true,
  "issue_summary": "...",
  "next_step": "retrieve_reboot_steps or exit_graceful"
}
```

### Node Implementation

```python
def qualifier_node_with_manual(state: RouterModelState, vectorstore):
    """
    Qualify issue using router's actual manual for context.
    Ask questions in relation to manual's capabilities.
    """
    
    # Retrieve manual for user's router
    manual_chunks = retrieve_manual_for_model(state.router_model, vectorstore)
    manual_text = build_manual_context(manual_chunks)
    
    # Build prompt with manual context
    prompt = load_prompt("shared/prompts/v2_qualifier.md").format(
        router_model=state.router_model,
        manual_excerpt=manual_text,
        mode=state.mode,
        messages=format_messages(state.messages)
    )
    
    # LLM qualifies using manual as source of truth
    response = get_llm().invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=state.messages[-1].content)
    ])
    
    output = json.loads(response.content)
    state.reboot_appropriate = output["reboot_appropriate"]
    state.rag_context = manual_chunks  # Cache for next node
    
    if output["next_step"] == "exit_graceful":
        state.exit_reason = output.get("exit_reason", "not_reboot_issue")
        return state, "exit"
    else:
        return state, ("continue_to_reboot", output["next_message"])
```

---

## 7. Generic Reboot Method Queries (Model-Agnostic)

V2 reboot method retrieval is **generic and works for any router model**. Queries like "reboot steps" or "power cycle" are sufficient; the metadata filter handles model-specific filtering.

### Retrieval Pattern

```python
def retrieve_reboot_steps(model_name: str, vectorstore) -> list:
    """
    Retrieve reboot instructions for a model using generic queries.
    Metadata filter ensures model-specific results.
    """
    generic_queries = [
        "how to reboot restart restart power cycle",
        "restart WiFi router",
        "reset to factory defaults",
    ]
    
    all_results = []
    for query in generic_queries:
        results = vectorstore.similarity_search(
            query=query,
            k=3,
            filter={
                "$and": [
                    {"model_name": model_name},
                    {"language": "en"},
                    {"section_tag": "troubleshooting"}
                ]
            }
        )
        all_results.extend(results)
    
    # Deduplicate by chunk_id and rank by relevance
    unique_results = {}
    for doc in all_results:
        chunk_id = doc.metadata.get("chunk_id")
        if chunk_id and chunk_id not in unique_results:
            unique_results[chunk_id] = doc
    
    return list(unique_results.values())
```

### Why This Works

- **No model-specific queries needed:** "Reboot steps" retrieves EA6350 steps, TP-Link steps, etc. based on metadata filter
- **Extensible:** New models auto-work without prompt changes
- **Semantic similarity:** Vector embeddings find best matches regardless of model-specific terminology

---

## 8. LLM-Driven Decision Trees (No Hardcoded Logic)

V2 removes hardcoded decision trees for method selection and app reboot gating. **All decisions are LLM-driven**, with the LLM reasoning over manual context, user responses, and conversation state.

### App Reboot Decision Example

**Old V1 approach (hardcoded):**

```python
# In nodes.py (bad)
if state.app_mentioned:
    show_app_reboot = True
else:
    show_app_reboot = False
```

**New V2 approach (LLM-driven):**

```markdown
## In shared/prompts/v2_reboot_method.md

### Context
- User's issue: {issue_summary}
- Manual says: {manual_excerpt}
- Conversation so far: {messages}

### Decision: Should we try an app reboot?
- If user says "my apps are slow" and manual lists "Force Stop apps" as a troubleshooting step → YES
- If user says "no internet at all" and manual has no app-level fixes → NO (only hardware reboot)

### Output (JSON)
{
  "offer_app_reboot": true,
  "reasoning": "User mentioned app crashes; manual lists app restart as step 1",
  "method_priority": ["app_reboot", "soft_reboot", "hard_reboot"]
}
```

**Code implementation:**

```python
def reboot_method_selector_node(state: RouterModelState):
    """
    LLM decides which reboot methods to offer, based on manual and issue.
    Not hardcoded — LLM reasons over context.
    """
    
    prompt = load_prompt("shared/prompts/v2_reboot_method.md").format(
        issue_summary=state.issue_summary,
        manual_excerpt=state.rag_context,
        messages=format_messages(state.messages)
    )
    
    response = get_llm().invoke([
        SystemMessage(content=prompt),
        HumanMessage("What reboot methods should we try?")
    ])
    
    output = json.loads(response.content)
    
    state.reboot_methods_offered = output["method_priority"]
    state.offer_app_reboot = output["offer_app_reboot"]
    
    return state, ("show_methods", output["reasoning"])
```

**Benefits:**

- Flexible: reasoning changes with new manual content automatically
- Debuggable: LLM provides reasoning ("why did we offer this?")
- Extensible: works for app reboots, soft reboots, factory resets without code changes

---

## 9. State Schema Extensions (V2)

**File: `shared/state/state_v2.py`**

```python
from typing import Optional, Annotated
from pydantic import BaseModel, Field
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage

class ConversationStateV2(BaseModel):
    """Extended state for V2 with multi-model and mode support."""
    
    # From V1 (inherited / reused)
    messages: Annotated[list[BaseMessage], add_messages]
    exit_reason: Optional[str] = None
    reboot_appropriate: bool = False
    current_step: int = 0
    rag_context: list = Field(default_factory=list)
    
    # V2: Router discovery
    router_model: Optional[str] = None           # e.g., "EA6350" (normalized uppercase)
    router_brand: Optional[str] = None           # e.g., "Linksys"
    model_discovery_attempts: int = 0            # For 3-retry gate
    
    # V2: Conversation mode
    mode: str = "self_serve"                     # "self_serve" or "agent_assisted"
    
    # V2: Literacy (self-serve only, read-only for logging)
    detected_literacy_level: Optional[str] = None  # "high", "medium", "low"
    
    # V2: Issue tracking
    issue_summary: Optional[str] = None          # LLM's understanding of problem
    
    # V2: Reboot methods
    reboot_methods_offered: list = Field(default_factory=list)  # ["app_reboot", "soft_reboot", "hard_reboot"]
    offer_app_reboot: bool = False               # LLM decision (not hardcoded)
    selected_reboot_method: Optional[str] = None  # User's choice
    
    # V2: Language
    preferred_language: str = "en"               # Could extend to "fr", "es", etc.
    
    class Config:
        arbitrary_types_allowed = True
```

---

## 10. Metadata Schema and Retrieval Patterns

### Complete Metadata Structure

```json
{
  "model_name": "EA6350",
  "brand": "Linksys",
  "language": "en",
  "section_tag": "troubleshooting",
  "section_title": "Troubleshooting WiFi Issues",
  "model_aliases": ["R63", "LINKSYS EA6350"],
  "chunk_id": "EA6350_en_troubleshooting_003",
  "page_number": 16,
  "source_file": "user_guide_EA6350.pdf",
  "ingest_version": "2026-04-01"
}
```

### Retrieval Filter Patterns

**Pattern 1: Exact model, English, troubleshooting**
```python
filter={
    "$and": [
        {"model_name": "EA6350"},
        {"language": "en"},
        {"section_tag": "troubleshooting"}
    ]
}
```

**Pattern 2: Any model in collection, English only**
```python
filter={"language": "en"}
```

**Pattern 3: List available models**
```python
# Fetch all documents, deduplicate by model_name
results = vectorstore.get(limit=10000)
models = set(m["model_name"] for m in results["metadatas"])
```

**Pattern 4: Search across multiple sections (for future)**
```python
filter={
    "$and": [
        {"model_name": "EA6350"},
        {"language": "en"},
        {"$or": [
            {"section_tag": "troubleshooting"},
            {"section_tag": "setup"},
            {"section_tag": "advanced_config"}
        ]}
    ]
}
```

---

## 11. Integration with Shared Modules

### Dependencies

```
agents/v2/
├── app.py (Streamlit UI with mode selector)
├── graph.py (State machine with new nodes)
├── nodes.py (Node functions: discover_model, qualify, select_methods, etc.)
└── requirements.txt (inherits from v1, adds: langdetect)

shared/
├── state/
│   ├── state_v1.py (V1 base state)
│   └── state_v2.py (V2 extended state, backwards-compatible)
├── rag/
│   ├── ingest_v1.py (V1 single-model)
│   ├── ingest_v2.py (V2 multi-model with language detection)
│   ├── retriever.py (Generic retriever, used by v1 and v2)
│   └── verify_retrieval.py (Testing, works for any model)
└── prompts/
    ├── v1_*.md (V1 prompts)
    └── v2_*.md (V2 prompts with manual context, decision trees)
```

### Shared Code Patterns

**In `agents/v2/nodes.py`:**

```python
# Import shared modules (V2 can use V1 components)
from shared.state.state_v2 import ConversationStateV2
from shared.rag.retriever import retrieve_english_only, check_model_in_collection
from shared.prompts import load_prompt

# Graph compilation uses same LangGraph pattern as V1
def build_graph(vectorstore):
    graph = StateGraph(ConversationStateV2)
    
    # Add nodes (mix of V2-specific + reused V1 patterns)
    graph.add_node("discover_model", discover_model_node)
    graph.add_node("qualify", qualify_node_with_manual)
    graph.add_node("select_methods", reboot_method_selector)
    graph.add_node("walk_steps", walk_reboot_steps)
    
    # Routing uses same conditional patterns as V1
    graph.add_conditional_edges(
        "qualify",
        lambda state: "exit" if state.reboot_appropriate is False else "select_methods"
    )
    
    return graph.compile()
```

---

## 12. Testing Strategy

### Unit Tests

**Test 1: Multi-model retrieval**
```python
def test_retrieve_for_multiple_models(vectorstore):
    """Verify retrieval filters correctly for each model."""
    
    # Ingest 3 models
    ingest_model(vectorstore, "EA6350", "linksys_ea6350.pdf")
    ingest_model(vectorstore, "C80", "tplink_c80.pdf")
    ingest_model(vectorstore, "NIGHTHAWK", "netgear_nighthawk.pdf")
    
    # Retrieve for EA6350 should only return EA6350 chunks
    results_ea6350 = retrieve_for_model("reboot", "EA6350", vectorstore)
    assert all(r.metadata["model_name"] == "EA6350" for r in results_ea6350)
    
    # Retrieve for C80 should only return C80 chunks
    results_c80 = retrieve_for_model("reboot", "C80", vectorstore)
    assert all(r.metadata["model_name"] == "C80" for r in results_c80)
```

**Test 2: Language filtering**
```python
def test_english_only_filtering(vectorstore):
    """Verify ingest skips non-English pages."""
    
    # Ingest PDF with mixed languages
    ingest_pdf(vectorstore, "multi_language.pdf", "EA6350", "Linksys")
    
    # All chunks should have language="en"
    all_chunks = vectorstore.get()
    assert all(m["language"] == "en" for m in all_chunks["metadatas"])
```

**Test 3: Model discovery gate**
```python
def test_model_discovery_3_retry_gate(vectorstore):
    """Verify agent exits after 3 failed model discovery attempts."""
    
    ingest_model(vectorstore, "EA6350", "...")
    
    state = ConversationStateV2()
    
    # Attempt 1: unknown model
    state.messages.append(HumanMessage("I have a Linksys EA1234"))
    state, _ = discover_model_node(state, vectorstore)
    assert state.model_discovery_attempts == 1
    assert state.exit_reason is None  # Still in loop
    
    # Attempt 2
    state.messages.append(HumanMessage("Actually, maybe it's TP-Link?"))
    state, _ = discover_model_node(state, vectorstore)
    assert state.model_discovery_attempts == 2
    
    # Attempt 3
    state.messages.append(HumanMessage("I don't know"))
    state, _ = discover_model_node(state, vectorstore)
    assert state.model_discovery_attempts == 3
    assert state.exit_reason == "unsupported_model"
```

**Test 4: LLM-driven decisions**
```python
def test_llm_decides_app_reboot(vectorstore):
    """Verify LLM (not hardcoded logic) decides whether to offer app reboot."""
    
    state = ConversationStateV2(
        router_model="EA6350",
        mode="self_serve",
        issue_summary="WiFi apps crash when loading",
        rag_context=[...]  # Manual chunks mentioning app reboot
    )
    
    state, message = reboot_method_selector_node(state)
    
    # LLM should recommend app reboot based on manual context
    assert "app_reboot" in state.reboot_methods_offered
```

### Integration Tests

**Test 5: Full conversation flow (self-serve mode)**
```python
def test_self_serve_conversation_flow(vectorstore):
    """Walk through complete self-serve conversation."""
    
    graph = build_graph(vectorstore)
    
    # Start
    state = graph.invoke({
        "messages": [HumanMessage("I can't get WiFi")],
        "mode": "self_serve",
    })
    
    # Step 1: Discover model
    state = graph.invoke({
        **state,
        "messages": [..., HumanMessage("Linksys EA6350")]
    })
    assert state["router_model"] == "EA6350"
    
    # Step 2: Qualify issue
    state = graph.invoke({
        **state,
        "messages": [..., HumanMessage("No internet at all")]
    })
    assert state["reboot_appropriate"] is True
    
    # Step 3: Walk reboot steps
    # ... assert steps are from EA6350 manual
```

### Manual Validation Script

**File: `agents/v2/test_app_manual.py`**

```python
"""
Manual validation script — test agent conversations without mocking.
Requires: .env with OPENAI_API_KEY

Run: python agents/v2/test_app_manual.py
"""

def test_conversation_scenario(name: str, mode: str, messages: list):
    """Simulate a conversation scenario and print agent responses."""
    
    vectorstore = load_vectorstore("chroma_db/v2/")
    graph = build_graph(vectorstore)
    
    state = ConversationStateV2(mode=mode)
    
    print(f"\n=== Scenario: {name} (mode: {mode}) ===\n")
    
    for msg in messages:
        state.messages.append(HumanMessage(content=msg))
        state = graph.invoke(state)
        print(f"User: {msg}")
        print(f"Agent: {state.messages[-1].content}\n")
    
    print(f"Final exit_reason: {state.exit_reason}\n")

# Test scenarios
test_conversation_scenario(
    "Self-serve, successful reboot",
    mode="self_serve",
    messages=[
        "I have a Linksys EA6350",
        "WiFi just stopped working",
        "No, I haven't tried restarting yet",
        # ... rest of conversation
    ]
)

test_conversation_scenario(
    "Agent-assisted, unknown model",
    mode="agent_assisted",
    messages=[
        "I have a TP-Link Archer X90",  # Not in collection
        "I'm waiting for you to help",
        # Should exit after 3 retries with unsupported_model
    ]
)
```

---

## 13. Development Roadmap

### Phase 1: Foundation (Current)
- Multi-model metadata schema
- Router model discovery (3-retry gate)
- Language detection at ingest time
- Conversation mode selector (Streamlit)
- LLM-driven literacy detection (implicit, not explicit)
- Manual-aware qualifier node
- Generic reboot method queries
- LLM-driven decision trees (no hardcoding)

### Phase 2: Enhanced Methods
- App reboot workflows (LLM decides when)
- Soft reboot vs. hard reboot decision
- Recovery strategies (rollback if reboot doesn't work)

### Phase 3: Observability
- Logging for literacy level detection (read-only, for learning)
- Metrics: which reboot methods succeed for which models
- A/B testing: LLM prompt variants

### Phase 4: Multilingual
- Support "fr", "es", "de" modes (in addition to "en")
- Language selector in Streamlit (or detect from browser locale)
- Multilingual prompts

### Phase 5: Production Hardening
- Rate limiting (model discovery gate)
- Usage quotas per user
- Audit logging (which manual sections retrieved, why)

---

## 14. Design Rationale

### Why LLM-Driven Over Hardcoded?

| Aspect | V1 (Hardcoded) | V2 (LLM-Driven) | Benefit |
|--------|---|---|---|
| Literacy level | Upfront quiz | Inferred from chat | Natural, non-intrusive |
| Method selection | `if` statements | LLM reasons | Flexible, scales to new methods |
| Language complexity | Static prompt | Dynamic per user | Adapts in real-time |
| Model support | Single (EA6350) | Any model in Chroma | Extensible without code |

### Why Single Chroma Collection?

- **Operational:** One vector store to deploy, backup, monitor
- **Performance:** Metadata filters are O(1); no separate collections to query
- **Extensibility:** Add models via ingest CLI, not code changes
- **UX:** Same retrieval logic for all models — no model-specific branches

### Why Manual-Aware Qualifier?

- Grounds questions in reality (what the device actually can do)
- Prevents nonsensical suggestions (e.g., asking for features the manual doesn't mention)
- Builds context for downstream decisions (method selection, step guidance)

### Why LLM Decides Methods?

- Flexible: reasoning adapts to new manuals automatically
- Transparent: LLM provides reasoning ("why this method?")
- Robust: works for app reboots, soft reboots, factory resets without code changes

---

## 15. Future Considerations

### Edge Cases Handled

- **Unknown model:** 3-retry gate → graceful exit with "unsupported_model"
- **User mode mismatch:** LLM detects if self-serve user asks for agent help, can escalate (future)
- **Unsupported language:** Ingest skips non-English pages; retrieval filters to English only
- **Partial manual:** LLM adapts questions if manual has limited content

### Not in Scope (V2)

- Multiple devices per user (will be V3+)
- Multi-turn app reboot recovery (deferred to Phase 2)
- Multilingual support (deferred to Phase 4)
- Evaluation pipeline (deferred to Phase 3)

---

## Summary

V2 redesigns V1's MVP to support **multiple router models, dynamic literacy detection, and LLM-driven decision logic**. By removing static configuration (prompt_config.py) and hardcoded decision trees, the agent becomes **flexible, maintainable, and easily extensible** to new devices and conversation modes.

**Key architectural shift:** From static → dynamic, from hardcoded → LLM-driven, from single-model → multi-model.
