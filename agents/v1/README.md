# RouteThis V1 — Physical Reboot Agent

## What This Version Does

V1 is the MVP: a conversational WiFi troubleshooting agent that guides users through resolving connectivity issues with a Linksys EA6350 router. The agent qualifies whether the issue is appropriate for a physical reboot (all devices offline, no ISP outage, hasn't been rebooted excessively), retrieves step-by-step reboot instructions from the user manual via RAG, and walks the user through each step.

**Scope:** Physical reboot only. No app-based reboot, no multi-router support, no authentication.

## How to Run It

From the repo root:

```bash
# 1. Set up environment (edit .env with your OpenAI API key)
cp .env.example .env
# Then add: OPENAI_API_KEY=sk-...

# 2. Install dependencies
pip install -r agents/v1/requirements.txt

# 3. Ingest PDF into Chroma vector store (one-time)
python shared/rag/ingest_v1.py

# 4. Verify RAG retrieval is working
python shared/rag/verify_retrieval.py --version v1

# 5. Run the Streamlit app
streamlit run agents/v1/app.py
```

Then visit `http://localhost:8501` in your browser.

## What's Reused from shared/

- **`shared/rag/ingest_v1.py`** — PDF → sections → embeddings → Chroma store (`chroma_db/v1/`)
- **`shared/rag/retriever.py`** — Retrieval logic with metadata filtering (model, language, section)
- **`shared/state/state_v1.py`** — Pydantic state schema (ConversationState with message history, reboot_appropriate, current_step, rag_context, exit_reason)
- **`shared/prompts/`** — Prompt templates for each node, injected with RAG context, step numbers, and exit reasons
- **`shared/data/user_guide_EA6350.pdf`** — Single source of truth (pages 0–17, English only)

## Design Decisions Specific to V1

### Why physical reboot only?

The Linksys Smart Wi-Fi app method requires the router to have an active WAN connection — Linksys's servers need to reach the router to issue the reboot command. In the primary use case (all devices offline), the router has no internet. Offering the app method there would be a dead end. V2 adds the app method with proper connectivity-aware gating.

### Why single router model?

Focusing on the Linksys EA6350 for V1 allows us to validate the entire end-to-end pipeline — ingest, retrieval, qualification, step-by-step guidance — with one well-known manual. Multi-router support (V3) requires an evaluation pipeline to ensure quality across models.

### Why language filtering upfront?

The EA6350 manual is 50% English, 50% Spanish. Without language filtering at ingest, retrieval can return Spanish steps and the agent responds in Spanish. Language filtering is the first step in the ingest pipeline — before sectioning — so only English content reaches the vector store.

### Why LLM-based section detection?

Each router manufacturer structures their manual differently. Hard-coding "Troubleshooting" breaks when you add a TP-Link manual. The ingest pipeline uses an LLM to map any manual's sections onto a fixed canonical taxonomy (`troubleshooting`, `setup`, `security`, etc.). Retrieval always queries by canonical tag — the agent and retrieval code never change when you add a new router model.

### Why section-level storage instead of fixed-size chunking?

Fixed-size chunking risks fragmenting numbered steps across chunk boundaries — retrieval returns steps 1–3 but not 4–5, or returns a step with no heading. Section-level storage keeps each complete procedure as one coherent unit. For a support agent giving accurate step-by-step instructions, fragmentation is a correctness issue, not a quality preference.

### Why separate Chroma stores per version?

V1 and V2 use different ingest pipelines (page range vs per-page language detection) and may produce different chunks. Separate stores at `chroma_db/v1/` and `chroma_db/v2/` prevent cross-version contamination.

### Why RAG fires only in GUIDE_REBOOT?

Qualification is pure conversational reasoning — the manual isn't needed to decide if all devices are offline. Firing retrieval on every qualifying exchange adds latency and cost with zero benefit. Context is retrieved once (in GUIDE_REBOOT), cached in state, and reused for all subsequent step-guidance messages.

## Known Limitations of V1

- **App reboot method not available** — connectivity dependency (see design decisions)
- **Single router model** — EA6350 only; multi-model support in V3
- **No session persistence** — conversation resets on page refresh
- **Non-deterministic section detection** — LLM segmentation is not idempotent; ingest includes deduplication to prevent re-ingesting the same section twice
- **No user authentication** — no login, session tracking, or audit log
- **No escalation path** — after 3 inconclusive qualify exchanges, conversation continues indefinitely (V3 adds human escalation)

## Testing

```bash
# Run all tests
pytest agents/v1/ -v

# Key test files:
# - test_graph.py: Graph construction and routing
# - test_scenarios.py: All 8 Definition of Done scenarios
# - test_app_manual.py: Streamlit app smoke tests
```

See root `README.md` for full testing strategy.

## Debugging

- **RAG issues:** Run `python shared/rag/verify_retrieval.py --version v1`
- **Graph routing:** Inspect state in `test_graph.py` output
- **Streamlit errors:** Use `streamlit run --logger.level=debug agents/v1/app.py`
- **Missing Chroma store:** Re-run `python shared/rag/ingest_v1.py`
