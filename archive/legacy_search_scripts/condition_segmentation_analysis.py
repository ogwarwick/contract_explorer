#!/usr/bin/env python3
"""
Condition Segmentation & Chaining Analysis for Legal Contracts.

Analyzes all parsed contract JSONs in parser_separation:
1. Identifies all conditions exceeding the target embedding limit (default: 40,000 chars).
2. Computes the natural sub-clause split boundaries for each oversized condition.
3. Formulates context-anchored breadcrumb headers for each resulting fragment.
4. Generates a machine-readable JSON report and a formatted summary.

Usage:
    /usr/bin/python3 search_functionality/condition_segmentation_analysis.py
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = WORKSPACE_ROOT / "contracts" / "parsed_outputs" / "parser_separation" / "final_jsons_040926"
ENRICHED_DIR = WORKSPACE_ROOT / "contracts" / "enriched_outputs"
OUTPUT_DIR = WORKSPACE_ROOT / "search_functionality" / "data"

MAX_CHUNK_CHARS = 40000  # Conservative safe target below Kanon 2 48k limit

def get_subtree_clauses(node):
    """Collects direct and nested clauses under a condition with full text."""
    clauses = []
    
    def walk(n, parent_path=""):
        kind = n.get("kind", "")
        title = n.get("title", "").strip()
        num = n.get("number", "")
        text = n.get("text_full", "").strip()
        
        if kind in ("clause", "subclause", "text", "subtitle") and (text or title):
            clause_text = text if text else title
            clauses.append({
                "kind": kind,
                "number": num,
                "title": title,
                "char_length": len(clause_text),
                "text": clause_text
            })
            
        for ch in n.get("children", []):
            walk(ch, parent_path)
            
    walk(node)
    return clauses

def partition_condition_clauses(condition_node, doc_title, doc_id):
    """
    Partitions a large condition into semantic sub-chunks adhering to MAX_CHUNK_CHARS.
    """
    cond_num = condition_node.get("number") or ""
    cond_title = condition_node.get("title") or ""
    cond_breadcrumb = condition_node.get("breadcrumb") or f"Condition {cond_num}"
    
    clauses = get_subtree_clauses(condition_node)
    
    # If no child clauses, condition text itself
    if not clauses:
        raw_text = condition_node.get("text_full", "")
        return [{
            "chunk_index": 1,
            "total_chunks": 1,
            "clause_range": f"Condition {cond_num}",
            "char_length": len(raw_text),
            "est_tokens": int(round(len(raw_text) / 3.5)),
            "anchor_header": f"[{doc_title}] > {cond_breadcrumb} > {cond_title}",
            "text": raw_text
        }]
        
    chunks = []
    current_chunk_clauses = []
    current_chunk_len = 0
    
    for cl in clauses:
        # If adding this clause exceeds MAX_CHUNK_CHARS and we already have clauses, flush chunk
        if current_chunk_len + cl["char_length"] > MAX_CHUNK_CHARS and current_chunk_clauses:
            chunks.append(current_chunk_clauses)
            current_chunk_clauses = [cl]
            current_chunk_len = cl["char_length"]
        else:
            current_chunk_clauses.append(cl)
            current_chunk_len += cl["char_length"]
            
    if current_chunk_clauses:
        chunks.append(current_chunk_clauses)
        
    # Build finalized fragments with headers
    total_parts = len(chunks)
    fragments = []
    
    for idx, chunk_group in enumerate(chunks, 1):
        first_num = chunk_group[0].get("number") or chunk_group[0].get("title", "")[:15]
        last_num = chunk_group[-1].get("number") or chunk_group[-1].get("title", "")[:15]
        range_desc = f"Clauses {first_num} to {last_num}" if first_num != last_num else f"Clause {first_num}"
        
        combined_text = "\n\n".join(c["text"] for c in chunk_group)
        char_len = len(combined_text)
        
        header = f"[{doc_title}] > {cond_breadcrumb} (Part {idx} of {total_parts}: {range_desc})"
        fragments.append({
            "chunk_uid": f"{doc_id}:cond_{cond_num}:part_{idx}",
            "parent_condition": f"Condition {cond_num}",
            "chunk_index": idx,
            "total_chunks": total_parts,
            "clause_range": range_desc,
            "clause_count": len(chunk_group),
            "char_length": char_len,
            "est_tokens": int(round(char_len / 3.5)),
            "anchor_header": header,
            "text_preview": combined_text[:300] + "..." if len(combined_text) > 300 else combined_text
        })
        
    return fragments

def run_analysis():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_files = sorted(JSON_DIR.glob("*_stacked.json"))
    
    analysis_results = {
        "metadata": {
            "max_chunk_chars": MAX_CHUNK_CHARS,
            "total_contracts": len(json_files)
        },
        "contracts": {}
    }
    
    print("=" * 90)
    print("LEGAL CONTRACT CONDITION SEGMENTATION & CHAINING ANALYSIS")
    print(f"Target Max Chunk Size: {MAX_CHUNK_CHARS:,} chars (~{int(MAX_CHUNK_CHARS/3.5):,} tokens)")
    print("=" * 90)
    
    total_oversized_conditions = 0
    total_generated_fragments = 0
    
    for f in json_files:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            
        doc_meta = data.get("document", {})
        doc_id = doc_meta.get("id", f.stem.replace("_stacked", ""))
        doc_title = doc_meta.get("title", doc_id)
        
        oversized_list = []
        
        def check_conditions(node):
            nonlocal oversized_list
            if node.get("kind") == "condition":
                num = node.get("number") or ""
                title = node.get("title") or ""
                
                # Check if it is a definitions condition
                is_defs = "definition" in title.lower() or num == "1"
                
                clauses = get_subtree_clauses(node)
                total_chars = sum(c["char_length"] for c in clauses)
                
                if not is_defs and total_chars > MAX_CHUNK_CHARS:
                    fragments = partition_condition_clauses(node, doc_title, doc_id)
                    oversized_list.append({
                        "condition_number": num,
                        "condition_title": title,
                        "raw_char_length": total_chars,
                        "clause_count": len(clauses),
                        "num_fragments": len(fragments),
                        "fragments": fragments
                    })
                return
            for ch in node.get("children", []):
                check_conditions(ch)
                
        check_conditions(data.get("main_body", data))
        
        total_oversized_conditions += len(oversized_list)
        total_generated_fragments += sum(o["num_fragments"] for o in oversized_list)
        
        analysis_results["contracts"][doc_id] = {
            "title": doc_title,
            "source_file": doc_meta.get("source_file", f.name),
            "oversized_conditions_count": len(oversized_list),
            "conditions": oversized_list
        }
        
        print(f"\n Contract: {doc_title}")
        print(f"   Oversized Conditions (> {MAX_CHUNK_CHARS:,} chars): {len(oversized_list)}")
        for item in oversized_list:
            print(f"   - Condition {item['condition_number']}: '{item['condition_title'][:40]}' ({item['raw_char_length']:,} chars)")
            print(f"     ➔ Segmented into {item['num_fragments']} chained fragments:")
            for frag in item["fragments"]:
                print(f"        * Part {frag['chunk_index']}/{frag['total_chunks']}: {frag['clause_range']} ({frag['char_length']:,} chars, ~{frag['est_tokens']:,} tok)")
                
    # Save full machine readable JSON
    out_file = OUTPUT_DIR / "segmentation_analysis.json"
    with open(out_file, "w", encoding="utf-8") as out_fp:
        json.dump(analysis_results, out_fp, indent=2)
        
    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)
    print(f"Total Contracts Analyzed: {len(json_files)}")
    print(f"Total Conditions Requiring Segmentation: {total_oversized_conditions}")
    print(f"Total Chained Fragments Generated: {total_generated_fragments}")
    print(f"Results saved to: {out_file}")
    print("=" * 90)

if __name__ == "__main__":
    run_analysis()
