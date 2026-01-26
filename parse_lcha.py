#!/usr/bin/env python3
"""
parse_lcha.py

Unified LCHA Parser

Usage:
    python3 parse_lcha.py --discover 6      # Discover structure of Part 6
    python3 parse_lcha.py --part 6          # Parse Part 6
    python3 parse_lcha.py --all             # Parse all remaining parts
    python3 parse_lcha.py --validate        # Validate current structure
    python3 parse_lcha.py --stats           # Show statistics

This is the unified parser for all Parts. Uses lcha_utils.py for shared helpers
and produces canonical schema v2.1 output.
"""

import argparse
import json
import os
import re
from datetime import datetime
from typing import Optional, Dict, List

from lcha_utils import (
    clean_extracted_text,
    clean_text_for_embedding,
    extract_references,
    extract_part_text,
    extract_part_title,
    find_conditions_in_part,
    parse_nested_subsections,
    create_node,
    slugify,
    parse_formula,
    validate_structure
)

# =============================================================================
# CONFIGURATION
# =============================================================================

CACHE_FILE = "lcha_text_cache.json"
OUTPUT_FILE = "lcha_structure.json"


# =============================================================================
# DATA LOADING
# =============================================================================

def load_text() -> str:
    """Load cached text from PDF extraction"""
    if not os.path.exists(CACHE_FILE):
        raise FileNotFoundError(f"{CACHE_FILE} not found. Run PDF extraction first.")

    with open(CACHE_FILE, 'r') as f:
        data = json.load(f)

    return data['text']


def load_structure() -> dict:
    """Load existing structure or create new one"""
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r') as f:
            return json.load(f)

    return {
        "metadata": {
            "document": "Low-Carbon Hydrogen Agreement Standard Terms and Conditions",
            "parser_version": "2.1.0",
            "schema_version": "2.1"
        },
        "footnotes": [],
        "parts": {}
    }


def save_structure(data: dict):
    """Save structure to file"""
    data["metadata"]["parse_date"] = datetime.now().isoformat()
    data["metadata"]["last_updated"] = datetime.now().isoformat()

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Saved to {OUTPUT_FILE}")


# =============================================================================
# DISCOVERY MODE
# =============================================================================

def discover_part(part_num: int, all_text: str = None):
    """
    Discover structure of a Part without parsing.

    Analyzes the Part to identify conditions, sections, formulas, etc.
    """
    if all_text is None:
        all_text = clean_extracted_text(load_text())

    part_text = extract_part_text(all_text, part_num)

    if not part_text:
        print(f"Part {part_num} not found in document")
        return

    title = extract_part_title(part_text)

    print(f"\n{'=' * 60}")
    print(f"PART {part_num}: {title}")
    print(f"{'=' * 60}")
    print(f"Text length: {len(part_text):,} characters")

    # Find conditions
    conditions = find_conditions_in_part(part_text)
    print(f"\nConditions found: {len(conditions)}")
    for num, cond_title in conditions:
        print(f"  Condition {num}: {cond_title[:60]}...")

    # Find section numbers (X.Y pattern)
    sections = re.findall(r'(\d+\.\d+)\s+[A-Z]', part_text[:50000])
    unique_sections = sorted(set(sections), key=lambda x: (int(x.split('.')[0]), int(x.split('.')[1])))
    print(f"\nSections found (X.Y pattern): {len(unique_sections)}")
    if unique_sections:
        print(f"  Range: {unique_sections[0]} - {unique_sections[-1]}")
        print(f"  Sample: {', '.join(unique_sections[:10])}")

    # Check for formulas
    formula_count = part_text.lower().count('where:')
    print(f"\nFormulas (where: clauses): {formula_count}")

    # Check for sub-clauses (X.Y.Z pattern)
    subclauses = re.findall(r'(\d+\.\d+\.\d+)', part_text[:50000])
    unique_subclauses = sorted(set(subclauses))
    print(f"Sub-clauses (X.Y.X pattern): {len(unique_subclauses)}")
    if unique_subclauses:
        print(f"  Sample: {', '.join(unique_subclauses[:10])}")

    # Check for subsection patterns
    alpha_count = len(re.findall(r'(?<!\d)\([A-Z]\)', part_text))
    roman_count = len(re.findall(r'\([ivxlc]+\)', part_text, re.IGNORECASE))
    lower_count = len(re.findall(r'\([a-z]\)', part_text))

    print(f"\nSubsection markers:")
    print(f"  Alphabetic (A), (B): {alpha_count}")
    print(f"  Roman (i), (ii): {roman_count}")
    print(f"  Lowercase (a), (b): {lower_count}")

    # Check for definitions (for Part 1 or early parts)
    def_pattern = r'"([^"]+)"\s+means'
    definitions = re.findall(def_pattern, part_text[:20000])
    if definitions:
        print(f"\nPotential definitions found: {len(definitions)}")
        print(f"  Sample: {', '.join(definitions[:5])}")

    print()


# =============================================================================
# PARSING MODE
# =============================================================================

def parse_part(part_num: int, all_text: str = None) -> dict:
    """
    Parse a specific Part.

    This is a generic parser that handles most Part structures.
    For Parts with unusual structures, specialized handlers may be needed.
    """
    if all_text is None:
        all_text = clean_extracted_text(load_text())

    part_text = extract_part_text(all_text, part_num)

    if not part_text:
        raise ValueError(f"Part {part_num} not found in document")

    title = extract_part_title(part_text)
    part_id = f"part{part_num}"

    print(f"\nParsing Part {part_num}: {title}")
    print(f"Text length: {len(part_text):,} characters")

    # Build part structure
    part_data = {
        "id": part_id,
        "parent_id": None,
        "type": "part",
        "number": part_num,
        "title": title,
        "text_for_embedding": f"Part {part_num}: {title}",
        "sections": {}
    }

    # Check for conditions (multiple conditions per part)
    conditions = find_conditions_in_part(part_text)

    if conditions:
        # Part has multiple conditions - parse each
        print(f"Found {len(conditions)} conditions")

        for cond_num, cond_title in conditions:
            print(f"  Condition {cond_num}: {cond_title[:50]}...")

            cond_id = f"{part_id}.c{cond_num}"
            cond_sections = parse_condition_sections(
                part_text, cond_num, cond_id
            )

            # Create condition as a section
            section_key = f"{part_num}.{cond_num}"
            part_data["sections"][section_key] = {
                "id": cond_id,
                "parent_id": part_id,
                "type": "condition",
                "section_number": section_key,
                "title": cond_title,
                "text_for_embedding": f"Condition {cond_num}: {cond_title}",
                "references": [],
                "raw_text": f"Condition {cond_num}: {cond_title}",
                "section_count": len(cond_sections),
                "subsections": cond_sections
            }
    else:
        # Part has direct sections (X.Y pattern)
        sections = parse_sections(part_text, part_id)
        part_data["sections"] = sections
        print(f"Parsed {len(sections)} sections")

    return part_data


def parse_condition_sections(part_text: str, cond_num: int, parent_id: str) -> dict:
    """Parse sections within a condition"""
    # Find sections numbered as X.Y where X is the condition number
    pattern = rf'{cond_num}\.(\d+)\s+'
    matches = list(re.finditer(pattern, part_text))

    sections = {}

    for i, match in enumerate(matches):
        section_subnum = match.group(1)
        section_num = f"{cond_num}.{section_subnum}"
        section_id = f"{parent_id}.s{cond_num}_{section_subnum}"

        # Extract section content
        start = match.start()
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(part_text)

        content = part_text[start:end].strip()

        # Remove the section number from content
        content = re.sub(rf'^{cond_num}\.\d+\s+', '', content)

        # Check for subsections
        has_subsections = bool(re.search(r'(?<!\d)\([A-Z]\)', content))

        sections[section_num] = {
            "id": section_id,
            "parent_id": parent_id,
            "type": "section",
            "section_number": section_num,
            "text_for_embedding": clean_text_for_embedding(content),
            "references": extract_references(content),
            "raw_text": content[:500] + "..." if len(content) > 500 else content
        }

        if has_subsections:
            subsection_nodes = parse_nested_subsections(content, section_id)
            sections[section_num]["subsections"] = subsection_nodes

    return sections


def parse_sections(part_text: str, part_id: str) -> dict:
    """Parse sections in X.Y format"""
    # Match section numbers like "1.1", "5.2", etc.
    pattern = r'(\d+\.\d+)\s+'
    matches = list(re.finditer(pattern, part_text))

    sections = {}

    for i, match in enumerate(matches):
        section_num = match.group(1)
        section_id = f"{part_id}.s{section_num.replace('.', '_')}"

        # Extract section content
        start = match.start()
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(part_text)

        content = part_text[start:end].strip()

        # Remove the section number from content
        content = re.sub(rf'^{section_num}\s+', '', content)

        # Check for subsections
        has_subsections = bool(re.search(r'(?<!\d)\([A-Z]\)', content))
        has_formula = bool(re.search(r'\bwhere\s*:', content, re.IGNORECASE))

        section_type = "section"
        if has_formula:
            section_type = "formula"
        elif has_subsections:
            section_type = "nested"

        sections[section_num] = {
            "id": section_id,
            "parent_id": part_id,
            "type": section_type,
            "section_number": section_num,
            "text_for_embedding": clean_text_for_embedding(content),
            "references": extract_references(content),
            "raw_text": content[:500] + "..." if len(content) > 500 else content
        }

        if has_subsections:
            subsection_nodes = parse_nested_subsections(content, section_id)
            # Merge subsection nodes into the section
            for sub_id, sub_node in subsection_nodes.items():
                if "subsections" not in sections[section_num]:
                    sections[section_num]["subsections"] = {}
                marker = sub_id.replace(section_id, "")
                sections[section_num]["subsections"][marker] = sub_node

    return sections


# =============================================================================
# COMMANDS
# =============================================================================

def cmd_discover(args):
    """Discover structure of a part"""
    all_text = clean_extracted_text(load_text())
    discover_part(args.discover, all_text=all_text)


def cmd_parse(args):
    """Parse a specific part"""
    structure = load_structure()
    part_num = args.part

    # Check if already parsed
    if str(part_num) in structure.get("parts", {}):
        response = input(f"Part {part_num} already exists. Overwrite? (y/n): ").strip().lower()
        if response != 'y':
            print("Aborted")
            return

    # Parse the part
    all_text = clean_extracted_text(load_text())
    part_data = parse_part(part_num, all_text=all_text)

    # Add to structure
    if "parts" not in structure:
        structure["parts"] = {}

    structure["parts"][str(part_num)] = part_data
    save_structure(structure)

    print(f"\nPart {part_num} added to {OUTPUT_FILE}")


def cmd_parse_all(args):
    """Parse all remaining parts"""
    structure = load_structure()
    all_text = clean_extracted_text(load_text())

    # Find which parts exist in the document
    existing_parts = set()
    for match in re.finditer(r'PART\s*(\d+)\n', all_text, re.IGNORECASE):
        existing_parts.add(int(match.group(1)))

    print(f"Found {len(existing_parts)} parts in document: {sorted(existing_parts)}")

    # Parse missing parts
    parsed_parts = set(int(p) for p in structure.get("parts", {}).keys())
    missing_parts = sorted(existing_parts - parsed_parts)

    if not missing_parts:
        print("All parts already parsed!")
        return

    print(f"Parsing {len(missing_parts)} missing parts: {missing_parts}")

    for part_num in missing_parts:
        try:
            print(f"\n{'=' * 60}")
            part_data = parse_part(part_num, all_text)

            if "parts" not in structure:
                structure["parts"] = {}

            structure["parts"][str(part_num)] = part_data
            print(f"✓ Part {part_num} complete")

        except Exception as e:
            print(f"✗ Part {part_num} failed: {e}")

    save_structure(structure)

    print(f"\n{'=' * 60}")
    print(f"Parsed {len(missing_parts)} parts")


def cmd_validate(args):
    """Validate current structure"""
    if not os.path.exists(OUTPUT_FILE):
        print(f"{OUTPUT_FILE} not found")
        return 1

    with open(OUTPUT_FILE, 'r') as f:
        structure = json.load(f)

    print("Validating structure...")
    is_valid, errors = validate_structure(structure)

    if is_valid:
        print("✓ Schema validation passed")
        return 0
    else:
        print(f"✗ Schema validation failed ({len(errors)} errors):")
        for error in errors:
            print(f"  - {error}")
        return 1


def cmd_stats(args):
    """Show statistics about current structure"""
    if not os.path.exists(OUTPUT_FILE):
        print(f"{OUTPUT_FILE} not found")
        return 1

    with open(OUTPUT_FILE, 'r') as f:
        structure = json.load(f)

    print("\n" + "=" * 60)
    print("LCHA STRUCTURE STATISTICS")
    print("=" * 60)

    parts = structure.get("parts", {})
    print(f"\nTotal Parts: {len(parts)}")

    total_sections = 0
    total_definitions = 0

    for part_num, part_data in parts.items():
        sections = part_data.get("sections", {})
        section_count = len(sections)
        total_sections += section_count

        # Count definitions
        def_count = 0
        for section_data in sections.values():
            def_count += len(section_data.get("definitions", {}))
        total_definitions += def_count

        title = part_data.get("title", "UNKNOWN")[:40]
        print(f"  Part {part_num}: {title}...")
        print(f"    Sections: {section_count}")
        if def_count > 0:
            print(f"    Definitions: {def_count}")

    print(f"\nTotal Sections: {total_sections}")
    print(f"Total Definitions: {total_definitions}")

    # Metadata
    metadata = structure.get("metadata", {})
    print(f"\nSchema Version: {metadata.get('schema_version', 'unknown')}")
    print(f"Parser Version: {metadata.get('parser_version', 'unknown')}")
    print(f"Last Updated: {metadata.get('last_updated', 'unknown')}")

    print()


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Unified LCHA Parser',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 parse_lcha.py --discover 6       Discover Part 6 structure
  python3 parse_lcha.py --part 6           Parse Part 6
  python3 parse_lcha.py --all              Parse all remaining parts
  python3 parse_lcha.py --validate         Validate current structure
  python3 parse_lcha.py --stats            Show statistics
        """
    )

    parser.add_argument('--discover', type=int, metavar='N',
                        help='Discover structure of Part N without parsing')
    parser.add_argument('--part', type=int, metavar='N',
                        help='Parse specific Part N')
    parser.add_argument('--all', action='store_true',
                        help='Parse all remaining parts')
    parser.add_argument('--validate', action='store_true',
                        help='Validate current structure')
    parser.add_argument('--stats', action='store_true',
                        help='Show statistics about current structure')

    args = parser.parse_args()

    # Dispatch to appropriate command
    if args.discover:
        cmd_discover(args)
    elif args.part:
        cmd_parse(args)
    elif args.all:
        cmd_parse_all(args)
    elif args.validate:
        return cmd_validate(args)
    elif args.stats:
        return cmd_stats(args)
    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
