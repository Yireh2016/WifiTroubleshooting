# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**WifiTroubleshooting WiFi Assistant** is a conversational AI that guides users through WiFi troubleshooting using a Linksys EA6350 router manual as the source of truth. It qualifies issues through guided questions, retrieves reboot steps via RAG (Retrieval-Augmented Generation), and directs users through physical reboot steps.

**Current Status:** V1 MVP complete (Streamlit UI + agent logic). V2 multi-router design in progress.

## Architecture

### Multi-Agent Pattern
The repo follows a **versioned agent architecture** where each agent version (V1, V2, V3) is independent:
- **V1 (MVP):** Core qualification + physical reboot guidance for Linksys EA6350 (frozen, complete)
- **V2 (Enhanced):** Multi-router support (Archer C1200, Netgear WNR854T), app/browser reboot, literacy detection, LLM-driven routing
- **V3 (Production):** Evaluation pipeline, guardrails, structured logging, human escalation

Each agent:
- Lives in its own `agents/vN/` folder
- Has independent code (no cross-version imports between agents)
- Never modifies code from other versions
- Imports shared components from `shared/` only

**Key principle:** V1 always runs exactly as submitted; later versions are additive only.

### Shared Components
Code reused across agents lives in `shared/`:
- **`shared/rag/`** — PDF ingestion (LLM-based segmentation), retrieval, verification
- **`shared/state/`** — Pydantic state schemas (ConversationState with message history, router state, exit reasons)
- **`shared/prompts/`** — Prompt templates for each agent node, injected with dynamic context (RAG results, step numbers, etc.)
- **`shared/data/`** — User guide PDFs (single source of truth)
  - `user_guide_EA6350.pdf` — Linksys EA6350 (V1)
  - `Archer_C1200(US)_V1_UG.pdf` — TP-Link Archer C1200 (V2)
  - `wnr854t_setup_manual.pdf` — Netgear WNR854T (V2)

### Data Flow: RAG Pipeline
1. **Ingest** (`shared/rag/ingest_v1.py`): PDF → English text (page filter) → LLM segmentation → vector embeddings → Chroma store
2. **Retrieve** (`shared/rag/retriever.py`): Query + metadata filters → Chroma → ranked chunks with model/section tags
3. **Inject**: Retrieved context → prompt template → LLM response

### Agent Architecture: LangGraph State Machine
The agent is a directed graph with 7 nodes and conditional routing:
- **Nodes** (`agents/v1/nodes.py`): Pure functions that take state → return updated state + message
- **Routing functions**: Conditional logic for state transitions (e.g., "if reboot not appropriate → exit_reason, else continue")
- **Compiled graph** (`agents/v1/graph.py`): Serializable agent that handles message persistence and node sequencing

**Key state fields:**
- `messages`: Conversation history (LangGraph auto-manages with `add_messages` reducer)
- `reboot_appropriate`: Qualification result (bool)
- `current_step`: Physical reboot step counter (0-indexed, incremented after each step is confirmed)
- `rag_context`: Retrieved reboot instructions, cached after first query
- `exit_reason`: Why agent is exiting gracefully (e.g., "single_device", "isp_outage")

## Running the Project

### Setup
```bash
# 1. Copy environment (edit with your OpenAI key and LangSmith token if using tracing)
cp .env.example .env

# 2. Install dependencies
pip install -r agents/v1/requirements.txt

# 3. Ingest PDF into Chroma vector store (one-time)
python shared/rag/ingest_v1.py

# 4. Run the Streamlit app
streamlit run agents/v1/app.py
```

**Requirements:** Python 3.9+, OpenAI API key (sk-...)

### Running Tests
Tests are pytest-based and can also be run as standalone scripts:

```bash
# Run all V1 tests with pytest
pytest agents/v1/ -v

# Or run individual test modules
python agents/v1/test_graph.py          # Graph construction and routing
python agents/v1/test_scenarios.py      # End-to-end conversation scenarios
python agents/v1/test_nodes.py          # Individual node functions
python agents/v1/test_rag_integration.py # RAG retrieval integration

# Verify RAG retrieval and Chroma connectivity (after ingest)
python shared/rag/verify_retrieval.py
```

All tests should pass with exit code 0.

## Key Directories

| Directory | Purpose |
|-----------|---------|
| `agents/v1/` | V1 agent — app.py (Streamlit UI), graph.py (state machine), nodes.py (node functions) |
| `agents/v1/specs/` | V1 specifications — spec.md, implementation-plan.md, research.md |
| `agents/v2/` | V2 agent code (in development) |
| `agents/v2/` (specs) | V2 specifications — spec.md, implementation-plan.md, research.md |
| `shared/rag/` | PDF ingest, retrieval, verification — imported by all agent versions |
| `shared/state/` | State schema (Pydantic) — defines ConversationState |
| `shared/prompts/` | Prompt templates — injected with RAG context, step numbers, exit reasons |
| `shared/data/` | User guide PDFs (V1: EA6350, V2: Archer C1200 + Netgear WNR854T) |
| `chroma_db/` | Vector stores (v1/, v2/) — persisted between sessions |
| `.claude/` | Claude Code config, custom skills |

## Important Patterns & Decisions

### LLM Lazy Loading
The agent avoids loading OpenAI/embeddings at import time (would require `.env`). Instead:
- Nodes import `from agents.v1.graph import _get_llm()` and call it when needed
- Tests can mock LLM responses without API keys
- App uses lazy loading in graph compilation

### sys.path Handling
Agent code uses `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))` to import `shared/` as a top-level package:
```python
from shared.rag import ingest_v1
from shared.state import state_v1
```

This is done in `app.py`, `graph.py`, and test files.

### JSON Response Format
Nodes use OpenAI's `response_format={"type": "json_object"}` to force structured output. The prompt **must mention JSON** for this to work.

### Message Reducer
The state's `messages` field uses `Annotated[list[BaseMessage], add_messages]` to automatically deduplicate and merge messages from multiple node outputs.

### Chroma Metadata Filtering
Retrieval filters chunks by model and language:
```python
where_filter = {"$and": [
    {"model_name": "EA6350"},
    {"language": "en"},
    {"section_tag": "troubleshooting"}  # optional
]}
```

### PDF Page Range Filter
Only English pages (0–17) are ingested. Pages 18+ are other languages. This is critical for reducing noise in embeddings.

## Debugging Tips

### RAG Issues
- Run `verify_retrieval.py` to check Chroma connectivity and sample queries
- Look for `chroma_db/v1/` — if missing, ingest hasn't run
- Check metadata filters in `shared/rag/retriever.py` — wrong model_name will return zero chunks

### Graph Routing Issues
- Inspect state transitions in `test_graph.py` — prints actual routing decisions
- Check node functions in `nodes.py` — each must return `(state_update, message)` tuple
- Verify `add_messages` is used in state: `Annotated[list, add_messages]`

### Streamlit Issues
- Use `streamlit run --logger.level=debug agents/v1/app.py` for verbose logging
- Check `.env` — missing OPENAI_API_KEY will fail silently in Streamlit
- Session state in Streamlit persists across reruns; graph compilation should be cached with `@st.cache_resource`

## Development Workflow

1. **Before modifying:** Read the relevant version's spec and implementation-plan (e.g., `agents/v1/specs/spec.md` for V1 changes, `agents/v2/spec.md` for V2)
2. **When adding features:** Keep them in agent version folders; only add to `shared/` if truly reusable across versions
3. **When changing shared code:** Test with all agent versions that depend on it
4. **When adding prompts:** Remember JSON output format requires prompt to mention "JSON"
5. **When debugging:** Run tests first (`pytest agents/v1/ -v`), then manual validation, then Streamlit app
6. **Before committing:** Ensure all tests pass and Chroma vector store is clean (run ingest if adding PDF sections)

## External Resources

- **V1 Specifications:**
  - **Implementation Plan:** `agents/v1/specs/implementation-plan.md`
  - **Technical Spec:** `agents/v1/specs/spec.md`
  - **Research Notes:** `agents/v1/specs/research.md`
- **V2 Specifications:**
  - **Implementation Plan:** `agents/v2/implementation-plan.md`
  - **Technical Spec:** `agents/v2/spec.md`
  - **Research Notes:** `agents/v2/research.md`
- **OpenAI API Docs:** Structured outputs require `response_format={"type": "json_object"}`
- **LangGraph Docs:** State machine pattern, node routing, message persistence
- **Chroma Docs:** Vector store setup, filtering syntax
