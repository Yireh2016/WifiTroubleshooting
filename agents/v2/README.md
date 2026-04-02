# V2 WiFi Troubleshooting Agent

The V2 WiFi Troubleshooting Agent extends V1's single-model MVP with multi-router support, conversation mode selection, and LLM-driven adaptation.

## What's New in V2

- **Multi-router model support** — Single Chroma collection with metadata-based filtering for Linksys EA6350, TP-Link Archer C1200, Netgear WNR854T
- **Router model discovery** — 3-retry gate with available model guidance before proceeding
- **Conversation mode selector** — User chooses self-serve (patient, step-by-step) or agent-assisted (concise, technical)
- **LLM-driven literacy detection** — Self-serve mode analyzes user vocabulary dynamically (no static mapping)
- **Manual-aware qualifier** — Retrieves manual sections before asking qualification questions
- **Reboot method selection** — LLM decides physical vs app reboot based on connectivity context
- **Generic reboot guidance** — Model-agnostic instructions (not Linksys-specific)

## Architecture

### State Machine (9 Nodes)

```
[WELCOME] → asks for router model
[DISCOVER_MODEL] → retries up to 3 times if model not found
[UNSUPPORTED_MODEL_EXIT] → exits after 3 failed attempts
[QUALIFY] → retrieves manual context, asks qualifying questions
[SELECT_REBOOT_METHOD] → LLM decides physical vs app based on connectivity
[RETRIEVAL] → fetches reboot steps from Chroma with model filter
[GUIDE_REBOOT] → walks user through steps one at a time
[CHECK_RESOLUTION] → asks if issue is resolved
[CLOSE_SUCCESS] / [APOLOGIZE_AND_EXIT] / [GRACEFUL_EXIT] → terminal nodes
```

### State Schema (`shared/state/state_v2.py`)

Extends V1 `ConversationState` with:
- `router_model` — Normalized model name (e.g., "EA6350", "ARCHER C1200")
- `router_model_attempts` — Counter (0-3) for discovery gate
- `manual_context` — Cached manual sections retrieved during qualify
- `reboot_method` — Selected method ("physical" or "app")
- `conversation_mode` — User's choice ("self_serve" or "agent_assisted")
- `has_internet_on_other_device` — For app reboot gating

### Prompts (`shared/prompts/v2_prompts.py`)

All 10 prompts are mode-aware and model-agnostic:
- WELCOME_DISCOVER_MODEL_PROMPT
- DISCOVER_MODEL_RETRY_PROMPT
- UNSUPPORTED_MODEL_EXIT_PROMPT
- V2_QUALIFY_PROMPT (with manual context)
- V2_GUIDE_REBOOT_PROMPT (with method selection)
- V2_SELECT_REBOOT_METHOD_PROMPT
- V2_CHECK_RESOLUTION_PROMPT
- V2_GRACEFUL_EXIT_PROMPT
- V2_CLOSE_SUCCESS_PROMPT
- V2_APOLOGIZE_EXIT_PROMPT

## How to Run

### Setup

```bash
# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate
# On Windows: venv\Scripts\activate

# 2. Copy environment
cp .env.example .env
# Edit .env with your OPENAI_API_KEY

# 3. Install dependencies
pip install -r agents/v2/requirements.txt

# 4. Ingest PDFs into Chroma (one-time, creates chroma_db/v2/)
python shared/rag/ingest_v2.py --pdf shared/data/user_guide_EA6350.pdf --model EA6350 --brand Linksys
python shared/rag/ingest_v2.py --pdf shared/data/Archer_C1200\(US\)_V1_UG.pdf --model "Archer C1200" --brand "TP-Link"
python shared/rag/ingest_v2.py --pdf shared/data/wnr854t_setup_manual.pdf --model WNR854T --brand Netgear

# 5. Run the Streamlit app
streamlit run agents/v2/app.py
```

### Testing

```bash
# Run all V2 tests
pytest agents/v2/ -v

# Run specific test module
pytest agents/v2/test_nodes.py -v

# Run with coverage
pytest agents/v2/ --cov=agents.v2 --cov=shared
```

## Design Decisions

### Single Chroma Collection with Metadata Filtering

V2 uses a single `chroma_db/v2/` collection shared across all models, with metadata filters (`model_name`, `brand`, `language`) for retrieval. This allows:
- Easy addition of new router models (just ingest + add metadata)
- Single embedding space for all models
- Simplified app state management

Alternative considered: Separate Chroma collection per model. Rejected: unnecessary complexity for small scale.

### LLM-Driven Literacy Detection

Self-serve mode analyzes user vocabulary dynamically in prompts rather than using static literacy level categorization. This:
- Adapts to each user's language in real-time
- Avoids awkward meta-questions ("What's your tech level?")
- Simplifies the state schema (no `detected_literacy_level` field)

Literacy detection is **self-serve only**. Agent-assisted mode uses technical language throughout.

### No `prompt_config.py`

V1 had a `prompt_config.py` for static mode/model settings. V2 removes this:
- All mode adaptation happens in prompts (system message context)
- User selects mode via Streamlit radio at session start
- LLM handles language adaptation dynamically

Result: Simpler codebase, more flexible behavior.

### Manual-Aware Qualifier

The qualify node retrieves relevant manual sections before asking questions. This:
- Ensures questions are grounded in the specific router's manual
- Allows the LLM to reference manual sections in responses
- Improves relevance vs generic troubleshooting

Manual context is cached in state to avoid re-retrieval.

### No Local Admin Edge Case

V2 does not handle the "local admin" edge case from V1 (router accessible only from admin dashboard). This:
- Simplifies the state machine and routing
- Deferred to V3 when multi-user scenarios are needed

### App vs Physical Reboot Selection

V2 uses an LLM node (`select_reboot_method`) to decide between physical and app reboot. Rules:
- **Physical** — Always available (power cord disconnect)
- **App** — Only if user has internet on another device AND manual mentions web/app reboot

This allows flexible, context-aware recommendations vs hard-coded rules.

## Differences from V1

| Feature | V1 | V2 |
|---------|----|----|
| Router models | Linksys EA6350 only | EA6350, Archer C1200, Netgear WNR854T |
| Model discovery | N/A | 3-retry gate with guidance |
| Conversation mode | Single (patient, step-by-step) | User chooses self-serve or agent-assisted |
| Literacy detection | Static (V1 doesn't have it) | Dynamic, LLM-driven (self-serve) |
| Qualifier | Blind qualification | Manual-aware (retrieves before asking) |
| Reboot methods | Physical only | LLM selects physical or app |
| Chroma vectors | V1-only (language filter: pages 0-17) | V2-only (langdetect per-page) |
| Shared modules | V1-specific (base_prompts.py, state_v1.py) | V2-specific (v2_prompts.py, state_v2.py) + shared RAG/retriever |
| V1 modified? | N/A | No — fully isolated |

## Known Limitations

- **English only** — langdetect filters to English pages; other languages are excluded
- **No local admin edge case** — Deferred to V3
- **No evaluation pipeline** — Deferred to V3 (would include Langsmith golden dataset, evaluators, experiments)
- **Single language in prompts** — No multi-language support yet

## File Structure

```
agents/v2/
├── app.py              # Streamlit UI with mode selector
├── graph.py            # 9-node LangGraph state machine
├── nodes.py            # Node functions + routing logic
├── requirements.txt    # V2 dependencies
├── conftest.py         # Pytest fixtures (mocks)
├── test_nodes.py       # Unit tests for nodes
├── test_graph.py       # Graph structure + routing tests
├── test_scenarios.py   # End-to-end scenario tests
└── README.md           # This file

shared/
├── state/
│   ├── state_v1.py    # V1 state (unchanged)
│   └── state_v2.py    # V2 state schema (new)
├── prompts/
│   ├── base_prompts.py   # V1 prompts (unchanged)
│   └── v2_prompts.py     # V2 prompts (new)
├── rag/
│   ├── ingest_v1.py      # V1 ingest (unchanged)
│   ├── ingest_v2.py      # V2 ingest with langdetect (new)
│   ├── retriever.py      # Shared retrieval (unchanged)
│   └── verify_retrieval.py  # Verification script (unchanged)
└── data/
    ├── user_guide_EA6350.pdf      # Linksys manual
    ├── Archer_C1200(US)_V1_UG.pdf # TP-Link manual
    └── wnr854t_setup_manual.pdf   # Netgear manual

chroma_db/
├── v1/                 # V1 vectors (unchanged)
└── v2/                 # V2 vectors (multi-model)
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'langdetect'`
```bash
pip install langdetect>=1.0.9
```

### `OPENAI_API_KEY` not set
Create or update `.env`:
```bash
OPENAI_API_KEY=sk-...
LANGSMITH_API_KEY=ls_...  # Optional, for tracing
```

### `chroma_db/v2/` is empty or missing
Ingest PDFs:
```bash
python shared/rag/ingest_v2.py --pdf shared/data/user_guide_EA6350.pdf --model EA6350 --brand Linksys
```

### Tests fail with `MockLLM` errors
Ensure `conftest.py` is in `agents/v2/` and pytest finds it:
```bash
pytest agents/v2/ -v --tb=short
```

## Next Steps (V3)

- Evaluation pipeline (Langsmith golden dataset, evaluators, experiments)
- Human escalation / Supervisor node for edge cases
- Multi-language support
- Structured logging for observability
- Local admin detection and handling
