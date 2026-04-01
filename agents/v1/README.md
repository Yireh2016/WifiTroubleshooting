# WifiTroubleshooting V1 — Physical Reboot Agent

**Overview:** See the root [`README.md`](../../README.md) for project architecture, design decisions, testing strategy, and general setup.

This document covers **V1-specific implementation details**.

## Graph Structure & Nodes

V1's agent is a LangGraph state machine with 7 nodes:

| Node | Input | Logic | Output |
|------|-------|-------|--------|
| **QUALIFY** | User message, conversation history | Ask qualification questions (all devices offline? ISP outage? already rebooted?) | `reboot_appropriate: bool` |
| **GUIDE_REBOOT** | `reboot_appropriate=True` | Retrieve reboot steps (RAG) once, cache in state, show first step | `current_step=0`, `rag_context` |
| **CONFIRM_STEP** | User message | Ask "did that step work?" → increment `current_step` | `current_step++` |
| **CHECK_RESOLUTION** | After all steps | Ask "is WiFi back?" | `exit_reason: str` |
| **CLOSE_SUCCESS** | Resolution confirmed | "Glad I could help!" | Exit gracefully |
| **APOLOGIZE_AND_EXIT** | Resolution not confirmed | "Sorry I couldn't help, try contacting support." | Exit gracefully |
| **GRACEFUL_EXIT** | Qualification fails | "This isn't a reboot situation — [reason]. Let me know if you need more help." | Exit gracefully |

**Key routing:**
- If `reboot_appropriate=False` → GRACEFUL_EXIT
- If `reboot_appropriate=True` → GUIDE_REBOOT → loop CONFIRM_STEP → CHECK_RESOLUTION → CLOSE_SUCCESS or APOLOGIZE_AND_EXIT

## State Schema

V1 uses `shared/state/state_v1.py` (ConversationState):

```python
class ConversationState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # LangGraph auto-dedupes
    reboot_appropriate: bool  # Qualification result
    current_step: int  # 0-indexed; incremented after confirm
    rag_context: str  # Retrieved reboot instructions (cached after first GUIDE_REBOOT)
    exit_reason: str  # Why agent exited: "single_device", "isp_outage", "excessive_reboots", etc.
```

## Running V1

From repo root:

```bash
cp .env.example .env       # Edit with OPENAI_API_KEY
pip install -r agents/v1/requirements.txt
python shared/rag/ingest_v1.py       # One-time: ingest PDF
streamlit run agents/v1/app.py        # Then visit http://localhost:8501
```

See root `README.md` "Quickstart" for full setup with verification steps.

## Prompt Templates

All prompts live in `shared/prompts/` and are injected with:
- `{rag_context}` — Retrieved reboot steps from Chroma
- `{current_step}` — Step number to show user
- `{exit_reason}` — Reason for graceful exit
- `{reboot_appropriate}` — True/False qualification result

Each prompt must mention "JSON" in the text because nodes use `response_format={"type": "json_object"}` to force structured output.

**Example (GUIDE_REBOOT):**
```
User: "My WiFi is down"
Retrieved context: "Step 1: Unplug router from power... Step 2: Wait 30 seconds..."
Prompt: "The user's router is offline. Use the following steps to guide them through a physical reboot. Return JSON with 'step_number', 'action', and 'next_step_prompt'."
Output: {"step_number": 1, "action": "Unplug router", "next_step_prompt": "..."}
```

## Test Files

- **`test_graph.py`** — Graph compilation, node routing, state transitions
- **`test_scenarios.py`** — 8 end-to-end scenarios (single device, ISP outage, success, failure, etc.)
- **`test_app_manual.py`** — Streamlit app smoke tests (no crash, basic flow)

Run with: `pytest agents/v1/ -v` or `python agents/v1/test_graph.py`

For testing strategy and verification gates, see root `README.md` "Testing Strategy".

## Debugging Tips

- **RAG not retrieving:** Run `python shared/rag/verify_retrieval.py --version v1` to check Chroma connectivity and sample queries
- **Graph routing wrong:** Inspect state transitions in `test_graph.py` output — shows actual routing decisions at each node
- **Streamlit crashing:** Use `streamlit run --logger.level=debug agents/v1/app.py` for verbose logs; check `.env` for OPENAI_API_KEY
- **Missing Chroma store:** If `chroma_db/v1/` doesn't exist, re-run `python shared/rag/ingest_v1.py`

See `CLAUDE.md` for deeper debugging guidance (RAG metadata filters, lazy loading, message reducer details).
