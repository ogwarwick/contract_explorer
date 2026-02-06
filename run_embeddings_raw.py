#!/usr/bin/env python3
"""
Generate embeddings using the Isaacus Kanon 2 API via official SDK.

UPDATES:
- Using official isaacus SDK
- Corrected task parameter: "retrieval/document"
- Runtime patching for part3.c3
"""

import json
import time
import sys
import numpy as np
import os
from isaacus import Isaacus
from config import Config

# Validate configuration
Config.validate()

# --- CONFIGURATION ---
BATCH_SIZE = 10
OUTPUT_DIR = "data/vectors"

# --- THE RUNTIME PATCH (For Condition 3) ---
CONDITION_3_SUMMARY = """
3. CONDITIONS PRECEDENT
This condition covers the requirements that must be fulfilled before the LCHA becomes fully effective.

Sections covered:
- 3.1-3.4: Agreement Date Provisions and Initial Conditions Precedent
- 3.5-3.15: Operational Conditions Precedent
- 3.16-3.28: Fulfilment procedures and notifications
- 3.29-3.45: Waiver of Conditions Precedent
- 3.46-3.60: Subsidy Control requirements
- 3.61-3.81: Additional operational requirements

Key terms: Initial Conditions Precedent, Operational Conditions Precedent, Longstop Date, Milestone Requirement, Subsidy Control Declaration, Directors' Certificate, Start Date.
"""

# Create Isaacus client
client = Isaacus(api_key=Config.ISAACUS_API_KEY)


def call_kanon_api(texts):
    """
    Sends text batch to Isaacus API and returns vectors.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.embeddings.create(
                model=Config.ISAACUS_MODEL_ID,
                texts=texts,
                task="retrieval/document",
            )

            # Extract embeddings from response
            vectors = [item.embedding for item in response.embeddings]
            return np.array(vectors, dtype='float32')

        except Exception as e:
            print(f"\n Error: {e}")
            if attempt == max_retries - 1:
                return None
            time.sleep(2)

    return None


def extract_embeddable_items(data):
    items = []

    def traverse(obj):
        if isinstance(obj, dict):
            if 'raw_text' in obj and 'id' in obj:
                text_to_embed = obj['raw_text']
                node_id = obj['id']

                # --- RUNTIME PATCH ---
                if node_id == "part3.c3" or node_id == "part3.c3.condition_3":
                    print(f" PATCHING: Replacing content for {node_id}")
                    text_to_embed = CONDITION_3_SUMMARY

                if text_to_embed and len(text_to_embed.strip()) > 0:
                    items.append({
                        'id': node_id,
                        'text': text_to_embed,
                        'type': obj.get('type', 'unknown')
                    })

            for key, val in obj.items():
                traverse(val)
        elif isinstance(obj, list):
            for item in obj:
                traverse(item)

    traverse(data)
    return items


def main(input_file):
    print(f"Loading {input_file}...")
    with open(input_file) as f:
        data = json.load(f)

    items = extract_embeddable_items(data)
    total = len(items)
    print(f"Prepared {total} items. Model: {Config.ISAACUS_MODEL_ID}")

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    all_vectors = []
    metadata_map = []

    print(f"Starting batch processing (Batch size: {BATCH_SIZE})...")
    start_time = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch = items[i:i+BATCH_SIZE]
        batch_texts = [item['text'] for item in batch]

        print(f"  Batch {i//BATCH_SIZE + 1}/{(total//BATCH_SIZE)+1} ({len(batch)} items)...", end="\r")

        vectors = call_kanon_api(batch_texts)

        if vectors is not None:
            all_vectors.append(vectors)
            metadata_map.extend(batch)
        else:
            print(f"\n CRITICAL FAILURE at batch {i}. Stopping.")
            break

        time.sleep(0.1)

    if all_vectors:
        final_array = np.vstack(all_vectors)
        elapsed = time.time() - start_time
        print(f"\n\n DONE! Processed {len(final_array)} vectors in {elapsed:.1f}s.")

        vec_path = f"{OUTPUT_DIR}/lcha_vectors.npy"
        np.save(vec_path, final_array)

        meta_path = f"{OUTPUT_DIR}/lcha_metadata.json"
        with open(meta_path, 'w') as f:
            json.dump(metadata_map, f, indent=2)
        print(f"Files saved to {OUTPUT_DIR}")

        # Verify output shape
        print(f"Output shape: {final_array.shape} (expected: (4070, 1792))")
    else:
        print("\nNo vectors generated.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_embeddings_raw.py <input.json>")
        sys.exit(1)
    main(sys.argv[1])
