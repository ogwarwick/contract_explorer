# LCHA Parser

Parser for the Low-Carbon Hydrogen Agreement (LCHA) Standard Terms and Conditions PDF document. Extracts legal document structure into a canonical nested JSON format suitable for semantic enrichment.

## Project Status

**Consolidation Complete (v2.1)**

The codebase has been consolidated into a clean, maintainable structure:
- Shared utilities in `lcha_utils.py`
- Unified parser with `--part`, `--discover`, and `--all` flags
- Canonical schema v2.1 (dict-based parts)
- Legacy scripts archived in `legacy/`
- Individual part outputs in `output/`

## Parsed Parts

| Part | Title | Sections | Status |
|------|-------|----------|--------|
| 1 | INTERPRETATION AND CONSTRUCTION | 1.1-1.15 (915 definitions) | ✅ Done |
| 2 | TERM | 2.1-2.4 | ✅ Done |
| 3 | CONDITIONS PRECEDENT AND MILESTONE REQUIREMENT | Conditions 3+4, 98 sections | ✅ Done |
| 4 | ADJUSTMENTS TO INSTALLED CAPACITY ESTIMATE | 3 conditions | ✅ Done |
| 5 | PAYMENT CALCULATIONS | 9 conditions, 58 sections | ✅ Done |
| 6-14 | TBD | - | ⏳ Ready to parse |

## Quick Start

```bash
# View current statistics
python3 parse_lcha.py --stats

# Discover structure of an unarsed part
python3 parse_lcha.py --discover 6

# Parse a specific part
python3 parse_lcha.py --part 6

# Parse all remaining parts
python3 parse_lcha.py --all

# Validate current structure
python3 parse_lcha.py --validate
```

## Project Structure

```
├── lcha_utils.py              # Shared utility functions
├── parse_lcha.py              # Unified parser (main entry point)
├── migrate_schema.py          # One-time migration to v2.1
├── SCHEMA.md                  # Canonical schema v2.1 documentation
│
├── lcha_text_cache.json       # Cached PDF text extraction
├── lcha_structure.json        # Main output (canonical v2.1 format)
│
├── output/                    # Individual part outputs (for reference)
│   ├── part1_structure.json
│   ├── part2_structure.json
│   └── ...
│
└── legacy/                    # Old parser scripts (archived)
    ├── from PyPDF2 import Pdfreader.py
    ├── parse_part4.py
    └── ...
```

## Schema v2.1

All parsed parts use the canonical schema v2.1:

```json
{
  "metadata": {
    "document": "Low-Carbon Hydrogen Agreement Standard Terms and Conditions",
    "schema_version": "2.1",
    "parser_version": "2.1.0"
  },
  "parts": {
    "1": {
      "id": "part1",
      "parent_id": null,
      "type": "part",
      "number": 1,
      "title": "INTERPRETATION AND CONSTRUCTION",
      "sections": {
        "1.1": {
          "id": "part1.s1_1",
          "parent_id": "part1",
          "type": "section",
          "section_number": "1.1",
          "text_for_embedding": "...",
          "references": [...],
          "raw_text": "..."
        }
      }
    }
  }
}
```

See [SCHEMA.md](SCHEMA.md) for complete schema documentation.

## Required Node Fields

Every node must include:
- `id` - Unique identifier
- `parent_id` - Parent node ID (null for Parts)
- `type` - Node type (part, section, definition, condition, etc.)
- `text_for_embedding` - Cleaned text for vector embeddings
- `references` - Array of cross-references
- `raw_text` - Original extracted text

## ID Patterns

| Node Type | Pattern | Example |
|-----------|---------|---------|
| Part | `part{N}` | `part1`, `part5` |
| Section | `part{N}.s{X_Y}` | `part1.s1_1`, `part5.s10_3` |
| Definition | `part{N}.s{X_Y}.def.{Slug}` | `part1.s1_1.def.Acceptable_Collateral` |
| Subsection | `{parent_id}.({marker})` | `part1.s1_3.(A).(i)` |

## Definition Types (Part 1)

| Type | Count | Description |
|------|-------|-------------|
| `reference` | 435 | Cross-references to other sections/annexes |
| `simple` | 417 | Plain text definitions |
| `alphabetic` | 35 | Single-level (A), (B) structure |
| `nested_deep` | 13 | Three-level (A)(i)(a) structure |
| `nested_subsections` | 9 | Two-level (A)(i) structure |
| `formula` | 6 | Definitions with `where:` variable notation |

## Requirements

- Python 3.9+
- pdfplumber

```bash
pip install pdfplumber
```

## Known Patterns

- **Part boundary**: `PART\s*X\n` (uses `\n` anchor to avoid matching TOC)
- **Multiple Conditions per Part**: Parts can contain multiple Conditions with different section numbering
- **Section numbering**: Follows Condition number (Condition 3 → sections 3.1, 3.2...)
- **Subsection hierarchy**: (A) → (i) → (a)
- **Cross-reference patterns**: "Condition X.X", "Annex X", "Part X", "Schedule X"
- **Formulas**: `where:` notation with variable definitions

## Development Workflow

To parse a new Part (e.g., Part 6):

1. **Discover structure first:**
   ```bash
   python3 parse_lcha.py --discover 6
   ```
   This shows conditions, sections, formulas, and subsections without parsing.

2. **Parse the part:**
   ```bash
   python3 parse_lcha.py --part 6
   ```
   This adds Part 6 to `lcha_structure.json`.

3. **Validate:**
   ```bash
   python3 parse_lcha.py --validate
   ```
   Ensures schema compliance.

## Migration Notes

If you have data from an earlier schema version:

```bash
# Run the migration script
python3 migrate_schema.py

# This will:
# 1. Create a backup of lcha_structure.json
# 2. Load individual part files (part*_structure.json)
# 3. Merge into canonical v2.1 format
# 4. Validate the result
```

## License

This project is part of the LCHA document processing pipeline.
