#!/usr/bin/env python3
"""
Detailed LCHA Semantic Search - Shows full results with context and breadcrumbs.

Usage:
    python detailed_search.py
"""

import json
import numpy as np
import faiss
from isaacus import Isaacus
from config import Config

# Validate configuration
Config.validate()

# ============== INITIALIZE ISAACUS CLIENT ==============
client = Isaacus(api_key=Config.ISAACUS_API_KEY)

# ============== LOAD DATA ==============
print("Loading data...")
index = faiss.read_index(f"{Config.SEARCH_DIR}/lcha.faiss")
with open(f"{Config.SEARCH_DIR}/lcha_metadata.json") as f:
    metadata = json.load(f)
with open(Config.DATA_FILE) as f:
    structure = json.load(f)
print(f"Loaded: {index.ntotal} vectors, {len(metadata)} metadata entries\n")


# ============== HELPER FUNCTIONS ==============

def embed_query(text: str) -> np.ndarray:
    """Embed a query using Kanon 2 with retrieval/query task."""
    response = client.embeddings.create(
        model=Config.ISAACUS_MODEL_ID,
        texts=text,
        task="retrieval/query",
    )
    return np.array([response.embeddings[0].embedding], dtype='float32')


def find_item_in_structure(obj, target_id):
    """Recursively find an item by ID in the structure."""
    if isinstance(obj, dict):
        if obj.get('id') == target_id:
            return obj
        for v in obj.values():
            result = find_item_in_structure(v, target_id)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = find_item_in_structure(item, target_id)
            if result:
                return result
    return None


def get_item_details(item_id):
    """Get full item details including breadcrumb and raw text."""
    item = find_item_in_structure(structure, item_id)
    if item:
        return {
            'breadcrumb': item.get('breadcrumb', item_id),
            'title': item.get('title', item.get('term', '')),
            'raw_text': item.get('raw_text', ''),
        }
    return {
        'breadcrumb': item_id,
        'title': '',
        'raw_text': '',
    }


def get_quality_indicator(similarity):
    """Return emoji indicator based on similarity score."""
    if similarity >= 0.70:
        return ""
    elif similarity >= 0.60:
        return ""
    elif similarity >= 0.50:
        return ""
    else:
        return ""


def format_text(text, max_length=400):
    """Truncate text for display while preserving readability."""
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


# ============== SEARCH FUNCTION ==============

def search(query, k=5):
    """Search the index and return top k results with details."""
    # Embed and normalize query
    q_vec = embed_query(query)
    faiss.normalize_L2(q_vec)

    # Search
    distances, indices = index.search(q_vec, k)

    # Build results with full details
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        if idx >= len(metadata):
            continue

        meta_item = metadata[idx]
        item_id = meta_item['id']
        details = get_item_details(item_id)

        results.append({
            'id': item_id,
            'type': meta_item['type'],
            'similarity': float(dist),
            'breadcrumb': details['breadcrumb'],
            'title': details['title'],
            'text': details['raw_text'] or meta_item['text'],
        })

    return results


def print_result(result, rank):
    """Print a single search result with full details."""
    quality = get_quality_indicator(result['similarity'])

    print(f"RESULT #{rank} {quality}")
    print(f"─"*80)
    print(f"ID:          {result['id']}")
    print(f"Type:        {result['type']}")
    print(f"Similarity:  {result['similarity']:.4f}")
    print(f"Location:    {result['breadcrumb']}")

    if result['title']:
        print(f"Title:       {result['title']}")

    display_text = format_text(result['text'])
    print(f"\nTEXT:")
    print(f"{display_text}")
    print()


def print_query_header(query):
    """Print formatted query header."""
    print(f"\n{'='*80}")
    print(f"QUERY: {query}")
    print(f"{'='*80}\n")


# ============== TEST QUERIES ==============

TEST_QUERIES = [
    ("What happens if the producer misses a milestone?", 3),
    ("How are strike prices adjusted for inflation?", 3),
    ("What is a qualifying change in law?", 2),
    ("What is the Longstop Date?", 2),
    ("What are the termination rights for breach?", 3),
    ("What are the payment obligations?", 3),
    ("What happens if there's a force majeure event?", 2),
    ("What are the conditions precedent?", 2),
    ("How are carbon costs handled?", 2),
    ("What are the producer's reporting obligations?", 2),
]


# ============== MAIN EXECUTION ==============

def main():
    """Run detailed search analysis on test queries."""
    for query, k in TEST_QUERIES:
        print_query_header(query)

        results = search(query, k)

        if not results:
            print("No results found.\n")
            continue

        for i, result in enumerate(results, 1):
            print_result(result, i)

        # Summary statistics
        top_sim = results[0]['similarity']
        bottom_sim = results[-1]['similarity']

        if top_sim >= 0.70:
            quality = "EXCELLENT"
        elif top_sim >= 0.60:
            quality = "GOOD"
        elif top_sim >= 0.50:
            quality = "MODERATE"
        else:
            quality = "WEAK"

        print(f"Summary: Top similarity {top_sim:.4f}, Quality: {quality}")
        print()


if __name__ == "__main__":
    main()
