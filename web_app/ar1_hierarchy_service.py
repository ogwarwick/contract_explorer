#!/usr/bin/env python3
"""
AR1 Hierarchy Service.

Extracts and provides the clean, high-fidelity structural hierarchy
for Generic_CfD_TCs_29_August_2014 (AR1) from its stacked JSON source.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
AR1_STACKED_JSON = (
    WORKSPACE_ROOT
    / "contracts"
    / "parsed_outputs"
    / "parser_separation"
    / "final_jsons_040926"
    / "Generic_CfD_TCs__29_August_2014__stacked.json"
)

# In-memory cache
_AR1_CACHE: Optional[Dict[str, Any]] = None


def get_ar1_hierarchy() -> Dict[str, Any]:
    """
    Parse and return the complete structural hierarchy for AR1.
    Includes Parts, Conditions, and child Clauses/Definitions with exact page numbers.
    """
    global _AR1_CACHE
    if _AR1_CACHE is not None:
        return _AR1_CACHE

    if not AR1_STACKED_JSON.exists():
        raise FileNotFoundError(f"AR1 stacked JSON not found at: {AR1_STACKED_JSON}")

    with open(AR1_STACKED_JSON, "r", encoding="utf-8") as f:
        raw = json.load(f)

    meta = raw.get("document", {})
    mb = raw.get("main_body", {})

    parts_out: List[Dict[str, Any]] = []
    total_clauses = 0

    for pt in mb.get("children", []):
        p_num = str(pt.get("number", "")).strip()
        p_title = (pt.get("title") or "").strip()
        conds_out: List[Dict[str, Any]] = []

        for c in pt.get("children", []):
            prov = c.get("provenance", [])
            page_start = prov[0].get("page_no") if prov else c.get("page_start")

            clauses_out: List[Dict[str, Any]] = []
            for ch in c.get("children", []):
                ch_prov = ch.get("provenance", [])
                ch_page = ch_prov[0].get("page_no") if ch_prov else ch.get("page_start")
                title_text = (ch.get("title") or ch.get("text") or "").strip()
                # Clean line breaks
                title_text = " ".join(title_text.split())
                clauses_out.append({
                    "kind": ch.get("kind", "clause"),
                    "number": ch.get("number"),
                    "title": title_text[:160],
                    "page": ch_page,
                })

            total_clauses += len(clauses_out)

            conds_out.append({
                "number": str(c.get("number", "")).strip(),
                "title": (c.get("title") or "").strip(),
                "page_start": page_start,
                "page_end": c.get("page_end"),
                "item_count": len(clauses_out),
                "clauses": clauses_out,
            })

        parts_out.append({
            "part_number": p_num,
            "title": p_title,
            "condition_count": len(conds_out),
            "conditions": conds_out,
        })

    # Extract key schedules/annexes if available
    annexes_dict = raw.get("annexes", {})
    schedules_out: List[Dict[str, Any]] = []
    if isinstance(annexes_dict, dict):
        # Scan for distinct Schedule / Annex headings
        seen_headers = set()
        for v in annexes_dict.values():
            if not isinstance(v, dict):
                continue
            if v.get("label") == "section_header":
                txt = (v.get("text") or "").strip()
                if txt.startswith(("Schedule ", "Annex ")):
                    # Deduplicate
                    norm_txt = " ".join(txt.split())
                    if norm_txt not in seen_headers and len(norm_txt) < 80:
                        seen_headers.add(norm_txt)
                        prov = v.get("provenance", [{}])
                        p_no = prov[0].get("page_no") if prov else None
                        schedules_out.append({
                            "id": v.get("id"),
                            "title": norm_txt,
                            "page": p_no,
                        })

    result = {
        "document_id": meta.get("id", "Generic_CfD_TCs_29_August_2014"),
        "title": "Contract for Difference: Standard Terms and Conditions",
        "round": "AR1",
        "version": "V1",
        "agreement_date": "29 August 2014",
        "source_pdf": meta.get("source_file", "Generic_CfD_TCs__29_August_2014_.pdf"),
        "page_count": meta.get("page_count", 517),
        "total_parts": len(parts_out),
        "total_conditions": sum(p["condition_count"] for p in parts_out),
        "total_clauses": total_clauses,
        "parts": parts_out,
        "schedules_and_annexes": schedules_out,
    }

    _AR1_CACHE = result
    return result


if __name__ == "__main__":
    data = get_ar1_hierarchy()
    print(f"Title: {data['title']}")
    print(f"Round: {data['round']} ({data['agreement_date']})")
    print(f"Pages: {data['page_count']}")
    print(f"Parts: {data['total_parts']}, Conditions: {data['total_conditions']}, Clauses: {data['total_clauses']}")
    print(f"Schedules & Annexes: {len(data['schedules_and_annexes'])}")
