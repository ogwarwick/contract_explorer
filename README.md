# LCHA Parser

Parser for the Low-Carbon Hydrogen Agreement (LCHA) Standard Terms and Conditions PDF document. Extracts legal document structure into a nested JSON format suitable for semantic enrichment.

## Current Status

**Part 1 (Definitions & Interpretation): Complete**

- 915 definitions parsed and classified
- 14 interpretation clauses (1.2-1.15) structured
- Output: `part1_structure.json`

## Definition Types

| Type | Count | Description |
|------|-------|-------------|
| `reference` | 435 | Cross-references to other sections/annexes |
| `simple` | 417 | Plain text definitions |
| `alphabetic` | 35 | Single-level (A), (B) structure |
| `nested_deep` | 13 | Three-level (A)(i)(a) structure |
| `nested_subsections` | 9 | Two-level (A)(i) structure |
| `formula` | 6 | Definitions with `where:` variable notation |

## Usage

```bash
# Ensure you have the PDF in the project root
# Run the parser
python "from PyPDF2 import Pdfreader.py"
```

## Output Structure

```json
{
  "metadata": {
    "document": "Low-Carbon Hydrogen Agreement Standard Terms and Conditions",
    "source_file": "...",
    "parse_date": "...",
    "parser_version": "1.0.0"
  },
  "summary": {
    "total_definitions": 915,
    "definition_types": {...},
    "sections": ["1.1", "1.2", ...]
  },
  "part": {
    "part_number": 1,
    "title": "INTERPRETATION AND CONSTRUCTION",
    "sections": {
      "1.1": { "title": "Definitions", "definitions": {...} },
      "1.2": { "title": "...", "content": {...} }
    }
  }
}
```

## Requirements

- Python 3.9+
- pdfplumber

```bash
pip install pdfplumber
```

## Files

- `from PyPDF2 import Pdfreader.py` - Main parser script
- `lcha_text_cache.json` - Cached PDF text extraction
- `part1_structure.json` - Parsed Part 1 output

## Known Limitations

1. Some definitions lost `(A)`, `(B)` markers during PDF extraction
2. Formula variable parsing is imperfect due to Unicode math symbols
3. PDF page headers/footers occasionally appear in text

## Next Steps

- Parse Parts 2-14
- Build cross-reference tracker
- Integrate with Kanon 2 Enricher
