#!/usr/bin/env python3
"""
Build FAISS index from LCHA embeddings for fast similarity search.

FAISS (Facebook AI Similarity Search) provides efficient vector similarity
search at scale. We use IndexFlatIP for inner product (dot product) search,
which is equivalent to cosine similarity on normalized vectors.

Usage:
    python build_faiss_index.py
"""

import json
import numpy as np
import faiss
import os

INPUT_DIR = "data/vectors"
OUTPUT_DIR = "data/search"

def build_faiss_index():
    """Build FAISS index from embeddings and metadata."""

    print("Loading embeddings...")
    vectors = np.load(f"{INPUT_DIR}/lcha_vectors.npy")
    print(f"  Loaded {vectors.shape[0]} vectors, dim={vectors.shape[1]}")

    print("Loading metadata...")
    with open(f"{INPUT_DIR}/lcha_metadata.json") as f:
        metadata = json.load(f)
    print(f"  Loaded {len(metadata)} metadata entries")

    # Normalize vectors for cosine similarity
    # Inner Product on normalized vectors = Cosine Similarity
    print("Normalizing vectors for cosine similarity...")
    faiss.normalize_L2(vectors)

    # Create FAISS index
    # IndexFlatIP = Flat (exact) index using Inner Product
    print("Creating FAISS index (IndexFlatIP)...")
    dimension = vectors.shape[1]
    index = faiss.IndexFlatIP(dimension)

    # Add vectors to index
    print(f"Adding {vectors.shape[0]} vectors to index...")
    index.add(vectors)
    print(f"  Index now contains {index.ntotal} vectors")

    # Create output directory
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # Save FAISS index
    index_path = f"{OUTPUT_DIR}/lcha.faiss"
    faiss.write_index(index, index_path)
    print(f"Saved FAISS index to: {index_path}")

    # Save metadata for search
    metadata_path = f"{OUTPUT_DIR}/lcha_metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved metadata to: {metadata_path}")

    # Verify index
    print("\nVerifying index...")
    test_index = faiss.read_index(index_path)
    print(f"  Loaded index contains {test_index.ntotal} vectors")

    # Test search with a sample query
    print("\nTesting search with sample query...")
    query_vector = vectors[0:1]  # Use first vector as test query
    k = 5  # Return top 5 results
    distances, indices = test_index.search(query_vector, k)

    print(f"  Top {k} results for test query:")
    for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
        item_id = metadata[idx]['id']
        item_type = metadata[idx]['type']
        text_preview = metadata[idx]['text'][:50].replace('\n', ' ')
        print(f"    {i+1}. [{item_id}] ({item_type}) - similarity: {dist:.4f}")
        print(f"       {text_preview}...")

    print("\n" + "="*60)
    print("FAISS INDEX BUILD COMPLETE")
    print("="*60)
    print(f"Index: {index_path}")
    print(f"Metadata: {metadata_path}")
    print(f"Vectors: {index.ntotal}")
    print(f"Dimension: {dimension}")


if __name__ == "__main__":
    build_faiss_index()
