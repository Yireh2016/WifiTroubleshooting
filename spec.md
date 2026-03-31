# RouteThis WiFi Assistant — Versioned Technical Spec

## Challenge Summary

Build a conversational LLM interface that assists users in solving WiFi
connectivity problems through a guided router reboot, using the Linksys
EA6350 user guide (`user_guide_EA6350.pdf`) as the source of truth for reboot steps.

**Interview date:** Thursday, April 2nd, 10:30 AM — on-site, Kitchener
**Deliverable:** Public GitHub repo + run instructions to kam.deep@routethis.com
**Strategy:** Ship V1 first. It must be solid, runnable, and impressive on its
own. V2 and V3 are additive — build them only if V1 is done and tested.
Everything not built must be documented in the README to demonstrate
production-grade thinking.

---

## Versioning Philosophy

| Version | Goal | Time Estimate |
|---|---|---|
| **V1** | Working MVP — lands the job | 4–5 hrs |
| **V2** | Wow effect — shows product thinking | +2–3 hrs |
| **V3** | Production readiness — shows senior engineering instincts | +2–3 hrs |

---

## Multi-Agent Architecture Principle

Each version is a **standalone, independently runnable agent** living in
its own folder. V2 never modifies V1 code. V3 never modifies V1 or V2
code. Each agent has its own `README.md` describing exactly what it does
and how to run it.

Code that is genuinely reusable across versions lives in a single
`shared/` folder at the repo root. Agents import from `shared/` — they
do not copy code between agent folders. When a shared component needs to
be extended for V2 or V3, a new version of that component is added to
`shared/` alongside the original, and the consuming agent imports the
version it needs.

This structure means:
- V1 always runs exactly as submitted — no regressions from later work
- The repo tells a clear story of incremental capability growth
- Shared logic (PDF parsing, Chroma setup, base state schema) is written
  once and maintained in one place

---

## Monorepo Folder Structure

```
routethis-wifi-assistant/
│
├── README.md                        # Global readme — project overview,
│                                    # versioning rationale, how to navigate
│                                    # the repo, future work for all versions
│
├── shared/                          # All reusable code — imported by agents
│   ├── rag/
│   │   ├── ingest_v1.py             # Page-range language filter + LLM segmentation
│   │   ├── ingest_v2.py             # langdetect language filter + LLM segmentation
│   │   ├── retriever.py             # Retrieval wrapper with metadata filtering
│   │   └── verify_retrieval.py      # Verification script — run after any ingest
│   ├── state/
│   │   ├── state_v1.py              # Base Pydantic state schema (V1 fields)
│   │   └── state_v2.py              # Extended schema (V1 + V2 fields)
│   ├── prompts/
│   │   ├── base_prompts.py          # Shared prompt templates (qualify, exit, etc.)
│   │   └── prompt_config.py         # get_prompt_config() — mode/literacy injection
│   └── data/
│       └── user_guide_EA6350.pdf           # Single source of truth for the manual
│
├── agents/
│   ├── v1/                          # MVP — standalone, independently runnable
│   │   ├── README.md                # V1-specific: what it does, how to run it,
│   │   │                            # design decisions, known limitations
│   │   ├── app.py                   # Streamlit entry point
│   │   ├── graph.py                 # LangGraph state machine
│   │   ├── nodes.py                 # Node functions
│   │   └── requirements.txt         # V1 dependencies only
│   │
│   ├── v2/                          # Enhanced — standalone, does not modify v1
│   │   ├── README.md                # V2-specific: what's new, how to run it,
│   │   │                            # design decisions for V2 features
│   │   ├── app.py                   # Streamlit entry point
│   │   ├── graph.py                 # LangGraph state machine (extends V1 graph)
│   │   ├── nodes.py                 # Node functions (extends V1 nodes)
│   │   └── requirements.txt         # V2 dependencies (superset of V1)
│   │
│   └── v3/                          # Production-ready — standalone
│       ├── README.md                # V3-specific: what's new, how to run it,
│       │                            # production readiness decisions
│       ├── app.py                   # Streamlit entry point
│       ├── graph.py                 # LangGraph state machine (extends V2 graph)
│       ├── nodes.py                 # Node functions (extends V2 nodes)
│       ├── eval/
│       │   ├── golden_dataset.json  # ~20 reference conversations
│       │   └── run_eval.py          # Eval pipeline runner
│       └── requirements.txt         # V3 dependencies (superset of V2)
│
├── chroma_db/                       # Persisted vector store — gitignored
│   ├── v1/                          # Separate store per agent version
│   ├── v2/                          # (langdetect may produce different chunks)
│   └── v3/
│
├── .env.example                     # All env vars across all versions documented
└── .gitignore                       # .env, chroma_db/, __pycache__/
```

---

## Shared Module Ownership

This table defines what lives in `shared/` and which agent version
introduces each component. Later agents import — they never copy.

| Module | Introduced in | Used by |
|---|---|---|
| `shared/rag/ingest_v1.py` | V1 | V1, V3 |
| `shared/rag/ingest_v2.py` | V2 | V2, V3 |
| `shared/rag/retriever.py` | V1 | V1, V2, V3 |
| `shared/rag/verify_retrieval.py` | V1 | V1, V2, V3 |
| `shared/state/state_v1.py` | V1 | V1 |
| `shared/state/state_v2.py` | V2 | V2, V3 |
| `shared/prompts/base_prompts.py` | V1 | V1, V2, V3 |
| `shared/prompts/prompt_config.py` | V2 | V2, V3 |
| `shared/data/user_guide_EA6350.pdf` | V1 | V1, V2, V3 |

---

## Import Convention

Agents import from `shared/` using relative paths. Since agents are run
from their own folder, add the repo root to `sys.path` at the top of
each agent's `app.py`:

```python
# agents/v1/app.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.rag.retriever import build_retriever
from shared.state.state_v1 import ConversationState
from shared.prompts.base_prompts import QUALIFY_PROMPT, EXIT_PROMPT
```

This keeps imports clean without requiring a package install step.

---

---

# V1 — MVP (Must Ship)

**Folder:** `agents/v1/`
**Shared modules used:** `shared/rag/ingest_v1.py`, `shared/rag/retriever.py`,
`shared/rag/verify_retrieval.py`, `shared/state/state_v1.py`,
`shared/prompts/base_prompts.py`, `shared/data/user_guide_EA6350.pdf`

---

## Functional Scope

### In scope
- Qualify whether a reboot is appropriate (one question at a time)
- Guide through the **physical reboot method only** (power cord)
- Check if issue is resolved post-reboot
- Graceful exits for: single device, already rebooted, cables loose/fixed,
  ISP outage suspected
- Reboot steps retrieved via RAG from `user_guide_EA6350.pdf` — never hardcoded

### Out of scope for V1
- App/browser reboot method (deferred to V2 — connectivity rationale below)
- Literacy detection and adaptive language
- Multi-router model support
- Conversation mode switching
- Evaluation pipeline

---

## State Machine

```
[START]
   |
[QUALIFY]
   |-- not appropriate --> [GRACEFUL_EXIT]
   |-- appropriate ------> [PRE_REBOOT_CONFIRM]
                                |
                          [GUIDE_REBOOT]  <-- RAG context injected once here
                                |
                          [CHECK_RESOLUTION]
                           |-- resolved -------> [CLOSE_SUCCESS]
                           |-- not resolved ---> [APOLOGIZE_AND_EXIT]
```

---

## State Schema — V1 (`shared/state/state_v1.py`)

```python
class ConversationState(BaseModel):
    messages: list[BaseMessage]
    reboot_appropriate: Optional[bool] = None
    issue_resolved: Optional[bool] = None
    current_step: int = 0
    current_node: str = "qualify"
    rag_context: Optional[str] = None  # populated once on GUIDE_REBOOT entry
```

---

## Qualifying Logic

Ask one question at a time. Branch on the following signals:

| Signal | Decision |
|---|---|
| Only one device affected, others work | Exit — not a router issue |
| Cables not checked | Ask user to check first; if loose fixes it, close success |
| Neighbour also affected | Exit — likely ISP outage |
| Already rebooted twice, no improvement | Exit — escalate to ISP |
| Power outage recently | Fast-track to reboot — strong signal |
| All devices down, cables confirmed, no recent reboot | Proceed to reboot |

**Key principle:** Ask for observables, not acknowledgements.
Not "are the cables plugged in?" but "can you check the cable going into
the yellow Internet port on the back of the router and tell me if it's
firmly seated?"

---

## Reboot Steps (Physical — from user_guide_EA6350.pdf via RAG)

1. Disconnect the power cord from both the router and the modem.
2. Wait 10 seconds, then reconnect the power cord to the modem first.
3. Wait until the modem's online indicator stops blinking (~2 minutes).
4. Reconnect the power cord to the router.
5. Wait until the router's power indicator stops blinking, then wait
   2 more minutes before testing the connection.

> These steps must come from RAG retrieval. If retrieval fails or returns
> irrelevant content, fall back to: "Please refer to your router's manual
> for reboot instructions." Never let the LLM improvise steps.

---

## RAG Architecture (`shared/rag/ingest_v1.py`)

### Where Retrieval Happens

Retrieval fires **exactly once — at entry to the GUIDE_REBOOT node.**

The qualify step is pure conversational reasoning. No document context
is needed to ask whether all devices are offline or cables are checked.
Retrieving during qualify adds latency to every exchange with zero benefit
and risks bleeding irrelevant content into the qualifying prompt.

The retrieved context is stored in `state.rag_context` on first entry
to `GUIDE_REBOOT` and reused for every subsequent step confirmation.
It is never re-retrieved mid-flow.

```python
# agents/v1/nodes.py
def guide_reboot(state: ConversationState) -> ConversationState:
    if state.rag_context is None:  # retrieve once, cache in state
        results = retriever.invoke(
            "router reboot steps power cord",
            filter={
                "model_name": "EA6350",
                "language": "en",
                "section_tag": "troubleshooting"
            }
        )
        state.rag_context = results[0].page_content if results else None
    ...
```

### Ingest Pipeline Flow

```
PDF file
   |
1. Extract full text per page (PyPDFLoader)
   |
2. Language filter — keep English pages only (page range: 0–17)
   |
3. Concatenate English text into single document string
   |
4. LLM segments document into sections [{title, tag, content}]
   |
5. For each section: create Document with metadata, embed, store in Chroma
   |
6. Deduplication check — skip if model already indexed
   |
7. Verification query — assert troubleshooting section retrieves correctly
```

### Step 2 — Language Filtering (V1)

The EA6350 manual contains a full English version followed by a complete
Spanish repeat. Language filtering runs **first** — before any sectioning
or embedding. Only English content ever reaches the vector store.

```python
# shared/rag/ingest_v1.py
loader = PyPDFLoader("shared/data/user_guide_EA6350.pdf")
pages = loader.load()

# English content on pages 0-17 (0-indexed).
# Verify boundary: pdftotext -f 19 -l 19 shared/data/user_guide_EA6350.pdf -
english_pages = [p for p in pages if p.metadata["page"] <= 17]
full_english_text = "\n".join([p.page_content for p in english_pages])
```

### Step 4 — Structure-Agnostic Section Detection

Different router manuals use different section names and structures.
Hardcoding headers breaks the moment you add a TP-Link or Netgear manual.
The LLM segments any manual at ingest time and maps sections onto a
**fixed canonical taxonomy** — this runs once per manual, not per
conversation.

```python
# shared/rag/ingest_v1.py

CANONICAL_TAGS = [
    "overview", "setup", "features",
    "troubleshooting", "specifications", "other"
]

def segment_document_with_llm(full_text: str, model_name: str) -> list[dict]:
    prompt = f"""
You are parsing a router manual for the {model_name}.

Identify the major sections and extract each one.
Assign each section a tag from this fixed list ONLY: {CANONICAL_TAGS}

Return a JSON array. Each item must have:
- "section_title": the original heading as it appears in the document
- "section_tag": one value from the fixed list above
- "content": the complete text of that section

Manual text:
{full_text}

Return ONLY valid JSON. No preamble, no markdown fences.
"""
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)
```

**Why the canonical taxonomy is the key insight:** Retrieval always
filters by `section_tag`, never by the original heading. "Troubleshooting",
"FAQ & Troubleshooting Guide", and "Problem Solving" all map to
`section_tag: "troubleshooting"`. The retrieval query never changes
regardless of what any manual calls its sections.

### Step 5 — Extensible Metadata Schema

```python
{
    # Retrieval filter keys
    "model_name": "EA6350",            # always normalised UPPER at ingest
    "language": "en",                  # ISO 639-1
    "section_tag": "troubleshooting",  # always from canonical list

    # Debugging / observability
    "brand": "Linksys",
    "model_aliases": ["R63"],
    "section_title": "Troubleshooting",
    "source_file": "user_guide_EA6350.pdf",

    # Deduplication
    "chunk_id": "EA6350_en_troubleshooting"
}
```

Normalisation rule — Chroma filters are exact match only:
```python
model_name = model_name.upper().strip()  # "ea6350" -> "EA6350"
```

### Step 6 — Deduplication

```python
def is_already_indexed(vectorstore, model_name: str) -> bool:
    results = vectorstore.get(where={"model_name": model_name.upper()})
    return len(results["ids"]) > 0

if is_already_indexed(vectorstore, model_name):
    print(f"{model_name} already indexed — skipping.")
    return
```

### Step 7 — Retrieval Verification (`shared/rag/verify_retrieval.py`)

Run this before testing the agent. If it fails, fix the ingest
pipeline — never fix at prompt time.

```python
query = "how do I reboot my router using the power cord"
results = vectorstore.similarity_search(
    query,
    filter={"model_name": "EA6350", "language": "en",
            "section_tag": "troubleshooting"},
    k=1
)
assert results, "No results — check ingest pipeline"
assert "power cord" in results[0].page_content.lower(), \
    "Reboot steps not found in retrieved content"
print("Verification passed.")
print(results[0].page_content)
```

---

## Tech Stack — V1

| Component | Choice |
|---|---|
| Orchestration | LangGraph |
| LLM | `gpt-4o-mini` (configurable via `.env`) |
| Embeddings | `text-embedding-3-small` |
| Vector store | Chroma (local, persistent at `chroma_db/v1/`) |
| PDF parsing | LangChain PyPDFLoader |
| Frontend | Streamlit |
| Schema | Pydantic v2 |

---

## How to Run V1

```bash
# From repo root
cp .env.example .env               # add OPENAI_API_KEY
pip install -r agents/v1/requirements.txt
python shared/rag/ingest_v1.py     # builds chroma_db/v1/
python shared/rag/verify_retrieval.py --version v1
streamlit run agents/v1/app.py
```

---

## Definition of Done — V1

- [ ] All run steps above work first try from a clean clone
- [ ] `verify_retrieval.py --version v1` passes
- [ ] Spanish content absent from `chroma_db/v1/` — Spanish query returns nothing
- [ ] Qualify exits correctly for: single device, ISP outage, already rebooted
- [ ] Loose cable scenario resolves before reaching reboot node
- [ ] RAG context retrieved once on GUIDE_REBOOT entry, cached in state
- [ ] Physical reboot guided step-by-step with observable confirmations
- [ ] Post-reboot resolution handles both yes and no correctly
- [ ] No crash on empty input, off-topic message, or mid-flow interruption
- [ ] `agents/v1/README.md` complete (see README spec below)
- [ ] `chroma_db/` and `.env` in `.gitignore`

---

---

# V2 — Enhanced Experience (Wow Effect)

**Folder:** `agents/v2/`
**Shared modules introduced:** `shared/rag/ingest_v2.py`,
`shared/state/state_v2.py`, `shared/prompts/prompt_config.py`
**Shared modules reused from V1:** `shared/rag/retriever.py`,
`shared/rag/verify_retrieval.py`, `shared/prompts/base_prompts.py`,
`shared/data/user_guide_EA6350.pdf`

V2 does **not** modify any file inside `agents/v1/` or any `shared/`
module introduced by V1. New shared capabilities are added as new files
alongside the originals.

---

## What's New in V2

### 1. App/Browser Reboot Method — With Correct Connectivity Gating

The `www.linksyssmartwifi.com` portal is cloud-based. It requires:
- The **router** to have an active WAN connection so Linksys's servers
  can reach it and send the reboot command
- The **user's device** to have internet access to reach the portal

This means the app method is only valid when the router has LAN and WAN
connectivity but is behaving intermittently. It is **not** valid for the
primary "all devices offline" use case — the cloud portal cannot reach a
router with no WAN connection regardless of whether the user has mobile data.

**Decision tree before offering reboot methods:**

```
Does the user have internet on any device right now?
   |-- No  --> Physical reboot only
   |-- Yes --> Is it a full outage or intermittent?
                |-- Intermittent / partial --> Offer both methods
                |-- Fully offline ----------> Physical reboot only
                    (router has no WAN — cloud cannot reach it)
```

**Edge case — local admin access:**
If internet is down but the user's device can connect to the router's
local WiFi, the admin panel may be reachable at `192.168.1.1`. Offer
only when `user_literacy == "high"`.

**App reboot steps (from user_guide_EA6350.pdf via RAG):**
1. Go to www.linksyssmartwifi.com and log in.
2. Under Router Settings, click Troubleshooting.
3. Click the Diagnostics tab.
4. Under Reboot, click Reboot, then confirm with Yes.
5. All devices will briefly lose connection and reconnect automatically.

---

### 2. Language Detection Upgrade (`shared/rag/ingest_v2.py`)

Replaces the V1 page-range filter with per-page `langdetect` detection.
Makes the ingest pipeline work correctly for any manual regardless of
structure — no hardcoded page numbers per file.

```python
# shared/rag/ingest_v2.py
from langdetect import detect

def is_english(text: str) -> bool:
    try:
        return detect(text) == "en"
    except:
        return False

english_pages = [p for p in pages if is_english(p.page_content)]
```

V2 uses `chroma_db/v2/` — a separate store built with `ingest_v2.py`.
The V1 store at `chroma_db/v1/` is untouched.

---

### 3. Conversation Mode (`shared/prompts/prompt_config.py`)

```python
conversation_mode: Literal["self_serve", "agent_assisted"] = "self_serve"
```

| Dimension | Self-Serve | Agent-Assisted |
|---|---|---|
| Language | Plain, warm, patient | Concise, technical |
| Pacing | One step at a time | Can batch steps |
| Observables | "What do the lights look like?" | "Is the WAN LED solid?" |
| Escalation | "Contact your ISP" | "Create a support ticket" |
| Literacy detection | Active | Disabled |

`get_prompt_config(state)` injects the correct register into every node.
No duplicated prompt logic across nodes.

---

### 4. Literacy Detection and Adaptive Language

```python
user_literacy: Literal["low", "medium", "high"] = "medium"
```

Inferred from the user's opening message. Technical terms (WAN, DHCP,
firmware) → `high`. Casual and vague ("my wifi is broken idk") → `low`.

**Terminology substitution for `low` literacy:**

| Technical | Plain |
|---|---|
| Modem | "the box your internet cable plugs into" |
| Router | "the box that broadcasts your WiFi signal" |
| Power indicator | "the light on the front of the box" |
| WAN port | "the yellow internet port on the back" |

---

### 5. LangSmith Tracing

Zero agent code changes. Add two env vars:
```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<key>
```

---

## State Schema — V2 (`shared/state/state_v2.py`)

Extends V1 schema. V1 imports `state_v1.py`, V2 imports `state_v2.py`.

```python
# shared/state/state_v2.py
from shared.state.state_v1 import ConversationState as ConversationStateV1

class ConversationState(ConversationStateV1):
    # Reboot method extended
    reboot_method: Optional[Literal["physical", "app", "local_admin"]] = None
    # V2 additions
    conversation_mode: Literal["self_serve", "agent_assisted"] = "self_serve"
    user_literacy: Literal["low", "medium", "high"] = "medium"
    has_internet_on_other_device: Optional[bool] = None
    step_confidence: Literal["low", "medium", "high"] = "medium"
```

---

## How to Run V2

```bash
# From repo root — V1 does not need to be running
pip install -r agents/v2/requirements.txt
python shared/rag/ingest_v2.py     # builds chroma_db/v2/
python shared/rag/verify_retrieval.py --version v2
streamlit run agents/v2/app.py
```

---

## Definition of Done — V2

- [ ] V1 runs identically after V2 is introduced — no regressions
- [ ] App reboot offered only when connectivity gating conditions are met
- [ ] Physical-only path still works and is the default
- [ ] `ingest_v2.py` with langdetect runs cleanly on EA6350 manual
- [ ] `chroma_db/v2/` is separate from `chroma_db/v1/`
- [ ] Mode selector visible at session start (Streamlit radio)
- [ ] Agent-assisted mode uses tighter, technical language
- [ ] Literacy inferred from first message, maintained across conversation
- [ ] Low-literacy users receive plain language substitutions throughout
- [ ] LangSmith traces visible in dashboard for a sample conversation
- [ ] `agents/v2/README.md` complete

---

---

# V3 — Production Readiness

**Folder:** `agents/v3/`
**Shared modules introduced:** none (V3 adds to `agents/v3/` only)
**Shared modules reused:** all of `shared/` — uses `ingest_v2.py`,
`state_v2.py`, `prompt_config.py`, `retriever.py`, `verify_retrieval.py`

V3 does **not** modify any file in `agents/v1/`, `agents/v2/`, or any
existing `shared/` module. New V3-specific components (eval pipeline,
guardrails) live inside `agents/v3/`.

---

## What's New in V3

### 1. Evaluation Pipeline (`agents/v3/eval/`)

```
agents/v3/eval/
├── golden_dataset.json    # ~20 reference conversations with labelled outcomes
└── run_eval.py            # LLM-as-judge runner — outputs scored report
```

**LLM-as-judge scores each conversation on:**
- Correct qualify branch decision
- Reboot steps grounded in the manual (not hallucinated)
- Graceful exit quality (helpful, specific, actionable)
- Appropriate language register

**Metrics:**
- Qualify accuracy rate
- Reboot instruction grounding rate
- Resolution rate
- Average conversation length

```bash
python agents/v3/eval/run_eval.py
```

---

### 2. Guardrails (inside `agents/v3/nodes.py`)

**Scope enforcement:** Pre-qualify classifier blocks out-of-scope requests
(firewall config, VPN, password changes). Declines without entering main flow.

**Hallucination prevention:** After retrieval, verify returned content
contains expected reboot keywords. Below confidence threshold — safe
static fallback. Never let the LLM improvise steps.

**Prompt injection defence:** Lightweight classifier before qualify node.
Flags patterns like "ignore previous instructions" — refuses without
exposing agent internals.

**Credential protection:** If user volunteers passwords or IPs, agent
instructs them not to share sensitive information.

---

### 3. Multi-Router Model Support

V1 ingest already produces the correct metadata schema. V3 activates:
- Router model captured early in qualify (asked or inferred from description)
- `state.router_model` used as retrieval filter
- Fallback when model unknown: provides manufacturer support URL
- CLI ingest for any manual:

```bash
python shared/rag/ingest_v2.py \
    --pdf data/user_guide_AC1750.pdf \
    --model AC1750 \
    --brand TP-Link \
    --chroma-path chroma_db/v3/
```

---

### 4. Structured Logging (`agents/v3/nodes.py`)

```json
{
  "conversation_id": "uuid",
  "router_model": "EA6350",
  "conversation_mode": "self_serve",
  "qualify_outcome": "reboot_appropriate",
  "reboot_method": "physical",
  "resolution_outcome": "resolved",
  "total_latency_ms": 4200,
  "total_tokens": 1840,
  "node_trace": ["qualify", "guide_reboot", "check_resolution", "close_success"]
}
```

Alert trigger: resolution rate below 70% in rolling 24-hour window.

---

### 5. Human Escalation Path

When qualify confidence is low after 3 exchanges — agent does not guess.

- Self-serve: provides ISP support number and Linksys support URL
- Agent-assisted: outputs structured handoff summary

---

## How to Run V3

```bash
# From repo root
pip install -r agents/v3/requirements.txt
python shared/rag/ingest_v2.py --chroma-path chroma_db/v3/
python shared/rag/verify_retrieval.py --version v3
streamlit run agents/v3/app.py

# Run evaluation
python agents/v3/eval/run_eval.py
```

---

## Definition of Done — V3

- [ ] V1 and V2 run identically after V3 is introduced — no regressions
- [ ] Eval pipeline runs against golden dataset and produces a score report
- [ ] Scope classifier correctly blocks out-of-scope requests
- [ ] Injection classifier correctly flags adversarial inputs
- [ ] Multi-router: second manual indexed, retrieval returns correct steps
- [ ] Structured log written to file for every conversation
- [ ] Human escalation triggers on contradictory qualify signals
- [ ] `agents/v3/README.md` complete

---

---

# README Specifications

---

## Global README (repo root `README.md`)

Covers the project as a whole. Audiences: anyone landing on the repo.

### Sections

**1. What this project is**
One paragraph. A versioned AI support agent for WiFi troubleshooting,
built as a take-home challenge for RouteThis. Three independently runnable
agents of increasing capability.

**2. How to navigate the repo**
Point to `agents/v1/`, `agents/v2/`, `agents/v3/` with one-line descriptions.
Point to `shared/` and explain its purpose.

**3. Quickstart**
How to run V1 (the primary submission). Cross-reference V2 and V3 READMEs.

**4. Architecture overview**
- Multi-agent structure diagram (ASCII)
- Shared module dependency table
- One paragraph on the RAG pipeline design

**5. Key design decisions**

*Why retrieval fires only in GUIDE_REBOOT*
Qualify is pure conversational reasoning — no document context needed.
Retrieval in qualify adds latency to every exchange with zero benefit.
Context is retrieved once, cached in state, reused for all step messages.

*Why physical reboot only in V1*
The Linksys Smart Wi-Fi app method requires the router to have an active
WAN connection so Linksys's servers can reach it. In the primary use case
(all devices offline), the router has no WAN — the cloud portal cannot
reach it regardless of whether the user has mobile data. V1 defaults to
physical. V2 adds the app method with a correct connectivity decision tree.

*Why section-level storage instead of fixed-size chunking*
Fixed-size chunking risks fragmenting numbered procedure steps across chunk
boundaries — retrieval returns steps 1–3 but not 4–5, or returns a step
with no heading context. Section-level storage keeps each complete procedure
as one coherent unit. For a support agent giving accurate step-by-step
instructions, fragmentation is a correctness issue, not a quality issue.

*Why LLM-based section detection instead of hardcoded headers*
Different router manuals use different section names and structures.
Hardcoding "Troubleshooting" breaks the moment you add a TP-Link or
Netgear manual. The LLM segments any manual at ingest time and maps
sections onto a fixed canonical taxonomy. Retrieval always queries by
canonical tag — never by the original heading.

*Why a canonical section taxonomy*
The filter `section_tag: "troubleshooting"` works identically regardless
of whether the manual calls the section "Troubleshooting", "FAQ &
Troubleshooting Guide", or "Problem Solving". The taxonomy abstracts away
structural differences between manufacturers. Adding a new router model
requires no changes to the agent or retrieval code.

*Why language filtering runs first in the pipeline*
The EA6350 manual contains a full English version followed by a complete
Spanish repeat. Language filtering is the first step so only English
content ever reaches the vector store. V1 uses a page range (deterministic,
no extra dependency). V2 upgrades to per-page `langdetect` for unknown manuals.

*Why each agent version has its own Chroma store*
V1 and V2 use different ingest pipelines (page range vs langdetect) and
may produce slightly different chunks. Separate stores prevent cross-version
contamination and ensure each agent is always querying content built with
its own ingest logic.

**6. Known Limitations**
- App reboot method not in V1 — connectivity dependency (see design decisions)
- Single router model in V1/V2 — multi-model in V3
- No authentication or session persistence in any version
- LLM section detection is non-deterministic — deduplication guard prevents
  duplicate sections on re-ingest

**7. Future Work**
Document all V2 and V3 features not yet built, plus anything beyond V3:
- Multi-site awareness for corporate customers
- Resolution rate alerting and PagerDuty integration
- Fine-tuning on resolved conversation dataset
- Integration with live ISP outage APIs (skip reboot when outage confirmed)
- Tenant isolation for multi-customer deployments

---

## Agent README (`agents/vN/README.md`)

Each agent has its own README. Audiences: the interviewer running the code.

### Required sections for each

1. **What this version does** — one paragraph, what's new vs the previous version
2. **How to run it** — exact commands from a clean clone
3. **What's reused from shared/** — list of imported modules
4. **Design decisions specific to this version**
5. **Known limitations of this version**

---

---

# Key Insights for the Live Session

---

**On where retrieval fires:**
> "Retrieval is scoped to the GUIDE_REBOOT node only. Qualifying is pure
> conversational reasoning — the manual isn't needed to decide whether all
> devices are offline. Firing retrieval on every qualifying exchange adds
> latency and cost with zero benefit. The context is retrieved once, cached
> in state, and reused for every step confirmation message."

**On the app reboot method:**
> "I scoped V1 to physical reboot only because the cloud portal requires
> the router to have an active WAN connection — Linksys's servers need to
> reach the router to send the reboot command. In the primary use case the
> internet is down, so the router has no WAN. Offering the app method there
> is a dead end. V2 adds it with a proper decision tree — only surface it
> when the user confirms they have internet on another device AND the router
> isn't fully offline."

**On section-level storage vs fixed-size chunking:**
> "Fixed-size chunking risks fragmenting numbered procedure steps — retrieve
> steps 1 to 3 but not 4 and 5, or get a step with no heading context.
> Section-level storage keeps each complete procedure as one unit. For a
> support agent giving step-by-step instructions, fragmentation is a
> correctness issue, not a quality issue."

**On LLM-based section detection:**
> "I didn't want the ingest pipeline to only work with the EA6350 manual.
> Different manufacturers structure their manuals differently — TP-Link,
> Netgear, and ASUS all use different headings. Using an LLM to segment
> any manual at ingest time and map onto a fixed canonical taxonomy means
> the retrieval query never changes. Adding a new router model is one CLI
> command — no code changes anywhere."

**On language filtering:**
> "The EA6350 manual is half English, half Spanish. If I embed both,
> retrieval can return Spanish steps and the agent responds in Spanish.
> Language filtering is the first step in the ingest pipeline — before
> any sectioning — so only English content ever reaches the vector store.
> V2 upgrades from a hardcoded page range to per-page langdetect so it
> handles any manual automatically."

**On the metadata schema:**
> "The schema was designed for extensibility from day one — model_name,
> language, section_tag, brand, aliases. In V1 there's one document in
> the store but the retrieval filter already uses model_name and section_tag.
> Adding a second router model is just an ingest operation. The agent
> doesn't need to know how many models are in the corpus."

**On the multi-agent folder structure:**
> "Each version is independently runnable — V1 doesn't change when I ship
> V2, and V2 doesn't change when I ship V3. Shared logic lives in one place
> and is imported, never copied. This means V1 is always exactly what was
> submitted, and the repo tells a clean story of incremental capability growth."

**On production confidence:**
> "Confidence comes from a golden dataset eval, not intuition. The eval
> harness in V3 measures qualify accuracy and instruction grounding rate —
> whether steps came from the manual or the LLM invented them. That's the
> difference between a demo and something you'd put in front of ISP customers."

---

*Versioned spec for RouteThis take-home challenge. Updated March 2026.*
