#!/usr/bin/env python3
"""
LCHA Parser v2 - TOC-Based Extraction

Extracts LCHA structure using Table of Contents as ground truth.
Avoids pattern matching for Part detection (which caused 494 false positives).

Usage:
    python extract_lcha_v2.py

Output:
    lcha_structure_v3.json
"""

import pdfplumber
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# =============================================================================
# CONFIGURATION - Ground Truth from Table of Contents
# =============================================================================

PDF_PATH = "low-carbon-hydrogen-agreement-standard-terms-and-conditions.pdf"
OFFSET = 7  # Finder page = TOC page + 7

# TOC: Part start pages
TOC_PARTS = {
    1: {"title": "Introduction (Definitions and interpretation)", "page": 1, "end_page": 102},
    2: {"title": "Term", "page": 102, "end_page": 104},
    3: {"title": "Conditions Precedent and Milestone Requirement", "page": 104, "end_page": 130},
    4: {"title": "Adjustments to Installed Capacity Estimate", "page": 130, "end_page": 137},
    5: {"title": "Payment calculations", "page": 137, "end_page": 169},
    6: {"title": "Billing and payment", "page": 169, "end_page": 186},
    7: {"title": "Representations, warranties and undertakings", "page": 186, "end_page": 233},
    8: {"title": "Changes in Law", "page": 233, "end_page": 266},
    9: {"title": "Termination", "page": 266, "end_page": 287},
    10: {"title": "Credit Support", "page": 287, "end_page": 292},
    11: {"title": "Dispute Resolution", "page": 292, "end_page": 302},
    12: {"title": "General provisions", "page": 302, "end_page": 311},
    13: {"title": "Confidentiality, announcements, FOI", "page": 311, "end_page": 321},
    14: {"title": "Miscellaneous", "page": 321, "end_page": 332},
}

# TOC: Condition start pages for within-part parsing
TOC_CONDITIONS = {
    # Part 1: Condition 1 starts page 1
    1: {"page": 1},

    # Part 2: Condition 2 starts page 102
    2: {"page": 102},

    # Part 3
    3: {"page": 104},
    4: {"page": 126},

    # Part 4
    5: {"page": 130},
    6: {"page": 133},
    7: {"page": 134},

    # Part 5
    8: {"page": 137},
    9: {"page": 141},
    10: {"page": 146},
    11: {"page": 147},
    12: {"page": 148},
    13: {"page": 150},
    14: {"page": 155},
    15: {"page": 157},
    16: {"page": 158},
    17: {"page": 159},
    18: {"page": 161},
    19: {"page": 163},
    20: {"page": 167},

    # Part 6
    21: {"page": 169},
    22: {"page": 174},
    23: {"page": 182},
    24: {"page": 183},
    25: {"page": 184},
    26: {"page": 184},
    27: {"page": 184},

    # Part 7
    28: {"page": 186},
    29: {"page": 189},
    30: {"page": 191},
    31: {"page": 193},
    32: {"page": 195},
    33: {"page": 199},
    34: {"page": 202},
    35: {"page": 204},
    36: {"page": 206},
    37: {"page": 208},
    38: {"page": 210},
    39: {"page": 213},
    40: {"page": 214},
    41: {"page": 231},

    # Part 8
    42: {"page": 233},
    43: {"page": 238},
    44: {"page": 251},
    45: {"page": 252},
    46: {"page": 256},
    47: {"page": 257},
    48: {"page": 257},
    49: {"page": 259},
    50: {"page": 263},
    51: {"page": 263},

    # Part 9
    52: {"page": 266},
    53: {"page": 280},
    54: {"page": 284},
    55: {"page": 286},

    # Part 10
    56: {"page": 287},
    57: {"page": 288},

    # Part 11
    58: {"page": 292},
    59: {"page": 294},
    60: {"page": 295},
    61: {"page": 298},
    62: {"page": 299},
    63: {"page": 301},
    64: {"page": 301},

    # Part 12
    65: {"page": 302},
    66: {"page": 304},
    67: {"page": 305},
    68: {"page": 305},
    69: {"page": 305},
    70: {"page": 306},
    71: {"page": 308},
    72: {"page": 308},

    # Part 13
    73: {"page": 311},
    74: {"page": 316},
    75: {"page": 318},

    # Part 14
    76: {"page": 321},
    77: {"page": 322},
    78: {"page": 323},
    79: {"page": 324},
    80: {"page": 325},
    81: {"page": 326},
    82: {"page": 327},
    83: {"page": 327},
    84: {"page": 328},
    85: {"page": 329},
    86: {"page": 329},
    87: {"page": 330},
    88: {"page": 330},
    89: {"page": 331},
    90: {"page": 331},
}


# =============================================================================
# TEXT CLEANING (Preserved from original parser)
# =============================================================================

def clean_text(text: str) -> str:
    """Remove PDF artifacts and normalize text."""
    # Remove DRAFT footers
    text = re.sub(r'\n\d+\nDRAFT:\s*.*?\n', '\n', text)

    # Remove standalone page numbers
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        # Skip standalone page numbers (1-3 digits)
        if re.match(r'^\d{1,3}$', line.strip()):
            continue
        # Skip draft headers
        if re.match(r'^DRAFT:\s*.*$', line.strip()):
            continue
        cleaned.append(line)

    text = '\n'.join(cleaned)

    # Normalize whitespace
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)  # Single newlines to spaces
    text = re.sub(r' +', ' ', text)  # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)  # Final cleanup

    return text.strip()


# =============================================================================
# EXTRACTION FUNCTIONS
# =============================================================================

def toc_to_pdf_page(toc_page: int) -> int:
    """Convert TOC page number to Finder page number."""
    return toc_page + OFFSET


def extract_page_range(pdf, start_page: int, end_page: int) -> str:
    """Extract text from a range of PDF pages (Finder page numbers)."""
    text_parts = []
    for finder_page in range(start_page, end_page):
        pdf_index = finder_page - 1  # Convert to 0-indexed
        if 0 <= pdf_index < len(pdf.pages):
            page_text = pdf.pages[pdf_index].extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts)


def build_breadcrumb(part_num: int, part_title: str, cond_num: int, cond_title: str) -> str:
    """Build hierarchical breadcrumb for context."""
    return f"Part {part_num} > {part_title} > {cond_num}. {cond_title}"


def extract_references(text: str) -> List[Dict[str, str]]:
    """Extract cross-references from text."""
    references = []

    # Condition references
    for match in re.finditer(r'Condition\s+(\d+(?:\.\d+)?)', text):
        references.append({"type": "condition", "target": f"Condition {match.group(1)}"})

    # Annex references
    for match in re.finditer(r'Annex\s+(\d+(?:\.\w+)?)', text):
        references.append({"type": "annex", "target": f"Annex {match.group(1)}"})

    # Part references
    for match in re.finditer(r'Part\s+(\d+)', text):
        references.append({"type": "part", "target": f"Part {match.group(1)}"})

    # Deduplicate
    seen = set()
    unique = []
    for ref in references:
        key = (ref["type"], ref["target"])
        if key not in seen:
            seen.add(key)
            unique.append(ref)

    return unique


def extract_all_conditions_from_part(text: str, part_num: int, part_title: str, expected_conditions: List[int]) -> Dict[str, Any]:
    """
    Extract all conditions from Part text.

    Finds all condition headers (N. TITLE) and extracts each condition's text
    up to the next condition header.
    """
    conditions = {}

    # Pattern for condition headers: "N. TITLE" at start of line
    # Title goes until newline (not greedy)
    condition_pattern = r'^(\d{1,2})\.\s+([^\n]+)'

    # Find all condition headers with their positions
    matches = []
    for match in re.finditer(condition_pattern, text, re.MULTILINE):
        cond_num = int(match.group(1))
        cond_title = match.group(2).strip()
        position = match.start()
        matches.append((cond_num, cond_title, position))

    # Sort by position
    matches.sort(key=lambda x: x[2])

    # Extract each condition's text
    for i, (cond_num, cond_title, cond_start) in enumerate(matches):
        # Find end position (start of next condition or end of text)
        if i + 1 < len(matches):
            cond_end = matches[i + 1][2]
        else:
            cond_end = len(text)

        # Extract condition text
        cond_text = text[cond_start:cond_end]

        # Clean the text
        raw_text = clean_text(cond_text)

        # Only include if this is an expected condition for this part
        if cond_num in expected_conditions:
            # Build breadcrumb
            breadcrumb = build_breadcrumb(part_num, part_title, cond_num, cond_title)

            conditions[str(cond_num)] = {
                "id": f"part{part_num}.c{cond_num}",
                "parent_id": f"part{part_num}",
                "type": "condition",
                "number": cond_num,
                "title": cond_title,
                "breadcrumb": breadcrumb,
                "raw_text": raw_text,
                "text_for_embedding": f"{breadcrumb}: {raw_text}",
                "references": extract_references(raw_text),
            }

    return conditions


def parse_part_1_definitions(text: str) -> Dict[str, Any]:
    """Parse Part 1 definitions (alphabetical glossary, not conditions)."""

    definitions = {}

    # Pattern: "Term" definition format
    # Each definition starts with a quoted term followed by "means" or "has the meaning"
    pattern = r'"([^"]+)"\s+(means|has the meaning)'

    for match in re.finditer(pattern, text):
        term = match.group(1)
        position = match.start()

        # Find the extent of this definition (until next quote or reasonable limit)
        remaining = text[position:]

        # Look for next definition start or end of section
        next_def = re.search(r'\n\s?"', remaining[50:])

        if next_def:
            def_text = remaining[:next_def.start() + 50]
        else:
            def_text = remaining[:2000]

        def_text = clean_text(def_text)

        # Extract first meaningful sentence/phrase
        first_sentence = re.split(r'[.;]', def_text)[0].strip()

        definitions[term] = {
            "id": f"part1.def.{term.replace(' ', '_').replace('-', '_')}",
            "parent_id": "part1",
            "type": "definition",
            "term": term,
            "text_for_embedding": f"Part 1 > Definitions: {term} {first_sentence}",
            "raw_text": def_text,
            "references": extract_references(def_text),
        }

    return definitions


def extract_part(pdf, part_num: int) -> Dict[str, Any]:
    """Extract a complete Part from the PDF."""

    part_info = TOC_PARTS[part_num]
    start_finder = toc_to_pdf_page(part_info["page"])
    end_finder = toc_to_pdf_page(part_info["end_page"])

    print(f"  Extracting Part {part_num}: pages {start_finder}-{end_finder}")

    # Extract text from entire Part page range
    raw_text = extract_page_range(pdf, start_finder, end_finder)

    # Validate: first page should contain "Part N"
    if f"Part {part_num}" not in raw_text[:5000]:
        print(f"    ⚠️  Warning: Part {part_num} marker not found on expected page")

    # Build part node
    part = {
        "id": f"part{part_num}",
        "type": "part",
        "number": part_num,
        "title": part_info["title"],
        "toc_page": part_info["page"],
        "pdf_start_page": start_finder,
        "pdf_end_page": end_finder,
    }

    # Special handling for Part 1 (definitions)
    if part_num == 1:
        part["definitions"] = parse_part_1_definitions(raw_text)
        part["conditions"] = {}
    else:
        # Determine which conditions belong to this part
        expected_conditions = []
        for cond_num, cond_info in TOC_CONDITIONS.items():
            cond_page = cond_info["page"]
            # Check if condition is within this part's page range
            if part_info["page"] <= cond_page < part_info["end_page"]:
                expected_conditions.append(cond_num)

        # Extract all conditions from Part text at once
        part["conditions"] = extract_all_conditions_from_part(
            raw_text, part_num, part_info["title"], expected_conditions
        )

    return part


# =============================================================================
# VALIDATION
# =============================================================================

def validate_structure(structure: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Validate extracted structure against ground truth."""

    errors = []

    # Check all parts exist
    for part_num in range(1, 15):
        if str(part_num) not in structure["parts"]:
            errors.append(f"Part {part_num} missing")
            continue

        part = structure["parts"][str(part_num)]

        # Check conditions are in correct parts
        for cond_num, cond_info in TOC_CONDITIONS.items():
            # Determine which part this condition belongs to
            expected_part = None
            for pn in range(1, 15):
                part_info = TOC_PARTS[pn]
                if part_info["page"] <= cond_info["page"] < part_info["end_page"]:
                    expected_part = pn
                    break

            if expected_part == part_num:
                # Condition should be in this part
                if str(cond_num) not in part.get("conditions", {}):
                    errors.append(f"Condition {cond_num} missing from Part {part_num}")

    return len(errors) == 0, errors


# =============================================================================
# MAIN EXTRACTION
# =============================================================================

def main():
    """Run the TOC-based extraction."""

    print("=" * 70)
    print("LCHA PARSER V2 - TOC-BASED EXTRACTION")
    print("=" * 70)
    print()

    # Check PDF exists
    if not Path(PDF_PATH).exists():
        print(f"Error: PDF not found at {PDF_PATH}")
        return

    # Open PDF
    print(f"Opening PDF: {PDF_PATH}")
    with pdfplumber.open(PDF_PATH) as pdf:
        print(f"Total pages: {len(pdf.pages)}")
        print(f"Offset: TOC page + {OFFSET} = Finder page")
        print()

        # Extract all parts
        parts = {}
        for part_num in range(1, 15):
            part = extract_part(pdf, part_num)
            parts[str(part_num)] = part

        # Count conditions
        total_conditions = sum(
            len(p.get("conditions", {})) for p in parts.values()
        )
        print()
        print(f"Extracted {total_conditions} conditions across 14 parts")

        # Count definitions
        definitions_count = len(parts.get("1", {}).get("definitions", {}))
        print(f"Extracted {definitions_count} definitions from Part 1")

    # Build output structure
    structure = {
        "metadata": {
            "document": "Low-Carbon Hydrogen Agreement Standard Terms and Conditions",
            "source_pdf": PDF_PATH,
            "extraction_date": datetime.now().isoformat(),
            "schema_version": "3.0",
            "offset": OFFSET,
            "total_parts": 14,
            "total_conditions": total_conditions,
            "total_definitions": definitions_count,
        },
        "parts": parts,
    }

    # Validate
    print()
    print("=" * 70)
    print("VALIDATING STRUCTURE")
    print("=" * 70)
    print()

    is_valid, errors = validate_structure(structure)

    if errors:
        print(f"❌ Found {len(errors)} validation errors:")
        for error in errors[:20]:
            print(f"  - {error}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")
    else:
        print("✅ Validation passed")

    # Save output
    output_path = "lcha_structure_v3.json"
    print()
    print(f"Saving to: {output_path}")

    with open(output_path, 'w') as f:
        json.dump(structure, f, indent=2)

    print()
    print("=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)
    print()
    print(f"Output: {output_path}")
    print(f"Conditions extracted: {total_conditions}")
    print(f"Definitions extracted: {definitions_count}")

    if not is_valid:
        print()
        print("⚠️  Validation failed - review errors above")


if __name__ == '__main__':
    main()
