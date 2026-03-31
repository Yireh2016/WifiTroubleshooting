import argparse
import sys
from pathlib import Path

# Add repo root to path for shared imports FIRST
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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
        filter={"$and": [{"model_name": "EA6350"}, {"language": "es"}]},
    )
    assert not spanish_results, "FAIL: Spanish content found in store"
    print("PASS: No Spanish content in store")

    print(f"\nAll verification checks passed for {version}.")
    print(f"\nRetrieved content preview:\n{results[0].page_content[:500]}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1", choices=["v1", "v2", "v3"])
    args = parser.parse_args()

    verify(args.version)
