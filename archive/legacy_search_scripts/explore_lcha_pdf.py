#!/usr/bin/env python3
"""
LCHA PDF Exploration - Phase 1: Basic Structure Discovery

This script explores the LCHA PDF to understand its structure before
building a proper parser. We investigate:
1. PDF page count and numbering
2. Page offset between TOC and actual PDF pages
3. Part header patterns
4. Condition header patterns
5. Text extraction quality

Usage:
    python explore_lcha_pdf.py
"""

import pdfplumber
import re
import sys
from pathlib import Path

# Configuration
PDF_PATH = "low-carbon-hydrogen-agreement-standard-terms-and-conditions.pdf"

# Ground truth from Table of Contents (start pages)
TOC_DATA = {
    "parts": {
        1: {"title": "Introduction (Definitions and interpretation)", "page": 1, "conditions": [1]},
        2: {"title": "Term", "page": 102, "conditions": [2]},
        3: {"title": "Conditions Precedent and Milestone", "page": 104, "conditions": [3, 4]},
        4: {"title": "Adjustments to Installed Capacity", "page": 130, "conditions": [5, 6, 7]},
        5: {"title": "Payment calculations", "page": 137, "conditions": [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]},
        6: {"title": "Billing and payment", "page": 169, "conditions": [21, 22, 23, 24, 25, 26, 27]},
        7: {"title": "Representations, warranties, undertakings", "page": 186, "conditions": list(range(28, 42))},
        8: {"title": "Changes in Law", "page": 233, "conditions": [42, 43, 44, 45, 46, 47, 48, 49, 50, 51]},
        9: {"title": "Termination", "page": 266, "conditions": [52, 53, 54, 55]},
        10: {"title": "Credit Support", "page": 287, "conditions": [56, 57]},
        11: {"title": "Dispute Resolution", "page": 292, "conditions": [58, 59, 60, 61, 62, 63, 64]},
        12: {"title": "General provisions", "page": 302, "conditions": [65, 66, 67, 68, 69, 70, 71, 72]},
        13: {"title": "Confidentiality", "page": 311, "conditions": [73, 74, 75]},
        14: {"title": "Miscellaneous", "page": 321, "conditions": list(range(76, 91))},
    }
}


def phase_1_basic_info(pdf_path: str):
    """Phase 1: Basic PDF information and page numbering."""
    print("=" * 70)
    print("PHASE 1: BASIC PDF INFO")
    print("=" * 70)
    print()

    with pdfplumber.open(pdf_path) as pdf:
        print(f"Total pages in PDF: {len(pdf.pages)}")
        print()

        # Check first few pages for cover/TOC
        print("First 5 pages (checking for cover/TOC):")
        print("-" * 70)
        for i in range(min(5, len(pdf.pages))):
            page = pdf.pages[i]
            text = page.extract_text() or ""
            lines = text.split('\n')[:10]
            print(f"\nPDF Page {i} (0-indexed):")
            for line in lines:
                if line.strip():
                    print(f"  {line[:80]}")

    print()


def phase_2_find_part_boundaries(pdf_path: str):
    """Phase 2: Find Part header patterns and page offset."""
    print("=" * 70)
    print("PHASE 2: FIND PART BOUNDARIES")
    print("=" * 70)
    print()

    with pdfplumber.open(pdf_path) as pdf:
        # Test Part 5 (TOC says page 137)
        print("Testing Part 5 (TOC page 137):")
        print("-" * 70)

        for offset in range(-3, 4):
            page_idx = 137 + offset - 1  # Convert to 0-indexed
            if 0 <= page_idx < len(pdf.pages):
                text = pdf.pages[page_idx].extract_text() or ""
                first_lines = text.split('\n')[:15] if text else []

                has_part_5 = any(p in text for p in ["Part 5", "PART 5", "Part Five"])
                has_payment = "Payment" in text
                has_calc = "calculation" in text.lower()

                indicators = []
                if has_part_5:
                    indicators.append("*** PART 5 MARKER ***")
                if has_payment:
                    indicators.append("'Payment'")
                if has_calc:
                    indicators.append("'calculation'")

                if indicators:
                    print(f"\nOffset {offset:+d} (PDF index {page_idx}): {', '.join(indicators)}")
                    for line in first_lines[:8]:
                        if line.strip():
                            print(f"  {line[:70]}")

        # Now scan entire PDF for Part markers
        print("\n" + "=" * 70)
        print("Scanning entire PDF for Part markers:")
        print("-" * 70)

        part_markers = []
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            # Look for Part headers
            for match in re.finditer(r'\bPart\s+(\d+|[A-Z]+)\b', text, re.IGNORECASE):
                part_markers.append({
                    'pdf_page': i,
                    'part': match.group(1),
                    'context': text[max(0, match.start()-30):match.end()+30]
                })

        print(f"\nFound {len(part_markers)} Part markers:")
        for marker in part_markers[:20]:  # Show first 20
            print(f"  PDF page {marker['pdf_page']:3d}: Part {marker['part']}")
        if len(part_markers) > 20:
            print(f"  ... and {len(part_markers) - 20} more")

    print()


def phase_3_find_condition_patterns(pdf_path: str):
    """Phase 3: Find Condition header patterns."""
    print("=" * 70)
    print("PHASE 3: FIND CONDITION PATTERNS")
    print("=" * 70)
    print()

    with pdfplumber.open(pdf_path) as pdf:
        # Check around where Condition 8 should be (page 137)
        print("Testing Condition 8 area (TOC page 137):")
        print("-" * 70)

        for page_num in range(135, 142):
            page_idx = page_num - 1
            if 0 <= page_idx < len(pdf.pages):
                text = pdf.pages[page_idx].extract_text() or ""

                # Look for various condition patterns
                patterns = {
                    r'^8\.\s': "Start of line: '8. '",
                    r'\n8\.\s': "Newline: '8. '",
                    r'Condition 8': "'Condition 8'",
                    r'\b8\s+Definitions': "'8 Definitions'",
                    r'^9\.\s': "Start of line: '9. '",
                }

                found = []
                for pattern, desc in patterns.items():
                    if re.search(pattern, text, re.MULTILINE):
                        found.append(desc)

                if found:
                    print(f"\nPDF page {page_idx} (TOC page {page_num}): {', '.join(found)}")
                    # Show first few lines
                    lines = text.split('\n')[:10]
                    for line in lines:
                        if line.strip():
                            print(f"  {line[:70]}")

        # Scan for condition number patterns across a wider range
        print("\n" + "=" * 70)
        print("Scanning for condition patterns in Part 5 range (pages 137-168):")
        print("-" * 70)

        conditions_found = []
        for page_num in range(137, 169):
            page_idx = page_num - 1
            if 0 <= page_idx < len(pdf.pages):
                text = pdf.pages[page_idx].extract_text() or ""

                # Look for condition numbers at start of lines
                matches = re.findall(r'^(\d{1,2})\.\s+[A-Z]', text, re.MULTILINE)
                for m in matches:
                    conditions_found.append({'page': page_num, 'condition': int(m)})

        print(f"\nFound potential condition markers:")
        for item in conditions_found[:30]:
            print(f"  Page {item['page']}: Condition {item['condition']}")
        if len(conditions_found) > 30:
            print(f"  ... and {len(conditions_found) - 30} more")

    print()


def phase_4_validate_known_conditions(pdf_path: str):
    """Phase 4: Validate specific known conditions."""
    print("=" * 70)
    print("PHASE 4: VALIDATE KNOWN CONDITIONS")
    print("=" * 70)
    print()

    known_conditions = {
        8: {"page": 137, "title_contains": ["Definitions", "Part 5"]},
        10: {"page": 146, "title_contains": ["Difference", "Amount"]},
        42: {"page": 233, "title_contains": ["Qualifying", "Change", "Law"]},
        52: {"page": 266, "title_contains": ["Termination"]},
    }

    with pdfplumber.open(pdf_path) as pdf:
        for cond_num, expected in known_conditions.items():
            page_idx = expected["page"] - 1
            if page_idx < len(pdf.pages):
                text = pdf.pages[page_idx].extract_text() or ""

                found_num = str(cond_num) in text or f"{cond_num}." in text
                title_lower = text.lower()
                found_title = all(term.lower() in title_lower for term in expected["title_contains"])

                status = "✅" if (found_num and found_title) else "❌"
                print(f"{status} Condition {cond_num} on TOC page {expected['page']}")
                print(f"   Found number: {found_num}, Title terms: {found_title}")

                if not (found_num and found_title):
                    print(f"   Preview (first 300 chars):")
                    print(f"   {text[:300]}")
                print()

    print()


def phase_5_investigate_part_8(pdf_path: str):
    """Phase 5: Deep dive into Part 8 (problematic area)."""
    print("=" * 70)
    print("PHASE 5: PART 8 INVESTIGATION (Problem Area)")
    print("=" * 70)
    print()
    print("TOC: Part 8 'Changes in Law' starts page 233, should have conditions 42-51")
    print("-" * 70)
    print()

    with pdfplumber.open(pdf_path) as pdf:
        # Check page 233
        page_idx = 233 - 1
        if page_idx < len(pdf.pages):
            text = pdf.pages[page_idx].extract_text() or ""
            print(f"Page 233 content (first 1000 chars):")
            print(text[:1000])
            print()

        # Scan Part 8 range for ALL condition-like patterns
        print("Scanning pages 233-265 for condition patterns:")
        print("-" * 70)

        all_numbers = []
        for page_num in range(233, 266):
            page_idx = page_num - 1
            if page_idx < len(pdf.pages):
                text = pdf.pages[page_idx].extract_text() or ""

                # Find all numbers that look like condition markers
                matches = re.findall(r'^(\d{1,2})\.\s', text, re.MULTILINE)
                for m in matches:
                    all_numbers.append((page_num, int(m)))

        # Group by condition number
        by_condition = {}
        for page, cond in all_numbers:
            if cond not in by_condition:
                by_condition[cond] = []
            by_condition[cond].append(page)

        print(f"\nCondition markers found in Part 8 range:")
        for cond in sorted(by_condition.keys()):
            pages = by_condition[cond]
            print(f"  Condition {cond:2d}: pages {pages}")

        # Check what's actually there
        print(f"\nExpected in Part 8: 42-51")
        print(f"Actually found: {sorted([c for c, p in all_numbers])}")

        # Check for conditions that shouldn't be there
        unexpected = [c for c in sorted(by_condition.keys()) if c < 42 or c > 51]
        if unexpected:
            print(f"\n⚠️  Unexpected conditions found: {unexpected}")
        else:
            print(f"\n✅ Only expected conditions (42-51) found")

    print()


def main():
    """Run all exploration phases."""
    pdf_path = PDF_PATH

    # Check if PDF exists
    if not Path(pdf_path).exists():
        print(f"Error: PDF not found at {pdf_path}")
        print(f"Please check the path and try again.")
        sys.exit(1)

    print()
    print("*" * 70)
    print("* LCHA PDF STRUCTURE EXPLORATION")
    print("*" * 70)
    print()

    try:
        phase_1_basic_info(pdf_path)
        phase_2_find_part_boundaries(pdf_path)
        phase_3_find_condition_patterns(pdf_path)
        phase_4_validate_known_conditions(pdf_path)
        phase_5_investigate_part_8(pdf_path)

        print("=" * 70)
        print("EXPLORATION COMPLETE")
        print("=" * 70)
        print()
        print("Next steps:")
        print("1. Review findings above")
        print("2. Document patterns discovered")
        print("3. Build extraction logic based on findings")
        print()

    except Exception as e:
        print(f"\nError during exploration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
