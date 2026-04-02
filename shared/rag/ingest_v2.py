import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from langdetect import detect, LangDetectException
from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.documents import Document

load_dotenv()

CANONICAL_TAGS = [
    "overview", "setup", "features",
    "troubleshooting", "specifications", "other"
]

CHROMA_PATH = Path(__file__).resolve().parents[2] / "chroma_db" / "v2"
SUPPORTED_LANGUAGES = {"en", "fr", "es", "de", "pt", "it"}


def detect_page_language(page_text: str) -> str:
    """Detect language of a PDF page. Returns ISO 639-1 code or 'unknown'."""
    if not page_text or len(page_text.strip()) < 10:
        return "unknown"
    try:
        lang = detect(page_text)
        return lang if lang in SUPPORTED_LANGUAGES else "unknown"
    except LangDetectException:
        return "unknown"


def load_english_pages(pdf_path: str) -> list:
    """Load PDF, detect language per page with langdetect, keep only English."""
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    english_pages = []

    for page in pages:
        lang = detect_page_language(page.page_content)
        if lang == "en":
            english_pages.append(page)

    return english_pages


def segment_document_with_llm(full_text: str, model_name: str) -> list[dict]:
    """Use LLM to segment manual into canonical sections. Same pattern as V1."""
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


def build_documents(sections: list[dict], model_name: str, brand: str) -> tuple[list[Document], list[str]]:
    """Create Documents with V2 metadata schema (model_name, brand, language, section_tag, chunk_id, source_file)."""
    docs = []
    ids = []
    model_upper = model_name.upper().strip()
    brand_upper = brand.upper().strip()
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
            "brand": brand_upper,
            "language": "en",
            "section_tag": tag,
            "section_title": section["section_title"],
            "source_file": f"user_guide_{model_upper}.pdf",
            "chunk_id": chunk_id,
        }
        docs.append(Document(page_content=section["content"], metadata=metadata))
        ids.append(chunk_id)
    return docs, ids


def is_already_indexed(vectorstore, model_name: str) -> bool:
    """Check if model already exists in collection."""
    results = vectorstore.get(where={"model_name": model_name.upper().strip()})
    return len(results["ids"]) > 0


def ingest(model_name: str, brand: str, pdf_path: str, chroma_path: str = None):
    """Main ingest: load PDF -> langdetect filter -> LLM segment -> embed -> store."""
    chroma = chroma_path or str(CHROMA_PATH)

    # Create chroma directory if it doesn't exist
    Path(chroma).mkdir(parents=True, exist_ok=True)

    embedding_fn = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = Chroma(
        collection_name="router_manuals",
        persist_directory=chroma,
        embedding_function=embedding_fn,
    )

    if is_already_indexed(vectorstore, model_name):
        print(f"{model_name} already indexed — skipping.")
        return vectorstore

    print(f"Loading PDF: {pdf_path}")
    english_pages = load_english_pages(pdf_path)
    if not english_pages:
        print(f"Warning: No English pages found in {pdf_path}")
        return vectorstore

    full_text = "\n".join([p.page_content for p in english_pages])
    print(f"Loaded {len(english_pages)} English pages ({len(full_text)} chars)")

    print("Segmenting document with LLM...")
    sections = segment_document_with_llm(full_text, model_name)
    print(f"Found {len(sections)} sections: {[s['section_tag'] for s in sections]}")

    docs, ids = build_documents(sections, model_name, brand)

    print(f"Embedding and storing {len(docs)} sections...")
    vectorstore.add_documents(documents=docs, ids=ids)
    print(f"Ingest complete for {model_name}. Store at: {chroma}")

    return vectorstore


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest router manual into V2 Chroma collection")
    parser.add_argument("--pdf", required=True, help="Path to router manual PDF")
    parser.add_argument("--model", required=True, help="Router model name (e.g., EA6350)")
    parser.add_argument("--brand", required=True, help="Router brand (e.g., Linksys)")
    args = parser.parse_args()
    ingest(model_name=args.model, brand=args.brand, pdf_path=args.pdf)
