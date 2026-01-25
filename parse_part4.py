"""
Part 4 Parser for LCHA Document
Extracts Part 4 with schema: id, parent_id, type, text_for_embedding, references, raw_text
"""

import json
import re
import os

# ============================================
# HELPER FUNCTIONS
# ============================================

def clean_extracted_text(text):
    """Remove page numbers and draft headers from text"""
    # Remove page numbers (standalone numbers like "131", "132")
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
    return '\n'.join(cleaned)

def extract_references(text):
    """Extract cross-references to Conditions, Annexes, Schedules"""
    references = []
    # Condition references
    cond_refs = re.findall(r'Condition\s+(\d+(?:\.\d+)?)', text)
    for ref in cond_refs:
        references.append({"type": "condition", "target": f"Condition {ref}"})
    # Annex references
    annex_refs = re.findall(r'Annex\s+(\d+(?:\.\w+)?)', text)
    for ref in annex_refs:
        references.append({"type": "annex", "target": f"Annex {ref}"})
    # Schedule references
    schedule_refs = re.findall(r'Schedule\s+(\d+(?:\.\w+)?)', text)
    for ref in schedule_refs:
        references.append({"type": "schedule", "target": f"Schedule {ref}"})
    return references

def normalize_text_whitespace(text):
    """Normalize whitespace: collapse multiple spaces/newlines to single space"""
    return re.sub(r'\s+', ' ', text).strip()

def clean_text_for_embedding(text):
    """Clean text for embedding generation"""
    # Remove extra whitespace
    text = normalize_text_whitespace(text)
    # Remove section numbers at start
    text = re.sub(r'^\d+\.\d+\s+', '', text)
    return text

# ============================================
# NESTED STRUCTURE PARSING
# ============================================

def parse_alphabetic_subsections(content):
    """Parse (A), (B), (C) subsections"""
    subsections = {}
    pattern = r'\(([A-Z])\)\s*(.*?)(?=\([A-Z]\)|$)'
    matches = re.finditer(pattern, content, re.DOTALL)

    for match in matches:
        letter = f"({match.group(1)})"
        text = match.group(2).strip()
        subsections[letter] = text

    return subsections

def parse_roman_subsections(content):
    """Parse (i), (ii), (iii) subsections"""
    subsections = {}
    pattern = r'\(([ivxlc]+)\)\s*(.*?)(?=\([ivxlc]+\)|$)'
    matches = re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)

    for match in matches:
        numeral = f"({match.group(1).lower()})"
        text = match.group(2).strip()
        subsections[numeral] = text

    return subsections

def parse_lowercase_subsections(content):
    """Parse (a), (b), (c) subsections"""
    subsections = {}
    pattern = r'\(([a-z])\)\s*(.*?)(?=\([a-z]\)|$)'
    matches = re.finditer(pattern, content, re.DOTALL)

    for match in matches:
        letter = f"({match.group(1)})"
        text = match.group(2).strip()
        subsections[letter] = text

    return subsections

def parse_nested_subsections(content, parent_id):
    """Parse nested (A)(i)(a) structures with full node schema"""
    nodes = {}

    # Find all alphabetic subsections (A), (B), etc.
    alpha_pattern = r'\(([A-Z])\)\s*(.*?)(?=\([A-Z]\)|$)'
    alpha_matches = list(re.finditer(alpha_pattern, content, re.DOTALL))

    for match in alpha_matches:
        letter = match.group(1)
        section_id = f"{parent_id}({letter})"
        section_content = match.group(2).strip()

        # Check for roman subsections within
        if re.search(r'\([ivxlc]+\)', section_content, re.IGNORECASE):
            subsections = {}
            roman_pattern = r'\(([ivxlc]+)\)\s*(.*?)(?=\([ivxlc]+\)|$)'
            roman_matches = list(re.finditer(roman_pattern, section_content, re.DOTALL | re.IGNORECASE))

            for rm in roman_matches:
                roman = rm.group(1).lower()
                roman_id = f"{section_id}({roman})"
                roman_content = rm.group(2).strip()

                # Check for lowercase subsections
                if re.search(r'\([a-z]\)', roman_content):
                    lower_subs = {}
                    lower_pattern = r'\(([a-z])\)\s*(.*?)(?=\([a-z]\)|$)'
                    lower_matches = list(re.finditer(lower_pattern, roman_content, re.DOTALL))

                    intro_text = ""
                    for lm in lower_matches:
                        lower_letter = lm.group(1)
                        lower_id = f"{roman_id}({lower_letter})"
                        lower_content = lm.group(2).strip()
                        lower_subs[lower_letter] = lower_content

                        nodes[lower_id] = {
                            "id": lower_id,
                            "parent_id": roman_id,
                            "type": "subclause",
                            "text_for_embedding": clean_text_for_embedding(lower_content),
                            "references": extract_references(lower_content),
                            "raw_text": lower_content
                        }

                    # Get intro text before first lowercase
                    lower_intro = re.match(r'^(.*?)(?=\([a-z]\))', roman_content, re.DOTALL)
                    intro_text = lower_intro.group(1).strip() if lower_intro else ""

                    nodes[roman_id] = {
                        "id": roman_id,
                        "parent_id": section_id,
                        "type": "subclause",
                        "text_for_embedding": clean_text_for_embedding(intro_text),
                        "references": extract_references(intro_text),
                        "raw_text": intro_text,
                        "subsections": lower_subs
                    }
                else:
                    nodes[roman_id] = {
                        "id": roman_id,
                        "parent_id": section_id,
                        "type": "subclause",
                        "text_for_embedding": clean_text_for_embedding(roman_content),
                        "references": extract_references(roman_content),
                        "raw_text": roman_content
                    }

            # Get intro before first roman
            alpha_intro = re.match(r'^(.*?)(?=\([ivxlc]+\))', section_content, re.DOTALL | re.IGNORECASE)
            intro_text = alpha_intro.group(1).strip() if alpha_intro else ""

            nodes[section_id] = {
                "id": section_id,
                "parent_id": parent_id,
                "type": "subsection",
                "text_for_embedding": clean_text_for_embedding(intro_text),
                "references": extract_references(intro_text),
                "raw_text": intro_text,
                "subsections": {f"({rm.group(1).lower()})": rm.group(2).strip() for rm in roman_matches}
            }
        else:
            nodes[section_id] = {
                "id": section_id,
                "parent_id": parent_id,
                "type": "subsection",
                "text_for_embedding": clean_text_for_embedding(section_content),
                "references": extract_references(section_content),
                "raw_text": section_content
            }

    return nodes

# ============================================
# PART 4 EXTRACTION
# ============================================

def extract_part4(all_text):
    """Extract and parse Part 4"""

    # Use \n anchor to avoid matching TOC
    part4_match = re.search(r'Part\s*4\n(.*?)(?=Part\s*5|\Z)', all_text, re.DOTALL | re.IGNORECASE)
    if not part4_match:
        print("Could not find Part 4")
        return None

    part4_text = part4_match.group(1)
    part4_text = clean_extracted_text(part4_text)

    # Extract title (first line after "Part 4")
    lines = part4_text.split('\n')
    title = lines[0].strip() if lines else "Adjustments to Installed Capacity Estimate"

    print(f"Part 4: {title}")
    print(f"Text length: {len(part4_text)} characters")

    # Find all Conditions within Part 4 (numbered sections 5, 6, 7)
    # Pattern: "5. TITLE", "6. TITLE", etc.
    condition_matches = []

    # Find lines starting with "X. " followed by ALL CAPS title
    lines = part4_text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Match "X. ALL CAPS TITLE" pattern
        match = re.match(r'^(\d+)\.\s+([A-Z][A-Z\s:\-]*)$', line)
        if match:
            cond_num = match.group(1)
            cond_title = match.group(2).strip()

            # Check if title continues on next line (all caps)
            j = i + 1
            while j < len(lines) and lines[j].strip() and re.match(r'^[A-Z\s:\-]+$', lines[j].strip()):
                cond_title += ' ' + lines[j].strip()
                j += 1

            start_pos = part4_text.find(line, i > 0 and part4_text.find('\n'.join(lines[:i])) or 0)

            condition_matches.append((start_pos, cond_num, cond_title, i))
            i = j
        else:
            i += 1

    conditions = []
    all_nodes = {}

    for i, (start_pos, cond_num, cond_title, line_idx) in enumerate(condition_matches):
        # End position is start of next condition or end of Part 4
        if i + 1 < len(condition_matches):
            end_pos = condition_matches[i + 1][0]
        else:
            end_pos = len(part4_text)

        cond_text = part4_text[start_pos:end_pos].strip()

        # Skip the title lines when extracting content
        # Find first X.X pattern for actual content start
        content_match = re.search(r'\n\d+\.\d+\s+', cond_text)
        if content_match:
            content_start = content_match.start()
        else:
            content_start = len(cond_title) + 10
        cond_id = f"part4.c{cond_num}"

        # Find sections within this condition (5.1, 5.2, etc.)
        section_pattern = r'(\d+\.\d+)\s+(.*?)(?=\n\d+\.\d+|\Z)'
        section_matches = list(re.finditer(section_pattern, cond_text, re.DOTALL))

        sections = []
        for j, sect_match in enumerate(section_matches):
            sect_num = sect_match.group(1)
            sect_content = sect_match.group(2).strip()
            sect_id = f"{cond_id}.s{sect_num.replace('.', '_')}"

            # Check for nested subsections
            if re.search(r'\([A-Z]\)', sect_content):
                subsection_nodes = parse_nested_subsections(sect_content, sect_id)
                all_nodes.update(subsection_nodes)

                # Count subsections
                subsection_count = len([k for k in subsection_nodes.keys() if k.startswith(sect_id)])

                sections.append({
                    "id": sect_id,
                    "parent_id": cond_id,
                    "type": "section",
                    "section_number": sect_num,
                    "text_for_embedding": clean_text_for_embedding(sect_content),
                    "references": extract_references(sect_content),
                    "raw_text": sect_content,
                    "subsection_count": subsection_count
                })
            else:
                sections.append({
                    "id": sect_id,
                    "parent_id": cond_id,
                    "type": "section",
                    "section_number": sect_num,
                    "text_for_embedding": clean_text_for_embedding(sect_content),
                    "references": extract_references(sect_content),
                    "raw_text": sect_content
                })

        # Create the condition node
        all_nodes[cond_id] = {
            "id": cond_id,
            "parent_id": "part4",
            "type": "condition",
            "condition_number": cond_num,
            "title": cond_title,
            "text_for_embedding": clean_text_for_embedding(cond_title),
            "references": [],
            "raw_text": cond_text[:200] + "..." if len(cond_text) > 200 else cond_text,
            "sections": sections,
            "section_count": len(sections)
        }

        conditions.append({
            "condition_number": cond_num,
            "title": cond_title,
            "section_count": len(sections),
            "section_range": f"{sections[0]['section_number']}" if sections else "N/A"
        })

        print(f"  Condition {cond_num}: {cond_title[:50]}... ({len(sections)} sections)")

    # Build the result structure
    result = {
        "metadata": {
            "document": "Low-Carbon Hydrogen Agreement Standard Terms and Conditions",
            "part": 4,
            "title": title,
            "parse_date": __import__('datetime').datetime.now().isoformat(),
            "parser_version": "2.0.0"
        },
        "summary": {
            "condition_count": len(conditions),
            "total_sections": sum(c["section_count"] for c in conditions),
            "total_nodes": len(all_nodes),
            "conditions": conditions
        },
        "part": {
            "number": 4,
            "title": title,
            "conditions": conditions,
            "nodes": all_nodes
        }
    }

    return result

# ============================================
# MAIN EXECUTION
# ============================================

def main():
    """Parse Part 4 and save results"""

    # Load text from cache
    CACHE_FILE = "lcha_text_cache.json"
    if not os.path.exists(CACHE_FILE):
        print(f"Error: {CACHE_FILE} not found. Run main parser first.")
        return

    with open(CACHE_FILE, 'r') as f:
        all_text = json.load(f)['text']

    print(f"Loaded text: {len(all_text)} characters\n")

    # Extract Part 4
    part4_result = extract_part4(all_text)

    if part4_result:
        # Save Part 4 only
        with open('part4_structure.json', 'w') as f:
            json.dump(part4_result, f, indent=2)
        print(f"\nSaved Part 4 to part4_structure.json")

        # Print summary
        print(f"\n=== PART 4 SUMMARY ===")
        print(f"Conditions: {part4_result['summary']['condition_count']}")
        print(f"Total sections: {part4_result['summary']['total_sections']}")
        print(f"Total nodes: {part4_result['summary']['total_nodes']}")

        print(f"\nConditions:")
        for cond in part4_result['summary']['conditions']:
            print(f"  Condition {cond['condition_number']}: {cond['title'][:50]}...")
            print(f"    Sections: {cond['section_count']} ({cond['section_range']})")

        # Merge with existing lcha_structure.json if it exists
        if os.path.exists('lcha_structure.json'):
            with open('lcha_structure.json', 'r') as f:
                lcha = json.load(f)

            # Update parts array
            if "parts" not in lcha:
                lcha["parts"] = []

            # Remove existing Part 4 if present
            lcha["parts"] = [p for p in lcha["parts"] if p.get("number") != 4]

            # Add new Part 4
            lcha["parts"].append(part4_result["part"])
            lcha["metadata"]["last_updated"] = __import__('datetime').datetime.now().isoformat()

            with open('lcha_structure.json', 'w') as f:
                json.dump(lcha, f, indent=2)
            print(f"\nMerged with lcha_structure.json")
        else:
            # Create new lcha_structure.json
            lcha = {
                "metadata": {
                    "document": "Low-Carbon Hydrogen Agreement Standard Terms and Conditions",
                    "last_updated": __import__('datetime').datetime.now().isoformat()
                },
                "parts": [part4_result["part"]]
            }
            with open('lcha_structure.json', 'w') as f:
                json.dump(lcha, f, indent=2)
            print(f"\nCreated lcha_structure.json with Part 4")

if __name__ == "__main__":
    main()
