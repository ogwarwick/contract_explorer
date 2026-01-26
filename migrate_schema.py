#!/usr/bin/env python3
"""
migrate_schema.py

Migrate individual part JSON files to canonical schema v2.1

Instead of trying to migrate the incomplete lcha_structure.json,
this script loads from the individual part JSON files (part1_structure.json, etc.)
and creates a properly merged canonical schema.

Usage:
    python3 migrate_schema.py

Output:
    - lcha_structure.json (canonical v2.1 format)
    - Validation summary
"""

import json
import re
import os
from datetime import datetime

# Import utility functions
from lcha_utils import (
    clean_text_for_embedding,
    extract_references,
    normalize_text_whitespace,
    slugify,
    slugify_term,
    validate_node,
    validate_structure
)


# =============================================================================
# PART LOADING
# =============================================================================

def load_part_file(part_num: int) -> dict:
    """Load a part's JSON file (e.g., part1_structure.json)"""
    filename = f"part{part_num}_structure.json"

    if not os.path.exists(filename):
        return None

    with open(filename, 'r') as f:
        data = json.load(f)

    return data


def extract_part_from_file(part_num: int, part_data: dict) -> dict:
    """
    Extract the part object from a part file.

    Different part files have different structures:
    - Part 1: {"parts": {"1": {...}}}
    - Part 5: {"part": {...}}
    - Others: various formats
    """
    # Try different paths
    if "parts" in part_data:
        if isinstance(part_data["parts"], dict):
            if str(part_num) in part_data["parts"]:
                return part_data["parts"][str(part_num)]
        elif isinstance(part_data["parts"], list) and len(part_data["parts"]) > 0:
            return part_data["parts"][0]

    if "part" in part_data:
        return part_data["part"]

    # If data itself is the part (has 'title', 'number', etc.)
    if "title" in part_data or "part_number" in part_data:
        return part_data

    return None


def migrate_part_from_file(part_num: int) -> dict:
    """
    Load and migrate a part from its individual JSON file.
    """
    part_file_data = load_part_file(part_num)
    if not part_file_data:
        return None

    part_obj = extract_part_from_file(part_num, part_file_data)
    if not part_obj:
        return None

    part_id = f"part{part_num}"

    # Build canonical part structure
    migrated = {
        "id": part_id,
        "parent_id": None,
        "type": "part",
        "number": part_num,
        "title": part_obj.get("title", "UNKNOWN"),
        "text_for_embedding": f"Part {part_num}: {part_obj.get('title', '')}",
        "sections": {}
    }

    # Handle sections
    sections = part_obj.get("sections", {})

    # Part 5 might have conditions instead
    if not sections and "conditions" in part_obj:
        # Part 5 has conditions with numbered sections
        # The structure is different - we'll handle it specially
        conditions = part_obj.get("conditions", [])
        if isinstance(conditions, list):
            # Convert conditions to sections
            for cond in conditions:
                cond_num = cond.get("condition_number", "")
                if cond_num:
                    section_key = f"{part_num}.{cond_num}"
                    migrated["sections"][section_key] = {
                        "id": f"{part_id}.s{cond_num}",
                        "parent_id": part_id,
                        "type": "condition",
                        "section_number": section_key,
                        "title": cond.get("title", ""),
                        "text_for_embedding": f"Condition {cond_num}: {cond.get('title', '')}",
                        "references": [],
                        "raw_text": "",
                        "section_count": cond.get("section_count", 0)
                    }

    # Process dict-based sections
    if isinstance(sections, dict):
        for section_key, section_data in sections.items():
            migrated["sections"][section_key] = migrate_section(
                section_data, section_key, part_id
            )

    # Handle nodes (flat list from some parsers)
    if "nodes" in part_obj:
        nodes = part_obj["nodes"]
        # Add nodes to sections based on parent_id
        for node_id, node_data in nodes.items():
            parent_id = node_data.get("parent_id", "")
            if parent_id.startswith(part_id):
                # Find which section this belongs to
                for sect_key, sect_data in migrated["sections"].items():
                    if sect_data.get("id") == parent_id:
                        if "subsections" not in sect_data:
                            sect_data["subsections"] = {}
                        # Add as subsection
                        marker = node_id.replace(parent_id, "")
                        sect_data["subsections"][marker] = node_data

    return migrated


def migrate_section(section_data: dict, section_key: str, parent_id: str) -> dict:
    """Migrate a section to canonical schema"""
    section_id = section_data.get("id", f"{parent_id}.s{section_key.replace('.', '_')}")

    migrated = {
        "id": section_id,
        "parent_id": parent_id,
        "type": section_data.get("type", "section"),
        "section_number": section_key,
    }

    # Copy title if exists
    if "title" in section_data:
        migrated["title"] = section_data["title"]

    # Handle raw_text
    raw_text = section_data.get("raw_text", "")
    if not raw_text and "content" in section_data:
        if isinstance(section_data["content"], dict):
            raw_text = json.dumps(section_data["content"])
        else:
            raw_text = str(section_data["content"])
    if not raw_text and "parsed" in section_data:
        if isinstance(section_data["parsed"], dict):
            raw_text = json.dumps(section_data["parsed"])
        else:
            raw_text = str(section_data["parsed"])

    # Ensure text_for_embedding exists and is clean
    if "text_for_embedding" in section_data:
        migrated["text_for_embedding"] = section_data["text_for_embedding"]
    else:
        migrated["text_for_embedding"] = clean_text_for_embedding(raw_text)

    # Ensure references exists
    if "references" in section_data:
        migrated["references"] = section_data["references"]
    else:
        migrated["references"] = extract_references(raw_text)

    # Copy parsed content
    if "parsed" in section_data:
        migrated["parsed"] = section_data["parsed"]
    else:
        # Try to build parsed from other fields
        if "content" in section_data:
            migrated["parsed"] = section_data["content"]
        else:
            migrated["parsed"] = {}

    # Always include raw_text
    migrated["raw_text"] = raw_text

    # Handle definitions (Part 1 section 1.1)
    if "definitions" in section_data:
        migrated["definitions"] = {}
        for term, def_data in section_data["definitions"].items():
            migrated["definitions"][term] = migrate_definition(
                def_data, term, section_id
            )

    # Copy any other fields that might be present
    for key, value in section_data.items():
        if key not in migrated and key not in ["content", "subsections"]:
            migrated[key] = value

    # Handle subsections
    if "subsections" in section_data:
        migrated["subsections"] = section_data["subsections"]

    return migrated


def migrate_definition(def_data: dict, term: str, parent_id: str) -> dict:
    """Migrate a definition to canonical schema"""
    term_slug = slugify_term(term)
    def_id = def_data.get("id", f"{parent_id}.def.{term_slug}")

    raw_text = def_data.get("raw_text", "")

    migrated = {
        "id": def_id,
        "parent_id": parent_id,
        "type": "definition",
        "term": term,
        "raw_text": raw_text
    }

    # Handle classification (was called "type" in old schema)
    if "classification" in def_data:
        migrated["classification"] = def_data["classification"]
    elif "type" in def_data and def_data["type"] != "definition":
        migrated["classification"] = def_data["type"]
    else:
        migrated["classification"] = "simple"

    # Ensure text_for_embedding exists
    if "text_for_embedding" in def_data:
        migrated["text_for_embedding"] = def_data["text_for_embedding"]
    else:
        # Build from term and raw_text
        if '"means' in raw_text:
            embedding_text = raw_text.split('means', 1)[-1].strip()
            migrated["text_for_embedding"] = clean_text_for_embedding(f"{term} means {embedding_text}")
        elif 'has the meaning' in raw_text:
            migrated["text_for_embedding"] = clean_text_for_embedding(raw_text)
        else:
            migrated["text_for_embedding"] = clean_text_for_embedding(f"{term} {raw_text}")

    # Ensure references exists
    if "references" in def_data:
        migrated["references"] = def_data["references"]
    else:
        migrated["references"] = extract_references(raw_text)

    # Copy parsed
    if "parsed" in def_data:
        migrated["parsed"] = def_data["parsed"]
    else:
        migrated["parsed"] = {}

    return migrated


# =============================================================================
# MAIN MIGRATION FUNCTION
# =============================================================================

def migrate_all_parts(output_file: str, parts: list = None) -> dict:
    """
    Main migration function.

    Loads individual part JSON files and creates canonical v2.1 structure.
    """
    if parts is None:
        parts = [1, 2, 3, 4, 5]

    print("Migrating to schema v2.1 from individual part files...")
    print("=" * 60)

    # Create new structure
    migrated = {
        "metadata": {
            "document": "Low-Carbon Hydrogen Agreement Standard Terms and Conditions",
            "source_file": "low-carbon-hydrogen-agreement-standard-terms-and-conditions.pdf",
            "parse_date": datetime.now().isoformat(),
            "parser_version": "2.1.0",
            "schema_version": "2.1",
            "last_updated": datetime.now().isoformat()
        },
        "footnotes": [],
        "parts": {}
    }

    # Migrate each part
    for part_num in parts:
        print(f"Loading Part {part_num}...")

        part_data = migrate_part_from_file(part_num)
        if part_data:
            migrated["parts"][str(part_num)] = part_data
            sections = len(part_data.get("sections", {}))
            defs_count = sum(
                len(s.get("definitions", {}))
                for s in part_data.get("sections", {}).values()
            )
            print(f"  ✓ Part {part_num}: {part_data.get('title', 'UNKNOWN')[:40]}...")
            print(f"    Sections: {sections}")
            if defs_count > 0:
                print(f"    Definitions: {defs_count}")
        else:
            print(f"  ✗ Part {part_num}: File not found")

    # Write output
    print(f"\nWriting to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(migrated, f, indent=2)

    # Summary
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Total parts: {len(migrated['parts'])}")
    print(f"Output file: {output_file}")

    # Validate
    print("\n" + "=" * 60)
    print("VALIDATION")
    print("=" * 60)

    is_valid, errors = validate_structure(migrated)
    if is_valid:
        print("✓ Schema validation passed")
    else:
        print("✗ Schema validation failed:")
        for error in errors:
            print(f"  - {error}")

    print(f"\nMigration complete!")
    return migrated


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main execution"""
    OUTPUT_FILE = "lcha_structure.json"
    BACKUP_FILE = "lcha_structure_backup.json"

    # Check if we have part files
    part_files = [f"part{i}_structure.json" for i in range(1, 6)]
    existing_files = [f for f in part_files if os.path.exists(f)]

    if not existing_files:
        print("Error: No part structure files found!")
        print("Expected files: part1_structure.json, part2_structure.json, etc.")
        return 1

    print(f"Found part files: {', '.join(existing_files)}")

    # Create backup if output file exists
    if os.path.exists(OUTPUT_FILE):
        print(f"Creating backup: {BACKUP_FILE}")
        import shutil
        shutil.copy2(OUTPUT_FILE, BACKUP_FILE)

    # Run migration
    try:
        migrate_all_parts(OUTPUT_FILE)
        return 0

    except Exception as e:
        print(f"\nError during migration: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
