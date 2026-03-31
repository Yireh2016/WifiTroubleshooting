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
    tag_counts = {}  # Track how many times we've seen each tag

    for section in sections:
        tag = section["section_tag"]
        # Counter for duplicate tags (0 for first, 1 for second, etc.)
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
        counter = tag_counts[tag] - 1

        # Make chunk IDs unique by adding counter if needed
        if counter == 0:
            chunk_id = f"{model_upper}_en_{tag}"
        else:
            chunk_id = f"{model_upper}_en_{tag}_{counter}"

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
