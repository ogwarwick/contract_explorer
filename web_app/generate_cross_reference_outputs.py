#!/usr/bin/env python3
"""Generate normalized cross-reference JSON files for contract documents."""

import argparse
from typing import List, Optional

import psycopg
from psycopg.rows import dict_row

from contract_navigator_service import (
    find_matching_enricher_file,
    get_contract_hierarchy,
    write_enricher_cross_reference_output,
)


def document_keys(requested_key: Optional[int]) -> List[int]:
    if requested_key is not None:
        return [requested_key]

    with psycopg.connect("dbname=lcha") as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT document_key FROM document ORDER BY document_key")
            return [row["document_key"] for row in cur.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doc-key", type=int, help="Generate one document only")
    args = parser.parse_args()

    for doc_key in document_keys(args.doc_key):
        hierarchy = get_contract_hierarchy(doc_key)
        enricher_file = find_matching_enricher_file(hierarchy.get("document_id", ""))
        if not enricher_file or not enricher_file.exists():
            print(f"{doc_key}: no matching enricher file")
            continue

        output_path = write_enricher_cross_reference_output(
            doc_key,
            hierarchy,
            enricher_file,
        )
        print(f"{doc_key}: {output_path}")


if __name__ == "__main__":
    main()
