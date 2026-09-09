import json
import re
import sys
from pathlib import Path
from typing import Set, List, Dict, Any
from collections import defaultdict

# Add code/ path to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from parser.config import ParserConfig
from parser.text_processor import TextProcessor

PART_REGEX = re.compile(r"^Part\s+\d+[A-Z]?\b", re.IGNORECASE)
COND_REGEX = re.compile(r"^\d+\.\s", re.IGNORECASE)

# Bounding box vertical gap threshold (60 points)
VERTICAL_GAP_THRESHOLD = 60.0

def collect_line_ids(node: Dict[str, Any], ids_list: List[int]):
    line_id = node.get("line_id")
    if line_id is not None:
        ids_list.append(line_id)
    for child in node.get("children", []):
        collect_line_ids(child, ids_list)

def detect_vertical_holes(doc_dict: Dict[str, Any], threshold: float = VERTICAL_GAP_THRESHOLD) -> List[Dict[str, Any]]:
    items_by_page = defaultdict(list)
    for item in doc_dict.get("texts", []):
        text = item.get("text", "").strip()
        if not text:
            continue
        prov_list = item.get("prov", [])
        for prov in prov_list:
            page = prov.get("page_no")
            bbox = prov.get("bbox")
            if page is not None and bbox is not None:
                items_by_page[page].append({
                    "id": item.get("self_ref", "").split('/')[-1],
                    "text": text,
                    "bbox": bbox
                })
                break
                
    holes = []
    for page, items in sorted(items_by_page.items()):
        # Sort items by top coordinate decreasing (top to bottom on the page)
        items.sort(key=lambda x: x["bbox"]["t"], reverse=True)
        
        for i in range(len(items) - 1):
            item1 = items[i]
            item2 = items[i+1]
            
            # gap = bottom of higher item - top of lower item
            gap = item1["bbox"]["b"] - item2["bbox"]["t"]
            
            # Ignore gaps where coordinates are weird or negative (overlapping text blocks)
            if gap > threshold:
                holes.append({
                    "page": page,
                    "gap": gap,
                    "item1": {"id": item1["id"], "text": item1["text"][:30], "b": item1["bbox"]["b"]},
                    "item2": {"id": item2["id"], "text": item2["text"][:30], "t": item2["bbox"]["t"]}
                })
    return holes

def validate_contract_json(file_path: Path, flat_path: Path, matches_path: Path, docling_path: Path) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(flat_path, "r", encoding="utf-8") as f:
        flat_lines = json.load(f)
    with open(matches_path, "r", encoding="utf-8") as f:
        matches = json.load(f)
    with open(docling_path, "r", encoding="utf-8") as f:
        docling_data = json.load(f)
        
    main_body = data.get("main_body", {})
    annexes = data.get("annexes", {})
    
    # Collect all line IDs in pre-order traversal
    body_ids = []
    collect_line_ids(main_body, body_ids)
    body_ids_set = set(body_ids)
    
    annex_ids = sorted([int(k) for k in annexes.keys()])
    annex_ids_set = set(annex_ids)
    
    all_output_ids = body_ids_set | annex_ids_set
    
    # Collect all text content in output to verify content preservation (as an ordered list)
    all_output_texts = []
    def collect_texts(node):
        title = node.get("title", "")
        if title:
            all_output_texts.append(" ".join(title.split()))
        for child in node.get("children", []):
            collect_texts(child)
    collect_texts(main_body)
    for k in sorted(annexes.keys(), key=int):
        line = annexes[k]
        if "text" in line:
            all_output_texts.append(" ".join(line["text"].split()))
            
    report = {
        "file": file_path.name,
        "passed": True,
        "errors": [],
        "vertical_holes": []
    }
    
    # Check 1: Pre-order traversal is non-decreasing (sequential stacking)
    is_sorted = all(x <= y for x, y in zip(body_ids, body_ids[1:]))
    if not is_sorted:
        report["passed"] = False
        report["errors"].append("Line IDs in main_body are not non-decreasing.")
        
    # Find boundary cutoff
    min_body_id = min(body_ids) if body_ids else 0
    min_annex_id = min(annex_ids) if annex_ids else None
    
    # Check 2: Completeness check against TextProcessor classification
    config = ParserConfig(name="validation")
    processor = TextProcessor(config)
    
    expected_body_set = set()
    expected_annex_set = set()
    
    flat_lines = processor.flatten_text(docling_data)
    flat_lines_dict = {line.id: line for line in flat_lines}
    
    # Matches IDs are always expected in the main body if they are before annex cutoff
    matches_ids = {m["id"] for m in matches if min_annex_id is None or m["id"] < min_annex_id}
    expected_body_set.update(matches_ids)
    
    for line in flat_lines:
        lid = line.id
        text = line.text.strip()
        
        if min_annex_id is None or lid < min_annex_id:
            # Skip empty lines for main body range (since stacker ignores empty lines)
            if not text:
                continue
            # For lines in the main body range, if they are not matches, they are stacked in gaps
            if lid >= min_body_id and lid not in matches_ids:
                kind = processor.classify(text)
                # Stacker skips duplicate part and condition headers in the body
                if kind not in ("part", "condition"):
                    expected_body_set.add(lid)
        else:
            # Annex range - we keep all lines
            expected_annex_set.add(lid)
            
    # Validate main body completeness
    missing_body = expected_body_set - body_ids_set
    if missing_body:
        report["passed"] = False
        report["errors"].append(
            f"Missing lines from main body stacking. Count: {len(missing_body)}, Sample: {sorted(list(missing_body))[:10]}"
        )
        
    extra_body = body_ids_set - expected_body_set
    if extra_body:
        report["passed"] = False
        report["errors"].append(
            f"Stacked main body has unexpected/duplicate line IDs. Count: {len(extra_body)}, Sample: {sorted(list(extra_body))[:10]}"
        )
        
    # Validate annexes completeness
    missing_annex = expected_annex_set - annex_ids_set
    if missing_annex:
        report["passed"] = False
        report["errors"].append(
            f"Missing lines from flat annexes dict. Count: {len(missing_annex)}, Sample: {sorted(list(missing_annex))[:10]}"
        )
        
    extra_annex = annex_ids_set - expected_annex_set
    if extra_annex:
        report["passed"] = False
        report["errors"].append(
            f"Flat annexes dict has unexpected line IDs. Count: {len(extra_annex)}, Sample: {sorted(list(extra_annex))[:10]}"
        )
        
    # Check 3: Boundary separation & No overlap
    if body_ids and annex_ids:
        overlap = body_ids_set & annex_ids_set
        if overlap:
            report["passed"] = False
            report["errors"].append(f"Overlap detected between main body and annexes line IDs. Count: {len(overlap)}")
            
        if min_annex_id is not None and body_ids:
            max_body_id = max(body_ids)
            # Find all expected lines in flat text that exist between max_body_id and min_annex_id
            between_lines = [line.id for line in flat_lines if max_body_id < line.id < min_annex_id]
            # Filter to non-empty, non-header lines
            between_lines = [
                lid for lid in between_lines 
                if flat_lines_dict[lid].text.strip() and processor.classify(flat_lines_dict[lid].text.strip()) not in ("part", "condition")
            ]
            if between_lines:
                report["passed"] = False
                report["errors"].append(f"Lost lines between main body and annexes. Range: ({max_body_id}, {min_annex_id}), Lost IDs: {between_lines}")

    # Check 4: Pipeline Dropped ID Gaps (Inference gaps)
    full_output_corpus = " ".join(all_output_texts)
    alnum_corpus = "".join(c.lower() for c in full_output_corpus if c.isalnum())
    
    pipeline_dropped = []
    skip_labels = {"page_header", "page_footer"}
    for item in docling_data.get("texts", []):
        ref = item.get("self_ref", "")
        sid_str = ref.split("/")[-1]
        if not sid_str.isdigit():
            continue
        sid = int(sid_str)
        
        # Only verify range from min_body_id onwards (ignore cover pages / TOC front-matter)
        if sid < min_body_id:
            continue
            
        if sid not in all_output_ids:
            label = item.get("label")
            text = item.get("text", "").strip()
            
            # Exclude headers, footers, empty, and defined junk patterns
            if label in skip_labels or not text:
                continue
            if any(junk.search(text) for junk in config.junk_patterns):
                continue
                
            # Clean and normalize raw text to match the output text format
            clean_text = processor.clean_ocr_symbols(text)
            norm_text = " ".join(clean_text.split())
            
            # If the text is contained anywhere in the output corpus (merged/split),
            # then it is NOT dropped.
            alnum_norm = "".join(c.lower() for c in norm_text if c.isalnum())
            if alnum_norm in alnum_corpus:
                continue
                
            # If it's a part/condition header, we don't stack it in the body, which is correct
            if min_annex_id is None or sid < min_annex_id:
                kind = processor.classify(text)
                if kind in ("part", "condition"):
                    continue
                    
            pipeline_dropped.append((sid, label, text))
            
    if pipeline_dropped:
        report["passed"] = False
        report["errors"].append(
            f"Pipeline dropped content lines (non-benign ID gaps)! Count: {len(pipeline_dropped)}, Sample: {[(sid, text[:30]) for sid, _, text in pipeline_dropped[:10]]}"
        )

    # Check 5: Vertical Layout Holes (Observation holes where Docling missed content)
    report["vertical_holes"] = detect_vertical_holes(docling_data)
    
    # Include stats in report
    report["body_range"] = (min_body_id, max(body_ids) if body_ids else None)
    report["annex_range"] = (min_annex_id, max(annex_ids) if annex_ids else None)
    report["body_nodes_count"] = len(body_ids)
    report["annex_lines_count"] = len(annex_ids)
    
    return report

def main():
    workspace_root = Path(__file__).resolve().parent.parent
    experiment_dir = workspace_root / "contracts" / "parsed_outputs" / "experiment_flat_annexes"
    flat_dir = workspace_root / "contracts" / "flatten_docling_text"
    matches_dir = workspace_root / "contracts" / "toc_matches_with_flatten_text"
    docling_dir = workspace_root / "contracts" / "docling_files"
    
    json_files = sorted(list(experiment_dir.glob("*.json")))
    print(f"Running validation tests on {len(json_files)} contracts (Inference Gaps & Vertical Holes)...\n")
    
    passed_count = 0
    for f in json_files:
        stem = f.name.replace("_stacked.json", "")
        flat_path = flat_dir / f"{stem}_flatten_text.json"
        matches_path = matches_dir / f"{stem}_matches.json"
        
        # Check mapping to cache docling exports
        docling_converter = None
        # Try matching stemming files
        docling_path = docling_dir / f"{stem}_docling_export.json"
        if not docling_path.exists():
            # Try fuzzy mappings
            name_lower = stem.lower()
            if "icc" in name_lower:
                docling_path = docling_dir / "icc_docling_export.json"
            elif "lcha" in name_lower or "hydrogen" in name_lower:
                docling_path = docling_dir / "lcha_docling_export.json"
            else:
                for ar_num in ["ar1", "ar3", "ar4", "ar5", "ar6", "ar7"]:
                    num_val = ar_num[2:]
                    if ar_num in name_lower or f"ar-{num_val}" in name_lower or f"ar_{num_val}" in name_lower:
                        docling_path = docling_dir / f"{ar_num}_docling_export.json"
                        break
                        
        if not flat_path.exists() or not matches_path.exists() or not docling_path.exists():
            print(f"[ERROR] Required raw/flat/matches files missing for: {f.name}")
            continue
            
        report = validate_contract_json(f, flat_path, matches_path, docling_path)
        status = "PASS" if report["passed"] else "FAIL"
        print(f"[{status}] {report['file']}")
        print(f"  - Main Body Range: {report['body_range']} (nodes: {report['body_nodes_count']})")
        print(f"  - Annex Range:     {report['annex_range']} (lines: {report['annex_lines_count']})")
        
        # Log vertical holes summary
        holes = report["vertical_holes"]
        print(f"  - Vertical Holes (> {VERTICAL_GAP_THRESHOLD}pt): {len(holes)}")
        if holes:
            print(f"    * Sample holes (largest 3):")
            for h in sorted(holes, key=lambda x: x["gap"], reverse=True)[:3]:
                print(f"      [Page {h['page']}] Gap of {h['gap']:.1f}pt between '{h['item1']['text']}' (y={h['item1']['b']:.1f}) and '{h['item2']['text']}' (y={h['item2']['t']:.1f})")
                
        if not report["passed"]:
            for err in report["errors"]:
                print(f"    * {err}")
        else:
            passed_count += 1
        print()
        
    print(f"Validation complete: {passed_count}/{len(json_files)} files PASSED.")

if __name__ == "__main__":
    main()
