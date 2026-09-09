import os
import json
import argparse
from pathlib import Path
import sys

# Resolve workspace directory structure dynamically
SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent.parent

# Add paths relative to the runner script
sys.path.insert(0, str(WORKSPACE_ROOT / "code"))
sys.path.insert(0, str(SCRIPT_DIR))

from parser_separation.config import ParserConfig
from parser_separation.text_processor import TextProcessor
from parser_separation.stacker import Stacker
from parser_separation.formula_extractor import FormulaExtractor
from parser.docling_converter import DoclingConverter
from parser_separation.models import DocumentOutput, DocumentMetadata

def get_document_metadata(pdf_path: Path, doc_dict: dict) -> DocumentMetadata:
    import hashlib
    from datetime import datetime

    # Compute raw file sha256
    sha256 = hashlib.sha256()
    with open(pdf_path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha256.update(chunk)
    source_sha = sha256.hexdigest()

    # Generate document ID (clean alphanumeric + underscores slug)
    stem_clean = pdf_path.stem
    clean_id = ""
    for char in stem_clean:
        if char.isalnum() or char == "_":
            clean_id += char
        elif char in (" ", "-"):
            clean_id += "_"
    while "__" in clean_id:
        clean_id = clean_id.replace("__", "_")
    clean_id = clean_id.strip("_")

    name_lower = pdf_path.name.lower()
    
    # Scheme
    if "lcha" in name_lower or "hydrogen" in name_lower:
        scheme = "LCHA"
    elif "icc" in name_lower:
        scheme = "ICC"
    elif "dpa" in name_lower:
        scheme = "DPA"
    else:
        scheme = "CfD"

    # Allocation round & version mapping
    round_val = "AR6"
    version_val = "Unknown"
    
    if "ar3" in name_lower:
        round_val = "AR3"
        version_val = "V3"
    elif "ar4" in name_lower:
        round_val = "AR4"
        version_val = "V4"
    elif "ar5" in name_lower:
        round_val = "AR5"
        version_val = "V5"
    elif "ar7" in name_lower:
        round_val = "AR7"
        version_val = "V7"
    elif "2017" in name_lower or "v2" in name_lower:
        round_val = "AR2"
        version_val = "V2"
    elif "2014" in name_lower:
        round_val = "AR1"
        version_val = "V1"
    elif "icc" in name_lower:
        round_val = "ICC"
        version_val = "Template 1"
    elif "dpa" in name_lower:
        round_val = "DPA"
        version_val = "November 2022"
    elif "lcha" in name_lower:
        round_val = "LCHA"
        version_val = "V1"

    # Title
    title = pdf_path.stem.replace("_", " ").replace("-", " ")
    title = " ".join([w.capitalize() for w in title.split()])

    page_count = len(doc_dict.get("pages", {}))

    return DocumentMetadata(
        id=clean_id,
        title=title,
        scheme=scheme,
        round=round_val,
        version=version_val,
        source_file=pdf_path.name,
        source_sha256=source_sha,
        page_count=page_count,
        parsed_at=datetime.utcnow().isoformat() + "Z",
        parser_version="2.0",
        config_profile=pdf_path.stem
    )

def process_file(pdf_path: Path, docling_converter: DoclingConverter, workspace_root: Path, output_dir: Path):
    print(f"=== Processing File: {pdf_path.name} ===")
    
    # 1. Convert/Load Docling Export JSON
    docling_json_path = docling_converter.convert_pdf(pdf_path)
    
    with open(docling_json_path, 'r', encoding='utf-8') as f:
        doc_dict = json.load(f)

    # Initialize separated parser configurations
    config = ParserConfig(name=pdf_path.stem)
    processor = TextProcessor(config)
    stacker = Stacker(processor)

    # 2. Extract formula LaTeX via Pix2Tex + PDF crops
    formula_extractor = FormulaExtractor(
        crops_dir=workspace_root / "contracts" / "formula_crops"
    )
    formula_map = formula_extractor.extract_formula_text(
        pdf_path, doc_dict, pdf_path.stem
    )

    # 3. Flatten text sections using section separation with LaTeX formulas
    text_sections = processor.flatten_text(doc_dict, formula_map=formula_map)
    
    # Save flattened text sections
    flatten_text_dir = workspace_root / "contracts" / "flatten_docling_text_separated"
    flatten_text_dir.mkdir(parents=True, exist_ok=True)
    flatten_text_path = flatten_text_dir / f"{pdf_path.stem}_flatten_text.json"
    with open(flatten_text_path, 'w', encoding='utf-8') as f:
        json.dump([t.model_dump() for t in text_sections], f, indent=2)
    print(f"  [Output] Saved flattened text sections to: {flatten_text_path.name}")

    # 3. Extract TOC Tree
    toc = processor.build_toc_tree(doc_dict, text_sections)
    
    # Save unstacked TOC Tree
    toc_trees_dir = workspace_root / "contracts" / "toc_trees_separated"
    toc_trees_dir.mkdir(parents=True, exist_ok=True)
    unstacked_tree_path = toc_trees_dir / f"{pdf_path.stem}_toc_tree_unstacked.json"
    with open(unstacked_tree_path, 'w', encoding='utf-8') as f:
        json.dump(toc.model_dump(), f, indent=2)
    print(f"  [Output] Saved unstacked TOC tree to: {unstacked_tree_path.name}")

    # 4. Map text sections to TOC condition line numbers
    def find_matching_element(node, line_id):
        if node.line_id == line_id:
            return node
        for child in node.children:
            found = find_matching_element(child, line_id)
            if found:
                return found
        return None

    matches = []
    for line in text_sections:
        match = find_matching_element(toc, line.id)
        if match:
            matches.append({"id": line.id, "text": line.text, "number": match.number})

    # Save matches
    matches_dir = workspace_root / "contracts" / "toc_matches_with_flatten_text_separated"
    matches_dir.mkdir(parents=True, exist_ok=True)
    matches_path = matches_dir / f"{pdf_path.stem}_matches.json"
    with open(matches_path, 'w', encoding='utf-8') as f:
        json.dump(matches, f, indent=2)
    print(f"  [Output] Saved matches to: {matches_path.name}")

    # 5. Separate main body conditions and annexes
    annex_line_ids = [
        child.line_id for child in toc.children 
        if child.kind == "annex" and child.line_id is not None
    ]
    first_annex_line_id = min(annex_line_ids) if annex_line_ids else None

    # Filter matches to only include main body conditions
    main_body_matches = [
        m for m in matches 
        if first_annex_line_id is None or m["id"] < first_annex_line_id
    ]

    # Build gaps truncated at the first annex line ID
    gaps_by_id = stacker.build_gaps(text_sections, main_body_matches, end_boundary=first_annex_line_id)

    # Filter TOC tree to keep only main body parts
    main_body_toc = toc.model_copy(deep=True)
    main_body_toc.children = [child for child in main_body_toc.children if child.kind == "part"]

    # Generate metadata first
    metadata = get_document_metadata(pdf_path, doc_dict)

    # Set document_id on all text sections
    for line in text_sections:
        line.document_id = metadata.id

    # Stack content under the parts and conditions of the main body
    for part in main_body_toc.children:
        for cond in part.children:
            boundary = cond.line_id
            if boundary in gaps_by_id:
                stacker.stack_content(cond, gaps_by_id[boundary], text_sections=text_sections)

    # Post-process tree walk: adjust achieved depths, kinds, series, page range, breadcrumb, hash, node_uid, etc.
    stacker.post_process_tree(main_body_toc, metadata.id)

    # Store annex lines flat in a dictionary by line ID
    annexes_dict = {}
    if first_annex_line_id is not None:
        for line in text_sections:
            if line.id >= first_annex_line_id:
                annexes_dict[line.id] = line

    # 6. Save final serialized DocumentOutput schema
    output_data = DocumentOutput(
        document=metadata,
        main_body=main_body_toc,
        annexes=annexes_dict
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{pdf_path.stem}_stacked.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data.model_dump(), f, indent=2)
    print(f"  [Output] Saved experiment stacked TOC tree to: {output_path.name}")
    print(f"=== Successfully Processed: {pdf_path.name} ===\n")

def main():
    parser = argparse.ArgumentParser(description="End-to-End Separated Contract Parsing Pipeline")
    parser.add_argument("--pdf_dir", default=str(WORKSPACE_ROOT / "contracts" / "raw_pdf's"), help="Path to raw PDF files")
    parser.add_argument("--cache_dir", default=str(WORKSPACE_ROOT / "contracts" / "docling_files"), help="Path to cache docling exports")
    parser.add_argument("--output_dir", default=str(WORKSPACE_ROOT / "contracts" / "parsed_outputs" / "parser_separation"), help="Path to save stacked outputs")
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    cache_dir = Path(args.cache_dir)
    output_dir = Path(args.output_dir)

    # Rotate existing JSON files to previous/ folder
    prev_dir = output_dir / "previous"
    prev_dir.mkdir(parents=True, exist_ok=True)
    for f in output_dir.glob("*.json"):
        if f.is_file():
            target = prev_dir / f.name
            if target.exists():
                target.unlink()
            f.rename(target)

    input_files = list(pdf_dir.glob("*.pdf")) + list(pdf_dir.glob("*.docx"))
    if not input_files:
        print(f"No PDFs or DOCX files found in {pdf_dir}")
        return

    print(f"Found {len(input_files)} document files. Setting up converters...")
    docling_converter = DoclingConverter(cache_dir)

    for doc_file in input_files:
        try:
            process_file(doc_file, docling_converter, WORKSPACE_ROOT, output_dir)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error parsing file {doc_file.name}: {e}\n")

    print("Batch processing pipeline executed successfully!")

if __name__ == "__main__":
    main()
