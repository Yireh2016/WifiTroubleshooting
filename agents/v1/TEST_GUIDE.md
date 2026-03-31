# Test Guide - RouteThis V1 Agent

## Test Suite Overview

The agent test suite has been consolidated into a comprehensive pytest-based system:

| Test File | Purpose | Coverage | Type |
|-----------|---------|----------|------|
| `test_nodes.py` | Node logic and routing | 7 nodes, 9 routing functions, state mutations | Unit |
| `test_scenarios.py` | Conversation flows (8 scenarios) | End-to-end user journeys, message persistence | Integration |
| `test_rag_integration.py` | RAG pipeline | Vector store, retrieval, metadata filtering | Integration |
| `test_prompts.py` | Prompt templates and LLM responses | JSON parsing, template injection, edge cases | Unit |
| `test_graph.py` | Graph structure and imports | Graph build/compile, node imports | Unit |

## Setup

```bash
# 1. Install test dependencies
pip install -r agents/v1/requirements.txt

# 2. Ingest PDF (one-time)
python shared/rag/ingest_v1.py

# 3. Create .env with OPENAI_API_KEY
cp .env.example .env
# edit .env and add your API key
```

## Running Tests

### All Tests
```bash
# Run all tests with verbose output
pytest agents/v1/ -v

# Run with coverage report
pytest agents/v1/ -v --cov=agents/v1 --cov-report=html
```

### By Test Category

```bash
# Unit tests only (fast, mocked LLM)
pytest agents/v1/test_nodes.py agents/v1/test_prompts.py -v

# Integration tests (slower, real graph execution)
pytest agents/v1/test_scenarios.py -v

# RAG tests (requires chroma_db/v1/)
pytest agents/v1/test_rag_integration.py -v

# Specific test class
pytest agents/v1/test_nodes.py::TestQualifyNode -v

# Specific test function
pytest agents/v1/test_nodes.py::TestQualifyNode::test_qualify_asks_more_questions -v
```

### By Marker
```bash
# Unit tests only
pytest agents/v1/ -m unit -v

# Integration tests only
pytest agents/v1/ -m integration -v

# Edge cases
pytest agents/v1/ -m edge_case -v
```

## Test Structure

### Unit Tests (test_nodes.py)
Tests individual node functions with mocked LLM responses. No API calls, very fast.

```python
def test_qualify_asks_more_questions(self, patch_llm_module, json_response_factory):
    # Arrange
    state = ConversationState(messages=[...])
    response = Mock()
    response.content = json.dumps(json_response_factory("qualify", decision="ask_more"))
    patch_llm_module.invoke.return_value = response

    # Act
    result = nodes.qualify(state)

    # Assert
    assert "reboot_appropriate" not in result
```

**Fixtures:**
- `patch_llm_module` — Mocked ChatOpenAI
- `patch_vectorstore_module` — Mocked Chroma
- `sample_state` — Base ConversationState
- `json_response_factory` — Create mock node responses

### Integration Tests (test_scenarios.py)
Tests full conversation flows with the compiled graph. Real node execution, uses mocked LLM.

```python
def test_single_device_graceful_exit(self, graph, graph_config):
    messages = [
        "My laptop can't connect but my phone works fine.",
        "Yes, the phone works. It's just the laptop.",
    ]

    result = None
    for msg in messages:
        result = graph.invoke({"messages": [HumanMessage(content=msg)]}, config=graph_config)

    assert result.get("last_executed_node") == "graceful_exit"
```

**Fixtures:**
- `graph` — Compiled LangGraph agent
- `graph_config` — LangGraph config with thread ID
- `thread_id` — Unique thread identifier

### RAG Tests (test_rag_integration.py)
Tests vector store and retrieval logic. Skips if chroma_db/v1/ not present.

```python
def test_retrieve_troubleshooting_section(self, vectorstore):
    results = retrieve(vectorstore, query="reboot", section_tag="troubleshooting")
    assert isinstance(results, list)
```

**Fixtures:**
- `vectorstore` — Chroma instance (skips if missing)

### Prompt Tests (test_prompts.py)
Tests prompt structure, JSON parsing, and template injection.

```python
def test_graceful_exit_injects_exit_reason(self):
    prompt = GRACEFUL_EXIT_PROMPT.format(exit_reason="single_device")
    assert "single_device" in prompt
```

## Common Issues

### Tests Fail: `KeyError: 'OPENAI_API_KEY'`
**Cause:** Missing `.env` file or empty API key
**Solution:**
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### Tests Skip: `Vector store not initialized`
**Cause:** chroma_db/v1/ doesn't exist
**Solution:**
```bash
python shared/rag/ingest_v1.py
```

### Tests Fail: `No module named 'shared'`
**Cause:** sys.path not configured
**Solution:** conftest.py already handles this, but ensure you're running pytest from the repo root

### Tests Fail: `RuntimeError: no current event loop`
**Cause:** Async/await issues in LangGraph
**Solution:** Tests handle this, but ensure asyncio is available

## Coverage Goals

| Category | Goal | Current |
|----------|------|---------|
| Node functions | 95% | In progress |
| Routing logic | 100% | ✓ Complete |
| State mutations | 85% | In progress |
| RAG pipeline | 80% | Partial |
| Prompts | 90% | In progress |
| **Overall** | **85%** | In progress |

## Adding New Tests

### For a New Node
```python
class TestNewNode:
    """Tests for new_node."""

    def test_new_node_basic(self, patch_llm_module, json_response_factory):
        state = ConversationState(messages=[...])

        response = Mock()
        response.content = json.dumps(json_response_factory("new_node", ...))
        patch_llm_module.invoke.return_value = response

        result = nodes.new_node(state)

        assert "expected_field" in result
```

### For a New Scenario
```python
class TestScenarioNewScenario:
    """S99: New scenario description."""

    def test_scenario_description(self, graph, graph_config):
        messages = ["User message 1", "User message 2"]

        result = None
        for msg in messages:
            result = graph.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=graph_config,
            )

        assert result.get("last_executed_node") == "expected_node"
```

## Deprecated Scripts

The following scripts are now superseded by the pytest suite:

- ~~`manual_validation.py`~~ → Archived as `manual_validation.py.bak`
- ~~`test_app_manual.py`~~ → Replaced by `test_scenarios.py`

These were print-based validation scripts without assertions. The new pytest suite provides:
- ✓ Automatic test discovery
- ✓ Clear pass/fail status
- ✓ Coverage reporting
- ✓ CI/CD integration
- ✓ Faster failure detection

## Next Steps

1. **Run tests locally:** `pytest agents/v1/ -v`
2. **Check coverage:** `pytest agents/v1/ --cov=agents/v1 --cov-report=term-missing`
3. **Add to CI/CD:** Integrate pytest into your GitHub Actions / CI pipeline
4. **Monitor coverage:** Set up coverage badges and trends
5. **Expand RAG tests:** More edge cases once vector store is stable

## References

- Pytest docs: https://docs.pytest.org
- Pytest fixtures: https://docs.pytest.org/en/stable/how-to-use-fixtures.html
- LangGraph docs: https://langchain-ai.github.io/langgraph/
- Testing best practices: See `conftest.py` for fixture patterns
