# LCHA Parser - Canonical Schema v2.1

## Overview

This document defines the canonical schema v2.1 for the LCHA (Low-Carbon Hydrogen Agreement) parser output. All parsed Parts must conform to this schema for consistency and downstream compatibility.

## Schema Structure

```json
{
  "metadata": { ... },
  "footnotes": [ ... ],
  "parts": {
    "1": { ... },
    "2": { ... },
    ...
  }
}
```

### Decision: Dict-based vs Array-based

**Choice: Dict-based structure**

Rationale:
- Enables O(1) lookup by part number: `data["parts"]["5"]`
- Consistent with definition lookup: `data["parts"]["1"]["sections"]["1.1"]["definitions"]["Term"]`
- More intuitive for hierarchical data
- Easier to merge/update individual parts

---

## Metadata Section

```json
{
  "metadata": {
    "document": "Low-Carbon Hydrogen Agreement Standard Terms and Conditions",
    "source_file": "low-carbon-hydrogen-agreement-standard-terms-and-conditions.pdf",
    "parse_date": "2026-01-25T12:00:00Z",
    "parser_version": "2.1.0",
    "schema_version": "2.1"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `document` | string | Yes | Full document title |
| `source_file` | string | Yes | Original PDF filename |
| `parse_date` | string | Yes | ISO 8601 timestamp of parsing |
| `parser_version` | string | Yes | Version of parser used |
| `schema_version` | string | Yes | Must be "2.1" |

---

## Footnotes Section

```json
{
  "footnotes": [
    {
      "number": "2",
      "text": "Note to Reader: ..."
    }
  ]
}
```

Optional array for document footnotes extracted during parsing.

---

## Parts Section (Dict-based)

```json
{
  "parts": {
    "1": {
      "id": "part1",
      "parent_id": null,
      "type": "part",
      "number": 1,
      "title": "INTERPRETATION AND CONSTRUCTION",
      "text_for_embedding": "Part 1: Interpretation and Construction...",
      "sections": {
        "1.1": { ... },
        "1.2": { ... }
      }
    }
  }
}
```

**Key design decision:** Parts are stored as a dict with string keys ("1", "2", etc.) rather than an array. This allows direct access without iteration.

---

## Required Fields for Every Node

All nodes at every level (Part, Section, Definition, Clause, etc.) must include these fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier (see ID Patterns) |
| `parent_id` | string/null | Yes | Parent node ID (null for Parts) |
| `type` | string | Yes | Node type: `part`, `section`, `definition`, `condition`, `clause`, `subclause`, `subsection` |
| `text_for_embedding` | string | Yes | Cleaned text for vector embedding (single line, no artifacts) |
| `references` | array | Yes | Array of cross-reference objects (empty if none) |
| `raw_text` | string | Yes | Original extracted text |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `parsed` | dict | Structured parsed content (subsections, formulas, etc.) |
| `classification` | string | For definitions: `simple`, `alphabetic`, `nested_deep`, `reference`, `formula` |

---

## ID Patterns

Consistent ID patterns enable tree traversal and node lookup.

| Node Type | Pattern | Example |
|-----------|---------|---------|
| Part | `part{N}` | `part1`, `part5`, `part14` |
| Section | `part{N}.s{X_Y}` | `part1.s1_1`, `part5.s10_3` |
| Definition | `part{N}.s{X_Y}.def.{Slug}` | `part1.s1_1.def.Acceptable_Collateral` |
| Condition | `part{N}.c{N}` | `part3.c3`, `part5.c9` |
| Clause | `part{N}.s{X_Y}.clause.{X_Y_Z}` | `part5.s10_1.clause.10_1_1` |
| Subsection | `{parent_id}.({marker})` | `part1.s1_3.(A)`, `part1.s1_3.(A).(i)` |

**Rules:**
- Section IDs use underscores instead of dots: `s1_1` not `s1.1`
- Subsection markers are parenthesized suffixes
- Slugs use `slugify()` function: `Acceptable_Collateral` not `Acceptable Collateral`

---

## Reference Format

```json
{
  "references": [
    {"type": "condition", "target": "Condition 5.2"},
    {"type": "annex", "target": "Annex 10"},
    {"type": "part", "target": "Part 3"},
    {"type": "schedule", "target": "Schedule 2"}
  ]
}
```

| Reference Type | Example Pattern | Target Format |
|----------------|-----------------|---------------|
| Condition | "Condition 5.2" | "Condition {number}" |
| Annex | "Annex 10" | "Annex {number}" |
| Part | "Part 3" | "Part {number}" |
| Schedule | "Schedule 2.1" | "Schedule {number}" |

---

## Complete Example: Part 1 with Definitions

```json
{
  "metadata": {
    "document": "Low-Carbon Hydrogen Agreement Standard Terms and Conditions",
    "source_file": "low-carbon-hydrogen-agreement-standard-terms-and-conditions.pdf",
    "parse_date": "2026-01-25T12:00:00Z",
    "parser_version": "2.1.0",
    "schema_version": "2.1"
  },
  "footnotes": [],
  "parts": {
    "1": {
      "id": "part1",
      "parent_id": null,
      "type": "part",
      "number": 1,
      "title": "INTERPRETATION AND CONSTRUCTION",
      "text_for_embedding": "Part 1: Interpretation and Construction",
      "sections": {
        "1.1": {
          "id": "part1.s1_1",
          "parent_id": "part1",
          "type": "section",
          "section_number": "1.1",
          "title": "Definitions",
          "definitions": {
            "Acceptable Collateral": {
              "id": "part1.s1_1.def.Acceptable_Collateral",
              "parent_id": "part1.s1_1",
              "type": "definition",
              "classification": "simple",
              "term": "Acceptable Collateral",
              "text_for_embedding": "Acceptable Collateral means: (i) a Letter of Credit; and/or (ii) a cash amount (expressed in pounds (£)) transferred to the credit of a Reserve Account",
              "references": [],
              "parsed": {
                "text": ": (i) a Letter of Credit; and/or (ii) a cash amount"
              },
              "raw_text": "\"Acceptable Collateral\" means: (i) a Letter of Credit; and/or (ii) a cash amount (expressed in pounds (£)) transferred to the credit of a Reserve Account"
            }
          }
        },
        "1.2": {
          "id": "part1.s1_2",
          "parent_id": "part1",
          "type": "section",
          "section_number": "1.2",
          "title": "Interpretation",
          "text_for_embedding": "In these Conditions...",
          "references": [
            {"type": "condition", "target": "Condition 5"}
          ],
          "parsed": {
            "intro": "In these Conditions...",
            "subsections": {
              "(A)": "Unless a contrary intention appears..."
            }
          },
          "raw_text": "1.2 In these Conditions...\n(A) Unless a contrary intention appears..."
        }
      }
    }
  }
}
```

---

## Complete Example: Part with Nested Subsections

```json
{
  "parts": {
    "5": {
      "id": "part5",
      "parent_id": null,
      "type": "part",
      "number": 5,
      "title": "PAYMENT CALCULATIONS",
      "sections": {
        "5.1": {
          "id": "part5.s5_1",
          "parent_id": "part5",
          "type": "section",
          "section_number": "5.1",
          "text_for_embedding": "Thestrikepricemustbecalculated...",
          "references": [
            {"type": "condition", "target": "Condition 8"}
          ],
          "parsed": {
            "intro": "",
            "subsections": {
              "(A)": {
                "id": "part5.s5_1.(A)",
                "text": "The strike price must be calculated..."
              },
              "(B)": {
                "id": "part5.s5_1.(B)",
                "intro": "For the purposes of (A):",
                "subsections": {
                  "(i)": {
                    "id": "part5.s5_1.(B).(i)",
                    "text": "the Base Price is..."
                  }
                }
              }
            }
          },
          "raw_text": "5.1 (A) The strike price...\n(B) For the purposes...\n(i) the Base Price is..."
        }
      }
    }
  }
}
```

---

## Definition Classifications

Definitions in section 1.1 are classified by their structure:

| Classification | Description | Example |
|----------------|-------------|---------|
| `simple` | Plain text definition | "Acceptable Collateral means: ..." |
| `alphabetic` | Has (A), (B) subsections | "Accounting Standards means: (A) ..." |
| `nested_subsections` | Has (A)(i) nesting | "Appropriate Allowance means: (A) ..." |
| `nested_deep` | Has (A)(i)(a) three-level | "Adjustment Percentage means: (A) ..." |
| `reference` | Refers to another document | "10-BD Sample Period has the meaning given..." |
| `formula` | Contains `where:` clause | "Adjustment Factor = X where: ..." |

---

## Migration from Earlier Schemas

### v2.0 → v2.1 Changes

1. **Dict-based parts:** Array converted to dict with string keys
2. **Required fields:** All nodes must have `text_for_embedding` and `references`
3. **ID consistency:** Section IDs use underscores consistently

### Migration Path

Use `migrate_schema.py` to convert existing v2.0 data to v2.1:

```bash
python3 migrate_schema.py
```

---

## Validation

Use `lcha_utils.validate_structure()` to verify schema compliance:

```python
from lcha_utils import validate_structure

import json
with open('lcha_structure.json') as f:
    data = json.load(f)

is_valid, errors = validate_structure(data)
if not is_valid:
    for error in errors:
        print(error)
```

---

## Downstream Consumers

### Kanon 2 Embedder
Requires: `text_for_embedding` field (clean, single-line text)

### Hierarchical Viewer
Requires: `id`, `parent_id`, `type` for tree traversal

### Knowledge Graph / Enricher
Requires: `references` array for entity relationship extraction
