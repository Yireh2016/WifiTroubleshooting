# WifiTroubleshooting WiFi Assistant — Implementation Research

**Date**: 2026-03-30  
**Scope**: Research findings for V1, V2, V3 implementation strategy

---

## 1. LangGraph State Machine Architecture

### State Schema with Pydantic

LangGraph accepts a Pydantic `BaseModel` directly as the `StateGraph` type parameter. Each node receives the full state object and returns a **partial dict** (only changed fields), which LangGraph merges automatically.

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional, List
from langchain_core.messages import BaseMessage

class ConversationState(BaseModel):
    messages: List[BaseMessage] = Field(default_factory=list)
    user_input: str = ""
    reboot_appropriate: Optional[bool] = None
    issue_resolved: Optional[bool] = None
    current_step: int = 0
    current_node: str = "qualify"
    rag_context: Optional[str] = None
```

### Graph Construction Pattern

```python
from langgraph.graph import StateGraph, START, END

graph = StateGraph(ConversationState)

# Add all nodes
graph.add_node("qualify", qualify_node)
graph.add_node("graceful_exit", graceful_exit_node)
graph.add_node("guide_reboot", guide_reboot_node)
graph.add_node("check_resolution", check_resolution_node)
graph.add_node("close_success", close_success_node)
graph.add_node("apologize_and_exit", apologize_and_exit_node)

# Wire edges with conditional routing
graph.add_edge(START, "qualify")
graph.add_conditional_edges(
    "qualify",
    route_after_qualify,  # function that returns a string
    {
        "guide_reboot": "guide_reboot",
        "graceful_exit": "graceful_exit",
    }
)

# Terminal edges
graph.add_edge("graceful_exit", END)
graph.add_edge("close_success", END)
graph.add_edge("apologize_and_exit", END)

app = graph.compile()
```

### Routing Functions

```python
def route_after_qualify(state: ConversationState) -> str:
    """
    Return a string that maps to a node name in the path dict.
    Every possible return value must be covered or LangGraph raises KeyError.
    """
    return "guide_reboot" if state.reboot_appropriate else "graceful_exit"
```

### Node Function Pattern

```python
from langchain_openai import ChatOpenAI
import json

LLM = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

def qualify_node(state: ConversationState) -> dict:
    """
    Node functions read state in, call LLM, return partial dict.
    Only return fields that changed — LangGraph merges automatically.
    """
    prompt = f"""You are a WiFi troubleshooting agent. The user said:
"{state.user_input}"

Determine if all devices are offline or if just one device is affected.
Ask one question at a time about observable signs.

Respond with JSON:
{{
  "decision": "ask_more" | "proceed" | "exit",
  "reason": "...",
  "reply": "..."
}}"""
    
    response = LLM.invoke([{"role": "system", "content": prompt}])
    parsed = json.loads(response.content)
    
    return {
        "messages": state.messages + [
            {"role": "user", "content": state.user_input},
            {"role": "assistant", "content": parsed["reply"]},
        ],
        "reboot_appropriate": (parsed["decision"] == "proceed"),
    }
```

### Multi-Turn Qualify Logic

**Key insight**: The qualify node needs to loop until a decision is reached. Use a conditional edge that checks if `reboot_appropriate` is still `None`:

```python
def route_after_qualify(state: ConversationState) -> str:
    # If still deciding, stay in qualify for next turn
    if state.reboot_appropriate is None:
        return "qualify"
    # Once decided, route to next node
    return "guide_reboot" if state.reboot_appropriate else "graceful_exit"

graph.add_conditional_edges(
    "qualify",
    route_after_qualify,
    {
        "qualify": "qualify",  # Loop back
        "guide_reboot": "guide_reboot",
        "graceful_exit": "graceful_exit",
    }
)
```

### Conversation Continuity with MemorySaver

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
app = graph.compile(checkpointer=checkpointer)

# In Streamlit, pass thread_id in config
config = {"configurable": {"thread_id": st.session_state.thread_id}}
result = app.invoke(state, config=config)
```

---

## 2. RAG Pipeline (Chroma + PyPDFLoader)

### Required Packages

```
langchain-community>=0.2
langchain-openai>=0.3
langchain-chroma>=0.2
chromadb>=0.5
pypdf>=4.0
langdetect>=1.0.9
```

### Ingest Pipeline Flow

```
PDF file
  ↓
1. Load with PyPDFLoader → List[Document] (one per page)
  ↓
2. Language filter (V1: page range; V2: langdetect) → English pages only
  ↓
3. Concatenate English text
  ↓
4. LLM segments document into sections [{title, tag, content}]
  ↓
5. For each section: create Document with metadata
  ↓
6. Embed with text-embedding-3-small
  ↓
7. Store in Chroma with deduplication check
  ↓
8. Verification query assertion
```

### PyPDFLoader Usage

```python
from langchain_community.document_loaders import PyPDFLoader

loader = PyPDFLoader("shared/data/user_guide.pdf")
pages = loader.load()  # List[Document]

# Each page has:
#   page.page_content  → str (text content)
#   page.metadata      → {"source": "...", "page": 0}

# V1: Hardcoded page range (deterministic, no extra dependency)
english_pages = [p for p in pages if p.metadata["page"] <= 17]
```

### V2: Language Detection with langdetect

```python
from langdetect import detect, DetectorFactory

# Set seed for deterministic results (langdetect is non-deterministic by default)
DetectorFactory.seed = 0

def is_english(text: str, min_length: int = 50) -> bool:
    """Detect if text is English, with minimum length check."""
    if len(text.strip()) < min_length:
        return False
    try:
        return detect(text) == "en"
    except Exception:
        return False

english_pages = [p for p in pages if is_english(p.page_content)]
```

### LLM Section Segmentation

```python
import json
from langchain_openai import ChatOpenAI

LLM = ChatOpenAI(model="gpt-4o-mini")

CANONICAL_TAGS = [
    "overview", "setup", "features",
    "troubleshooting", "specifications", "other"
]

def segment_document_with_llm(full_text: str, model_name: str) -> list[dict]:
    """
    Use LLM to segment any manual structure into canonical sections.
    This allows different manufacturers' manuals to work without code changes.
    """
    prompt = f"""You are parsing a router manual for the {model_name}.

Identify the major sections and extract each one.
Assign each section a tag from this fixed list ONLY: {CANONICAL_TAGS}

Return a JSON array. Each item must have:
- "section_title": the original heading as it appears
- "section_tag": one value from the fixed list
- "content": the complete text of that section

Manual text:
{full_text}

Return ONLY valid JSON. No preamble, no markdown fences."""

    response = LLM.invoke([{"role": "user", "content": prompt}])
    return json.loads(response.content)
```

### Chroma Persistent Vector Store

```python
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

# Embedding function (reuse across ingest and retrieval)
embedding_fn = OpenAIEmbeddings(model="text-embedding-3-small")

# Create or load persistent store
vectorstore = Chroma(
    collection_name="router_manuals",
    persist_directory="chroma_db/v1/",  # Persists to disk
    embedding_function=embedding_fn,
)

# Add documents with metadata
docs = [
    Document(
        page_content="Disconnect the power cord from both router and modem...",
        metadata={
            "model_name": "EA6350",
            "language": "en",
            "section_tag": "troubleshooting",
            "section_title": "Troubleshooting",
            "source_file": "user_guide.pdf",
            "brand": "Linksys",
        }
    ),
    # ... more documents
]

vectorstore.add_documents(documents=docs, ids=ids)
```

### Metadata Schema and Normalization

All metadata fields used in filters must follow exact-match semantics (Chroma does not support fuzzy/substring matching):

```python
metadata = {
    # Filter keys (used in retrieval)
    "model_name": model_name.upper().strip(),  # "ea6350" → "EA6350"
    "language": "en",  # ISO 639-1
    "section_tag": "troubleshooting",  # From canonical list only

    # Observability / debugging
    "brand": "Linksys",
    "model_aliases": ["R63"],
    "section_title": "Troubleshooting",
    "source_file": "user_guide.pdf",
    
    # Deduplication
    "chunk_id": "EA6350_en_troubleshooting",
}
```

### Deduplication Check

```python
import hashlib

def make_doc_id(model_name: str, language: str, section_tag: str) -> str:
    """Generate deterministic ID for deduplication."""
    key = f"{model_name}_{language}_{section_tag}"
    return hashlib.sha256(key.encode()).hexdigest()

def is_already_indexed(vectorstore, model_name: str) -> bool:
    """Check if model already has indexed content."""
    results = vectorstore.get(where={"model_name": model_name.upper()})
    return len(results["ids"]) > 0

# At ingest time
if is_already_indexed(vectorstore, model_name):
    print(f"{model_name} already indexed — skipping.")
    return

# Add documents with explicit IDs
doc_ids = [make_doc_id(model_name, "en", section["section_tag"]) 
           for section in sections]
vectorstore.add_documents(documents=docs, ids=doc_ids)
```

### Retrieval with Metadata Filter

```python
# Single model, single language, single section
results = vectorstore.similarity_search(
    query="How do I reboot my router using the power cord?",
    k=1,
    filter={
        "model_name": "EA6350",
        "language": "en",
        "section_tag": "troubleshooting",
    },
)

if results:
    reboot_steps = results[0].page_content
else:
    reboot_steps = None  # Fallback to safe static message

# Compound filters for multi-model (V3)
results = vectorstore.similarity_search(
    query="reboot steps",
    k=1,
    filter={
        "$and": [
            {"language": "en"},
            {"section_tag": {"$in": ["troubleshooting", "setup"]}},
        ]
    },
)
```

### Retrieval Verification Script

```python
# shared/rag/verify_retrieval.py
def verify_retrieval(vectorstore, model_name: str, version: str):
    """Run after ingest to verify content retrieval."""
    results = vectorstore.similarity_search(
        query="how do I reboot my router using the power cord",
        k=1,
        filter={
            "model_name": model_name.upper(),
            "language": "en",
            "section_tag": "troubleshooting",
        },
    )
    
    assert results, f"No results for {model_name} — check ingest pipeline"
    assert "power cord" in results[0].page_content.lower(), \
        "Reboot steps not found — content missing from manual"
    
    print(f"✓ Verification passed for {model_name}")
    print(f"Retrieved {len(results[0].page_content)} characters")
```

---

## 3. Streamlit Chat UI

### Basic Chat Loop

```python
import streamlit as st
import uuid

st.set_page_config(page_title="WiFi Troubleshooting", layout="wide")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

st.title("WiFi Troubleshooting Assistant")

# Replay message history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Accept user input
if prompt := st.chat_input("Describe your WiFi issue"):
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Call backend (LangGraph)
    with st.chat_message("assistant"):
        response = get_agent_response(prompt, st.session_state.thread_id)
        st.markdown(response)
    
    # Add assistant message to history
    st.session_state.messages.append({"role": "assistant", "content": response})
```

### Caching the Graph Resource

```python
from langgraph.checkpoint.memory import MemorySaver

@st.cache_resource
def get_compiled_graph():
    """Cache the compiled graph so it persists across reruns."""
    checkpointer = MemorySaver()
    graph = build_graph()  # Your graph construction
    return graph.compile(checkpointer=checkpointer)

def get_agent_response(prompt: str, thread_id: str) -> str:
    """Invoke the cached graph with thread continuity."""
    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": thread_id}}
    
    result = graph.invoke(
        {"messages": [HumanMessage(content=prompt)]},
        config=config,
    )
    
    # Extract last assistant message
    return result["messages"][-1].content
```

### Mode Selection (V2)

```python
if "mode" not in st.session_state:
    st.session_state.mode = None

# Show mode selector before chat starts
if st.session_state.mode is None:
    st.title("Select Conversation Mode")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🛠️ Self-Serve (Plain Language)"):
            st.session_state.mode = "self_serve"
            st.rerun()
    with col2:
        if st.button("👨‍💼 Agent-Assisted (Technical)"):
            st.session_state.mode = "agent_assisted"
            st.rerun()
else:
    # Render chat UI with selected mode
    st.info(f"Mode: {st.session_state.mode.replace('_', ' ').title()}")
    render_chat()
```

### Streaming Responses

```python
if prompt := st.chat_input("Message"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        container = st.empty()
        full_response = ""
        
        # Stream mode="messages" yields token-level chunks
        for chunk, metadata in graph.stream(
            {"messages": [HumanMessage(content=prompt)]},
            config={"configurable": {"thread_id": st.session_state.thread_id}},
            stream_mode="messages",
        ):
            if hasattr(chunk, "content") and chunk.content:
                full_response += chunk.content
                container.markdown(full_response + "▌")  # Typewriter effect
        
        container.markdown(full_response)
    
    st.session_state.messages.append({"role": "assistant", "content": full_response})
```

### Key Streamlit Patterns

| Pattern | Note |
|---|---|
| `@st.cache_resource` | Cache expensive resources (compiled graphs, vectorstores) |
| `st.chat_message` | Renders a chat bubble with role styling |
| `st.chat_input` | Single input widget per app, pinned to bottom, returns on Enter |
| `st.session_state` | Persists across reruns — use for conversation history, mode, thread_id |
| `st.empty()` | Replaceable container for streaming/updating content |
| `st.rerun()` | Force re-render after state changes (renamed from `experimental_rerun`) |
| `if prompt := st.chat_input(...)` | Walrus operator — input only added when user types |

---

## 4. LLM Configuration

### gpt-4o-mini for Conversational Agent

```python
from langchain_openai import ChatOpenAI

# Routing decisions: low temperature for consistency
router_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.1,
    api_key=os.getenv("OPENAI_API_KEY"),
)

# User-facing replies: slightly higher temperature for variety
reply_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.3,
)
```

### gpt-4o-mini for Ingest Segmentation

```python
# At ingest time: structure-agnostic section detection
response = ChatOpenAI(model="gpt-4o-mini").invoke([{
    "role": "user",
    "content": f"Segment this manual into sections...\n{full_text}"
}])
sections = json.loads(response.content)
```

---

## 5. Key Implementation Gotchas & Solutions

| Issue | Solution |
|---|---|
| **Multi-turn qualify** | Use conditional edge that checks `if state.reboot_appropriate is None: return "qualify"` to loop |
| **Retrieval timing** | Fire retrieval **only** at `GUIDE_REBOOT` entry. Qualify is pure conversation — no document context needed |
| **langdetect non-determinism** | Set `DetectorFactory.seed = 0` before any detect() calls |
| **Chroma exact-match filters** | Normalize model_name to uppercase at ingest. Filters do not support substring/fuzzy matching |
| **Separate Chroma stores per version** | V1 and V2 use different ingest pipelines (page range vs langdetect). Use separate `chroma_db/v1/` and `chroma_db/v2/` to prevent cross-contamination |
| **sys.path for imports** | In `agents/vN/app.py`, add: `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))` to import from `shared/` |
| **MemorySaver thread_id** | Pass `config={"configurable": {"thread_id": uuid}}` to every graph invoke for conversation continuity |
| **Pydantic v2 validation** | State schema validates on every transition — catches routing bugs early |
| **LangSmith tracing (V2)** | Set env vars `LANGCHAIN_TRACING=true` and `LANGCHAIN_API_KEY=<key>`. Zero code changes needed |

---

## 6. Recommended Implementation Order for V1

1. **`shared/state/state_v1.py`** — Pydantic schema with all V1 fields
2. **`shared/rag/ingest_v1.py`** — PDF load → English filter (page range) → LLM segment → Chroma store
3. **`shared/rag/retriever.py`** — Wrapper for similarity_search with metadata filter
4. **`shared/rag/verify_retrieval.py`** — Verification script (run after ingest)
5. **`shared/prompts/base_prompts.py`** — Prompt templates (qualify, guide, check, exits)
6. **`agents/v1/nodes.py`** — All 7 node functions (qualify, graceful_exit, etc.)
7. **`agents/v1/graph.py`** — StateGraph construction + routing functions
8. **`agents/v1/app.py`** — Streamlit UI + graph integration
9. **`agents/v1/requirements.txt`** — Pinned dependencies
10. **`agents/v1/README.md`** — User-facing documentation

---

## 7. Testing Strategy

### Verify Ingest Pipeline

```bash
python shared/rag/ingest_v1.py
python shared/rag/verify_retrieval.py --version v1
```

Assertions:
- Spanish content absent from store (verify with Spanish query returning empty)
- "power cord" appears in retrieved reboot section
- Retrieval latency reasonable (~100-200ms)

### Test State Machine Flow

```python
# Test file: test_graph.py
from agents.v1.graph import build_graph

graph = build_graph()
app = graph.compile()

# Test qualify → graceful_exit (single device affected)
state = ConversationState(
    messages=[],
    user_input="My laptop can't connect but others work fine"
)
result = app.invoke(state)
assert result["current_node"] == "graceful_exit"

# Test qualify → guide_reboot (all devices down)
state = ConversationState(
    messages=[],
    user_input="Everything is offline"
)
result = app.invoke(state)
# After multiple turns, should reach guide_reboot
```

### Manual Streamlit Testing

```bash
streamlit run agents/v1/app.py
# Test: Single-device scenario → should exit gracefully
# Test: All-offline scenario → should guide reboot
# Test: Empty input → should not crash
# Test: Off-topic input → should stay in qualify
```

---

## 8. Environment Setup

### `.env.example`

```
# OpenAI API
OPENAI_API_KEY=sk-...

# LangSmith (optional, V2+)
LANGCHAIN_TRACING=false
LANGCHAIN_API_KEY=

# LangChain debugging
LANGCHAIN_VERBOSE=false
```

### `.gitignore`

```
.env
chroma_db/
__pycache__/
*.pyc
.streamlit/secrets.toml
```

---

## Sources

- [LangGraph Graph API Overview](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [Pydantic v2 BaseModel](https://docs.pydantic.dev/latest/)
- [PyPDFLoader - LangChain](https://python.langchain.com/docs/integrations/document_loaders/pypdfloader/)
- [Chroma Vector Store Guide](https://docs.trychroma.com/guides)
- [LangChain Chroma Integration](https://python.langchain.com/docs/integrations/vectorstores/chroma/)
- [langdetect PyPI](https://pypi.org/project/langdetect/)
- [Streamlit Chat Elements](https://docs.streamlit.io/develop/api-reference/chat)
- [Streamlit Session State](https://docs.streamlit.io/develop/concepts/design-patterns/session-state)

