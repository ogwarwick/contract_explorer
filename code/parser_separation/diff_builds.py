import json
import argparse
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple

def get_node_flat_list(node: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    results.append(node)
    for child in node.get("children", []):
        get_node_flat_list(child, results)

def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def diff_document(curr_path: Path, prev_path: Path):
    with open(curr_path, "r", encoding="utf-8") as f:
        curr_data = json.load(f)
    with open(prev_path, "r", encoding="utf-8") as f:
        prev_data = json.load(f)

    # 1. Main Body Nodes
    curr_nodes: List[Dict[str, Any]] = []
    get_node_flat_list(curr_data["main_body"], curr_nodes)
    
    prev_nodes: List[Dict[str, Any]] = []
    get_node_flat_list(prev_data["main_body"], prev_nodes)

    curr_nodes_by_uid = {n["node_uid"]: n for n in curr_nodes if "node_uid" in n}
    prev_nodes_by_uid = {n["node_uid"]: n for n in prev_nodes if "node_uid" in n}

    # Node additions / deletions
    added_nodes = sorted(list(set(curr_nodes_by_uid.keys()) - set(prev_nodes_by_uid.keys())))
    removed_nodes = sorted(list(set(prev_nodes_by_uid.keys()) - set(curr_nodes_by_uid.keys())))

    # Node mutations
    mutated_nodes: List[Tuple[str, str, str]] = []
    common_uids = set(curr_nodes_by_uid.keys()) & set(prev_nodes_by_uid.keys())
    for uid in common_uids:
        c_node = curr_nodes_by_uid[uid]
        p_node = prev_nodes_by_uid[uid]
        c_hash = c_node.get("text_sha256")
        p_hash = p_node.get("text_sha256")
        if not c_hash:
            c_hash = compute_sha256(c_node.get("title", ""))
        if not p_hash:
            p_hash = compute_sha256(p_node.get("title", ""))
        if c_hash != p_hash:
            mutated_nodes.append((uid, p_node.get("title", ""), c_node.get("title", "")))

    # Main Body Metrics
    curr_body_chars = sum(len(n.get("title", "")) for n in curr_nodes)
    prev_body_chars = sum(len(n.get("title", "")) for n in prev_nodes)

    # 2. Annex Items
    curr_annexes = curr_data.get("annexes", {})
    prev_annexes = prev_data.get("annexes", {})

    doc_id = curr_data.get("document", {}).get("id", curr_path.stem.replace("_stacked", ""))
    
    # Map by {document_id}:{id}
    curr_annex_by_key = {f"{doc_id}:{k}": v for k, v in curr_annexes.items()}
    prev_annex_by_key = {f"{doc_id}:{k}": v for k, v in prev_annexes.items()}

    added_annex = sorted(list(set(curr_annex_by_key.keys()) - set(prev_annex_by_key.keys())))
    removed_annex = sorted(list(set(prev_annex_by_key.keys()) - set(curr_annex_by_key.keys())))

    mutated_annex: List[Tuple[str, str, str]] = []
    common_annex_keys = set(curr_annex_by_key.keys()) & set(prev_annex_by_key.keys())
    for key in common_annex_keys:
        c_item = curr_annex_by_key[key]
        p_item = prev_annex_by_key[key]
        c_text = c_item.get("text", "")
        p_text = p_item.get("text", "")
        if c_text != p_text:
            mutated_annex.append((key, p_text, c_text))

    curr_annex_chars = sum(len(item.get("text", "")) for item in curr_annexes.values())
    prev_annex_chars = sum(len(item.get("text", "")) for item in prev_annexes.values())

    print(f"\n==================================================")
    print(f"DIFF REPORT: {curr_path.name}")
    print(f"==================================================")
    print(f"Main Body:")
    print(f"  Nodes: {len(prev_nodes)} -> {len(curr_nodes)} (change: {len(curr_nodes) - len(prev_nodes):+d})")
    print(f"  Chars: {prev_body_chars} -> {curr_body_chars} (change: {curr_body_chars - prev_body_chars:+d})")
    print(f"Annexes:")
    print(f"  Items: {len(prev_annexes)} -> {len(curr_annexes)} (change: {len(curr_annexes) - len(prev_annexes):+d})")
    print(f"  Chars: {prev_annex_chars} -> {curr_annex_chars} (change: {curr_annex_chars - prev_annex_chars:+d})")

    if added_nodes:
        print(f"\nAdded Main Body Nodes ({len(added_nodes)}):")
        for uid in added_nodes[:10]:
            print(f"  + {uid}: {repr(curr_nodes_by_uid[uid].get('title', ''))[:80]}")
        if len(added_nodes) > 10:
            print(f"  ... and {len(added_nodes) - 10} more")

    if removed_nodes:
        print(f"\nRemoved Main Body Nodes ({len(removed_nodes)}):")
        for uid in removed_nodes[:10]:
            print(f"  - {uid}: {repr(prev_nodes_by_uid[uid].get('title', ''))[:80]}")
        if len(removed_nodes) > 10:
            print(f"  ... and {len(removed_nodes) - 10} more")

    if mutated_nodes:
        print(f"\nMutated Main Body Nodes ({len(mutated_nodes)}):")
        for uid, prev_txt, curr_txt in mutated_nodes[:10]:
            print(f"  * {uid}:")
            print(f"    Prev: {repr(prev_txt)[:80]}")
            print(f"    Curr: {repr(curr_txt)[:80]}")
        if len(mutated_nodes) > 10:
            print(f"  ... and {len(mutated_nodes) - 10} more")

    if added_annex:
        print(f"\nAdded Annex Items ({len(added_annex)}):")
        for key in added_annex[:10]:
            print(f"  + {key}: {repr(curr_annex_by_key[key].get('text', ''))[:80]}")
        if len(added_annex) > 10:
            print(f"  ... and {len(added_annex) - 10} more")

    if removed_annex:
        print(f"\nRemoved Annex Items ({len(removed_annex)}):")
        for key in removed_annex[:10]:
            print(f"  - {key}: {repr(prev_annex_by_key[key].get('text', ''))[:80]}")
        if len(removed_annex) > 10:
            print(f"  ... and {len(removed_annex) - 10} more")

    if mutated_annex:
        print(f"\nMutated Annex Items ({len(mutated_annex)}):")
        for key, prev_txt, curr_txt in mutated_annex[:10]:
            print(f"  * {key}:")
            print(f"    Prev: {repr(prev_txt)[:80]}")
            print(f"    Curr: {repr(curr_txt)[:80]}")
        if len(mutated_annex) > 10:
            print(f"  ... and {len(mutated_annex) - 10} more")

def main():
    parser = argparse.ArgumentParser(description="Diff stacked contract builds")
    parser.add_argument("--curr_dir", default="/Users/owenwarwick/lcha/contracts/parsed_outputs/parser_separation", help="Current output dir")
    parser.add_argument("--prev_dir", default="/Users/owenwarwick/lcha/contracts/parsed_outputs/parser_separation/previous", help="Previous output dir")
    args = parser.parse_args()

    curr_dir = Path(args.curr_dir)
    prev_dir = Path(args.prev_dir)

    curr_files = sorted(list(curr_dir.glob("*.json")))
    for curr_path in curr_files:
        prev_path = prev_dir / curr_path.name
        if prev_path.exists():
            diff_document(curr_path, prev_path)
        else:
            print(f"\n[Warning] Previous build for {curr_path.name} not found in {prev_dir}")

if __name__ == "__main__":
    main()
