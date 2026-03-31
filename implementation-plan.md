# RouteThis WiFi Assistant — Implementation Plan

## Overview

Build a conversational WiFi troubleshooting agent (V1 MVP) that qualifies user issues, guides physical router reboots using RAG from the Linksys EA6350 manual, and handles graceful exits. Uses LangGraph for orchestration, Chroma for vector storage, OpenAI gpt-4o-mini for conversation, and Streamlit for the UI.

**Interview date:** Thursday, April 2nd, 10:30 AM  
**Primary deliverable:** V1 must be solid, runnable, and impressive on its own.

## Current State Analysis

- **Repo:** `/Users/jainer/Documents/routeThis/` — mostly empty, only `src/shared/data/user_guide_EA6350.pdf` exists
- **PDF:** 499 pages, multi-language. English pages 0-18, Spanish 19-38, then French, Danish, Ukrainian, etc.
- **Reboot instructions:** Pages 15-16 contain both physical and app reboot methods
- **No code exists yet** — building from scratch

### Key Discoveries:

- The PDF is much larger than expected (499 pages, not ~36). The V1 page-range filter (`<= 17`) still works but is critical to avoid embedding 480+ non-English pages
- Physical reboot steps span pages 15-16 (split across page boundary) — the LLM segmentation approach correctly handles this by concatenating all English text first
- Both reboot methods (physical + app/Smart Wi-Fi) are in the troubleshooting section — V1 must retrieve the full section but only guide the physical method
- The `response_format={"type": "json_object"}` flag in OpenAI's API requires the prompt to mention "JSON" — already handled in the spec's prompt template

## Desired End State

A fully functional V1 agent at `agents/v1/` that:
1. Runs from a clean clone with 4 commands (cp .env, pip install, ingest, streamlit run)
2. Qualifies WiFi issues through conversational Q&A (one question at a time)
3. Retrieves reboot steps from Chroma via RAG (never hardcoded)
4. Guides physical reboot step-by-step with observable confirmations
5. Handles all graceful exit scenarios (single device, ISP outage, already rebooted, cables fixed)
6. Passes all Definition of Done criteria from spec.md

**Verification:** Run the 4-step quickstart, then test all 6 conversation scenarios from the DoD checklist.

## What We're NOT Doing

- App/browser reboot method (V2)
- Literacy detection or adaptive language (V2)
- Conversation mode switching (V2)
- Multi-router model support (V3)
- Evaluation pipeline (V3)
- Guardrails / prompt injection defense (V3)
- Structured logging (V3)
- LangSmith tracing setup (V2 — just env vars, no code)

## Implementation Deviations

<!-- Auto-populated during execution -->

_No deviations recorded yet._

---

## Implementation Approach

Build bottom-up: data layer first (RAG pipeline), then state/prompts, then agent logic, then UI. This allows each layer to be tested independently before wiring together. The RAG pipeline is the riskiest component (LLM segmentation is non-deterministic) so it goes first.

## Task Dependencies & Parallelization

### Dependency Graph

```
        ┌─────────────────┐
        │  Phase 1:       │
        │  Scaffolding    │
        └────────┬────────┘
                 │
         ┌───────┴───────┐
         │               │
         v               v
┌─────────────────┐ ┌─────────────────┐
│  Phase 2:       │ │  Phase 3:       │  <- Can run in parallel
│  RAG Pipeline   │ │  State & Prompts│
└────────┬────────┘ └────────┬────────┘
         │               │
         └───────┬───────┘
                 │
                 v
        ┌─────────────────┐
        │  Phase 4:       │
        │  Agent Logic    │  <- Blocked by Phase 2 AND Phase 3
        └────────┬────────┘
                 │
                 v
        ┌─────────────────┐
        │  Phase 5:       │
        │  Streamlit UI   │  <- Blocked by Phase 4
        └────────┬────────┘
                 │
                 v
        ┌─────────────────┐
        │  Phase 6:       │
        │  Test & Polish  │  <- Blocked by Phase 5
        └─────────────────┘
```

### Execution Groups

| Group | Phases           | Notes                                  |
| ----- | ---------------- | -------------------------------------- |
| 1     | Phase 1          | Scaffolding — must be first            |
| 2     | Phase 2, Phase 3 | No cross-dependencies, can parallelize |
| 3     | Phase 4          | Needs RAG + state + prompts            |
| 4     | Phase 5          | Needs compiled graph                   |
| 5     | Phase 6          | Integration testing + docs             |

### Phase Dependencies

| Phase   | Depends On       | Blocks   | Can Parallel With |
| ------- | ---------------- | -------- | ----------------- |
| Phase 1 | -                | 2, 3     | -                 |
| Phase 2 | Phase 1          | Phase 4  | Phase 3           |
| Phase 3 | Phase 1          | Phase 4  | Phase 2           |
| Phase 4 | Phase 2, Phase 3 | Phase 5  | -                 |
| Phase 5 | Phase 4          | Phase 6  | -                 |
| Phase 6 | Phase 5          | -        | -                 |

---

## Phase 1: Project Scaffolding

**Status**: [ ] Not Started | [ ] In Progress | [ ] Complete  
**Depends On**: None  
**Blocks**: Phase 2, Phase 3

### Overview

Create the monorepo folder structure, move the PDF, set up environment config, .gitignore, and requirements.txt. This establishes the foundation everything else builds on.

### Changes Required:

#### 1. Create folder structure

- [ ] **Action**: Create all directories per spec

```bash
# From repo root
mkdir -p shared/rag shared/state shared/prompts shared/data
mkdir -p agents/v1
mkdir -p chroma_db/v1
```

#### 2. Move PDF to correct location

- [ ] **File**: `shared/data/user_guide_EA6350.pdf`
  - **Changes**: Move from `src/shared/data/user_guide_EA6350.pdf` to `shared/data/user_guide_EA6350.pdf`. Remove `src/` directory.

#### 3. Create .env.example

- [ ] **File**: `.env.example`
  - **Changes**: Create with all documented env vars

```ini
# OpenAI API
OPENAI_API_KEY=sk-...

# LangSmith (optional, V2+)
LANGCHAIN_TRACING_V2=false
LANGCHAIN_API_KEY=
```

#### 4. Create .gitignore

- [ ] **File**: `.gitignore`
  - **Changes**: Create with required exclusions

```
.env
chroma_db/
__pycache__/
*.pyc
.streamlit/secrets.toml
```

#### 5. Create V1 requirements.txt

- [ ] **File**: `agents/v1/requirements.txt`
  - **Changes**: Create with pinned V1 dependencies

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
```

#### 6. Create shared __init__.py files

- [ ] **Files**: `shared/__init__.py`, `shared/rag/__init__.py`, `shared/state/__init__.py`, `shared/prompts/__init__.py`
  - **Changes**: Empty init files for Python package resolution

### Success Criteria:

#### Automated Verification (Gates):

- [ ] `ls shared/data/user_guide_EA6350.pdf` succeeds
- [ ] `ls agents/v1/requirements.txt` succeeds
- [ ] `ls .env.example` succeeds
- [ ] `cat .gitignore | grep chroma_db` succeeds
- [ ] `pip install -r agents/v1/requirements.txt` succeeds without errors
- [ ] `python -c "import shared"` succeeds from repo root

#### Manual Verification:

- [ ] Folder structure matches spec.md monorepo layout

---

## Phase 2: RAG Pipeline

**Status**: [ ] Not Started | [ ] In Progress | [ ] Complete  
**Depends On**: Phase 1  
**Blocks**: Phase 4

### Overview

Build the ingest pipeline (PDF → English filter → LLM segmentation → Chroma), the retrieval wrapper, and the verification script. This is the data foundation — everything the agent knows comes from here.

### Changes Required:

#### 1. Ingest Pipeline

- [ ] **File**: `shared/rag/ingest_v1.py`
  - **Changes**: Full ingest pipeline with CLI entry point

**Key implementation details:**

```python
# shared/rag/ingest_v1.py
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.documents import Document

load_dotenv()

CANONICAL_TAGS = [
    "overview", "setup", "features",
    "troubleshooting", "specifications", "other"
]

PDF_PATH = Path(__file__).resolve().parents[1] / "data" / "user_guide_EA6350.pdf"
CHROMA_PATH = Path(__file__).resolve().parents[2] / "chroma_db" / "v1"

def load_english_pages(pdf_path: str) -> list:
    """Load PDF and filter to English pages only (pages 0-17, 0-indexed)."""
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    # English content on pages 0-17. Page 18 is regulatory notes.
    # Page 19+ is Spanish/French/Danish/etc.
    english_pages = [p for p in pages if p.metadata["page"] <= 17]
    return english_pages

def segment_document_with_llm(full_text: str, model_name: str) -> list[dict]:
    """Use LLM to segment manual into canonical sections."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    prompt = f"""You are parsing a router manual for the {model_name}.

Identify the major sections and extract each one.
Assign each section a tag from this fixed list ONLY: {CANONICAL_TAGS}

Return a JSON object with a "sections" key containing an array.
Each item must have:
- "section_title": the original heading as it appears in the document
- "section_tag": one value from the fixed list above
- "content": the complete text of that section

Manual text:
{full_text}

Return ONLY valid JSON. No preamble, no markdown fences."""

    response = llm.invoke([{"role": "user", "content": prompt}])
    parsed = json.loads(response.content)
    # Handle both {"sections": [...]} and direct [...]
    if isinstance(parsed, dict) and "sections" in parsed:
        return parsed["sections"]
    if isinstance(parsed, list):
        return parsed
    raise ValueError(f"Unexpected LLM response format: {type(parsed)}")

def build_documents(sections: list[dict], model_name: str) -> tuple[list[Document], list[str]]:
    """Create LangChain Documents with metadata from segmented sections."""
    docs = []
    ids = []
    model_upper = model_name.upper().strip()
    for section in sections:
        tag = section["section_tag"]
        chunk_id = f"{model_upper}_en_{tag}"
        metadata = {
            "model_name": model_upper,
            "language": "en",
            "section_tag": tag,
            "section_title": section["section_title"],
            "source_file": f"user_guide_{model_upper}.pdf",
            "brand": "Linksys",
            "chunk_id": chunk_id,
        }
        docs.append(Document(page_content=section["content"], metadata=metadata))
        ids.append(chunk_id)
    return docs, ids

def is_already_indexed(vectorstore, model_name: str) -> bool:
    """Check if model is already in the vector store."""
    results = vectorstore.get(where={"model_name": model_name.upper().strip()})
    return len(results["ids"]) > 0

def ingest(model_name: str = "EA6350", pdf_path: str = None, chroma_path: str = None):
    """Main ingest function."""
    pdf = pdf_path or str(PDF_PATH)
    chroma = chroma_path or str(CHROMA_PATH)
    
    embedding_fn = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = Chroma(
        collection_name="router_manuals",
        persist_directory=chroma,
        embedding_function=embedding_fn,
    )
    
    if is_already_indexed(vectorstore, model_name):
        print(f"{model_name} already indexed — skipping.")
        return vectorstore
    
    print(f"Loading PDF: {pdf}")
    english_pages = load_english_pages(pdf)
    full_text = "\n".join([p.page_content for p in english_pages])
    print(f"Loaded {len(english_pages)} English pages ({len(full_text)} chars)")
    
    print("Segmenting document with LLM...")
    sections = segment_document_with_llm(full_text, model_name)
    print(f"Found {len(sections)} sections: {[s['section_tag'] for s in sections]}")
    
    docs, ids = build_documents(sections, model_name)
    
    print(f"Embedding and storing {len(docs)} sections...")
    vectorstore.add_documents(documents=docs, ids=ids)
    print(f"Ingest complete. Store at: {chroma}")
    
    return vectorstore

if __name__ == "__main__":
    ingest()
```

#### 2. Retrieval Wrapper

- [ ] **File**: `shared/rag/retriever.py`
  - **Changes**: Thin wrapper around Chroma similarity_search with metadata filter

```python
# shared/rag/retriever.py
from pathlib import Path
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

def build_retriever(chroma_path: str = None, collection_name: str = "router_manuals"):
    """Build a Chroma vectorstore instance for retrieval."""
    if chroma_path is None:
        chroma_path = str(Path(__file__).resolve().parents[2] / "chroma_db" / "v1")
    
    embedding_fn = OpenAIEmbeddings(model="text-embedding-3-small")
    return Chroma(
        collection_name=collection_name,
        persist_directory=chroma_path,
        embedding_function=embedding_fn,
    )

def retrieve(vectorstore, query: str, model_name: str = "EA6350",
             section_tag: str = "troubleshooting", k: int = 1) -> list:
    """Retrieve documents with metadata filter."""
    results = vectorstore.similarity_search(
        query=query,
        k=k,
        filter={
            "model_name": model_name.upper().strip(),
            "language": "en",
            "section_tag": section_tag,
        },
    )
    return results
```

#### 3. Verification Script

- [ ] **File**: `shared/rag/verify_retrieval.py`
  - **Changes**: Assertion-based verification, CLI with --version flag

```python
# shared/rag/verify_retrieval.py
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from shared.rag.retriever import build_retriever, retrieve

def verify(version: str = "v1"):
    chroma_path = str(Path(__file__).resolve().parents[2] / "chroma_db" / version)
    vectorstore = build_retriever(chroma_path=chroma_path)
    
    # Test 1: English troubleshooting retrieval
    results = retrieve(vectorstore, "how do I reboot my router using the power cord")
    assert results, "FAIL: No results — check ingest pipeline"
    assert "power cord" in results[0].page_content.lower(), \
        "FAIL: Reboot steps not found in retrieved content"
    print(f"PASS: Troubleshooting section retrieved ({len(results[0].page_content)} chars)")
    
    # Test 2: Spanish content should NOT be in the store
    spanish_results = vectorstore.similarity_search(
        "reiniciar el router",
        k=1,
        filter={"model_name": "EA6350", "language": "es"},
    )
    assert not spanish_results, "FAIL: Spanish content found in store"
    print("PASS: No Spanish content in store")
    
    print(f"\nAll verification checks passed for {version}.")
    print(f"\nRetrieved content preview:\n{results[0].page_content[:500]}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1", choices=["v1", "v2", "v3"])
    args = parser.parse_args()
    
    # Add repo root to path for shared imports
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    verify(args.version)
```

### Success Criteria:

#### Automated Verification (Gates):

- [ ] `python shared/rag/ingest_v1.py` runs without errors and prints section tags including "troubleshooting"
- [ ] `ls chroma_db/v1/` shows Chroma files created
- [ ] `python shared/rag/verify_retrieval.py --version v1` passes all assertions
- [ ] Retrieved troubleshooting content contains "power cord" and "disconnect"

#### Manual Verification:

- [ ] Inspect the sections printed during ingest — verify they map sensibly to the manual
- [ ] Run a Spanish query manually and confirm empty results

**Implementation Note**: After completing this phase and all automated gates pass, pause here for manual confirmation before proceeding.

---

## Phase 3: State Schema & Prompts

**Status**: [ ] Not Started | [ ] In Progress | [ ] Complete  
**Depends On**: Phase 1  
**Blocks**: Phase 4

### Overview

Define the Pydantic state schema and all prompt templates. These are the contracts that every node function operates against.

### Changes Required:

#### 1. V1 State Schema

- [ ] **File**: `shared/state/state_v1.py`
  - **Changes**: Pydantic BaseModel with all V1 fields

```python
# shared/state/state_v1.py
from typing import Optional, Annotated
from pydantic import BaseModel, Field
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage

class ConversationState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    reboot_appropriate: Optional[bool] = None
    issue_resolved: Optional[bool] = None
    current_step: int = 0
    current_node: str = "qualify"
    rag_context: Optional[str] = None
    exit_reason: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
```

**Key design decision:** Use `Annotated[list[BaseMessage], add_messages]` — this is LangGraph's message reducer pattern. When a node returns `{"messages": [new_msg]}`, the reducer appends rather than replacing. This is critical for multi-turn conversation.

#### 2. Base Prompts

- [ ] **File**: `shared/prompts/base_prompts.py`
  - **Changes**: All V1 prompt templates

```python
# shared/prompts/base_prompts.py

SYSTEM_PROMPT = """You are a friendly WiFi troubleshooting assistant for Linksys routers.
You help users diagnose and fix WiFi connectivity issues.
You ask one question at a time and wait for the user's response.
You focus on observable facts, not yes/no acknowledgements.
You never make up router instructions — you only use information provided to you."""

QUALIFY_PROMPT = """You are qualifying whether a router reboot is appropriate.

Based on the conversation so far, determine:
1. Are ALL devices affected, or just one? (one device = not a router issue)
2. Has the user checked cable connections? (loose cable may fix it without reboot)
3. Is the neighbour also affected? (likely ISP outage)
4. Has the user already rebooted recently? (if twice with no improvement, escalate)
5. Was there a recent power outage? (strong signal for reboot)

Rules:
- Ask ONE question at a time about observable signs
- Don't ask "are the cables plugged in?" — ask "can you check the cable going into the yellow Internet port on the back of the router and tell me if it's firmly seated?"
- If you have enough information to decide, set your decision

Respond with JSON:
{{
    "decision": "ask_more" | "reboot" | "exit",
    "exit_reason": null | "single_device" | "isp_outage" | "already_rebooted" | "cables_fixed",
    "reply": "your message to the user"
}}"""

GUIDE_REBOOT_PROMPT = """You are guiding a user through a physical router reboot.

Use ONLY the following instructions from the manual — do not improvise or add steps:

{rag_context}

Rules:
- Present one step at a time
- After each step, ask the user to confirm what they observe (e.g., "what do the lights look like?")
- Use plain, patient language
- If the user seems confused, rephrase the current step
- Current step number: {current_step} (0-indexed, 0 = first step)

Respond with JSON:
{{
    "reply": "your message to the user",
    "step_complete": true | false,
    "all_steps_done": true | false
}}"""

CHECK_RESOLUTION_PROMPT = """The user has completed all reboot steps.
Ask them to test their internet connection and report back.

Respond with JSON:
{{
    "reply": "your message to the user",
    "resolved": true | false | null
}}

Set resolved to null if the user hasn't confirmed yet."""

GRACEFUL_EXIT_PROMPT = """The user's issue does not require a router reboot.
Exit reason: {exit_reason}

Provide a helpful, specific exit message:
- single_device: Suggest checking device WiFi settings, forgetting and reconnecting to the network
- isp_outage: Suggest contacting ISP, provide Linksys support URL
- already_rebooted: Suggest contacting ISP for further diagnosis
- cables_fixed: Congratulate and suggest monitoring

Respond with JSON:
{{
    "reply": "your farewell message to the user"
}}"""

CLOSE_SUCCESS_PROMPT = """The user's internet is working again after the reboot.
Provide a brief, warm closing message. Mention they can reach out again if issues return.

Respond with JSON:
{{
    "reply": "your closing message"
}}"""

APOLOGIZE_EXIT_PROMPT = """The reboot did not fix the user's issue.
Express empathy, suggest contacting their ISP, and provide the Linksys support URL:
Linksys.com/support/EA6350

Respond with JSON:
{{
    "reply": "your message to the user"
}}"""
```

### Success Criteria:

#### Automated Verification (Gates):

- [ ] `python -c "from shared.state.state_v1 import ConversationState; s = ConversationState(); print(s.model_dump())"` succeeds
- [ ] `python -c "from shared.prompts.base_prompts import QUALIFY_PROMPT; print('OK')"` succeeds
- [ ] State schema accepts `BaseMessage` objects in messages list

#### Manual Verification:

- [ ] Review prompt templates for clarity, completeness, and correct JSON schema
- [ ] Verify state fields cover all V1 flow requirements

---

## Phase 4: Agent Logic (LangGraph)

**Status**: [ ] Not Started | [ ] In Progress | [ ] Complete  
**Depends On**: Phase 2, Phase 3  
**Blocks**: Phase 5

### Overview

Build the LangGraph state machine with all node functions and routing logic. This is the core of the agent — the most complex phase.

### Changes Required:

#### 1. Node Functions

- [ ] **File**: `agents/v1/nodes.py`
  - **Changes**: All 7 node functions + routing functions

**Node functions to implement:**

| Node | Purpose | LLM Call? | RAG? |
|------|---------|-----------|------|
| `qualify` | Ask qualifying questions, decide if reboot needed | Yes | No |
| `graceful_exit` | Provide helpful exit for non-reboot scenarios | Yes | No |
| `pre_reboot_confirm` | Confirm user is ready to reboot | Yes | No |
| `guide_reboot` | Walk through reboot steps one at a time | Yes | Yes (once) |
| `check_resolution` | Ask if internet is working after reboot | Yes | No |
| `close_success` | Happy closing message | Yes | No |
| `apologize_and_exit` | Empathetic exit when reboot didn't help | Yes | No |

**Routing functions:**

| Router | From Node | Possible Destinations |
|--------|-----------|----------------------|
| `route_after_qualify` | qualify | qualify (loop), pre_reboot_confirm, graceful_exit |
| `route_after_guide` | guide_reboot | guide_reboot (loop), check_resolution |
| `route_after_check` | check_resolution | check_resolution (loop), close_success, apologize_and_exit |

```python
# agents/v1/nodes.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from shared.state.state_v1 import ConversationState
from shared.prompts.base_prompts import (
    SYSTEM_PROMPT, QUALIFY_PROMPT, GUIDE_REBOOT_PROMPT,
    CHECK_RESOLUTION_PROMPT, GRACEFUL_EXIT_PROMPT,
    CLOSE_SUCCESS_PROMPT, APOLOGIZE_EXIT_PROMPT,
)
from shared.rag.retriever import build_retriever, retrieve

LLM = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
VECTORSTORE = None  # Lazy-loaded on first RAG call

def _get_vectorstore():
    global VECTORSTORE
    if VECTORSTORE is None:
        VECTORSTORE = build_retriever()
    return VECTORSTORE

def _call_llm(messages: list, prompt: str) -> dict:
    """Call LLM with conversation history + prompt, parse JSON response."""
    llm_messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *messages,
        SystemMessage(content=prompt),
    ]
    response = LLM.invoke(llm_messages)
    # Parse JSON from response, handling markdown fences
    content = response.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(content)

# --- Node Functions ---

def qualify(state: ConversationState) -> dict:
    result = _call_llm(state.messages, QUALIFY_PROMPT)
    updates = {"messages": [AIMessage(content=result["reply"])]}
    
    if result["decision"] == "reboot":
        updates["reboot_appropriate"] = True
    elif result["decision"] == "exit":
        updates["reboot_appropriate"] = False
        updates["exit_reason"] = result.get("exit_reason", "unknown")
    # "ask_more" → reboot_appropriate stays None, loops back
    
    return updates

def graceful_exit(state: ConversationState) -> dict:
    prompt = GRACEFUL_EXIT_PROMPT.format(exit_reason=state.exit_reason or "unknown")
    result = _call_llm(state.messages, prompt)
    return {"messages": [AIMessage(content=result["reply"])], "current_node": "graceful_exit"}

def pre_reboot_confirm(state: ConversationState) -> dict:
    msg = ("I'd recommend we try rebooting your router. This is the most common fix "
           "for the kind of issue you're describing. I'll walk you through it step by step. "
           "Before we start — do you have access to your router and modem right now?")
    return {"messages": [AIMessage(content=msg)], "current_node": "pre_reboot_confirm"}

def guide_reboot(state: ConversationState) -> dict:
    # Retrieve RAG context once, cache in state
    rag_context = state.rag_context
    if rag_context is None:
        vs = _get_vectorstore()
        results = retrieve(vs, "router reboot steps power cord disconnect")
        rag_context = results[0].page_content if results else None
    
    if rag_context is None:
        # Fallback — retrieval failed
        return {
            "messages": [AIMessage(content=(
                "I'm having trouble accessing the specific reboot instructions. "
                "Please refer to your router's manual for reboot instructions, "
                "or visit Linksys.com/support/EA6350 for help."
            ))],
            "current_node": "apologize_and_exit",
        }
    
    prompt = GUIDE_REBOOT_PROMPT.format(
        rag_context=rag_context,
        current_step=state.current_step,
    )
    result = _call_llm(state.messages, prompt)
    
    updates = {
        "messages": [AIMessage(content=result["reply"])],
        "rag_context": rag_context,
        "current_node": "guide_reboot",
    }
    if result.get("step_complete"):
        updates["current_step"] = state.current_step + 1
    
    return updates

def check_resolution(state: ConversationState) -> dict:
    result = _call_llm(state.messages, CHECK_RESOLUTION_PROMPT)
    updates = {
        "messages": [AIMessage(content=result["reply"])],
        "current_node": "check_resolution",
    }
    if result.get("resolved") is True:
        updates["issue_resolved"] = True
    elif result.get("resolved") is False:
        updates["issue_resolved"] = False
    # None → keep asking
    return updates

def close_success(state: ConversationState) -> dict:
    result = _call_llm(state.messages, CLOSE_SUCCESS_PROMPT)
    return {"messages": [AIMessage(content=result["reply"])], "current_node": "close_success"}

def apologize_and_exit(state: ConversationState) -> dict:
    result = _call_llm(state.messages, APOLOGIZE_EXIT_PROMPT)
    return {"messages": [AIMessage(content=result["reply"])], "current_node": "apologize_and_exit"}

# --- Routing Functions ---

def route_after_qualify(state: ConversationState) -> str:
    if state.reboot_appropriate is None:
        return "qualify"  # Need more info, loop back
    if state.reboot_appropriate:
        return "pre_reboot_confirm"
    return "graceful_exit"

def route_after_pre_reboot(state: ConversationState) -> str:
    # After user confirms they're ready, proceed to guide
    return "guide_reboot"

def route_after_guide(state: ConversationState) -> str:
    # Check the last LLM response to see if all steps are done
    last_msg = state.messages[-1].content if state.messages else ""
    # The guide_reboot node sets all_steps_done in the JSON
    # But we parse the AI message — simpler to check current_step
    # Physical reboot has ~4 steps
    if state.current_step >= 4:
        return "check_resolution"
    return "guide_reboot"  # More steps to go

def route_after_check(state: ConversationState) -> str:
    if state.issue_resolved is None:
        return "check_resolution"  # Still waiting for answer
    if state.issue_resolved:
        return "close_success"
    return "apologize_and_exit"
```

#### 2. Graph Definition

- [ ] **File**: `agents/v1/graph.py`
  - **Changes**: LangGraph StateGraph construction and compilation

```python
# agents/v1/graph.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from shared.state.state_v1 import ConversationState
from agents.v1.nodes import (
    qualify, graceful_exit, pre_reboot_confirm, guide_reboot,
    check_resolution, close_success, apologize_and_exit,
    route_after_qualify, route_after_guide, route_after_check,
)

def build_graph():
    graph = StateGraph(ConversationState)
    
    # Add nodes
    graph.add_node("qualify", qualify)
    graph.add_node("graceful_exit", graceful_exit)
    graph.add_node("pre_reboot_confirm", pre_reboot_confirm)
    graph.add_node("guide_reboot", guide_reboot)
    graph.add_node("check_resolution", check_resolution)
    graph.add_node("close_success", close_success)
    graph.add_node("apologize_and_exit", apologize_and_exit)
    
    # Entry point
    graph.add_edge(START, "qualify")
    
    # Qualify routing — loops until decision made
    graph.add_conditional_edges("qualify", route_after_qualify, {
        "qualify": "qualify",
        "pre_reboot_confirm": "pre_reboot_confirm",
        "graceful_exit": "graceful_exit",
    })
    
    # Pre-reboot → guide
    graph.add_edge("pre_reboot_confirm", "guide_reboot")
    
    # Guide routing — loops through steps
    graph.add_conditional_edges("guide_reboot", route_after_guide, {
        "guide_reboot": "guide_reboot",
        "check_resolution": "check_resolution",
    })
    
    # Check resolution routing
    graph.add_conditional_edges("check_resolution", route_after_check, {
        "check_resolution": "check_resolution",
        "close_success": "close_success",
        "apologize_and_exit": "apologize_and_exit",
    })
    
    # Terminal nodes
    graph.add_edge("graceful_exit", END)
    graph.add_edge("close_success", END)
    graph.add_edge("apologize_and_exit", END)
    
    return graph

def compile_graph():
    graph = build_graph()
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
```

**Critical design decision — human-in-the-loop pattern:**
The graph uses `interrupt_before` or the Streamlit loop to wait for user input between turns. Each user message triggers a new `graph.invoke()` with the same `thread_id`, and the MemorySaver checkpointer maintains state continuity. The routing functions check state fields (not conversation content) to decide next steps.

### Success Criteria:

#### Automated Verification (Gates):

- [ ] `python -c "from agents.v1.graph import build_graph; g = build_graph(); print('Graph built')"` succeeds
- [ ] `python -c "from agents.v1.graph import compile_graph; app = compile_graph(); print('Compiled')"` succeeds
- [ ] Graph has 7 nodes and correct edge structure
- [ ] All node imports resolve without errors

#### Manual Verification:

- [ ] Trace through the state machine diagram and verify all paths are covered
- [ ] Verify qualify routing handles all exit scenarios from spec
- [ ] Verify RAG retrieval happens only once (in guide_reboot, cached in state)

---

## Phase 5: Streamlit UI

**Status**: [ ] Not Started | [ ] In Progress | [ ] Complete  
**Depends On**: Phase 4  
**Blocks**: Phase 6

### Overview

Build the Streamlit chat interface that wires to the LangGraph agent. Simple, clean, functional.

### Changes Required:

#### 1. Streamlit App

- [ ] **File**: `agents/v1/app.py`
  - **Changes**: Full Streamlit chat app

```python
# agents/v1/app.py
import sys
import uuid
from pathlib import Path

# Add repo root for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from langchain_core.messages import HumanMessage

from agents.v1.graph import compile_graph

st.set_page_config(
    page_title="WiFi Troubleshooting Assistant",
    page_icon="📶",
    layout="centered",
)

st.title("WiFi Troubleshooting Assistant")
st.caption("Linksys EA6350 — Guided Router Reboot")

# Initialize session state
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_ended" not in st.session_state:
    st.session_state.conversation_ended = False

@st.cache_resource
def get_graph():
    return compile_graph()

graph = get_graph()
config = {"configurable": {"thread_id": st.session_state.thread_id}}

# Display welcome message
if not st.session_state.messages:
    welcome = ("Hi! I'm your WiFi troubleshooting assistant. "
               "I can help you diagnose and fix connectivity issues with your Linksys router. "
               "What's going on with your internet?")
    st.session_state.messages.append({"role": "assistant", "content": welcome})

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if not st.session_state.conversation_ended:
    if prompt := st.chat_input("Describe your WiFi issue..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Invoke graph
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result = graph.invoke(
                    {"messages": [HumanMessage(content=prompt)]},
                    config=config,
                )
                # Get last AI message
                ai_messages = [m for m in result["messages"] if hasattr(m, 'type') and m.type == "ai"]
                if ai_messages:
                    response = ai_messages[-1].content
                else:
                    response = "I'm sorry, I encountered an issue. Please try again."
                
                st.markdown(response)
        
        st.session_state.messages.append({"role": "assistant", "content": response})
        
        # Check if conversation ended (terminal nodes)
        current_node = result.get("current_node", "")
        if current_node in ("graceful_exit", "close_success", "apologize_and_exit"):
            st.session_state.conversation_ended = True
        
        st.rerun()
else:
    st.info("Conversation ended. Refresh the page to start a new session.")
    if st.button("Start New Conversation"):
        st.session_state.clear()
        st.rerun()
```

### Success Criteria:

#### Automated Verification (Gates):

- [ ] `python -c "import agents.v1.app"` does not crash on import (syntax check)
- [ ] `streamlit run agents/v1/app.py` starts without errors (verify server starts)

#### Manual Verification:

- [ ] Welcome message appears on load
- [ ] User can type and receive responses
- [ ] Conversation flows through qualify → reboot → resolution correctly
- [ ] Empty input doesn't crash
- [ ] Off-topic messages are handled gracefully in qualify
- [ ] Conversation end state shows "Start New Conversation" button
- [ ] Page refresh resets conversation

**Implementation Note**: After completing this phase and all automated gates pass, pause here for manual end-to-end testing of all conversation scenarios.

---

## Phase 6: Testing & Polish

**Status**: [ ] Not Started | [ ] In Progress | [ ] Complete  
**Depends On**: Phase 5  
**Blocks**: None

### Overview

End-to-end testing of all conversation scenarios from the Definition of Done, README documentation, and final polish.

### Changes Required:

#### 1. V1 README

- [ ] **File**: `agents/v1/README.md`
  - **Changes**: Per-agent README with required sections from spec

Required sections:
1. What this version does
2. How to run it (exact commands)
3. What's reused from shared/
4. Design decisions specific to V1
5. Known limitations

#### 2. Global README

- [ ] **File**: `README.md`
  - **Changes**: Project overview with all sections from spec (section 6 of spec)

Required sections:
1. What this project is
2. How to navigate the repo
3. Quickstart
4. Architecture overview (ASCII diagram + shared module table)
5. Key design decisions (all 7 from spec)
6. Known limitations
7. Future work (V2, V3, beyond)

#### 3. End-to-End Scenario Testing

Test every scenario from the V1 Definition of Done:

| # | Scenario | Expected Outcome |
|---|----------|------------------|
| 1 | Single device affected ("my laptop can't connect but my phone works") | Graceful exit — not a router issue |
| 2 | ISP outage ("my neighbour's internet is also down") | Graceful exit — contact ISP |
| 3 | Already rebooted twice | Graceful exit — escalate to ISP |
| 4 | Loose cable found and fixed | Close success before reaching reboot |
| 5 | All devices offline, cables checked → full reboot flow | Complete: qualify → reboot → resolved |
| 6 | Full reboot flow → not resolved | Complete: qualify → reboot → apologize exit |
| 7 | Empty input / off-topic message | No crash, stays in qualify |
| 8 | Power outage recently reported | Fast-track to reboot |

### Success Criteria:

#### Automated Verification (Gates):

- [ ] All 4 run steps from spec work from repo root:
  ```bash
  cp .env.example .env  # (with real key)
  pip install -r agents/v1/requirements.txt
  python shared/rag/ingest_v1.py
  python shared/rag/verify_retrieval.py --version v1
  streamlit run agents/v1/app.py
  ```
- [ ] `verify_retrieval.py --version v1` passes
- [ ] `chroma_db/` and `.env` are in `.gitignore`

#### Manual Verification (Definition of Done):

- [ ] All 8 test scenarios above produce correct outcomes
- [ ] RAG context retrieved once on GUIDE_REBOOT entry, cached in state
- [ ] Physical reboot guided step-by-step with observable confirmations
- [ ] No crash on empty input, off-topic message, or mid-flow interruption
- [ ] `agents/v1/README.md` complete with all required sections
- [ ] Global `README.md` complete with all required sections

---

## V2 & V3 — Future Phases (Outline Only)

### V2 — Enhanced Experience

- App/browser reboot method with connectivity gating
- `shared/rag/ingest_v2.py` with langdetect language detection
- `shared/state/state_v2.py` extending V1 schema
- `shared/prompts/prompt_config.py` for mode/literacy injection
- Conversation mode selector (self_serve / agent_assisted)
- Literacy detection from opening message
- LangSmith tracing (env vars only)
- Separate `chroma_db/v2/` store

### V3 — Production Readiness

- Evaluation pipeline (`agents/v3/eval/`) with golden dataset + LLM-as-judge
- Guardrails: scope enforcement, hallucination prevention, prompt injection defense
- Multi-router model support with CLI ingest
- Structured logging per conversation
- Human escalation path after 3 inconclusive qualify exchanges

---

## Testing Strategy

### Unit-Level (per phase):

- Phase 2: Verify ingest produces correct sections, retrieval returns troubleshooting content
- Phase 3: Verify state schema instantiation, prompt template formatting
- Phase 4: Verify graph builds and compiles, node functions return valid state updates

### Integration (Phase 6):

- Full conversation flow through all 8 scenarios
- RAG retrieval fires exactly once per conversation
- State persistence across turns via MemorySaver

### Manual (Phase 6):

- All Definition of Done criteria from spec.md
- UI responsiveness and conversation quality

## Performance Considerations

- **LLM latency**: gpt-4o-mini is fast (~500ms per call). Each turn = 1 LLM call.
- **RAG retrieval**: Single retrieval at GUIDE_REBOOT entry, cached. ~200ms.
- **Chroma startup**: First load may take 1-2s. Cached via `@st.cache_resource`.
- **Streamlit reruns**: Each user message triggers full rerun. Conversation history replay is fast.

## References

- Spec: [spec.md](spec.md)
- Research: [research.md](research.md)
- PDF: [shared/data/user_guide_EA6350.pdf](shared/data/user_guide_EA6350.pdf)
- LangGraph docs: https://docs.langchain.com/oss/python/langgraph/
- Chroma docs: https://docs.trychroma.com/
- Streamlit chat docs: https://docs.streamlit.io/develop/api-reference/chat
