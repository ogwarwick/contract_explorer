#!/usr/bin/env python3
"""
Analyse text_for_embedding capacity usage in LCHA structure.

Reports:
1. Current vs potential text_for_embedding lengths by type
2. Items exceeding Kanon 2 limit (48K chars)
3. Recommendations for each oversized item
4. Total token estimates for embedding cost

Usage:
    python analyse_embedding_capacity.py lcha_structure_v4.json

Output:
    - Console report
    - embedding_analysis.json (machine-readable results)
"""

import json
import sys
from collections import defaultdict
from datetime import datetime

# Kanon 2 limit: 16,384 tokens ≈ 48,000 chars (conservative at 3 chars/token)
KANON_CHAR_LIMIT = 48000
CHARS_PER_TOKEN = 3  # Conservative estimate


def analyse_structure(filepath: str) -> dict:
    """Analyse all items with text_for_embedding."""

    with open(filepath) as f:
        data = json.load(f)

    results = {
        'metadata': {
            'source_file': filepath,
            'analysis_date': datetime.now().isoformat(),
            'kanon_char_limit': KANON_CHAR_LIMIT
        },
        'by_type': defaultdict(lambda: {
            'count': 0,
            'current_total_chars': 0,
            'target_total_chars': 0,
            'items': []
        }),
        'exceeds_limit': [],
        'summary': {}
    }

    def analyse_item(obj, path=''):
        if not isinstance(obj, dict):
            return

        # Check if this is an embeddable item
        if 'text_for_embedding' in obj and 'raw_text' in obj:
            item_type = obj.get('type', 'unknown')
            item_id = obj.get('id', path)
            breadcrumb = obj.get('breadcrumb', '')
            title = obj.get('title', obj.get('term', ''))

            current_len = len(obj['text_for_embedding'])
            raw_len = len(obj['raw_text'])

            # For embeddings: we'll use raw_text only (no breadcrumb)
            target_len = raw_len

            # Count children
            child_count = (
                len(obj.get('sections', {})) +
                len(obj.get('subsections', {})) +
                len(obj.get('subclauses', {}))
            )

            item_data = {
                'id': item_id,
                'type': item_type,
                'title': title[:100],
                'current_len': current_len,
                'raw_len': raw_len,
                'target_len': target_len,
                'usage_pct': round(current_len / max(1, target_len) * 100, 1),
                'exceeds_limit': target_len > KANON_CHAR_LIMIT,
                'overflow': max(0, target_len - KANON_CHAR_LIMIT),
                'child_count': child_count,
                'has_children': child_count > 0
            }

            results['by_type'][item_type]['count'] += 1
            results['by_type'][item_type]['current_total_chars'] += current_len
            results['by_type'][item_type]['target_total_chars'] += target_len
            results['by_type'][item_type]['items'].append(item_data)

            if item_data['exceeds_limit']:
                results['exceeds_limit'].append(item_data)

        # Recurse into nested structures
        for key, value in obj.items():
            if isinstance(value, dict):
                analyse_item(value, f"{path}.{key}")

    analyse_item(data)

    # Calculate summary statistics
    total_items = sum(t['count'] for t in results['by_type'].values())
    total_current = sum(t['current_total_chars'] for t in results['by_type'].values())
    total_target = sum(t['target_total_chars'] for t in results['by_type'].values())

    results['summary'] = {
        'total_items': total_items,
        'total_current_chars': total_current,
        'total_target_chars': total_target,
        'total_current_tokens': total_current // CHARS_PER_TOKEN,
        'total_target_tokens': total_target // CHARS_PER_TOKEN,
        'exceeds_limit_count': len(results['exceeds_limit']),
        'capacity_usage_pct': round(total_current / max(1, total_target) * 100, 1)
    }

    return results


def print_report(results: dict):
    """Print human-readable analysis report."""

    print("=" * 70)
    print("LCHA text_for_embedding CAPACITY ANALYSIS")
    print("=" * 70)
    print(f"Source: {results['metadata']['source_file']}")
    print(f"Analysis date: {results['metadata']['analysis_date']}")
    print(f"Kanon 2 char limit: {results['metadata']['kanon_char_limit']:,}")
    print()

    # Summary by type
    print("CAPACITY USAGE BY TYPE (raw_text only)")
    print("-" * 70)
    print(f"{'Type':<12} {'Count':<8} {'Curr Avg':<12} {'Target':<12} {'Usage':<8} {'Exceeds'}")
    print("-" * 70)

    for item_type in ['definition', 'condition', 'section', 'subsection', 'subclause']:
        type_data = results['by_type'].get(item_type)
        if not type_data or type_data['count'] == 0:
            continue

        count = type_data['count']
        avg_current = type_data['current_total_chars'] // count
        avg_target = type_data['target_total_chars'] // count
        usage = round(type_data['current_total_chars'] / max(1, type_data['target_total_chars']) * 100, 1)
        exceeds = sum(1 for i in type_data['items'] if i['exceeds_limit'])

        status = "!" if usage < 50 else "OK" if usage > 90 else "~"
        print(f"{item_type:<12} {count:<8} {avg_current:>6,} ch   {avg_target:>6,} ch   {usage:>5}% {status:3}  {exceeds}")

    print("-" * 70)
    s = results['summary']
    print(f"{'TOTAL':<12} {s['total_items']:<8} {s['total_current_chars']:>6,} ch   {s['total_target_chars']:>6,} ch   {s['capacity_usage_pct']:>5}%    {s['exceeds_limit_count']}")
    print()

    # Token estimates
    print("TOKEN ESTIMATES (for Kanon 2 API cost)")
    print("-" * 70)
    print(f"  Current:   ~{s['total_current_tokens']:,} tokens")
    print(f"  Target:    ~{s['total_target_tokens']:,} tokens")
    if s['total_current_tokens'] > 0:
        increase_pct = round((s['total_target_tokens']/s['total_current_tokens']-1)*100)
        print(f"  Increase:  ~{s['total_target_tokens'] - s['total_current_tokens']:,} tokens (+{increase_pct}%)")
    print()

    # Items exceeding limit
    print("=" * 70)
    print(f"ITEMS EXCEEDING LIMIT ({KANON_CHAR_LIMIT:,} chars)")
    print("=" * 70)

    if not results['exceeds_limit']:
        print("  OK None! All items fit within the Kanon 2 limit.")
    else:
        print()
        for item in sorted(results['exceeds_limit'], key=lambda x: -x['target_len']):
            print(f"  {item['id']}")
            print(f"     Title: {item['title']}")
            print(f"     Type: {item['type']}")
            print(f"     Size: {item['target_len']:,} chars ({item['overflow']:,} over limit)")
            print(f"     Children: {item['child_count']}")
            print()

            # Recommendation
            if item['has_children']:
                print(f"     RECOMMENDATION: Structured Summary")
                print(f"        - Use intro + section table of contents + key terms")
                print(f"        - Limit parent embedding to ~4,000 chars")
                print(f"        - {item['child_count']} child sections carry detailed content")
            else:
                print(f"     RECOMMENDATION: Overlapping Chunks")
                chunks_needed = (item['potential_len'] // (KANON_CHAR_LIMIT - 5000)) + 1
                print(f"        - Split into {chunks_needed} chunks with 5,000 char overlap")
                print(f"        - Each chunk independently searchable")
            print()

    print("=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print()
    if s['capacity_usage_pct'] < 50:
        print(f"  WARNING Current capacity usage is LOW ({s['capacity_usage_pct']:.0f}%)")
        print("  WARNING Semantic search quality will be POOR")
        print()
        print("  Run: python fix_text_for_embedding.py <input> <output>")
        print("  This will populate text_for_embedding with full content.")
    else:
        print(f"  OK Capacity usage is good ({s['capacity_usage_pct']:.0f}%)")
        print("  Ready for embedding pipeline.")


def save_results(results: dict, filepath: str):
    """Save machine-readable results."""
    # Convert defaultdict to regular dict for JSON serialization
    output = {
        'metadata': results['metadata'],
        'summary': results['summary'],
        'exceeds_limit': results['exceeds_limit'],
        'by_type': {k: {
            'count': v['count'],
            'current_total_chars': v['current_total_chars'],
            'target_total_chars': v['target_total_chars'],
            'avg_current': v['current_total_chars'] // max(1, v['count']),
            'avg_target': v['target_total_chars'] // max(1, v['count']),
        } for k, v in results['by_type'].items()}
    }

    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {filepath}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python analyse_embedding_capacity.py <json_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    results = analyse_structure(input_file)
    print_report(results)

    # Save machine-readable results
    output_file = input_file.replace('.json', '_embedding_analysis.json')
    save_results(results, output_file)
