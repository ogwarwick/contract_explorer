#!/usr/bin/env python3
"""
Add section-level parsing to LCHA structure v3.

Usage:
    python add_sections_to_v3.py

Input:  lcha_structure_v3.json
Output: lcha_structure_v4.json

This script parses sections, subsections, and subclauses from the existing
raw_text fields in conditions, transforming 1,004 embeddable items into
approximately 2,500-3,500 embeddable items with section-level precision.
"""

import json
import re
from datetime import datetime


def parse_sections(condition_num: int, raw_text: str) -> dict:
    """
    Parse sections from condition raw_text.

    Example: For condition 52, finds 52.1, 52.2, 52.3, etc.

    Args:
        condition_num: The condition number (e.g., 52)
        raw_text: The full raw text of the condition

    Returns:
        Dictionary mapping section numbers to their text
    """
    sections = {}
    # Pattern to match sections like 52.1, 52.2, 3.81, etc.
    pattern = rf'\b({condition_num}\.\d+)\b'

    # Find all matches, deduplicate, keep first occurrence only
    matches = list(re.finditer(pattern, raw_text))
    seen = set()
    unique_matches = []
    for match in matches:
        section_num = match.group(1)
        if section_num not in seen:
            seen.add(section_num)
            unique_matches.append(match)

    # Extract text for each section
    for i, match in enumerate(unique_matches):
        section_num = match.group(1)
        start = match.start()
        end = unique_matches[i + 1].start() if i + 1 < len(unique_matches) else len(raw_text)

        sections[section_num] = raw_text[start:end].strip()

    return sections


def parse_subsections(section_text: str) -> dict:
    """
    Parse (A), (B), (C) subsections from section text.

    Args:
        section_text: The text of a section

    Returns:
        Dictionary mapping subsection markers to their text
    """
    subsections = {}
    pattern = r'(?:^|\s)\(([A-Z])\)'

    matches = list(re.finditer(pattern, section_text))
    for i, match in enumerate(matches):
        marker = f"({match.group(1)})"
        start = match.start()
        # Skip the whitespace before the marker
        if section_text[start] in ' \t\n':
            start += 1
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)

        subsections[marker] = section_text[start:end].strip()

    return subsections


def parse_subclauses(subsection_text: str) -> dict:
    """
    Parse (i), (ii), (iii) or (a), (b), (c) subclauses.

    Args:
        subsection_text: The text of a subsection

    Returns:
        Dictionary mapping subclause markers to their text
    """
    subclauses = {}
    pattern = r'(?:^|\s)\(([ivxlc]+|[a-z])\)'

    matches = list(re.finditer(pattern, subsection_text, re.IGNORECASE))
    for i, match in enumerate(matches):
        marker = f"({match.group(1)})"
        start = match.start()
        if subsection_text[start] in ' \t\n':
            start += 1
        end = matches[i + 1].start() if i + 1 < len(matches) else len(subsection_text)

        subclauses[marker] = subsection_text[start:end].strip()

    return subclauses


def extract_references(text: str) -> list:
    """
    Extract cross-references from text.

    Args:
        text: Text to search for references

    Returns:
        List of reference dictionaries with 'type' and 'target' keys
    """
    references = []

    # Condition references: "Condition 52.3", "Conditions 52 and 53"
    for match in re.finditer(r'Condition\s+(\d+(?:\.\d+)?)', text):
        references.append({"type": "condition", "target": f"Condition {match.group(1)}"})

    # Annex references
    for match in re.finditer(r'Annex\s+(\d+)', text):
        references.append({"type": "annex", "target": f"Annex {match.group(1)}"})

    # Part references
    for match in re.finditer(r'Part\s+(\d+)', text):
        references.append({"type": "part", "target": f"Part {match.group(1)}"})

    # Deduplicate
    seen = set()
    unique = []
    for ref in references:
        key = (ref['type'], ref['target'])
        if key not in seen:
            seen.add(key)
            unique.append(ref)

    return unique


def get_intro_text(text: str, first_child_pattern: str, max_len: int = 500) -> str:
    """
    Extract intro text before first child, with truncation.

    Args:
        text: Full text to extract intro from
        first_child_pattern: Regex pattern to find first child marker
        max_len: Maximum length of intro text

    Returns:
        Intro text, truncated if necessary
    """
    match = re.search(first_child_pattern, text)
    intro = text[:match.start()] if match else text
    intro = intro.strip()

    if len(intro) > max_len:
        intro = intro[:max_len] + "..."

    return intro


def build_section_hierarchy(condition: dict) -> dict:
    """
    Add sections, subsections, subclauses to a condition.

    Args:
        condition: Condition dictionary with raw_text

    Returns:
        Dictionary of sections with their subsections and subclauses
    """
    raw_text = condition.get('raw_text', '')
    cond_num = condition.get('number')

    if not cond_num or not raw_text:
        return {}

    sections_raw = parse_sections(int(cond_num), raw_text)
    sections = {}

    for section_num, section_text in sections_raw.items():
        # Create section ID (e.g., part9.c52.s52_1)
        section_id = f"{condition['id']}.s{section_num.replace('.', '_')}"
        section_breadcrumb = f"{condition['breadcrumb']} > {section_num}"

        # Parse subsections
        subsections_raw = parse_subsections(section_text)
        subsections = {}

        for marker, sub_text in subsections_raw.items():
            # Create subsection ID (e.g., part9.c52.s52_1.sub_A)
            sub_id = f"{section_id}.sub_{marker.strip('()')}"
            sub_breadcrumb = f"{section_breadcrumb} > {marker}"

            # Parse subclauses
            subclauses_raw = parse_subclauses(sub_text)
            subclauses = {}

            for cl_marker, cl_text in subclauses_raw.items():
                # Create subclause ID (e.g., part9.c52.s52_1.sub_A.cl_i)
                cl_id = f"{sub_id}.cl_{cl_marker.strip('()').lower()}"
                cl_breadcrumb = f"{sub_breadcrumb} > {cl_marker}"

                subclauses[cl_marker] = {
                    "id": cl_id,
                    "parent_id": sub_id,
                    "type": "subclause",
                    "marker": cl_marker,
                    "breadcrumb": cl_breadcrumb,
                    "raw_text": cl_text,
                    "text_for_embedding": f"{cl_breadcrumb}: {cl_text[:500]}",
                    "references": extract_references(cl_text)
                }

            # Subsection intro (before subclauses)
            sub_intro = get_intro_text(sub_text, r'\(([ivxlc]+|[a-z])\)', 500)

            subsections[marker] = {
                "id": sub_id,
                "parent_id": section_id,
                "type": "subsection",
                "marker": marker,
                "breadcrumb": sub_breadcrumb,
                "raw_text": sub_text,
                "text_for_embedding": f"{sub_breadcrumb}: {sub_intro}",
                "references": extract_references(sub_text),
                "subclauses": subclauses
            }

        # Section intro (before subsections)
        section_intro = get_intro_text(section_text, r'\([A-Z]\)', 1000)

        sections[section_num] = {
            "id": section_id,
            "parent_id": condition['id'],
            "type": "section",
            "number": section_num,
            "breadcrumb": section_breadcrumb,
            "raw_text": section_text,
            "text_for_embedding": f"{section_breadcrumb}: {section_intro}",
            "references": extract_references(section_text),
            "subsections": subsections
        }

    return sections


def process_structure(input_path: str, output_path: str):
    """
    Process entire v3 structure to add section-level parsing.

    Args:
        input_path: Path to lcha_structure_v3.json
        output_path: Path for lcha_structure_v4.json
    """

    print(f"Loading {input_path}...")
    with open(input_path) as f:
        structure = json.load(f)

    stats = {
        'conditions_processed': 0,
        'sections_added': 0,
        'subsections_added': 0,
        'subclauses_added': 0
    }

    # Process each part
    for part_num, part in structure['parts'].items():
        print(f"Processing Part {part_num}...")

        for cond_num, condition in part.get('conditions', {}).items():
            # Build section hierarchy
            sections = build_section_hierarchy(condition)
            condition['sections'] = sections

            # Update condition's text_for_embedding to intro only
            if sections:
                pattern = rf'\b{cond_num}\.\d+\b'
                intro = get_intro_text(condition['raw_text'], pattern, 500)
                condition['text_for_embedding'] = f"{condition['breadcrumb']}: {intro}"

            # Count stats
            stats['conditions_processed'] += 1
            for section in sections.values():
                stats['sections_added'] += 1
                for subsection in section.get('subsections', {}).values():
                    stats['subsections_added'] += 1
                    stats['subclauses_added'] += len(subsection.get('subclauses', {}))

    # Update metadata
    structure['metadata']['schema_version'] = '4.0'
    structure['metadata']['enhancement_date'] = datetime.now().isoformat()
    structure['metadata']['total_sections'] = stats['sections_added']
    structure['metadata']['total_subsections'] = stats['subsections_added']
    structure['metadata']['total_subclauses'] = stats['subclauses_added']

    # Save
    print(f"Saving {output_path}...")
    with open(output_path, 'w') as f:
        json.dump(structure, f, indent=2)

    # Report
    print("\n" + "="*60)
    print("ENHANCEMENT COMPLETE")
    print("="*60)
    print(f"Conditions processed: {stats['conditions_processed']}")
    print(f"Sections added: {stats['sections_added']}")
    print(f"Subsections added: {stats['subsections_added']}")
    print(f"Subclauses added: {stats['subclauses_added']}")

    total_new = stats['sections_added'] + stats['subsections_added'] + stats['subclauses_added']
    total_embeddable = 915 + 89 + total_new  # definitions + conditions + new nodes
    print(f"\nTotal new embeddable items: {total_new}")
    print(f"Total embeddable items: {total_embeddable}")


if __name__ == '__main__':
    process_structure(
        '/Users/owenwarwick/lcha/lcha_structure_v3.json',
        '/Users/owenwarwick/lcha/lcha_structure_v4.json'
    )
