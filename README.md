# RouteThis — Conversational WiFi Troubleshooting Agent

## What This Project Is

**RouteThis** is a conversational AI that guides users through WiFi troubleshooting for their home routers, using manufacturer manuals as the source of truth. It qualifies whether an issue is appropriate for a physical reboot through guided questions, retrieves step-by-step reboot instructions via RAG (Retrieval-Augmented Generation), and walks users through each step with confirmations. The project is built as a versioned agent architecture with three independently runnable agents (V1, V2, V3) of increasing capability, allowing each version to be frozen and evaluated separately.

## How to Navigate the Repo

### Core Agents

- **`agents/v1/`** — MVP: Physical reboot guidance for Linksys EA6350. Start here.
  - `app.py` — Streamlit UI
  - `graph.py` — LangGraph state machine (7 nodes, conditional routing)
  - `nodes.py` — Node functions (qualify, guide_reboot, check_resolution, etc.)
  - `README.md` — V1-specific docs
  - `requirements.txt` — V1 dependencies

- **`agents/v2/`** — [Future] Enhanced experience: app/browser reboot with connectivity gating, multi-language support, literacy detection. Will not modify V1.

- **`agents/v3/`** — [Future] Production readiness: evaluation pipeline, guardrails, multi-router support, human escalation path. Will not modify V1 or V2.

### Shared Components

**`shared/`** — Code reused by all agent versions. Never imported directly between agents (each version is independent).

- **`shared/rag/`** — PDF ingestion and retrieval
  - `ingest_v1.py` — Parse PDF → English pages → LLM segmentation → embeddings → Chroma (`chroma_db/v1/`)
  - `retriever.py` — Query → metadata filter (model, language, section) → ranked chunks
  - `verify_retrieval.py` — Test retrieval with sample queries

- **`shared/state/`** — Pydantic state schemas
  - `state_v1.py` — ConversationState: messages, reboot_appropriate, current_step, rag_context, exit_reason

- **`shared/prompts/`** — Prompt templates for each agent node
  - Injected with dynamic context: RAG results, step numbers, exit reasons
  - Designed to force JSON output via OpenAI's `response_format`

- **`shared/data/`** — User guide PDFs (single source of truth)
  - `user_guide_EA6350.pdf` — Linksys EA6350 English manual (pages 0–17) [V1]
  - `Archer_C1200(US)_V1_UG.pdf` — TP-Link Archer C1200 English manual [V2]
  - `wnr854t_setup_manual.pdf` — Netgear WNR854T English manual [V2]

### Documentation & Testing

- **`CLAUDE.md`** — Development workflow, patterns, debugging tips
- **Version-specific docs:**
  - **`agents/v1/specs/spec.md`** — V1 system design, conversation flows, Definition of Done
  - **`agents/v1/specs/implementation-plan.md`** — V1 development strategy and progress
  - **`agents/v1/specs/research.md`** — V1 PDF analysis and design rationale
  - **`agents/v2/spec.md`** — V2 multi-model architecture and enhanced features
  - **`agents/v2/implementation-plan.md`** — V2 phased development plan
  - **`agents/v2/research.md`** — V2 multi-router design analysis
- **`agents/v1/test_*.py`** — Unit and integration tests (8 end-to-end scenarios)
- **`.claude/`** — Claude Code config and custom skills

## Quickstart

**Prerequisites:** Python 3.9+, OpenAI API key (sk-...)

```bash
# 1. Clone and set up
cd routeThis
cp .env.example .env
# Edit .env: add your OPENAI_API_KEY

# 2. Install V1 dependencies
pip install -r agents/v1/requirements.txt

# 3. Ingest the PDF into Chroma (one-time)
python shared/rag/ingest_v1.py

# 4. Verify RAG retrieval
python shared/rag/verify_retrieval.py --version v1

# 5. Run the agent
streamlit run agents/v1/app.py
```

Then visit `http://localhost:8501` and start a conversation:

> **User:** "My WiFi is down"
> **Agent:** "I can help with that. Are all your devices offline, or just one?"
> **User:** "All devices"
> **Agent:** "Got it. Have you rebooted the router recently?"
> ... [after qualification] ...
> **Agent:** "Let's reboot your router. First, unplug it from power..."

## Architecture Overview

### Multi-Agent Structure

```
┌─────────────────────────────────────────┐
│         User (Streamlit UI)             │
└────────────────┬────────────────────────┘
                 │
    ┌────────────▼────────────┐
    │   agents/v1/app.py      │ ◄── V1 frozen at submission
    │   (entry point)         │
    └────────────┬────────────┘
                 │
    ┌────────────▼────────────────────────┐
    │   agents/v1/graph.py                │
    │   (LangGraph state machine)         │
    │                                     │
    │   qualify ──► reboot_appropriate?  │
    │        └─► graceful_exit           │
    │                                     │
    │   guide_reboot ──► retrieval        │
    │       (RAG cached)                  │
    │                                     │
    │   check_resolution                  │
    │        └─► close_success or         │
    │            apologize_and_exit       │
    └────────────┬───────────────────────┘
                 │
    ┌────────────▼─────────────────┐
    │  shared/ (reused by all)     │
    │                              │
    │  ├─ rag/                     │
    │  │  ├─ ingest_v1.py          │
    │  │  └─ retriever.py          │
    │  │                           │
    │  ├─ state/state_v1.py        │
    │  ├─ prompts/                 │
    │  └─ data/EA6350.pdf          │
    └────────────┬─────────────────┘
                 │
    ┌────────────▼──────────┐
    │  chroma_db/v1/        │
    │  (vector store)       │
    └───────────────────────┘
```

### Shared Module Dependencies

| Module | Purpose | Used By |
|--------|---------|---------|
| `shared/rag/ingest_v1.py` | Ingest pipeline: PDF → sections → embeddings | `shared/rag/retriever.py` |
| `shared/rag/retriever.py` | Metadata-filtered retrieval from Chroma | `agents/v1/nodes.py` (GUIDE_REBOOT) |
| `shared/state/state_v1.py` | Pydantic state schema for agent | `agents/v1/graph.py`, `agents/v1/nodes.py` |
| `shared/prompts/` | Prompt templates (JSON-formatted) | `agents/v1/nodes.py` |
| `shared/data/` | PDFs (source of truth) | `shared/rag/ingest_v1.py` |

### Data Flow: RAG Pipeline

```
PDF (EA6350 manual, pages 0–17)
  │
  ▼ [ingest_v1.py]
Language filter (English only)
  │
  ▼
LLM-based section detection
  Sections: [intro, setup, troubleshooting, ..., faq]
  │
  ▼
Per-section embeddings (OpenAI text-embedding-3-small)
  │
  ▼
Chroma vector store (chroma_db/v1/)
  ├─ Metadata: {"model_name": "EA6350", "language": "en", "section_tag": "troubleshooting"}
  │
  └─ On query (GUIDE_REBOOT node):
     1. Retrieve: "how to reboot router" → filtered by EA6350 + English + troubleshooting
     2. Cache in state["rag_context"]
     3. Inject into prompt for guide_reboot and check_resolution nodes
```

## Key Design Decisions

### Why retrieval fires only in GUIDE_REBOOT

Qualification is pure conversational reasoning — determining if all devices are offline requires no manual context. Firing retrieval on every qualifying exchange adds latency (~200ms) and API cost with zero benefit. Context is retrieved once (GUIDE_REBOOT entry), cached in state, reused for all step-guidance messages.

### Why physical reboot only in V1

The Linksys Smart Wi-Fi app requires the router to have active WAN — Linksys's servers must reach the router to issue commands. In the primary use case (all devices offline), the router has no WAN. Offering the app method there is a dead end. V2 adds proper connectivity-aware gating; V1 focuses on physical reboot.

### Why section-level storage instead of fixed-size chunking

Fixed-size chunking risks fragmenting numbered steps across boundaries — retrieval returns steps 1–3 but skips 4–5, or returns step 3 with no "reboot procedure" heading context. Section-level storage keeps each procedure as one coherent unit. For a troubleshooting agent giving step-by-step instructions, fragmentation is a correctness issue, not a preference.

### Why LLM-based section detection instead of hard-coded headers

Different manufacturers structure manuals differently (TP-Link, Netgear, ASUS all use different section names). Hard-coding "Troubleshooting" breaks when you add a new model. The ingest pipeline uses an LLM to map any manual's sections onto a fixed canonical taxonomy (`troubleshooting`, `setup`, `security`, etc.). Retrieval always queries by canonical tag; adding a new router model requires no code changes.

### Why canonical section taxonomy

The filter `{"section_tag": "troubleshooting"}` works identically regardless of whether the manual calls it "Troubleshooting", "FAQ & Troubleshooting Guide", or "Problem Solving". The taxonomy abstracts structural differences between manufacturers, making the agent and retrieval code manufacturer-agnostic.

### Why language filtering runs first in the pipeline

The EA6350 manual is written in English, Spanish and more languages. Without language filtering at ingest, retrieval can return Spanish steps and the agent responds in Spanish. Language filtering is the first step — before sectioning — so only English content reaches the vector store. V1 uses page range (deterministic); V2 upgrades to per-page language detection for unknown manuals.

### Why each agent version has its own Chroma store

V1 and V2 use different ingest pipelines (page range vs per-page language detection) and may produce different chunks. Separate stores at `chroma_db/v1/` and `chroma_db/v2/` prevent cross-version contamination; each agent always queries content built with its own ingest logic.

## Known Limitations

- **App reboot method not in V1** — connectivity dependency (see design decisions). V2 adds with proper gating.
- **Single router model** — EA6350 only in V1/V2. V3 adds multi-model support.
- **No session persistence** — conversation resets on page refresh. No database backend.
- **No authentication** — no login, user tracking, or audit log.
- **Non-deterministic section detection** — LLM segmentation isn't idempotent. Ingest includes deduplication to prevent duplicate sections.
- **No escalation path** — after 3 inconclusive qualify exchanges, conversation continues. V3 adds human escalation.
- **No structured logging** — no per-conversation logging or analytics. V3 adds logging infrastructure.

## Future Work

### V2 — Enhanced Experience (In Design)

- **Multi-router support:** Archer C1200, Netgear WNR854T (added to shared/data/)
- **App/browser reboot method** with connectivity-aware gating (only offer if router has WAN)
- **Multi-language support** via per-page language detection (`langdetect`)
- **Literacy detection** from opening message (self-serve vs agent-assisted mode)
- **Router discovery flow** via LLM-driven routing decisions
- **LangSmith tracing** for observability and debugging
- Separate `chroma_db/v2/` store with metadata-based model filtering

See `agents/v2/spec.md`, `implementation-plan.md`, and `research.md` for full design details.

### V3 — Production Readiness

- **Evaluation pipeline** (`agents/v3/eval/`) with golden dataset and LLM-as-judge scoring
- **Guardrails:** scope enforcement, hallucination prevention, prompt injection defense
- **Multi-router support** with CLI-driven ingest for new models
- **Structured logging** per conversation (request ID, node execution, LLM payloads, latencies)
- **Human escalation path** after N inconclusive exchanges

See `agents/v3/README.md` (future) for full scope.

### Beyond V3

- Multi-site awareness for corporate customers (manage routers across multiple locations)
- Resolution rate alerting and PagerDuty integration for support teams
- Fine-tuning on resolved conversation dataset
- Live ISP outage API integration (skip reboot when outage confirmed)
- Tenant isolation for multi-customer SaaS deployments

## Testing Strategy

### Unit Tests (Phase 2–4)

- **`shared/rag/`** — Ingest produces correct sections; retrieval returns troubleshooting content
- **`shared/state/`** — State schema instantiation and prompt formatting
- **`agents/v1/graph.py`** — Graph compilation, node routing, state updates

### Integration Tests (Phase 5–6)

All tests in `agents/v1/test_*.py`:

```bash
# Run all
pytest agents/v1/ -v

# Key scenarios (Definition of Done):
pytest agents/v1/test_scenarios.py -v
```

**8 Scenarios:**
1. Single device affected → graceful exit
2. ISP outage → graceful exit
3. Already rebooted twice → graceful exit
4. Loose cable found and fixed → success (no reboot)
5. Full reboot flow → resolved
6. Full reboot flow → not resolved
7. Empty/off-topic input → no crash, stays in qualify
8. Power outage detected → fast-track to reboot

### Automated Verification Gates

From repo root, all must pass:

```bash
# Setup
cp .env.example .env  # (with real key)
pip install -r agents/v1/requirements.txt
python shared/rag/ingest_v1.py

# Verification
python shared/rag/verify_retrieval.py --version v1
streamlit run agents/v1/app.py --help  # no crash on import

# Check .gitignore
grep -q "^.env$" .gitignore
grep -q "^chroma_db/$" .gitignore
```

### Manual Verification (Definition of Done)

- [ ] All 8 scenarios above produce correct outcomes
- [ ] RAG context retrieved once on GUIDE_REBOOT entry, cached in state
- [ ] Physical reboot guided step-by-step with observable confirmations
- [ ] No crash on empty input, off-topic message, mid-flow interruption
- [ ] `agents/v1/README.md` complete with all required sections
- [ ] Global `README.md` complete with all required sections

## Development Workflow

1. **Before modifying code:** Read the relevant version's spec and implementation-plan (e.g., `agents/v1/specs/spec.md` for V1 changes)
2. **When adding features:** Keep in agent version folders; only add to `shared/` if reusable across versions
3. **When changing shared code:** Test with all agent versions that depend on it
4. **When adding prompts:** Remember JSON output requires prompt to mention "JSON"
5. **When debugging:** Run tests first (`test_graph.py`), then manual validation, then Streamlit app
6. **Before committing:** Ensure all tests pass; re-ingest if adding PDF sections

## External Resources

- **V1 Documentation:**
  - **Implementation Plan:** `agents/v1/specs/implementation-plan.md`
  - **Technical Spec:** `agents/v1/specs/spec.md`
  - **Research Notes:** `agents/v1/specs/research.md`
- **V2 Documentation:**
  - **Implementation Plan:** `agents/v2/implementation-plan.md`
  - **Technical Spec:** `agents/v2/spec.md`
  - **Research Notes:** `agents/v2/research.md`
- **OpenAI API:** [Structured outputs](https://platform.openai.com/docs/guides/structured-outputs) (response_format)
- **LangGraph:** [Documentation](https://docs.langchain.com/oss/python/langgraph/)
- **Chroma:** [Documentation](https://docs.trychroma.com/)
- **Streamlit:** [Chat API](https://docs.streamlit.io/develop/api-reference/chat)
