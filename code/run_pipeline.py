import os
import json
import argparse
from pathlib import Path

# Resolve workspace directory structure dynamically
SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent

# Add paths to sys.path so modules can be imported relative to the run script CWD
import sys
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from parser.config import ParserConfig
from parser.text_processor import TextProcessor
from parser.stacker import Stacker
from parser.docling_converter import DoclingConverter
from parser.models import DocumentOutput

def process_file(pdf_path: Path, docling_converter: DoclingConverter, workspace_root: Path):
    print(f"=== Processing File: {pdf_path.name} ===")
    
    # 1. Convert/Load Docling Export JSON
    docling_json_path = docling_converter.convert_pdf(pdf_path)
    
    with open(docling_json_path, 'r', encoding='utf-8') as f:
        doc_dict = json.load(f)

    # Initialize parser configurations
    config = ParserConfig(name=pdf_path.stem)
    processor = TextProcessor(config)
    stacker = Stacker(processor)

    # 2. Flatten text sections
    text_sections = processor.flatten_text(doc_dict)
    
    # Save flattened text sections to contracts/flatten_docling_text/
    flatten_text_dir = workspace_root / "contracts" / "flatten_docling_text"
    flatten_text_dir.mkdir(parents=True, exist_ok=True)
    flatten_text_path = flatten_text_dir / f"{pdf_path.stem}_flatten_text.json"
    with open(flatten_text_path, 'w', encoding='utf-8') as f:
        json.dump([t.model_dump() for t in text_sections], f, indent=2)
    print(f"  [Output] Saved flattened text sections to: {flatten_text_path.name}")

    # 3. Extract TOC Tree
    toc = processor.build_toc_tree(doc_dict, text_sections)
    
    # Save unstacked TOC Tree to contracts/toc_trees/
    toc_trees_dir = workspace_root / "contracts" / "toc_trees"
    toc_trees_dir.mkdir(parents=True, exist_ok=True)
    unstacked_tree_path = toc_trees_dir / f"{pdf_path.stem}_toc_tree_unstacked.json"
    with open(unstacked_tree_path, 'w', encoding='utf-8') as f:
        json.dump(toc.model_dump(), f, indent=2)
    print(f"  [Output] Saved unstacked TOC tree to: {unstacked_tree_path.name}")

    # 4. Map text sections to TOC condition line numbers (recursive helper)
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

    # Save matches to contracts/toc_matches_with_flatten_text/
    matches_dir = workspace_root / "contracts" / "toc_matches_with_flatten_text"
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

    # Stack content under the parts and conditions of the main body
    for part in main_body_toc.children:
        for cond in part.children:
            boundary = cond.line_id
            if boundary in gaps_by_id:
                stacker.stack_content(cond, gaps_by_id[boundary])

    # Store annex lines flat in a dictionary by line ID
    annexes_dict = {}
    if first_annex_line_id is not None:
        for line in text_sections:
            if line.id >= first_annex_line_id:
                annexes_dict[line.id] = line

    # 6. Save final serialized DocumentOutput schema
    output_data = DocumentOutput(
        main_body=main_body_toc,
        annexes=annexes_dict
    )

    output_dir = workspace_root / "contracts" / "parsed_outputs" / "experiment_flat_annexes"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{pdf_path.stem}_stacked.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data.model_dump(), f, indent=2)
    print(f"  [Output] Saved experiment stacked TOC tree to: {output_path.name}")
    print(f"=== Successfully Processed: {pdf_path.name} ===\n")


def main():
    parser = argparse.ArgumentParser(description="End-to-End Type-Safe Contract Parsing Pipeline")
    parser.add_argument("--pdf_dir", default=str(WORKSPACE_ROOT / "contracts" / "raw_pdf's"), help="Path to raw PDF files")
    parser.add_argument("--cache_dir", default=str(WORKSPACE_ROOT / "contracts" / "docling_files"), help="Path to cache docling exports")
    parser.add_argument("--output_dir", default=str(WORKSPACE_ROOT / "contracts" / "parsed_outputs" / "experiment_flat_annexes"), help="Path to save stacked outputs")
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    cache_dir = Path(args.cache_dir)
    output_dir = Path(args.output_dir)

    # Support both pdf and docx files
    input_files = list(pdf_dir.glob("*.pdf")) + list(pdf_dir.glob("*.docx"))
    if not input_files:
        print(f"No PDFs or DOCX files found in {pdf_dir}")
        return

    print(f"Found {len(input_files)} document files. Setting up converters...")
    docling_converter = DoclingConverter(cache_dir)

    for doc_file in input_files:
        try:
            process_file(doc_file, docling_converter, WORKSPACE_ROOT)
        except Exception as e:
            print(f"Error parsing file {doc_file.name}: {e}\n")

    print("Batch processing pipeline executed successfully!")

if __name__ == "__main__":
    main()
