# lcha_utils.py
"""
LCHA Parser Utilities
Shared helper functions for parsing the Low-Carbon Hydrogen Agreement.

This module provides the single source of truth for all parsing helpers.
Import functions from here rather than duplicating code.
"""

import re
import json
from typing import Optional, Dict, List, Tuple

# =============================================================================
# TEXT CLEANING
# =============================================================================

def clean_extracted_text(text: str) -> str:
    """
    Remove PDF artifacts (page numbers, DRAFT footers).

    Args:
        text: Raw extracted text from PDF

    Returns:
        Cleaned text with page numbers and footers removed
    """
    # Remove page footers (DRAFT: August 2023 format)
    text = re.sub(r'\n\d+\nDRAFT:\s*.*?\n', '\n', text)
    # Remove standalone page numbers (1-3 digits on their own line)
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        # Skip standalone page numbers
        if re.match(r'^\d{1,3}$', line.strip()):
            continue
        # Skip draft headers
        if re.match(r'^DRAFT:\s*.*$', line.strip()):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


def normalize_text_whitespace(text: str) -> str:
    """
    Normalize whitespace - collapse multiple spaces/newlines to single space.

    Args:
        text: Text with irregular whitespace

    Returns:
        Text with normalized single spaces
    """
    # Single newlines to spaces (preserve paragraph breaks)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    # Collapse multiple spaces
    text = re.sub(r' +', ' ', text)
    return text.strip()


def clean_text_for_embedding(text: str) -> str:
    """
    Prepare text for embedding generation - clean artifacts and normalize.

    Args:
        text: Raw text to clean

    Returns:
        Cleaned, single-line text suitable for vector embedding
    """
    text = clean_extracted_text(text)
    text = normalize_text_whitespace(text)
    text = re.sub(r'\s+', ' ', text)
    # Remove section numbers at start (e.g., "5.2 " at beginning)
    text = re.sub(r'^\d+\.\d+\s+', '', text)
    return text.strip()


# =============================================================================
# REFERENCE EXTRACTION
# =============================================================================

def extract_references(text: str) -> List[Dict[str, str]]:
    """
    Extract cross-references to Conditions, Annexes, Parts, Schedules.

    Args:
        text: Text to search for references

    Returns:
        List of reference dicts with 'type' and 'target' keys
    """
    references = []

    # Condition references (e.g., "Condition 5.2", "Conditions 3.1 and 3.2")
    for match in re.finditer(r'Condition\s+(\d+(?:\.\d+)?)', text):
        references.append({"type": "condition", "target": f"Condition {match.group(1)}"})

    # Annex references
    for match in re.finditer(r'Annex\s+(\d+(?:\.\w+)?)', text):
        references.append({"type": "annex", "target": f"Annex {match.group(1)}"})

    # Part references
    for match in re.finditer(r'Part\s+(\d+)', text):
        references.append({"type": "part", "target": f"Part {match.group(1)}"})

    # Schedule references
    for match in re.finditer(r'Schedule\s+(\d+(?:\.\w+)?)', text):
        references.append({"type": "schedule", "target": f"Schedule {match.group(1)}"})

    # Deduplicate
    seen = set()
    unique = []
    for ref in references:
        key = (ref["type"], ref["target"])
        if key not in seen:
            seen.add(key)
            unique.append(ref)

    return unique


# =============================================================================
# SUBSECTION PARSING
# =============================================================================

def parse_alphabetic_subsections(content: str) -> Dict[str, str]:
    """
    Parse (A), (B), (C) subsections.

    Uses negative lookbehind for digit to avoid matching "2.3(B)" patterns
    (e.g., "Withdrawal Act 2018" contains "(W)" that should not be parsed).

    Args:
        content: Text containing alphabetic subsections

    Returns:
        Dict mapping subsection markers to text
    """
    subsections = {}
    # Negative lookbehind for digit to avoid matching "2.3(B)"
    pattern = r'(?<!\d)\(([A-Z])\)\s*(.*?)(?=(?<!\d)\([A-Z]\)|$)'
    matches = re.finditer(pattern, content, re.DOTALL)

    for match in matches:
        letter = f"({match.group(1)})"
        text = match.group(2).strip()
        subsections[letter] = text

    return subsections


def parse_roman_subsections(content: str) -> Dict[str, str]:
    """
    Parse (i), (ii), (iii) subsections.

    Args:
        content: Text containing roman numeral subsections

    Returns:
        Dict mapping subsection markers to text
    """
    subsections = {}
    pattern = r'\(([ivxlc]+)\)\s*(.*?)(?=\([ivxlc]+\)|$)'
    matches = re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)

    for match in matches:
        numeral = f"({match.group(1).lower()})"
        text = match.group(2).strip()
        subsections[numeral] = text

    return subsections


def parse_lowercase_subsections(content: str) -> Dict[str, str]:
    """
    Parse (a), (b), (c) subsections.

    Args:
        content: Text containing lowercase subsections

    Returns:
        Dict mapping subsection markers to text
    """
    subsections = {}
    pattern = r'\(([a-z])\)\s*(.*?)(?=\([a-z]\)|$)'
    matches = re.finditer(pattern, content, re.DOTALL)

    for match in matches:
        letter = f"({match.group(1)})"
        text = match.group(2).strip()
        subsections[letter] = text

    return subsections


def parse_nested_subsections(content: str, parent_id: str) -> Dict[str, dict]:
    """
    Parse nested (A)(i)(a) hierarchies with full node schema.

    Creates nodes for each level with id, parent_id, type, text_for_embedding,
    references, and raw_text fields.

    Args:
        content: Text containing nested subsections
        parent_id: ID of parent node

    Returns:
        Dict of node dicts keyed by node ID
    """
    nodes = {}

    # Parse (A), (B), etc.
    alpha_subs = parse_alphabetic_subsections(content)

    for letter, alpha_content in alpha_subs.items():
        section_id = f"{parent_id}{letter}"

        # Check for nested (i), (ii)
        if re.search(r'\([ivxlc]+\)', alpha_content, re.IGNORECASE):
            roman_subs = parse_roman_subsections(alpha_content)
            roman_intro = re.match(r'^(.*?)(?=\([ivxlc]+\))', alpha_content, re.DOTALL | re.IGNORECASE)
            intro_text = roman_intro.group(1).strip() if roman_intro else ""

            # Create intermediate subsection nodes for roman levels
            for numeral, roman_content in roman_subs.items():
                roman_id = f"{section_id}.{numeral}"

                # Check for nested (a), (b)
                if re.search(r'\([a-z]\)', roman_content):
                    lower_subs = parse_lowercase_subsections(roman_content)
                    lower_intro = re.match(r'^(.*?)(?=\([a-z]\))', roman_content, re.DOTALL)

                    # Create lowercase level nodes
                    for lower_letter, lower_content in lower_subs.items():
                        lower_id = f"{roman_id}.{lower_letter}"
                        nodes[lower_id] = {
                            "id": lower_id,
                            "parent_id": roman_id,
                            "type": "subclause",
                            "text_for_embedding": clean_text_for_embedding(lower_content),
                            "references": extract_references(lower_content),
                            "raw_text": lower_content
                        }

                    # Create roman level node with intro
                    nodes[roman_id] = {
                        "id": roman_id,
                        "parent_id": section_id,
                        "type": "subclause",
                        "text_for_embedding": clean_text_for_embedding(
                            lower_intro.group(1) if lower_intro else ""
                        ),
                        "references": extract_references(lower_intro.group(1)) if lower_intro else [],
                        "raw_text": intro_text,
                        "subsections": lower_subs
                    }
                else:
                    # Create roman level node without lowercase children
                    nodes[roman_id] = {
                        "id": roman_id,
                        "parent_id": section_id,
                        "type": "subclause",
                        "text_for_embedding": clean_text_for_embedding(roman_content),
                        "references": extract_references(roman_content),
                        "raw_text": roman_content
                    }

            # Create alphabetic level node
            nodes[section_id] = {
                "id": section_id,
                "parent_id": parent_id,
                "type": "subsection",
                "text_for_embedding": clean_text_for_embedding(intro_text),
                "references": extract_references(intro_text),
                "raw_text": intro_text,
                "subsections": {f"({rm.group(1).lower()})": rm.group(2).strip()
                               for rm in re.finditer(r'\(([ivxlc]+)\)\s*(.*?)(?=\([ivxlc]+\)|$)',
                                                    alpha_content, re.DOTALL | re.IGNORECASE)}
            }
        else:
            # Simple alphabetic subsection without roman nesting
            nodes[section_id] = {
                "id": section_id,
                "parent_id": parent_id,
                "type": "subsection",
                "text_for_embedding": clean_text_for_embedding(alpha_content),
                "references": extract_references(alpha_content),
                "raw_text": alpha_content
            }

    return nodes


# =============================================================================
# NODE CREATION
# =============================================================================

def create_node(
    id: str,
    parent_id: str,
    node_type: str,
    raw_text: str,
    parsed: dict,
    **kwargs
) -> dict:
    """
    Create a standardized node with all required fields.

    Args:
        id: Unique node identifier
        parent_id: Parent node ID
        node_type: Node type (part, section, definition, clause, etc.)
        raw_text: Original extracted text
        parsed: Structured parsed content
        **kwargs: Additional fields to include

    Returns:
        Dict with all standard node fields
    """
    node = {
        "id": id,
        "parent_id": parent_id,
        "type": node_type,
        "text_for_embedding": clean_text_for_embedding(raw_text),
        "references": extract_references(raw_text),
        "parsed": parsed,
        "raw_text": raw_text
    }
    node.update(kwargs)
    return node


def slugify(text: str) -> str:
    """
    Convert text to valid ID slug.

    Args:
        text: Text to slugify

    Returns:
        Slug with special chars replaced by underscores
    """
    return re.sub(r'[^a-zA-Z0-9]+', '_', text).strip('_')


def slugify_term(term: str) -> str:
    """Alias for slugify for semantic clarity with term names."""
    return slugify(term)


# =============================================================================
# PART EXTRACTION
# =============================================================================

def extract_part_text(all_text: str, part_num: int) -> Optional[str]:
    """
    Extract text for a specific Part.

    Uses newline anchor to avoid matching Table of Contents.

    Args:
        all_text: Full document text
        part_num: Part number to extract

    Returns:
        Part text or None if not found
    """
    next_part = part_num + 1
    # Use \n anchor to avoid matching TOC
    pattern = rf'PART\s*{part_num}\n(.*?)(?=PART\s*{next_part}\n|\Z)'
    match = re.search(pattern, all_text, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else None


def extract_part_title(part_text: str) -> str:
    """
    Extract Part title from Part text.

    Args:
        part_text: Text of a Part

    Returns:
        Extracted title or "UNKNOWN" if not found
    """
    # Title is typically first line in all caps
    match = re.search(r'^([A-Z][A-Z\s,\(\):\-]+)', part_text.strip())
    return match.group(1).strip() if match else "UNKNOWN"


def find_conditions_in_part(part_text: str) -> List[Tuple[int, str]]:
    """
    Find all Conditions within a Part.

    Args:
        part_text: Text of a Part

    Returns:
        List of (condition_number, title) tuples
    """
    matches = re.findall(r'Condition\s+(\d+)\s*\n[:\s]*([A-Z][A-Z\s]+)', part_text)
    # Also try pattern: "X. TITLE" on its own line
    alt_matches = re.findall(r'^(\d+)\.\s+([A-Z][A-Z\s:\-]+)$', part_text, re.MULTILINE)
    return [(int(num), title.strip()) for num, title in matches + alt_matches]


# =============================================================================
# FORMULA PARSING
# =============================================================================

def parse_formula(content: str) -> dict:
    """
    Parse formula definitions with 'where:' notation.

    Args:
        content: Text containing formula with where clause

    Returns:
        Dict with formula, variables, and raw_where_clause
    """
    result = {"formula": "", "variables": {}, "raw_where_clause": ""}

    parts = re.split(r'\bwhere\s*:', content, flags=re.IGNORECASE, maxsplit=1)

    if len(parts) >= 2:
        result["formula"] = parts[0].strip()
        where_content = parts[1].strip()
        result["raw_where_clause"] = where_content

        lines = where_content.split('\n')
        variables = []
        current_var = None
        current_def_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('= '):
                if current_var and current_def_lines:
                    variables.append((current_var, ' '.join(current_def_lines)))
                current_var = None
                current_def_lines = [line[2:].strip()]
            elif re.match(r'^[^\s=]+\s*=\s*.+', line):
                if current_var and current_def_lines:
                    variables.append((current_var, ' '.join(current_def_lines)))
                match = re.match(r'^([^\s=]+)\s*=\s*(.+)', line)
                if match:
                    variables.append((match.group(1), match.group(2)))
                current_var = None
                current_def_lines = []
            elif len(line) < 30 and not line.startswith('(') and not line[0].islower():
                if current_var and current_def_lines:
                    variables.append((current_var, ' '.join(current_def_lines)))
                current_var = line
                current_def_lines = []
            else:
                current_def_lines.append(line)

        if current_var and current_def_lines:
            variables.append((current_var, ' '.join(current_def_lines)))
        elif current_def_lines and not current_var:
            variables.append(("_unnamed", ' '.join(current_def_lines)))

        for var_name, var_def in variables:
            result["variables"][var_name] = var_def
    else:
        result["formula"] = content.strip()

    return result


# =============================================================================
# VALIDATION
# =============================================================================

def validate_node(node: dict) -> bool:
    """
    Validate that a node has all required fields.

    Args:
        node: Node dict to validate

    Returns:
        True if valid, False otherwise
    """
    required_fields = {"id", "parent_id", "type", "text_for_embedding", "references", "raw_text"}
    return required_fields.issubset(node.keys())


def validate_structure(structure: dict) -> Tuple[bool, List[str]]:
    """
    Validate entire structure for consistency.

    Args:
        structure: Full structure dict

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Check metadata
    if "metadata" not in structure:
        errors.append("Missing metadata")
    elif "schema_version" not in structure["metadata"]:
        errors.append("Missing schema_version in metadata")

    # Check parts
    if "parts" not in structure:
        errors.append("Missing parts")
        return False, errors

    # Validate all nodes recursively
    def validate_recursive(obj, path=""):
        if isinstance(obj, dict):
            if validate_node(obj):
                # Recursively validate nested structures
                for key, value in obj.items():
                    validate_recursive(value, f"{path}.{key}")
            elif "id" in obj:  # Has id but missing required fields
                errors.append(f"Invalid node at {path}: {obj.get('id')}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                validate_recursive(item, f"{path}[{i}]")

    validate_recursive(structure)

    return len(errors) == 0, errors


# =============================================================================
# MODULE TEST
# =============================================================================

if __name__ == "__main__":
    # Quick validation test
    print("LCHA Utils Module")
    print("=" * 50)

    # Test imports
    print("Testing functions...")

    test_text = "Condition 5.2 refers to Annex 10 and Part 3."
    refs = extract_references(test_text)
    print(f"extract_references: {refs}")

    test_slug = slugify("Acceptable Certification Scheme")
    print(f"slugify: '{test_slug}'")

    clean = clean_text_for_embedding("  5.2   This is   a test  \n\n  ")
    print(f"clean_text_for_embedding: '{clean}'")

    print("\nAll functions loaded successfully!")
