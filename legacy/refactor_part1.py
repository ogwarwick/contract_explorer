"""
Part 1 Schema Refactor
Updates Part 1 structure to match the new schema used in Parts 2-4:
- Add id, parent_id, type, classification, term, text_for_embedding, references
"""

import json
import re

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
    """Extract cross-references to Conditions, Annexes, Schedules, and defined terms"""
    references = []
    # Condition references
    cond_refs = re.findall(r'Condition\s+(\d+(?:\.\d+)?)', text)
    for ref in cond_refs:
        references.append({"type": "condition", "target": ref})
    # Annex references
    annex_refs = re.findall(r'Annex\s+(\d+(?:\.\w+)?)', text)
    for ref in annex_refs:
        references.append({"type": "annex", "target": ref})
    # Schedule references
    schedule_refs = re.findall(r'Schedule\s+(\d+(?:\.\w+)?)', text)
    for ref in schedule_refs:
        references.append({"type": "schedule", "target": ref})
    # Part references
    part_refs = re.findall(r'Part\s+(\d+)', text)
    for ref in part_refs:
        references.append({"type": "part", "target": ref})
    return references

def normalize_text_whitespace(text):
    """Normalize whitespace: collapse multiple spaces/newlines to single space"""
    return re.sub(r'\s+', ' ', text).strip()

def clean_text_for_embedding(text):
    """Clean text for embedding generation"""
    text = normalize_text_whitespace(text)
    text = re.sub(r'^\d+\.\d+\s+', '', text)
    return text

def slugify_term(term):
    """Convert term name to slug for ID generation"""
    # Replace special chars with underscores
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', term)
    # Remove leading/trailing underscores
    slug = slug.strip('_')
    return slug

# ============================================
# REFACTOR FUNCTIONS
# ============================================

def refactor_definition(term, data, parent_id="part1.s1_1"):
    """Refactor a single definition to new schema"""
    # Create new entry
    new_data = {}

    # Generate ID
    term_slug = slugify_term(term)
    new_data["id"] = f"{parent_id}.def.{term_slug}"
    new_data["parent_id"] = parent_id

    # Rename type -> classification, add type
    old_type = data.get("type", "simple")
    new_data["classification"] = old_type
    new_data["type"] = "definition"

    # Add term
    new_data["term"] = term

    # Generate text_for_embedding
    raw_text = data.get("raw_text", "")
    # Extract the term from the raw text for cleaner embedding
    # Format: "Term" means... or "Term" has the meaning...
    if '"means' in raw_text:
        embedding_text = raw_text.split('means', 1)[-1].strip()
        embedding_text = f"{term} means {embedding_text}"
    elif 'has the meaning' in raw_text:
        embedding_text = raw_text
    else:
        embedding_text = f"{term} {raw_text}"
    new_data["text_for_embedding"] = clean_text_for_embedding(embedding_text)

    # Extract references
    new_data["references"] = extract_references(raw_text)

    # Copy existing fields
    new_data["parsed"] = data.get("parsed", {})
    new_data["raw_text"] = raw_text

    return new_data

def refactor_section_1_1(section_data, parent_id="part1"):
    """Refactor section 1.1 (Definitions)"""
    new_section = {
        "id": "part1.s1_1",
        "parent_id": parent_id,
        "type": "section",
        "section_number": "1.1",
        "title": "Definitions",
        "definitions": {}
    }

    definitions = section_data.get("definitions", {})
    for term, data in definitions.items():
        new_section["definitions"][term] = refactor_definition(term, data, "part1.s1_1")

    return new_section

def refactor_other_section(section_num, section_data, parent_id="part1"):
    """Refactor sections 1.2-1.15"""
    section_id = f"part1.s{section_num.replace('.', '_')}"

    new_section = {
        "id": section_id,
        "parent_id": parent_id,
        "type": "section",
        "section_number": section_num,
    }

    # Copy title if exists
    if "title" in section_data:
        new_section["title"] = section_data["title"]

    # Get content for text_for_embedding and references
    content = section_data.get("content", section_data)

    if isinstance(content, dict) and "text" in content:
        # Simple text section
        raw_text = content["text"]
        new_section["text_for_embedding"] = clean_text_for_embedding(raw_text)
        new_section["references"] = extract_references(raw_text)
        new_section["parsed"] = content
    elif isinstance(content, dict) and ("intro" in content or "subsections" in content):
        # Nested structure
        new_section["parsed"] = content
        # Build text from intro and subsections
        text_parts = []
        if "intro" in content:
            text_parts.append(content["intro"])
        if "subsections" in content:
            for key, value in content["subsections"].items():
                if isinstance(value, dict) and "intro" in value:
                    text_parts.append(value["intro"])
                else:
                    text_parts.append(str(value))
        combined_text = " ".join(text_parts)
        new_section["text_for_embedding"] = clean_text_for_embedding(combined_text)
        new_section["references"] = extract_references(combined_text)
    else:
        # Fallback
        new_section["text_for_embedding"] = ""
        new_section["references"] = []
        new_section["parsed"] = content

    # Copy any other fields
    for key, value in section_data.items():
        if key not in new_section:
            new_section[key] = value

    return new_section

def refactor_part1(input_file, output_file):
    """Refactor entire Part 1 structure"""

    print(f"Loading {input_file}...")
    with open(input_file, 'r') as f:
        data = json.load(f)

    print("Refactoring Part 1 structure...")

    # Create new structure
    new_data = {
        "metadata": data.get("metadata", {}),
        "summary": data.get("summary", {}),
        "parts": {
            "1": {
                "id": "part1",
                "parent_id": None,
                "type": "part",
                "part_number": 1,
                "title": data.get("part", {}).get("title", "INTERPRETATION AND CONSTRUCTION"),
                "sections": {}
            }
        }
    }

    part = data.get("part", {})
    sections = part.get("sections", {})

    # Refactor section 1.1 (Definitions)
    if "1.1" in sections:
        print("  Refactoring section 1.1 (Definitions)...")
        new_data["parts"]["1"]["sections"]["1.1"] = refactor_section_1_1(sections["1.1"], "part1")

        # Count definitions
        def_count = len(new_data["parts"]["1"]["sections"]["1.1"]["definitions"])
        print(f"    Updated {def_count} definitions")

    # Refactor sections 1.2-1.15
    for section_num in sorted(sections.keys()):
        if section_num == "1.1":
            continue
        print(f"  Refactoring section {section_num}...")
        new_data["parts"]["1"]["sections"][section_num] = refactor_other_section(
            section_num, sections[section_num], "part1"
        )

    # Update metadata
    new_data["metadata"]["parser_version"] = "2.0.0"
    new_data["metadata"]["last_updated"] = __import__('datetime').datetime.now().isoformat()
    new_data["metadata"]["schema_version"] = "2.0"

    # Save output
    print(f"Saving to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(new_data, f, indent=2)

    print("Done!")

    # Validation stats
    print("\n=== VALIDATION ===")
    defs = new_data["parts"]["1"]["sections"]["1.1"]["definitions"]
    with_id = sum(1 for d in defs.values() if "id" in d)
    with_embedding = sum(1 for d in defs.values() if "text_for_embedding" in d)
    with_refs = sum(1 for d in defs.values() if "references" in d)
    with_refs_nonempty = sum(1 for d in defs.values() if d.get("references") and len(d.get("references", [])) > 0)

    print(f"Definitions: {len(defs)}")
    print(f"  With id: {with_id}")
    print(f"  With text_for_embedding: {with_embedding}")
    print(f"  With references array: {with_refs}")
    print(f"  With non-empty references: {with_refs_nonempty}")

    return new_data

# ============================================
# MAIN EXECUTION
# ============================================

if __name__ == "__main__":
    import os

    INPUT_FILE = "part1_structure.json"
    OUTPUT_FILE = "part1_structure.json"

    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found!")
        exit(1)

    refactor_part1(INPUT_FILE, OUTPUT_FILE)
