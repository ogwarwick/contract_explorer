import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, Generator, Tuple
from dotenv import load_dotenv
from isaacus import Isaacus

# Load environment variables (e.g. ISAACUS_API_KEY from .env)
load_dotenv()

def load_jsons(folder: str) -> Generator[Tuple[str, Dict[str, Any]], None, None]:
    """Yields (filename, json_data) for all JSON files in the given directory."""
    folder_path = Path(folder)
    if not folder_path.exists():
        print(f"Folder not found: {folder}")
        return
    for file_path in sorted(folder_path.glob("*.json")):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        yield file_path.name, data

def explore_structure(filename: str, data: Dict[str, Any], output_dir: Optional[str] = None) -> Path:
    """
    Recursively extracts the hierarchical structure from a stacked JSON document
    and writes it as a tab-indented text file.
    """
    out_folder = Path(output_dir) if output_dir else Path(".")
    out_folder.mkdir(parents=True, exist_ok=True)
    
    output_filename = filename.replace(".json", "_structure.txt")
    output_path = out_folder / output_filename
    
    def write_node(node: Dict[str, Any], depth: int, file_handle):
        title = node.get("title")
        if title is not None and str(title).strip():
            indent = "\t" * depth
            file_handle.write(f"{indent}{str(title).strip()}\n")
        for child in node.get("children", []):
            write_node(child, depth + 1, file_handle)

    main_body = data.get("main_body", data)
    with open(output_path, "w", encoding="utf-8") as f:
        for element in main_body.get("children", []):
            write_node(element, depth=0, file_handle=f)

    return output_path

def enrich_text(
    client: Isaacus,
    text: str,
    model: str = "kanon-2-enricher",
    overflow_strategy: str = "auto"
):
    """
    Sends a text string to the Isaacus enrichment API.
    """
    response = client.enrichments.create(
        model=model,
        texts=text,
        overflow_strategy=overflow_strategy
    )
    return response

def parse_contract_enricher(
    input_folder: str = "contracts/parsed_outputs/parser_separation",
    structure_dir: str = "contracts/structure_text_files",
    enriched_dir: str = "contracts/enriched_outputs",
    api_key: Optional[str] = None,
    model: str = "kanon-2-enricher"
):
    """
    Orchestrates:
    1. Extracting hierarchical structure from all parsed contract JSONs into .txt files.
    2. Sending each text file to the Isaacus enricher.
    3. Saving enriched outputs into the enriched_dir folder.
    """
    key = api_key or os.getenv("ISAACUS_API_KEY")
    if not key:
        raise ValueError("ISAACUS_API_KEY not provided. Set it in .env or pass api_key to parse_contract_enricher().")

    client = Isaacus(api_key=key)
    
    enriched_folder = Path(enriched_dir)
    enriched_folder.mkdir(parents=True, exist_ok=True)

    print(f"=== Starting Contract Structure Extraction & Isaacus Enrichment ===")
    print(f"  Input JSON folder: {input_folder}")
    print(f"  Structure TXT folder: {structure_dir}")
    print(f"  Enriched output folder: {enriched_dir}\n")

    for filename, data in load_jsons(input_folder):
        print(f"Processing: {filename}")
        
        # 1. Export structure to text file
        txt_path = explore_structure(filename, data, output_dir=structure_dir)
        print(f"  [1/2] Extracted structure to: {txt_path}")
        
        # Read text content
        with open(txt_path, "r", encoding="utf-8") as f:
            doc_text = f.read()

        # 2. Send to Isaacus enricher
        print(f"  [2/2] Sending to Isaacus ({model})...")
        try:
            response = enrich_text(client, doc_text, model=model, overflow_strategy="auto")
            
            # 3. Save enriched response
            out_json_path = enriched_folder / filename.replace(".json", "_enriched.json")
            with open(out_json_path, "w", encoding="utf-8") as f:
                # Store full serialized response
                if hasattr(response, "model_dump"):
                    json.dump(response.model_dump(), f, indent=2)
                elif hasattr(response, "to_dict"):
                    json.dump(response.to_dict(), f, indent=2)
                else:
                    json.dump(response.dict() if hasattr(response, "dict") else str(response), f, indent=2)
                    
            print(f"  [Success] Saved enriched output to: {out_json_path.name}\n")
        except Exception as e:
            print(f"  [Error] Failed to enrich {filename}: {e}\n")

    print("=== All contracts processed successfully! ===")

if __name__ == "__main__":
    # Example standalone execution:
    # To run enrichment across all files, ensure ISAACUS_API_KEY is in .env and run:
    # parse_contract_enricher()
    
    # Run structure extraction locally
    folder = "contracts/parsed_outputs/parser_separation"
    for filename, data in load_jsons(folder):
        txt_path = explore_structure(filename, data)
        print(f"Generated structure: {txt_path.name}")


parse_contract_enricher()