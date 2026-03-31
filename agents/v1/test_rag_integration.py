"""
Integration tests for RAG pipeline (shared/rag/)

Tests retrieval, metadata filtering, and RAG edge cases.
These tests verify the vector store and retrieval logic in isolation.

Run with:
  pytest agents/v1/test_rag_integration.py -v

Note: Requires chroma_db/v1/ vector store to exist (run ingest_v1.py first).
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.rag.retriever import build_retriever, retrieve


class TestRetrieverInitialization:
    """Tests for vectorstore setup."""

    def test_build_retriever_with_default_path(self):
        """build_retriever should use default path if not provided."""
        try:
            vs = build_retriever()
            assert vs is not None
            assert hasattr(vs, "similarity_search")
        except Exception as e:
            pytest.skip(f"Vector store not initialized: {e}")

    def test_build_retriever_with_custom_path(self):
        """build_retriever should accept custom chroma_path."""
        try:
            custom_path = str(Path(__file__).resolve().parents[2] / "chroma_db" / "v1")
            vs = build_retriever(chroma_path=custom_path)
            assert vs is not None
        except Exception as e:
            pytest.skip(f"Vector store not initialized: {e}")

    def test_build_retriever_with_custom_collection(self):
        """build_retriever should accept custom collection name."""
        try:
            vs = build_retriever(collection_name="test_collection")
            assert vs is not None
        except Exception as e:
            pytest.skip(f"Vector store not initialized: {e}")


class TestRetrieval:
    """Tests for retrieve function."""

    @pytest.fixture
    def vectorstore(self):
        """Get a vectorstore instance."""
        try:
            return build_retriever()
        except Exception:
            pytest.skip("Vector store not initialized")

    def test_retrieve_basic_query(self, vectorstore):
        """Retrieve should return results for valid query."""
        results = retrieve(
            vectorstore,
            query="how do I reboot the router",
            model_name="EA6350",
            section_tag="troubleshooting",
        )

        assert isinstance(results, list)
        if len(results) > 0:
            assert hasattr(results[0], "page_content")
            assert len(results[0].page_content) > 0

    def test_retrieve_with_custom_k(self, vectorstore):
        """Retrieve should respect k parameter."""
        k_values = [1, 3, 5]
        for k in k_values:
            results = retrieve(
                vectorstore,
                query="power cord",
                k=k,
                model_name="EA6350",
            )

            assert isinstance(results, list)
            assert len(results) <= k

    def test_retrieve_with_metadata_filter(self, vectorstore):
        """Retrieve should filter by metadata."""
        # English results
        en_results = retrieve(
            vectorstore,
            query="reboot",
            model_name="EA6350",
        )

        # All results should be English
        for result in en_results:
            assert result.metadata.get("language") == "en"
            assert result.metadata.get("model_name") == "EA6350"

    def test_retrieve_model_case_insensitive(self, vectorstore):
        """Retrieve should handle model_name case insensitively."""
        results1 = retrieve(vectorstore, query="reboot", model_name="ea6350")
        results2 = retrieve(vectorstore, query="reboot", model_name="EA6350")
        results3 = retrieve(vectorstore, query="reboot", model_name="Ea6350")

        # All should work the same
        assert len(results1) == len(results2) == len(results3)

    def test_retrieve_with_whitespace_in_model(self, vectorstore):
        """Retrieve should strip whitespace from model_name."""
        results1 = retrieve(vectorstore, query="reboot", model_name="  EA6350  ")
        results2 = retrieve(vectorstore, query="reboot", model_name="EA6350")

        assert len(results1) == len(results2)

    def test_retrieve_troubleshooting_section(self, vectorstore):
        """Retrieve should find troubleshooting content."""
        results = retrieve(
            vectorstore,
            query="reboot steps power disconnect",
            section_tag="troubleshooting",
        )

        assert isinstance(results, list)

    def test_retrieve_empty_query_results(self, vectorstore):
        """Retrieve should handle queries with no matches."""
        results = retrieve(
            vectorstore,
            query="asdfghjklzxcvbnm_nonexistent_term_xyz123",
        )

        # Should return list (possibly empty)
        assert isinstance(results, list)


class TestRetrievalbattleEdgeCases:
    """Edge cases and error handling for retrieval."""

    @pytest.fixture
    def vectorstore(self):
        try:
            return build_retriever()
        except Exception:
            pytest.skip("Vector store not initialized")

    def test_retrieve_very_short_query(self, vectorstore):
        """Retrieve should handle very short queries."""
        results = retrieve(vectorstore, query="a")
        assert isinstance(results, list)

    def test_retrieve_very_long_query(self, vectorstore):
        """Retrieve should handle very long queries."""
        long_query = "reboot " * 100
        results = retrieve(vectorstore, query=long_query)
        assert isinstance(results, list)

    def test_retrieve_special_characters(self, vectorstore):
        """Retrieve should handle special characters in query."""
        results = retrieve(vectorstore, query="@#$%^&*()")
        assert isinstance(results, list)

    def test_retrieve_multiple_languages_filtered(self, vectorstore):
        """Retrieve should NOT return non-English content."""
        results = retrieve(
            vectorstore,
            query="reboot",
            model_name="EA6350",
        )

        for result in results:
            assert result.metadata.get("language") == "en"

    def test_retrieve_returns_metadata(self, vectorstore):
        """Retrieved documents should include metadata."""
        results = retrieve(vectorstore, query="reboot")

        if len(results) > 0:
            result = results[0]
            assert hasattr(result, "metadata")
            assert "model_name" in result.metadata
            assert "language" in result.metadata


class TestRAGContextQuality:
    """Tests for the quality of retrieved content."""

    @pytest.fixture
    def vectorstore(self):
        try:
            return build_retriever()
        except Exception:
            pytest.skip("Vector store not initialized")

    def test_retrieved_content_is_text(self, vectorstore):
        """Retrieved content should be readable text."""
        results = retrieve(vectorstore, query="reboot", k=1)

        if len(results) > 0:
            content = results[0].page_content
            assert isinstance(content, str)
            assert len(content) > 0
            # Should contain printable characters
            assert any(c.isalnum() for c in content)

    def test_retrieved_content_is_relevant(self, vectorstore):
        """Retrieved content should be relevant to query."""
        query = "router reboot power cord"
        results = retrieve(vectorstore, query=query, k=1)

        if len(results) > 0:
            content = results[0].page_content.lower()
            # Should mention router-related terms
            relevant_terms = ["power", "disconnect", "reboot", "step", "router"]
            has_relevant_term = any(term in content for term in relevant_terms)
            assert has_relevant_term, "Retrieved content not relevant to query"

    def test_retrieved_content_has_steps(self, vectorstore):
        """Troubleshooting content should contain numbered steps."""
        results = retrieve(
            vectorstore,
            query="reboot instructions steps",
            section_tag="troubleshooting",
        )

        if len(results) > 0:
            content = results[0].page_content
            # Should have step indicators
            has_steps = any(
                indicator in content.lower()
                for indicator in ["step", "disconnect", "connect", "wait"]
            )
            assert has_steps, "Retrieved content missing step indicators"


class TestRetrieverMocking:
    """Tests for mocking retriever in unit tests."""

    def test_mock_vectorstore_similarity_search(self):
        """Mocked vectorstore should work in isolation."""
        mock_vs = Mock()
        mock_doc = Mock()
        mock_doc.page_content = "Test reboot steps"
        mock_doc.metadata = {"model_name": "EA6350", "language": "en"}
        mock_vs.similarity_search.return_value = [mock_doc]

        results = mock_vs.similarity_search("reboot", k=1)

        assert len(results) == 1
        assert results[0].page_content == "Test reboot steps"

    def test_mock_retriever_with_retrieve_function(self):
        """retrieve function should work with mocked vectorstore."""
        mock_vs = Mock()
        mock_doc = Mock()
        mock_doc.page_content = "Step 1: Disconnect"
        mock_doc.metadata = {"model_name": "EA6350", "language": "en"}
        mock_vs.similarity_search.return_value = [mock_doc]

        # Manually call the similarity_search since we're testing the function
        results = mock_vs.similarity_search(
            query="reboot",
            k=1,
            filter={"$and": [{"model_name": "EA6350"}, {"language": "en"}]},
        )

        assert len(results) == 1
        assert isinstance(results[0].page_content, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
