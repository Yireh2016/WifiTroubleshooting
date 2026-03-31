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
            "$and": [
                {"model_name": model_name.upper().strip()},
                {"language": "en"},
                {"section_tag": section_tag},
            ]
        },
    )
    return results
