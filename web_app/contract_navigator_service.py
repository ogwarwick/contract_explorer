#!/usr/bin/env python3
"""
Contract Navigator Service — Hierarchy & Isaacus Cross-Reference Provider.
Provides:
1. Document Tree Hierarchy (Parts -> Conditions -> Sections with page numbers)
2. Isaacus Enricher Cross-References & Impact Analysis (citation frequencies, target pages, definitions)
3. In-contract scoped search integration
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict
import psycopg
from psycopg.rows import dict_row

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
ENRICHED_DIR = WORKSPACE_ROOT / "contracts" / "enriched_outputs"
CROSS_REFERENCE_DIR = ENRICHED_DIR / "cross_references"
RAW_PDF_DIR = WORKSPACE_ROOT / "contracts" / "raw_pdf's"

# In-memory cache for parsed enricher data
_ENRICHER_CACHE: Dict[str, Dict[str, Any]] = {}
_HIERARCHY_CACHE: Dict[int, Dict[str, Any]] = {}

# The parsed contract metadata uses the printed page number from the source
# document. PDF.js, however, navigates by the physical page index in the PDF.
# Keep this translation in the service layer so every client (navigator,
# search, and future integrations) receives the same target page.
PDF_PAGE_OFFSETS = {
    12: 8,   # AR3
    13: 8,   # AR4
    14: 8,   # AR7
    15: 0,   # CCUS ICC
    16: 7,   # AR2
    17: 7,   # AR1
    18: 8,   # AR5
    19: 7,   # CCUS DPA
    20: 8,   # AR6
    21: 7,   # Legacy LCHA DOCX record, served with the canonical LCHA PDF
    22: 7,   # LCHA PDF
}

# A small number of CfD Condition 32 records contain physical page values in
# the database even though the rest of that document uses printed pages. These
# are verified PDF page ranges and must not receive the document offset.
PDF_PAGE_OVERRIDES = {
    (13, "32"): (135, 145),  # AR4
    (14, "32"): (146, 157),  # AR7
    (18, "32"): (136, 146),  # AR5
    (20, "32"): (137, 148),  # AR6
}


def get_pdf_page_range(
    doc_key: int,
    page_start: Optional[int],
    page_end: Optional[int] = None,
    node_number: Optional[str] = None,
) -> tuple[Optional[int], Optional[int]]:
    """Translate printed contract pages into physical PDF.js page indexes."""
    if page_start is None:
        return None, None

    override = PDF_PAGE_OVERRIDES.get((int(doc_key), str(node_number or "")))
    if override:
        return override

    offset = PDF_PAGE_OFFSETS.get(int(doc_key), 0)
    return (
        max(1, int(page_start) + offset),
        max(1, int(page_end if page_end is not None else page_start) + offset),
    )


def get_doc_metadata(doc_key: int) -> Optional[Dict[str, Any]]:
    """Fetch document metadata from PostgreSQL."""
    with psycopg.connect("dbname=lcha") as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT 
                    document_key, 
                    document_id, 
                    title, 
                    scheme, 
                    round, 
                    version, 
                    page_count, 
                    source_file
                FROM document 
                WHERE document_key = %s;
            """, (doc_key,))
            return cur.fetchone()


def get_contract_hierarchy(doc_key: int) -> Dict[str, Any]:
    """
    Extracts structured Parts and Conditions for a contract from PostgreSQL `node` table.
    Groups conditions under their respective Part nodes with page references and numbers.
    """
    if doc_key in _HIERARCHY_CACHE:
        return _HIERARCHY_CACHE[doc_key]

    doc_meta = get_doc_metadata(doc_key)
    if not doc_meta:
        return {"error": f"Document {doc_key} not found"}

    with psycopg.connect("dbname=lcha") as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT 
                    node_uid,
                    parent_uid,
                    kind,
                    depth,
                    number,
                    title,
                    breadcrumb,
                    page_start,
                    page_end,
                    ordinal
                FROM node
                WHERE document_key = %s AND kind IN ('root', 'part', 'condition', 'annex')
                ORDER BY page_start ASC NULLS LAST, depth ASC, ordinal ASC;
            """, (doc_key,))
            rows = cur.fetchall()

    # Part color palette matching UI design
    PART_COLORS = [
        "#6366f1", "#8b5cf6", "#ec4899", "#f43f5e", 
        "#f59e0b", "#10b981", "#06b6d4", "#3b82f6", 
        "#14b8a6", "#eab308", "#a855f7", "#64748b"
    ]

    rows_by_uid = {r["node_uid"]: r for r in rows}
    children_by_parent = defaultdict(list)
    for row in rows:
        children_by_parent[row.get("parent_uid")].append(row)

    def node_order(row: Dict[str, Any]):
        return (
            row.get("page_start") if row.get("page_start") is not None else 10**9,
            row.get("depth") or 0,
            row.get("ordinal") or 0,
        )

    # Parts are identified from their parent relationship, not from the
    # flattened row order. This keeps each section under its actual Part.
    part_rows = [
        row for row in rows
        if row["kind"] == "part"
        and rows_by_uid.get(row.get("parent_uid"), {}).get("kind") != "annex"
    ]
    part_rows.sort(key=node_order)

    parts_list = []
    for part_idx, part_row in enumerate(part_rows):
        part_title = part_row["title"].strip()
        p_num = part_row.get("number") or f"{part_idx + 1}"
        display_title = (
            part_title
            if part_title.upper().startswith("PART") or part_title.upper().startswith("PT")
            else f"PT {p_num} · {part_title}"
        )

        part_obj = {
            "id": part_row["node_uid"],
            "kind": "part",
            "number": part_row.get("number") or str(part_idx + 1),
            "title": display_title,
            "raw_title": part_title,
            "color": PART_COLORS[part_idx % len(PART_COLORS)],
            "page_start": part_row["page_start"] or 1,
            "page_end": part_row["page_end"] or part_row["page_start"] or 1,
            "conditions": [],
        }
        part_obj["pdf_page_start"], part_obj["pdf_page_end"] = get_pdf_page_range(
            doc_key,
            part_row.get("page_start"),
            part_row.get("page_end"),
            part_row.get("number"),
        )

        # Main contract sections are direct condition children of a Part.
        # Annexes are never traversed, so their sections cannot leak into the
        # main contract tree.
        condition_rows = [
            row for row in children_by_parent.get(part_row["node_uid"], [])
            if row["kind"] == "condition"
        ]
        condition_rows.sort(key=node_order)
        for row in condition_rows:
            cond_num = row.get("number") or ""
            cond_title = row["title"].strip()
            clean_title = cond_title
            if cond_num and clean_title.startswith(str(cond_num)):
                clean_title = clean_title[len(str(cond_num)):].lstrip(" .:-")

            part_obj["conditions"].append({
                "id": row["node_uid"],
                "kind": row["kind"],
                "number": cond_num,
                "title": clean_title if clean_title else cond_title,
                "full_title": f"Condition {cond_num}: {clean_title}" if cond_num else cond_title,
                "breadcrumb": row.get("breadcrumb") or f"Condition {cond_num}",
                "page_start": row["page_start"] or 1,
                "page_end": row["page_end"] or row["page_start"] or 1,
                "pdf_page_start": get_pdf_page_range(
                    doc_key,
                    row.get("page_start"),
                    row.get("page_end"),
                    row.get("number"),
                )[0],
                "pdf_page_end": get_pdf_page_range(
                    doc_key,
                    row.get("page_start"),
                    row.get("page_end"),
                    row.get("number"),
                )[1],
            })

        parts_list.append(part_obj)

    total_conditions = sum(len(p["conditions"]) for p in parts_list)
    result = {
        "document_key": doc_key,
        "document_id": doc_meta["document_id"],
        "title": doc_meta["title"],
        "scheme": doc_meta["scheme"],
        "round": doc_meta["round"],
        "page_count": doc_meta["page_count"] or (rows[-1]["page_end"] if rows else 1),
        "total_parts": len(parts_list),
        "total_conditions": total_conditions,
        "pdf_page_offset": PDF_PAGE_OFFSETS.get(doc_key, 0),
        "parts": parts_list
    }
    
    _HIERARCHY_CACHE[doc_key] = result
    return result


def find_matching_enricher_file(doc_id: str) -> Optional[Path]:
    """Finds the corresponding Isaacus enricher JSON file for a document ID."""
    clean_id = doc_id.lower().replace("-", "_").replace(" ", "_")
    
    for f in ENRICHED_DIR.glob("*_enriched.json"):
        f_clean = f.stem.lower().replace("-", "_").replace(" ", "_")
        if clean_id in f_clean or f_clean.startswith(clean_id) or clean_id.startswith(f_clean.replace("_stacked_enriched", "")):
            return f
            
    keywords = [w for w in clean_id.split("_") if len(w) > 2 and w not in ("standard", "terms", "and", "conditions", "stacked")]
    best_file = None
    best_matches = 0
    for f in ENRICHED_DIR.glob("*_enriched.json"):
        f_name = f.stem.lower()
        matches = sum(1 for kw in keywords if kw in f_name)
        if matches > best_matches:
            best_matches = matches
            best_file = f
            
    return best_file


def _span_text(document: Dict[str, Any], span: Optional[Dict[str, int]]) -> str:
    """Safely extract a character span from an Isaacus enriched document."""
    if not span or not document.get("text"):
        return ""
    start = int(span.get("start", 0))
    end = int(span.get("end", start))
    return document["text"][start:end]


def _normalise_reference_number(value: str) -> str:
    return str(value).strip().split(".", 1)[0]


def _source_condition_for_segment(
    segment_id: Optional[str],
    segments_by_id: Dict[str, Dict[str, Any]],
    document: Dict[str, Any],
    cond_lookup_by_num: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    """Walk an enriched segment's ancestors until its condition code is found."""
    visited = set()
    current_id = segment_id
    while current_id and current_id not in visited:
        visited.add(current_id)
        segment = segments_by_id.get(current_id)
        if not segment:
            break

        code_text = _span_text(document, segment.get("code"))
        for token in re.findall(r"\b\d+[A-Za-z]?(?:\.\d+)?\b", code_text):
            condition_number = _normalise_reference_number(token)
            if condition_number in cond_lookup_by_num:
                return condition_number

        current_id = segment.get("parent")

    return None


def _segment_id_for_occurrence(
    occurrence_span: Optional[Dict[str, int]],
    segments: List[Dict[str, Any]],
) -> Optional[str]:
    """Find the most specific segment containing a cross-reference occurrence."""
    if not occurrence_span:
        return None

    start = int(occurrence_span.get("start", 0))
    end = int(occurrence_span.get("end", start + 1))
    candidates = []
    for segment in segments:
        segment_span = segment.get("span") or {}
        segment_start = segment_span.get("start")
        segment_end = segment_span.get("end")
        if segment_start is None or segment_end is None:
            continue
        if segment_start <= start and end <= segment_end:
            candidates.append((segment_end - segment_start, segment))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1].get("id")


def build_enricher_cross_reference_output(
    doc_key: int,
    hierarchy: Dict[str, Any],
    enricher_file: Path,
) -> Dict[str, Any]:
    """Convert a raw Isaacus result into a compact app-facing cross-reference graph."""
    with enricher_file.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    document = (payload.get("results") or [{}])[0].get("document") or {}
    raw_segments = [
        segment
        for segment in document.get("segments", [])
        if segment.get("id")
    ]
    segments_by_id = {
        segment.get("id"): segment
        for segment in raw_segments
    }

    cond_lookup_by_num: Dict[str, Dict[str, Any]] = {}
    for part in hierarchy.get("parts", []):
        for condition in part.get("conditions", []):
            number = str(condition.get("number") or "").strip()
            if not number:
                continue
            cond_lookup_by_num[number] = {
                "node_uid": condition["id"],
                "number": number,
                "title": condition["title"],
                "full_title": condition["full_title"],
                "page_start": condition["page_start"],
                "page_end": condition["page_end"],
                "pdf_page_start": condition.get("pdf_page_start"),
                "pdf_page_end": condition.get("pdf_page_end"),
                "part_number": part.get("number", "1"),
                "part_title": part.get("raw_title", ""),
            }

    outbound = defaultdict(lambda: defaultdict(int))
    unresolved_sources = 0
    unresolved_targets = 0
    raw_reference_count = 0

    for reference in document.get("crossreferences", []):
        span_text = _span_text(document, reference.get("span"))
        # Isaacus semantics: `span` is where the reference occurs, while
        # `start` and `end` identify the target segment(s). Do not parse
        # subsection numbers out of the occurrence text to infer the target.
        source_segment_id = _segment_id_for_occurrence(
            reference.get("span"),
            raw_segments,
        )
        source_number = _source_condition_for_segment(
            source_segment_id,
            segments_by_id,
            document,
            cond_lookup_by_num,
        )
        if not source_number:
            unresolved_sources += 1
            continue

        target_numbers = []
        for target_segment_id in (reference.get("start"), reference.get("end")):
            target_number = _source_condition_for_segment(
                target_segment_id,
                segments_by_id,
                document,
                cond_lookup_by_num,
            )
            if target_number and target_number not in target_numbers:
                target_numbers.append(target_number)

        if not target_numbers:
            unresolved_targets += 1
            continue

        for target_number in target_numbers:
            if target_number != source_number:
                outbound[source_number][target_number] += 1
                raw_reference_count += 1

    inbound = defaultdict(lambda: defaultdict(int))
    for source_number, targets in outbound.items():
        for target_number, count in targets.items():
            inbound[target_number][source_number] += count

    conditions = {}
    for number, info in cond_lookup_by_num.items():
        impact = []
        for target_number, count in sorted(
            outbound[number].items(), key=lambda item: (-item[1], item[0])
        ):
            target = cond_lookup_by_num[target_number]
            impact.append({
                "target_node_uid": target["node_uid"],
                "target_number": target_number,
                "title": f"C{target_number}. {target['title'].upper()}",
                "subtitle": f"Part {target['part_number']} · PDF p.{target['pdf_page_start']}",
                "part_number": target["part_number"],
                "page_start": target["page_start"],
                "page_end": target["page_end"],
                "pdf_page_start": target["pdf_page_start"],
                "pdf_page_end": target["pdf_page_end"],
                "source_pdf_page": info["pdf_page_start"],
                "target_pdf_page": target["pdf_page_start"],
                "navigation_pdf_page": target["pdf_page_start"],
                "count": count,
                "count_badge": f"{count}×",
            })

        referenced_by = []
        for source_number, count in sorted(
            inbound[number].items(), key=lambda item: (-item[1], item[0])
        ):
            source = cond_lookup_by_num[source_number]
            referenced_by.append({
                "source_node_uid": source["node_uid"],
                "source_number": source_number,
                "title": f"C{source_number}. {source['title'].upper()}",
                "subtitle": f"Part {source['part_number']} · PDF p.{source['pdf_page_start']}",
                "part_number": source["part_number"],
                "page_start": source["page_start"],
                "page_end": source["page_end"],
                "pdf_page_start": source["pdf_page_start"],
                "pdf_page_end": source["pdf_page_end"],
                "source_pdf_page": source["pdf_page_start"],
                "target_pdf_page": info["pdf_page_start"],
                "navigation_pdf_page": source["pdf_page_start"],
                "count": count,
                "count_badge": f"{count}×",
            })

        conditions[number] = {
            "condition_number": number,
            "node_uid": info["node_uid"],
            "title": info["title"],
            "header_title": f"C{number}. {info['title'].upper()}",
            "header_subtitle": f"Part {info['part_number']}: {info['part_title']} · PDF p.{info['pdf_page_start']}",
            "page_start": info["page_start"],
            "page_end": info["page_end"],
            "pdf_page_start": info["pdf_page_start"],
            "pdf_page_end": info["pdf_page_end"],
            "impact_count": len(impact),
            "impact": impact,
            "referenced_by_count": len(referenced_by),
            "referenced_by": referenced_by,
            "defs_count": 0,
            "definitions": [],
        }

    return {
        "schema_version": 2,
        "document_key": doc_key,
        "document_id": hierarchy.get("document_id", ""),
        "source_enricher_file": enricher_file.name,
        "raw_crossreference_count": len(document.get("crossreferences", [])),
        "resolved_crossreference_count": raw_reference_count,
        "unresolved_target_count": unresolved_targets,
        "unresolved_source_count": unresolved_sources,
        "conditions": conditions,
    }


def write_enricher_cross_reference_output(
    doc_key: int,
    hierarchy: Dict[str, Any],
    enricher_file: Path,
) -> Path:
    """Write one compact normalized cross-reference output for a contract."""
    CROSS_REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    output = build_enricher_cross_reference_output(doc_key, hierarchy, enricher_file)
    output_path = CROSS_REFERENCE_DIR / f"{doc_key}_{hierarchy.get('document_id', 'contract')}_cross_references.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def parse_enricher_cross_references(doc_key: int) -> Dict[str, Any]:
    """
    Parses the Isaacus Enricher JSON for a document and computes:
    1. Condition-to-Condition cross-references with citation counts (e.g. 18x C33...)
    2. Cross-reference target pages and breadcrumbs
    3. Defined terms occurrences
    4. Backlinks (Referenced By)
    """
    if str(doc_key) in _ENRICHER_CACHE:
        return _ENRICHER_CACHE[str(doc_key)]

    hierarchy = get_contract_hierarchy(doc_key)
    doc_id = hierarchy.get("document_id", "")
    enricher_file = find_matching_enricher_file(doc_id)
    if not enricher_file or not enricher_file.exists():
        return _extract_fallback_cross_references(doc_key, hierarchy, {})

    output_path = CROSS_REFERENCE_DIR / f"{doc_key}_{doc_id}_cross_references.json"
    try:
        if output_path.exists():
            result = json.loads(output_path.read_text(encoding="utf-8"))
        else:
            result = build_enricher_cross_reference_output(doc_key, hierarchy, enricher_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        _ENRICHER_CACHE[str(doc_key)] = result
        return result
    except Exception as e:
        print(f"[Warning] Error loading enricher cross-references: {e}")
        return _extract_fallback_cross_references(doc_key, hierarchy, {})


def _extract_fallback_cross_references(doc_key: int, hierarchy: Dict, cond_lookup_by_num: Dict) -> Dict[str, Any]:
    """Fallback cross-reference parser directly from PostgreSQL database."""
    condition_data = {}
    for p in hierarchy.get("parts", []):
        for c in p.get("conditions", []):
            c_num = str(c.get("number") or "").strip()
            condition_data[c_num] = {
                "condition_number": c_num,
                "node_uid": c["id"],
                "title": c["title"],
                "header_title": f"C{c_num}. {c['title'].upper()}",
                "header_subtitle": f"Part {p.get('number', '1')}: {p.get('raw_title', '')} · p.{c['page_start']}",
                "page_start": c["page_start"],
                "page_end": c["page_end"],
                "pdf_page_start": c.get("pdf_page_start"),
                "pdf_page_end": c.get("pdf_page_end"),
                "impact_count": 0,
                "impact": [],
                "referenced_by_count": 0,
                "referenced_by": [],
                "defs_count": 0,
                "definitions": []
            }
    return {
        "document_key": doc_key,
        "document_id": hierarchy.get("document_id", ""),
        "conditions": condition_data
    }
