#!/usr/bin/env python3
"""Standalone CLI to query LanceDB vector store on GCS.

Usage:
    python local_vector_cli.py

Requirements:
    pip install lancedb sentence-transformers
"""

import os
import sys

import lancedb
from sentence_transformers import SentenceTransformer


def main():
    """Simple CLI to query handbook vector store."""
    # Configuration
    GCS_BUCKET = os.getenv("GCS_BUCKET_NAME", "thoth-dev-485501-thoth-storage")
    GCS_PROJECT = os.getenv("GCP_PROJECT_ID", "thoth-dev-485501")
    LANCEDB_URI = f"gs://{GCS_BUCKET}/lancedb"
    COLLECTION_NAME = "handbook_documents"
    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

    print("=" * 80)
    print("📚 Handbook Vector Search CLI")
    print("=" * 80)
    print(f"LanceDB URI: {LANCEDB_URI}")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Model: {MODEL_NAME}")
    print("-" * 80)

    # Load embedding model
    print("Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME)
    print("✓ Model loaded")

    # Connect to LanceDB
    print(f"Connecting to LanceDB at {LANCEDB_URI}...")
    try:
        db = lancedb.connect(LANCEDB_URI)
        print("✓ Connected to LanceDB")
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        sys.exit(1)

    # Open table
    print(f"Opening table '{COLLECTION_NAME}'...")
    try:
        table = db.open_table(COLLECTION_NAME)
        count = table.count_rows()
        print(f"✓ Table opened ({count:,} documents)")
    except Exception as e:
        print(f"✗ Failed to open table: {e}")
        print(f"\nAvailable tables: {db.table_names()}")
        sys.exit(1)

    print("=" * 80)
    print("Ready! Type your questions (or 'quit' to exit)")
    print("=" * 80)

    # Query loop
    while True:
        try:
            # Get query
            print()
            query = input("❓ Question: ").strip()

            if not query:
                continue

            if query.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            # Generate embedding
            query_vector = model.encode(query).tolist()

            # Search
            results = table.search(query_vector).limit(5).to_pandas()

            # Display results
            print(f"\n🔍 Found {len(results)} results:\n")

            for idx, row in results.iterrows():
                print(f"📄 Result {idx + 1}:")
                print(f"   Score: {row.get('_distance', 'N/A'):.4f}")

                # Show metadata
                if "source_file" in row:
                    print(f"   File: {row['source_file']}")
                if "chunk_index" in row:
                    print(f"   Chunk: {row['chunk_index']}")

                # Show text snippet
                text = row.get("text", "")
                if len(text) > 300:
                    text = text[:297] + "..."
                print(f"   Text: {text}")
                print()

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\n✗ Error: {e}")


if __name__ == "__main__":
    main()
