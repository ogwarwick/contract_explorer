#!/usr/bin/env python3
"""
Phase 2: Embedding Space Diagnostics

Analyzes the structure of the 1,792-dimensional embedding space:
- Basic statistics per item type
- Similarity matrix between types
- Baseline similarity distribution (random pairs)
- Centroid drift analysis by Part and type

Outputs:
- outputs/embedding_diagnostics_summary.json
- outputs/type_similarity_matrix.png
- outputs/baseline_similarity_distribution.png
- outputs/centroid_drift_heatmap.png
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import seaborn as sns
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from analysis.analysis_utils import (
    load_embeddings, load_metadata, load_structure,
    normalize_embeddings, cosine_similarity, compute_pairwise_similarities,
    get_centroid, compute_mean_distance_to_centroid,
    get_part_from_id, get_part_number, group_by_type, group_by_part,
    print_section_header, OUTPUT_DIR
)

# Plotting settings
sns.set_style('whitegrid')
plt.rcParams['figure.dpi'] = 150
plt.rcParams['savefig.dpi'] = 150
plt.rcParams['font.size'] = 10


def compute_type_statistics(embeddings: np.ndarray,
                            metadata: List[Dict]) -> Dict[str, Dict]:
    """Compute statistics for each item type."""
    print("\n1. Computing Type Statistics...")

    type_groups = group_by_type(embeddings, metadata)
    type_stats = {}

    for item_type, type_embeddings in type_groups.items():
        # Normalize for cosine similarity
        norm_embeddings = normalize_embeddings(type_embeddings)

        # Mean pairwise cosine similarity within type
        n = len(norm_embeddings)
        if n < 2:
            within_sim = 0.0
        else:
            # Sample pairs for speed
            n_samples = min(5000, n * (n - 1) // 2)
            indices_i = np.random.choice(n, n_samples, replace=True)
            indices_j = np.random.choice(n, n_samples, replace=True)
            # Ensure different items
            mask = indices_i != indices_j
            indices_i = indices_i[mask]
            indices_j = indices_j[mask]

            if len(indices_i) > 0:
                similarities = np.array([
                    cosine_similarity(norm_embeddings[i], norm_embeddings[j])
                    for i, j in zip(indices_i, indices_j)
                ])
                within_sim = float(np.mean(similarities))
            else:
                within_sim = 0.0

        # Centroid and drift
        centroid = get_centroid(norm_embeddings)
        drift = compute_mean_distance_to_centroid(norm_embeddings, centroid)

        type_stats[item_type] = {
            'count': n,
            'within_type_similarity': within_sim,
            'centroid_drift': drift,
            'centroid': centroid.tolist()[:10]  # First 10 dims for reference
        }
        print(f"   {item_type}: n={n}, within_sim={within_sim:.4f}, drift={drift:.4f}")

    return type_stats


def compute_similarity_matrix(embeddings: np.ndarray,
                              metadata: List[Dict],
                              type_stats: Dict) -> np.ndarray:
    """Compute cross-type similarity matrix."""
    print("\n2. Computing Cross-Type Similarity Matrix...")

    type_groups = group_by_type(embeddings, metadata)
    types = sorted(type_groups.keys())

    matrix = np.zeros((len(types), len(types)))

    for i, type1 in enumerate(types):
        for j, type2 in enumerate(types):
            if i == j:
                matrix[i, j] = type_stats[type1]['within_type_similarity']
            else:
                # Compute mean similarity between types
                emb1 = normalize_embeddings(type_groups[type1])
                emb2 = normalize_embeddings(type_groups[type2])

                # Sample pairs
                n1, n2 = len(emb1), len(emb2)
                n_samples = min(1000, n1 * n2)

                idx1 = np.random.choice(n1, n_samples, replace=True)
                idx2 = np.random.choice(n2, n_samples, replace=True)

                similarities = np.array([
                    cosine_similarity(emb1[i], emb2[j])
                    for i, j in zip(idx1, idx2)
                ])
                matrix[i, j] = float(np.mean(similarities))

    # Print matrix
    print("\n   Similarity Matrix (rows/cols = types):")
    print("   " + " ".join(f"{t[:10]:>10}" for t in types))
    for i, t1 in enumerate(types):
        print(f"   {t1[:10]:>10}", end="")
        for j in range(len(types)):
            print(f" {matrix[i, j]:>9.4f}", end="")
        print()

    return matrix, types


def compute_baseline_distribution(embeddings: np.ndarray) -> Tuple[np.ndarray, float, float]:
    """Compute baseline similarity distribution from random pairs."""
    print("\n3. Computing Baseline Similarity Distribution...")

    similarities = compute_pairwise_similarities(embeddings, n_samples=10000)

    mean_sim = float(np.mean(similarities))
    std_sim = float(np.std(similarities))

    print(f"   Mean: {mean_sim:.4f}")
    print(f"   Std:  {std_sim:.4f}")
    print(f"   Min:  {float(np.min(similarities)):.4f}")
    print(f"   Max:  {float(np.max(similarities)):.4f}")

    return similarities, mean_sim, std_sim


def compute_centroid_drift(embeddings: np.ndarray,
                           metadata: List[Dict]) -> Dict[str, Dict[str, float]]:
    """Compute centroid drift by Part and type."""
    print("\n4. Computing Centroid Drift Analysis...")

    drift_data = defaultdict(lambda: defaultdict(list))

    for emb, meta in zip(embeddings, metadata):
        part = get_part_from_id(meta['id'])
        item_type = meta['type']
        drift_data[part][item_type].append(emb)

    # Compute drift for each Part x Type combination
    drift_matrix = {}
    for part, types_dict in drift_data.items():
        drift_matrix[part] = {}
        for item_type, type_embeddings in types_dict.items():
            if len(type_embeddings) > 1:
                norm_emb = normalize_embeddings(np.array(type_embeddings))
                centroid = get_centroid(norm_emb)
                drift = compute_mean_distance_to_centroid(norm_emb, centroid)
            else:
                drift = 0.0
            drift_matrix[part][item_type] = drift

    return drift_matrix


def plot_similarity_matrix(matrix: np.ndarray, types: List[str]):
    """Plot the type similarity matrix as a heatmap."""
    fig, ax = plt.subplots(figsize=(8, 7))

    # Create labels
    type_labels = [t.replace('_', ' ').title() for t in types]

    sns.heatmap(matrix, annot=True, fmt='.3f', cmap='RdYlBu_r',
                xticklabels=type_labels, yticklabels=type_labels,
                vmin=-0.2, vmax=0.8, cbar_kws={'label': 'Cosine Similarity'},
                ax=ax)

    plt.title('Item Type Similarity Matrix\n(Cosine Similarity Between Embeddings)')
    plt.tight_layout()

    output_path = OUTPUT_DIR / 'type_similarity_matrix.png'
    plt.savefig(output_path, bbox_inches='tight')
    print(f"\n   Saved: {output_path}")
    plt.close()


def plot_baseline_distribution(similarities: np.ndarray, mean: float, std: float):
    """Plot the baseline similarity distribution."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    # Histogram
    ax1.hist(similarities, bins=50, alpha=0.7, color='steelblue', edgecolor='black')
    ax1.axvline(mean, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean:.3f}')
    ax1.axvline(mean + std, color='orange', linestyle='--', linewidth=1, label=f'+1 SD: {mean+std:.3f}')
    ax1.axvline(mean - std, color='orange', linestyle='--', linewidth=1, label=f'-1 SD: {mean-std:.3f}')
    ax1.set_xlabel('Cosine Similarity')
    ax1.set_ylabel('Frequency')
    ax1.set_title('Baseline Similarity Distribution\n(10,000 Random Item Pairs)')
    ax1.legend()

    # Box plot
    ax2.boxplot(similarities, vert=True)
    ax2.set_ylabel('Cosine Similarity')
    ax2.set_title('Baseline Similarity Box Plot')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()

    output_path = OUTPUT_DIR / 'baseline_similarity_distribution.png'
    plt.savefig(output_path, bbox_inches='tight')
    print(f"   Saved: {output_path}")
    plt.close()


def plot_centroid_drift(drift_matrix: Dict[str, Dict[str, float]]):
    """Plot centroid drift as a heatmap."""
    # Get all unique parts and types
    parts = sorted([p for p in drift_matrix.keys() if p.startswith('part')],
                   key=lambda x: get_part_number(x))
    types = ['definition', 'condition', 'section', 'subsection', 'subclause']

    # Build matrix
    data = []
    for part in parts[:10]:  # Top 10 parts by number
        row = []
        for t in types:
            row.append(drift_matrix.get(part, {}).get(t, 0.0))
        data.append(row)

    part_labels = [f"Part {get_part_number(p)}" for p in parts[:10]]
    type_labels = [t.replace('_', ' ').title() for t in types]

    data = np.array(data)

    fig, ax = plt.subplots(figsize=(10, 6))

    sns.heatmap(data, annot=True, fmt='.3f', cmap='YlOrRd',
                xticklabels=type_labels, yticklabels=part_labels,
                vmin=0, vmax=0.5, cbar_kws={'label': 'Centroid Drift (1 - Similarity)'},
                ax=ax)

    plt.title('Centroid Drift by Part and Item Type\n(Lower = Tighter Clustering)')
    plt.tight_layout()

    output_path = OUTPUT_DIR / 'centroid_drift_heatmap.png'
    plt.savefig(output_path, bbox_inches='tight')
    print(f"   Saved: {output_path}")
    plt.close()


def main():
    """Main execution function."""
    print_section_header("LCHA Embedding Space Diagnostics")

    # Load data
    embeddings = load_embeddings()
    metadata = load_metadata()

    # 1. Type statistics
    type_stats = compute_type_statistics(embeddings, metadata)

    # 2. Similarity matrix
    similarity_matrix, types = compute_similarity_matrix(embeddings, metadata, type_stats)
    plot_similarity_matrix(similarity_matrix, types)

    # 3. Baseline distribution
    baseline_sims, baseline_mean, baseline_std = compute_baseline_distribution(embeddings)
    plot_baseline_distribution(baseline_sims, baseline_mean, baseline_std)

    # 4. Centroid drift
    drift_matrix = compute_centroid_drift(embeddings, metadata)
    plot_centroid_drift(drift_matrix)

    # Save summary
    summary = {
        'type_statistics': type_stats,
        'baseline_similarity': {
            'mean': baseline_mean,
            'std': baseline_std,
            'min': float(np.min(baseline_sims)),
            'max': float(np.max(baseline_sims))
        },
        'similarity_matrix': {
            'types': types,
            'matrix': similarity_matrix.tolist()
        },
        'centroid_drift': {
            part: {t: float(v) for t, v in drift_dict.items()}
            for part, drift_dict in drift_matrix.items()
        }
    }

    output_path = OUTPUT_DIR / 'embedding_diagnostics_summary.json'
    with open(output_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"\n   Saved: {output_path}")

    # Print key findings
    print("\n" + "=" * 60)
    print("  KEY FINDINGS")
    print("=" * 60)
    print(f"\n1. Baseline Similarity: {baseline_mean:.4f} ± {baseline_std:.4f}")
    print(f"   This is the null baseline - results above {baseline_mean + baseline_std:.4f}")
    print(f"   are statistically meaningful.")

    print("\n2. Type Clustering:")
    for t, stats in sorted(type_stats.items(), key=lambda x: x[1]['within_type_similarity'], reverse=True):
        print(f"   {t[:15]:>15}: within_sim={stats['within_type_similarity']:.4f}, drift={stats['centroid_drift']:.4f}")

    print("\n3. Cross-Type Similarities:")
    print("   Similarity > baseline indicates the model distinguishes types.")

    print("\n" + "=" * 60)
    print("  Phase 2 Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
