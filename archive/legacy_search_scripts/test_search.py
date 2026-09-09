#!/usr/bin/env python3
"""
Test semantic search on LCHA FAISS index.

This script demonstrates natural language queries against the LCHA contract
using the Kanon 2 embeddings and FAISS for similarity search.

Usage:
    python test_search.py
"""

import json
import numpy as np
import faiss
from isaacus import Isaacus
from config import Config

# Validate configuration
Config.validate()

# Initialize Isaacus client
client = Isaacus(api_key=Config.ISAACUS_API_KEY)


def load_index():
    """Load FAISS index and metadata."""
    print("Loading FAISS index...")
    index = faiss.read_index(f"{Config.SEARCH_DIR}/lcha.faiss")
    print(f"  Index contains {index.ntotal} vectors")

    print("Loading metadata...")
    with open(f"{Config.SEARCH_DIR}/lcha_metadata.json") as f:
        metadata = json.load(f)
    print(f"  Loaded {len(metadata)} metadata entries")

    return index, metadata


def embed_query(query_text):
    """Embed a query using Kanon 2 with retrieval/query task."""
    response = client.embeddings.create(
        model=Config.ISAACUS_MODEL_ID,
        texts=query_text,
        task="retrieval/query",
    )
    return np.array([response.embeddings[0].embedding], dtype='float32')


def search(query, index, metadata, k=5):
    """Search the index and return top k results."""
    # Embed query
    query_vector = embed_query(query)

    # Normalize for cosine similarity
    faiss.normalize_L2(query_vector)

    # Search
    distances, indices = index.search(query_vector, k)

    return distances[0], indices[0]


def format_result(dist, idx, metadata):
    """Format a search result for display."""
    item = metadata[idx]
    item_id = item['id']
    item_type = item['type']
    text = item['text']

    # Get breadcrumb if available
    # (We don't have breadcrumb in current metadata, but we have id)
    part_num = item_id.split('.')[0].replace('part', 'Part ')

    # Truncate text for display
    max_len = 150
    if len(text) > max_len:
        text = text[:max_len] + "..."

    return {
        'id': item_id,
        'part': part_num,
        'type': item_type,
        'similarity': float(dist),
        'text': text
    }


def print_results(query, distances, indices, metadata):
    """Print search results."""
    print(f"\n{'='*70}")
    print(f"QUERY: {query}")
    print(f"{'='*70}")

    if len(distances) == 0:
        print("No results found.")
        return

    for i, (dist, idx) in enumerate(zip(distances, indices)):
        if idx == -1:  # FAISS returns -1 for empty slots
            continue

        result = format_result(dist, idx, metadata)
        print(f"\n[{i+1}] {result['id']} ({result['type']})")
        print(f"    Similarity: {result['similarity']:.4f}")
        print(f"    Text: {result['text']}")


def main():
    # Load index
    index, metadata = load_index()

    # Test queries
    test_queries = [
        "What happens if the producer misses a milestone?",
        "How are strike prices adjusted for inflation?",
        "What are the termination rights for breach of contract?",
        "What is a qualifying change in law?",
        "What are the payment obligations?",
        "What happens if there's a force majeure event?",
        "What are the conditions precedent?",
        "How are carbon costs handled?",
        "What are the producer's reporting obligations?",
        "What is the Longstop Date?",
    ]

    print(f"\nRunning {len(test_queries)} test queries...\n")

    for query in test_queries:
        distances, indices = search(query, index, metadata, k=3)
        print_results(query, distances, indices, metadata)

    print(f"\n{'='*70}")
    print("SEARCH TEST COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
