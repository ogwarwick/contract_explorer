"""
Part 5 Parser for LCHA Document
Extracts Part 5 with schema: id, parent_id, type, text_for_embedding, references, raw_text
"""

import json
import re
import os

# ============================================
# HELPER FUNCTIONS
# ============================================

def clean_extracted_text(text):
    """Remove page numbers and draft headers from text"""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        if re.match(r'^\d{1,3}$', line.strip()):
            continue
        if re.match(r'^DRAFT:\s*.*$', line.strip()):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)

def extract_references(text):
    """Extract cross-references to Conditions, Annexes, Schedules"""
    references = []
    cond_refs = re.findall(r'Condition\s+(\d+(?:\.\d+)?)', text)
    for ref in cond_refs:
        references.append({"type": "condition", "target": ref})
    annex_refs = re.findall(r'Annex\s+(\d+(?:\.\w+)?)', text)
    for ref in annex_refs:
        references.append({"type": "annex", "target": ref})
    schedule_refs = re.findall(r'Schedule\s+(\d+(?:\.\w+)?)', text)
    for ref in schedule_refs:
        references.append({"type": "schedule", "target": ref})
    return references

def normalize_text_whitespace(text):
    """Normalize whitespace: collapse multiple spaces/newlines to single space"""
    return re.sub(r'\s+', ' ', text).strip()

def clean_text_for_embedding(text):
    """Clean text for embedding generation"""
    text = normalize_text_whitespace(text)
    text = re.sub(r'^\d+\.\d+\s+', '', text)
    return text

def parse_formula(content):
    """Parse formula definitions with 'where:' notation"""
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

def parse_nested_subsections(content, parent_id):
    """Parse nested (A)(i)(a) structures with full node schema"""
    nodes = {}

    alpha_pattern = r'\(([A-Z])\)\s*(.*?)(?=\([A-Z]\)|$)'
    alpha_matches = list(re.finditer(alpha_pattern, content, re.DOTALL))

    for match in alpha_matches:
        letter = match.group(1)
        section_id = f"{parent_id}({letter})"
        section_content = match.group(2).strip()

        if re.search(r'\([ivxlc]+\)', section_content, re.IGNORECASE):
            subsections = {}
            roman_pattern = r'\(([ivxlc]+)\)\s*(.*?)(?=\([ivxlc]+\)|$)'
            roman_matches = list(re.finditer(roman_pattern, section_content, re.DOTALL | re.IGNORECASE))

            for rm in roman_matches:
                roman = rm.group(1).lower()
                roman_id = f"{section_id}({roman})"
                roman_content = rm.group(2).strip()

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
# PART 5 EXTRACTION
# ============================================

def extract_part5(all_text):
    """Extract and parse Part 5"""

    part5_match = re.search(r'Part\s*5\n(.*?)(?=Part\s*6|\Z)', all_text, re.DOTALL | re.IGNORECASE)
    if not part5_match:
        print("Could not find Part 5")
        return None

    part5_text = part5_match.group(1)
    part5_text = clean_extracted_text(part5_text)

    lines = part5_text.split('\n')
    title = "Payment calculations"
    for line in lines[:5]:
        if line.strip() and not re.match(r'^\d+\.\s+', line.strip()):
            title = line.strip()
            break

    print(f"Part 5: {title}")
    print(f"Text length: {len(part5_text)} characters")

    # Find Conditions within Part 5 (Condition 8 and 9)
    condition_matches = []
    lines = part5_text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        match = re.match(r'^(\d+)\.\s+([A-Z][A-Z\s:\-]*)$', line)
        if match:
            cond_num = match.group(1)
            cond_title = match.group(2).strip()

            j = i + 1
            while j < len(lines) and lines[j].strip() and re.match(r'^[A-Z\s:\-]+$', lines[j].strip()):
                cond_title += ' ' + lines[j].strip()
                j += 1

            start_pos = part5_text.find(line, i > 0 and part5_text.find('\n'.join(lines[:i])) or 0)
            condition_matches.append((start_pos, cond_num, cond_title, i))
            i = j
        else:
            i += 1

    conditions = []
    all_nodes = {}

    for i, (start_pos, cond_num, cond_title, line_idx) in enumerate(condition_matches):
        if i + 1 < len(condition_matches):
            end_pos = condition_matches[i + 1][0]
        else:
            end_pos = len(part5_text)

        cond_text = part5_text[start_pos:end_pos].strip()
        cond_id = f"part5.c{cond_num}"

        # Special handling for Condition 8 (Definitions: Part 5)
        if cond_num == "8":
            # Condition 8 is a definitions section - parse differently
            definitions = parse_part5_definitions(cond_text)
            all_nodes.update(definitions)

            sections = [{
                "id": f"{cond_id}.s8_all",
                "parent_id": cond_id,
                "type": "section",
                "section_number": "8",
                "title": "DEFINITIONS: PART 5",
                "text_for_embedding": clean_text_for_embedding(cond_text[:500]),
                "references": extract_references(cond_text),
                "raw_text": cond_text[:500] + "..."
            }]
        else:
            # Regular condition with numbered sections
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

                    subsection_count = len([k for k in subsection_nodes.keys() if k.startswith(sect_id)])

                    # Check for formula
                    if re.search(r'\bwhere\s*:', sect_content, re.IGNORECASE):
                        section_type = "formula"
                    else:
                        section_type = "nested"

                    sections.append({
                        "id": sect_id,
                        "parent_id": cond_id,
                        "type": section_type,
                        "section_number": sect_num,
                        "text_for_embedding": clean_text_for_embedding(sect_content),
                        "references": extract_references(sect_content),
                        "raw_text": sect_content,
                        "subsection_count": subsection_count
                    })
                else:
                    section_type = "simple"
                    if re.search(r'\bwhere\s*:', sect_content, re.IGNORECASE):
                        section_type = "formula"

                    sections.append({
                        "id": sect_id,
                        "parent_id": cond_id,
                        "type": section_type,
                        "section_number": sect_num,
                        "text_for_embedding": clean_text_for_embedding(sect_content),
                        "references": extract_references(sect_content),
                        "raw_text": sect_content
                    })

        all_nodes[cond_id] = {
            "id": cond_id,
            "parent_id": "part5",
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
            "section_range": f"{sections[0].get('section_number', cond_num)}" if sections else "N/A"
        })

        print(f"  Condition {cond_num}: {cond_title[:50]}... ({len(sections)} sections)")

    # Build the result structure
    result = {
        "metadata": {
            "document": "Low-Carbon Hydrogen Agreement Standard Terms and Conditions",
            "part": 5,
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
            "number": 5,
            "title": title,
            "conditions": conditions,
            "nodes": all_nodes
        }
    }

    return result

def parse_part5_definitions(cond_text):
    """Parse Condition 8 definitions in Part 5"""
    nodes = {}
    parent_id = "part5.c8"

    # Pattern: "Term" means... or "Term" has the meaning...
    term_pattern = r'"([^"]+)"\s*(means|has the meaning)'
    term_matches = list(re.finditer(term_pattern, cond_text))

    for i, match in enumerate(term_matches):
        term = match.group(1).strip()
        start_pos = match.start()

        if i + 1 < len(term_matches):
            end_pos = term_matches[i + 1].start()
        else:
            end_pos = len(cond_text)

        full_text = cond_text[start_pos:end_pos].strip()

        # Generate ID
        term_slug = re.sub(r'[^a-zA-Z0-9]+', '_', term).strip('_')
        def_id = f"{parent_id}.def.{term_slug}"

        # Determine type
        if 'where:' in full_text.lower():
            def_type = "formula"
        elif re.search(r'\([A-Z]\)', full_text):
            def_type = "alphabetic"
        else:
            def_type = "simple"

        nodes[def_id] = {
            "id": def_id,
            "parent_id": parent_id,
            "type": "definition",
            "classification": def_type,
            "term": term,
            "text_for_embedding": clean_text_for_embedding(full_text),
            "references": extract_references(full_text),
            "raw_text": full_text
        }

    return nodes

# ============================================
# MAIN EXECUTION
# ============================================

def main():
    """Parse Part 5 and save results"""

    CACHE_FILE = "lcha_text_cache.json"
    if not os.path.exists(CACHE_FILE):
        print(f"Error: {CACHE_FILE} not found. Run main parser first.")
        return

    with open(CACHE_FILE, 'r') as f:
        all_text = json.load(f)['text']

    print(f"Loaded text: {len(all_text)} characters\n")

    part5_result = extract_part5(all_text)

    if part5_result:
        # Save Part 5 only
        with open('part5_structure.json', 'w') as f:
            json.dump(part5_result, f, indent=2)
        print(f"\nSaved Part 5 to part5_structure.json")

        # Print summary
        print(f"\n=== PART 5 SUMMARY ===")
        print(f"Conditions: {part5_result['summary']['condition_count']}")
        print(f"Total sections: {part5_result['summary']['total_sections']}")
        print(f"Total nodes: {part5_result['summary']['total_nodes']}")

        print(f"\nConditions:")
        for cond in part5_result['summary']['conditions']:
            print(f"  Condition {cond['condition_number']}: {cond['title'][:50]}...")
            print(f"    Sections: {cond['section_count']} ({cond['section_range']})")

        # Merge with existing lcha_structure.json if it exists
        if os.path.exists('lcha_structure.json'):
            with open('lcha_structure.json', 'r') as f:
                lcha = json.load(f)

            if "parts" not in lcha:
                lcha["parts"] = []

            lcha["parts"] = [p for p in lcha["parts"] if p.get("number") != 5]
            lcha["parts"].append(part5_result["part"])
            lcha["metadata"]["last_updated"] = __import__('datetime').datetime.now().isoformat()

            with open('lcha_structure.json', 'w') as f:
                json.dump(lcha, f, indent=2)
            print(f"\nMerged with lcha_structure.json")
        else:
            lcha = {
                "metadata": {
                    "document": "Low-Carbon Hydrogen Agreement Standard Terms and Conditions",
                    "last_updated": __import__('datetime').datetime.now().isoformat()
                },
                "parts": [part5_result["part"]]
            }
            with open('lcha_structure.json', 'w') as f:
                json.dump(lcha, f, indent=2)
            print(f"\nCreated lcha_structure.json with Part 5")

if __name__ == "__main__":
    main()
