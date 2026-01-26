"""
Part 5 Discovery Script
Analyzes Part 5 of the LCHA document to understand its structure before parsing.
"""

import json
import re
import os

def discover_part5():
    """Discover Part 5 structure"""

    # Load text from cache
    CACHE_FILE = "lcha_text_cache.json"
    if not os.path.exists(CACHE_FILE):
        print(f"Error: {CACHE_FILE} not found!")
        return

    with open(CACHE_FILE, 'r') as f:
        all_text = json.load(f)['text']

    # Extract Part 5 text
    part5_match = re.search(r'Part\s*5\n(.*?)(?=Part\s*6|\Z)', all_text, re.DOTALL | re.IGNORECASE)
    if not part5_match:
        print("Could not find Part 5")
        return

    part5_text = part5_match.group(1)
    part5_text = part5_text.strip()

    print("=" * 60)
    print("PART 5 DISCOVERY")
    print("=" * 60)

    # Find title
    lines = part5_text.split('\n')
    print(f"\nFirst 10 lines:")
    for i, line in enumerate(lines[:10]):
        print(f"  {i+1}: {line[:80]}")

    # Extract title (first all-caps line after Part 5)
    title_match = re.search(r'^([A-Z][A-Z\s,\(\):\-]+)', part5_text.strip(), re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
        print(f"\nPart 5 Title: {title}")

    # Check for Conditions
    print(f"\n--- CONDITION DETECTION ---")
    cond_pattern = r'(\d+)\.\s+([A-Z][A-Z\s:\-]+)'
    conditions = re.findall(cond_pattern, part5_text[:20000])
    if conditions:
        print(f"Found {len(conditions)} potential conditions:")
        for num, title in conditions[:10]:
            print(f"  Condition {num}: {title[:60]}")
    else:
        # Try different patterns
        alt_conds = re.findall(r'(?:^|\n)(\d+)\.\s+', part5_text[:20000])
        if alt_conds:
            print(f"Found sections numbered: {set(alt_conds)}")

    # Section numbering
    print(f"\n--- SECTION NUMBERING ---")
    sections = re.findall(r'(\d+\.\d+)\s+', part5_text[:20000])
    section_nums = sorted(set(sections))
    print(f"Section numbers found: {section_nums[:20]}")

    # Sub-clauses
    print(f"\n--- SUB-CLAUSE DETECTION ---")
    subclauses = re.findall(r'(\d+\.\d+\.\d+)', part5_text[:20000])
    if subclauses:
        print(f"Found sub-clauses: {sorted(set(subclauses))[:10]}")
    else:
        print("No sub-clauses (X.Y.Z) found")

    # Formulas
    print(f"\n--- FORMULA DETECTION ---")
    if 'where:' in part5_text.lower():
        print("Part 5 contains 'where:' clauses (formulas)")
        # Find where clauses
        where_matches = re.finditer(r'\bwhere\s*:', part5_text, re.IGNORECASE)
        where_count = sum(1 for _ in where_matches)
        print(f"  Found {where_count} 'where:' clauses")
    else:
        print("No 'where:' clauses found")

    # Check for (A), (B) subsections
    print(f"\n--- SUBSECTION PATTERNS ---")
    alpha_count = len(re.findall(r'\([A-Z]\)\s*', part5_text))
    roman_count = len(re.findall(r'\([ivx]+\)\s*', part5_text, re.IGNORECASE))
    lower_count = len(re.findall(r'\([a-z]\)\s*', part5_text))
    print(f"Alphabetic (A), (B): {alpha_count} matches")
    print(f"Roman (i), (ii): {roman_count} matches")
    print(f"Lowercase (a), (b): {lower_count} matches")

    # Check total text length
    print(f"\n--- TEXT STATS ---")
    print(f"Total characters: {len(part5_text)}")
    print(f"Total lines: {len(lines)}")

    # Find all numbered sections (X.Y)
    all_sections = re.finditer(r'(\d+\.\d+)\s+(.*?)(?=\n\d+\.\d+|\Z)', part5_text, re.DOTALL)
    section_list = list(all_sections)
    print(f"Total sections (X.Y pattern): {len(section_list)}")

    # Sample first section
    if section_list:
        print(f"\n--- FIRST SECTION SAMPLE ---")
        first_match = section_list[0]
        print(f"Section: {first_match.group(1)}")
        content = first_match.group(2).strip()[:300]
        print(f"Content preview: {content}...")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    discover_part5()
