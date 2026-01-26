import pdfplumber
import re
import json
import os

PDF_FILE = "low-carbon-hydrogen-agreement-standard-terms-and-conditions.pdf"
CACHE_FILE = "lcha_text_cache.json"

# ============================================
# STEP 1: LOAD OR EXTRACT TEXT
# ============================================

def load_or_extract_text():
    """Load from cache if exists, otherwise extract from PDF"""
    if os.path.exists(CACHE_FILE):
        print("Loading from cache...")
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)['text']
    else:
        print("Extracting from PDF...")
        all_text = ""
        with pdfplumber.open(PDF_FILE) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text += text + "\n"
        
        with open(CACHE_FILE, 'w') as f:
            json.dump({'text': all_text}, f)
        print("Saved to cache.")
        return all_text

# ============================================
# STEP 2: SUBSECTION PARSING FUNCTIONS
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
        numeral = f"({match.group(1)})"
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

def parse_formula(content):
    """Parse formula definitions with 'where:' notation

    Formula definitions in LCHA have the pattern:
    - Description/formula expression
    - where:
    - Variable definitions (often using mathematical Unicode symbols)

    The variable definitions often use '=' followed by description text.
    """
    result = {"formula": "", "variables": {}, "raw_where_clause": ""}

    parts = re.split(r'\bwhere\s*:', content, flags=re.IGNORECASE, maxsplit=1)

    if len(parts) >= 2:
        result["formula"] = parts[0].strip()
        where_content = parts[1].strip()
        result["raw_where_clause"] = where_content

        # Try to extract variable definitions
        # Pattern: look for lines that start with "= " which indicate a variable definition
        # The variable name is typically on the previous line (Unicode math symbols)
        lines = where_content.split('\n')
        variables = []
        current_var = None
        current_def_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check if line starts with "=" - this is a variable definition
            if line.startswith('= '):
                if current_var and current_def_lines:
                    variables.append((current_var, ' '.join(current_def_lines)))
                current_var = None
                current_def_lines = [line[2:].strip()]  # Remove "= "
            # Check if line contains an isolated "=" (variable name = definition on same line)
            elif re.match(r'^[^\s=]+\s*=\s*.+', line):
                if current_var and current_def_lines:
                    variables.append((current_var, ' '.join(current_def_lines)))
                match = re.match(r'^([^\s=]+)\s*=\s*(.+)', line)
                if match:
                    variables.append((match.group(1), match.group(2)))
                current_var = None
                current_def_lines = []
            # Check if this looks like a variable name (short, possibly with subscripts)
            elif len(line) < 30 and not line.startswith('(') and not line[0].islower():
                if current_var and current_def_lines:
                    variables.append((current_var, ' '.join(current_def_lines)))
                current_var = line
                current_def_lines = []
            else:
                # Continuation of current definition
                current_def_lines.append(line)

        # Don't forget the last variable
        if current_var and current_def_lines:
            variables.append((current_var, ' '.join(current_def_lines)))
        elif current_def_lines and not current_var:
            # Definition without clear variable name
            variables.append(("_unnamed", ' '.join(current_def_lines)))

        # Store as dict
        for var_name, var_def in variables:
            result["variables"][var_name] = var_def

    else:
        result["formula"] = content.strip()

    return result

def parse_nested_definition(content):
    """Parse nested structures like (A)(i)(a)"""
    result = {"intro": "", "subsections": {}}
    
    intro_match = re.match(r'^(.*?)(?=\([A-Z]\))', content, re.DOTALL)
    if intro_match:
        result["intro"] = intro_match.group(1).strip()
    
    alpha_pattern = r'\(([A-Z])\)\s*(.*?)(?=\([A-Z]\)|$)'
    alpha_matches = re.finditer(alpha_pattern, content, re.DOTALL)
    
    for match in alpha_matches:
        letter = f"({match.group(1)})"
        section_content = match.group(2).strip()
        
        if re.search(r'\([ivxlc]+\)', section_content, re.IGNORECASE):
            roman_subs = {}
            roman_pattern = r'\(([ivxlc]+)\)\s*(.*?)(?=\([ivxlc]+\)|$)'
            roman_matches = re.finditer(roman_pattern, section_content, re.DOTALL | re.IGNORECASE)
            
            for rm in roman_matches:
                numeral = f"({rm.group(1)})"
                roman_content = rm.group(2).strip()
                
                if re.search(r'\([a-z]\)', roman_content):
                    lower_subs = parse_lowercase_subsections(roman_content)
                    lower_intro = re.match(r'^(.*?)(?=\([a-z]\))', roman_content, re.DOTALL)
                    roman_subs[numeral] = {
                        "intro": lower_intro.group(1).strip() if lower_intro else "",
                        "subsections": lower_subs
                    }
                else:
                    roman_subs[numeral] = roman_content
            
            alpha_intro = re.match(r'^(.*?)(?=\([ivxlc]+\))', section_content, re.DOTALL | re.IGNORECASE)
            result["subsections"][letter] = {
                "intro": alpha_intro.group(1).strip() if alpha_intro else "",
                "subsections": roman_subs
            }
        else:
            result["subsections"][letter] = section_content
    
    return result

def classify_definition(content):
    """Classify a definition by its structure

    Types:
    - reference: Points to another location (Annex, Condition, Schedule)
    - formula: Contains 'where:' notation with variable definitions
    - nested_deep: Has three levels (A)(i)(a)
    - nested_subsections: Has two levels (A)(i)
    - alphabetic: Has one level (A), (B), etc.
    - simple: Plain text definition
    """
    # Check for cross-references first
    if re.search(r'has the meaning given to that term in', content):
        return "reference"
    elif re.search(r'\bwhere\s*:', content, re.IGNORECASE):
        return "formula"
    elif re.search(r'\([A-Z]\)\s*.*?\([ivx]+\)\s*.*?\([a-z]\)', content, re.DOTALL):
        return "nested_deep"
    elif re.search(r'\([A-Z]\)\s*.*?\([ivx]+\)', content, re.DOTALL):
        return "nested_subsections"
    elif re.search(r'\([A-Z]\)', content):
        return "alphabetic"
    else:
        return "simple"

def parse_definition(content, def_type):
    """Parse a definition based on its type"""
    if def_type == "reference":
        # Extract the reference location
        ref_match = re.search(r'has the meaning given to that term in\s+(.+)', content, re.DOTALL)
        if ref_match:
            location = ref_match.group(1).strip()
            return {"reference_to": location}
        return {"text": content}
    elif def_type == "formula":
        return parse_formula(content)
    elif def_type in ["nested_deep", "nested_subsections"]:
        return parse_nested_definition(content)
    elif def_type == "alphabetic":
        intro_match = re.match(r'^(.*?)(?=\([A-Z]\))', content, re.DOTALL)
        intro = intro_match.group(1).strip() if intro_match else ""
        return {
            "intro": intro,
            "subsections": parse_alphabetic_subsections(content)
        }
    else:
        return {"text": content}

# ============================================
# STEP 3: SECTION PARSING FUNCTIONS
# ============================================

def parse_definitions_section(text):
    """Parse section 1.1 Definitions

    Strategy: Find all "Term" positions, then extract text from each term
    to the next term. This captures the full definition including nested
    structures like (A), (i), (a).
    """
    # Find all term positions - each definition starts with "Term" means/has the meaning
    term_pattern = r'"([^"]+)"\s*(means|has the meaning)'
    term_matches = list(re.finditer(term_pattern, text))

    definitions = {}
    for i, match in enumerate(term_matches):
        term = match.group(1).strip()
        start_pos = match.start()

        # End position is start of next term, or end of section
        if i + 1 < len(term_matches):
            end_pos = term_matches[i + 1].start()
        else:
            end_pos = len(text)

        # Extract full definition text
        full_text = text[start_pos:end_pos].strip()

        # Remove trailing semicolon if present (common delimiter)
        if full_text.endswith(';'):
            full_text = full_text[:-1].strip()

        # Extract the body (everything after the term name and verb)
        # Pattern: "Term" means X  OR  "Term" has the meaning given to that term in X
        body_match = re.match(r'"[^"]+"\s*(means|has the meaning given to that term in)\s*', full_text)
        if body_match:
            verb = body_match.group(1)
            body = full_text[body_match.end():].strip()
            # For "has the meaning" refs, include the reference location
            if verb == "has the meaning given to that term in":
                body = "has the meaning given to that term in " + body
        else:
            body = full_text

        # Classify and parse
        def_type = classify_definition(body)
        parsed = parse_definition(body, def_type)

        definitions[term] = {
            "type": def_type,
            "raw_text": full_text,
            "parsed": parsed
        }

    return definitions

def parse_interpretation_section(text):
    """Parse section 1.2 Interpretation"""
    # Pattern: 1.2.X or (A), (B) etc. followed by content
    clauses = {}
    
    # Look for numbered clauses like 1.2.1, 1.2.2
    clause_pattern = r'(1\.2\.(\d+))\s*(.*?)(?=1\.2\.\d+|$)'
    matches = re.finditer(clause_pattern, text, re.DOTALL)
    
    for match in matches:
        clause_num = match.group(1)
        content = match.group(3).strip()
        
        # Check if content has subsections
        if re.search(r'\([A-Z]\)', content):
            clauses[clause_num] = parse_nested_definition(content)
        else:
            clauses[clause_num] = {"text": content}
    
    # If no numbered clauses found, try alphabetic
    if not clauses:
        if re.search(r'\([A-Z]\)', text):
            return parse_nested_definition(text)
        else:
            return {"text": text.strip()}
    
    return clauses

def parse_section(section_num, text):
    """Parse a section based on its number"""
    if section_num == "1.1":
        return {
            "title": "Definitions",
            "definitions": parse_definitions_section(text)
        }
    elif section_num == "1.2":
        return {
            "title": "Interpretation",
            "clauses": parse_interpretation_section(text)
        }
    else:
        # Generic section parsing
        if re.search(r'\([A-Z]\)', text):
            return parse_nested_definition(text)
        else:
            return {"text": text.strip()}

# ============================================
# STEP 4: PART 1 EXTRACTION
# ============================================

def extract_part1(all_text):
    """Extract and parse Part 1 completely

    Part 1 structure:
    - Section 1.1: Definitions (bulk of the content, ~915 terms)
    - Sections 1.2-1.15: Interpretation clauses
    """

    # Extract Part 1 text - document uses "Part 1" not "PART 1"
    part1_match = re.search(r'(Part\s+1\n.*?)(?=Part\s+2\n)', all_text, re.DOTALL)
    if not part1_match:
        print("Could not find Part 1")
        return None

    part1_text = part1_match.group(1)
    print(f"Part 1 extracted: {len(part1_text)} characters")

    sections = {}

    # Find where Interpretation section begins (marks end of definitions)
    interp_match = re.search(r'Interpretation\n(1\.2)', part1_text)
    if interp_match:
        definitions_end = interp_match.start()
        interp_start = interp_match.start()
    else:
        # Fallback: find 1.2 directly
        section_12 = re.search(r'\n1\.2\s+', part1_text)
        definitions_end = section_12.start() if section_12 else len(part1_text)
        interp_start = definitions_end

    # Parse Section 1.1 - Definitions
    definitions_text = part1_text[:definitions_end]
    print(f"Definitions section: {len(definitions_text)} characters")
    sections["1.1"] = {
        "title": "Definitions",
        "definitions": parse_definitions_section(definitions_text)
    }

    # Parse Interpretation sections (1.2 onwards)
    interp_text = part1_text[interp_start:]
    interp_sections = parse_interpretation_sections(interp_text)
    sections.update(interp_sections)

    return {
        "part_number": 1,
        "title": "INTERPRETATION AND CONSTRUCTION",
        "sections": sections
    }


def parse_interpretation_sections(text):
    """Parse interpretation sections 1.2 through 1.15"""
    sections = {}

    # Find all section headers: 1.2, 1.3, etc.
    section_pattern = r'\n(1\.(\d+))\s+'
    matches = list(re.finditer(section_pattern, text))

    for i, match in enumerate(matches):
        section_num = match.group(1)
        start = match.end()

        # End is start of next section or end of text
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(text)

        section_text = text[start:end].strip()

        # Get first line as title hint
        first_line = section_text.split('\n')[0] if section_text else ""

        # Parse content - check for subsections
        if re.search(r'\([A-Z]\)', section_text):
            parsed = parse_nested_definition(section_text)
        else:
            parsed = {"text": section_text}

        sections[section_num] = {
            "title": first_line[:80] + "..." if len(first_line) > 80 else first_line,
            "content": parsed
        }

    return sections

# ============================================
# STEP 5: MAIN EXECUTION
# ============================================

def main():
    # Load text
    all_text = load_or_extract_text()
    print(f"Total characters: {len(all_text)}")

    # Extract and parse Part 1
    part1 = extract_part1(all_text)

    if part1:
        # Count definitions by type
        type_counts = {}
        if "1.1" in part1["sections"] and "definitions" in part1["sections"]["1.1"]:
            definitions = part1["sections"]["1.1"]["definitions"]
            for term, data in definitions.items():
                t = data["type"]
                type_counts[t] = type_counts.get(t, 0) + 1

            print(f"\nTotal definitions: {len(definitions)}")
            print(f"By type: {type_counts}")

        # Create output with metadata
        output = {
            "metadata": {
                "document": "Low-Carbon Hydrogen Agreement Standard Terms and Conditions",
                "source_file": PDF_FILE,
                "parse_date": __import__('datetime').datetime.now().isoformat(),
                "parser_version": "1.0.0"
            },
            "summary": {
                "total_definitions": len(definitions) if "1.1" in part1["sections"] else 0,
                "definition_types": type_counts,
                "sections": list(part1["sections"].keys())
            },
            "part": part1
        }

        # Save to JSON
        with open('part1_structure.json', 'w') as f:
            json.dump(output, f, indent=2)
        print("\nSaved to part1_structure.json")

        # Print sample
        print("\n--- Sample definitions ---")
        if "1.1" in part1["sections"] and "definitions" in part1["sections"]["1.1"]:
            for i, (term, data) in enumerate(list(part1["sections"]["1.1"]["definitions"].items())[:5]):
                print(f"\n{i+1}. \"{term}\" [{data['type']}]")
                print(json.dumps(data["parsed"], indent=2)[:300])

if __name__ == "__main__":
    main()
