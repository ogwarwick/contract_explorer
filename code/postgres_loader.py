import os
import sys
import json
import hashlib
import time
import math
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

# Add path for Isaacus SDK & Config
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "search_functionality"))
from isaacus import Isaacus
from config import Config

Config.validate()
client = Isaacus(api_key=Config.ISAACUS_API_KEY)

MAX_CONDITION_CHARS = 40000
ENRICHED_DIR = WORKSPACE_ROOT / "contracts" / "enriched_outputs"

def get_db_connection():
    conn_str = os.getenv("PGCONNSTR")
    if conn_str:
        return psycopg.connect(conn_str, autocommit=True)
    
    # Connect directly to local database
    return psycopg.connect("dbname=lcha", autocommit=True)


def truncate_and_normalize(vector, dimensions=1024):
    truncated = vector[:dimensions]
    sq_sum = sum(x*x for x in truncated)
    if sq_sum == 0:
        return truncated
    norm = math.sqrt(sq_sum)
    return [float(x / norm) for x in truncated]

def init_db(conn):
    schema_path = Path(__file__).resolve().parent / "parser_separation" / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()
    print("Database schema initialized successfully.")

def get_subtree_text_and_clauses(node):
    """Recursively collect full condition text and distinct child clauses."""
    texts = []
    clauses = []
    
    def walk(n):
        kind = n.get("kind", "")
        title = n.get("title", "").strip()
        num = n.get("number", "")
        t_full = n.get("text_full", "").strip()
        
        c_text = t_full if t_full else title
        if c_text:
            texts.append(c_text)
            
        if kind in ("clause", "subclause", "text", "subtitle") and c_text:
            clauses.append({
                "kind": kind,
                "number": num,
                "title": title,
                "text": c_text,
                "char_length": len(c_text)
            })
            
        for ch in n.get("children", []):
            walk(ch)
            
    walk(node)
    return "\n\n".join(texts), clauses

def load_enricher_segments(doc_id):
    """Finds and loads the matching Isaacus Enricher JSON for a document."""
    matched = list(ENRICHED_DIR.glob(f"*{doc_id}*_enriched.json"))
    if not matched:
        # Try finding by relaxed pattern
        for f in ENRICHED_DIR.glob("*_enriched.json"):
            if doc_id.lower().replace("-", "_").replace(" ", "_") in f.name.lower().replace("-", "_").replace(" ", "_"):
                matched = [f]
                break
                
    if not matched:
        return None, None
        
    with open(matched[0], "r", encoding="utf-8") as f:
        data = json.load(f)
        
    doc = data.get("results", [{}])[0].get("document", {})
    return doc.get("text", ""), doc.get("segments", [])

def build_condition_chunks(condition_node, doc_id, doc_title, doc_key, parser_version, enriched_text, enriched_segments):
    """
    Creates 1 or N chunks for a condition.
    - If <= MAX_CONDITION_CHARS: 1 chunk
    - If > MAX_CONDITION_CHARS: Slices via Enricher segments & partitions into chained parts.
    """
    cond_num = condition_node.get("number") or ""
    cond_title = condition_node.get("title") or ""
    cond_breadcrumb = condition_node.get("breadcrumb") or f"Condition {cond_num}"
    node_uid = condition_node.get("node_uid")
    
    full_text, clauses = get_subtree_clauses_from_node(condition_node)
    total_chars = len(full_text)
    
    # -------------------------------------------------------------
    # CASE 1: Standard Condition (Fits in Kanon 2)
    # -------------------------------------------------------------
def get_condition_enricher_subtitles(cond_num, cond_title, enriched_text, enriched_segments):
    """Finds enricher sub-container titles belonging strictly to this condition."""
    if not enriched_segments or not enriched_text:
        return []
        
    seg_map = {s["id"]: s for s in enriched_segments if "id" in s}
    subtitles = []
    
    cond_title_clean = cond_title.lower().strip()
    cond_num_str = str(cond_num).strip() if cond_num else ""
    
    for s in enriched_segments:
        if s.get("kind") == "container":
            t_span = s.get("title")
            c_span = s.get("code")
            stitle = enriched_text[t_span["start"]:t_span["end"]].strip() if t_span else ""
            scode = enriched_text[c_span["start"]:c_span["end"]].strip() if c_span else ""
            
            # Match condition container
            is_match = False
            if cond_title_clean and cond_title_clean in stitle.lower() and "definition" not in stitle.lower():
                is_match = True
            elif cond_num_str and (scode == cond_num_str or scode == f"Condition {cond_num_str}"):
                is_match = True
                
            if is_match:
                # Extract child container titles
                for cid in s.get("children", []):
                    child = seg_map.get(cid)
                    if child and child.get("title"):
                        ct_span = child["title"]
                        ctitle = enriched_text[ct_span["start"]:ct_span["end"]].strip()
                        if ctitle and ctitle not in subtitles:
                            subtitles.append(ctitle)
                            
    return subtitles

def build_condition_chunks(condition_node, doc_id, doc_title, doc_key, parser_version, enriched_text, enriched_segments):
    """
    Creates 1 or N chunks for a condition.
    - If <= MAX_CONDITION_CHARS: 1 chunk
    - If > MAX_CONDITION_CHARS: Slices via Enricher segments & partitions into chained parts.
    """
    cond_num = condition_node.get("number") or ""
    cond_title = condition_node.get("title") or ""
    cond_breadcrumb = condition_node.get("breadcrumb") or f"Condition {cond_num}"
    node_uid = condition_node.get("node_uid")
    
    full_text, clauses = get_subtree_clauses_from_node(condition_node)
    total_chars = len(full_text)
    
    # -------------------------------------------------------------
    # CASE 1: Standard Condition (Fits in Kanon 2)
    # -------------------------------------------------------------
    if total_chars <= MAX_CONDITION_CHARS or not clauses:
        header = f"[{doc_title}] > {cond_breadcrumb} > {cond_title}"
        text_to_embed = f"{header}\n\n{full_text}"
        sha256 = hashlib.sha256(text_to_embed.encode("utf-8")).hexdigest()
        
        return [{
            "chunk_uid": f"{node_uid}",
            "document_key": doc_key,
            "source_table": "node",
            "source_uid": node_uid,
            "text_sha256": sha256,
            "char_length": len(text_to_embed),
            "breadcrumb": cond_breadcrumb,
            "page_start": condition_node.get("page_start"),
            "page_end": condition_node.get("page_end"),
            "sequence_index": 1,
            "total_parts": 1,
            "clause_range": f"Condition {cond_num}",
            "enriched_subtitle": cond_title,
            "text_to_embed": text_to_embed
        }]
        
    # -------------------------------------------------------------
    # CASE 2: Oversized Condition -> Partition along Enricher / Clause groups
    # -------------------------------------------------------------
    print(f"    [Oversized Condition {cond_num}] {total_chars:,} chars -> Partitioning into sub-chunks...")
    
    # Query matching enricher sub-containers specifically for this condition
    enricher_subtitles = get_condition_enricher_subtitles(cond_num, cond_title, enriched_text, enriched_segments)
                    
    # Partition clauses into <= MAX_CONDITION_CHARS groups
    clause_groups = []
    current_group = []
    current_len = 0
    
    for cl in clauses:
        if current_len + cl["char_length"] > MAX_CONDITION_CHARS and current_group:
            clause_groups.append(current_group)
            current_group = [cl]
            current_len = cl["char_length"]
        else:
            current_group.append(cl)
            current_len += cl["char_length"]
            
    if current_group:
        clause_groups.append(current_group)
        
    total_parts = len(clause_groups)
    chunks = []
    
    for idx, grp in enumerate(clause_groups, 1):
        first_num = grp[0].get("number") or grp[0].get("title", "")[:15]
        last_num = grp[-1].get("number") or grp[-1].get("title", "")[:15]
        clause_range = f"Clauses {first_num} to {last_num}" if first_num != last_num else f"Clause {first_num}"
        
        # Subtitle: use matched enricher subtitle or fall back cleanly to condition title
        subtitle = enricher_subtitles[idx-1] if (idx-1 < len(enricher_subtitles)) else cond_title
        subtitle_hdr = f": {subtitle}" if subtitle else ""
        
        header = f"[{doc_title}] > {cond_breadcrumb} (Part {idx}/{total_parts}{subtitle_hdr} - {clause_range})"
        body = "\n\n".join(c["text"] for c in grp)
        text_to_embed = f"{header}\n\n{body}"
        sha256 = hashlib.sha256(text_to_embed.encode("utf-8")).hexdigest()
        
        chunks.append({
            "chunk_uid": f"{node_uid}:part_{idx}",
            "document_key": doc_key,
            "source_table": "node",
            "source_uid": node_uid,
            "text_sha256": sha256,
            "char_length": len(text_to_embed),
            "breadcrumb": f"{cond_breadcrumb} (Part {idx}/{total_parts})",
            "page_start": condition_node.get("page_start"),
            "page_end": condition_node.get("page_end"),
            "sequence_index": idx,
            "total_parts": total_parts,
            "clause_range": clause_range,
            "enriched_subtitle": subtitle,
            "text_to_embed": text_to_embed
        })

        
    return chunks

def get_subtree_clauses_from_node(node):
    texts = []
    clauses = []
    
    def walk(n):
        kind = n.get("kind", "")
        title = n.get("title", "").strip()
        num = n.get("number", "")
        t_full = n.get("text_full", "").strip()
        
        c_text = t_full if t_full else title
        if c_text:
            texts.append(c_text)
            
        if kind in ("clause", "subclause", "text", "subtitle") and c_text:
            clauses.append({
                "kind": kind,
                "number": num,
                "title": title,
                "text": c_text,
                "char_length": len(c_text)
            })
            
        for ch in n.get("children", []):
            walk(ch)
            
    walk(node)
    return "\n\n".join(texts), clauses

def walk_and_populate_nodes(node, parent_uid, doc_key, ordinal_index, nodes_list, chunks_list, document_id, doc_title, parser_version, enriched_text, enriched_segments):
    kind = node.get("kind")
    number = node.get("number")
    line_id = node.get("line_id")
    
    if number == "":
        number = None
        
    if line_id is not None:
        node_uid = f"{document_id}:{parser_version}:{line_id}"
    else:
        node_uid = f"{document_id}:{parser_version}:{kind}:{number or ''}:{ordinal_index}"
        
    title = node.get("title", "")
    text_full = node.get("text_full", "")
    text_sha256 = node.get("text_sha256")
    if not text_sha256:
        norm_text = " ".join(title.lower().split())
        text_sha256 = hashlib.sha256(norm_text.encode('utf-8')).hexdigest()
        
    node["node_uid"] = node_uid
    
    nodes_list.append({
        "node_uid": node_uid,
        "document_key": doc_key,
        "parent_uid": parent_uid,
        "line_id": line_id,
        "kind": kind,
        "depth": node.get("depth", 0),
        "label_depth": node.get("label_depth"),
        "series": node.get("series"),
        "number": number,
        "title": title,
        "text_full": text_full,
        "text_sha256": text_sha256,
        "breadcrumb": node.get("breadcrumb"),
        "page_start": node.get("page_start"),
        "page_end": node.get("page_end"),
        "absorbed": node.get("absorbed"),
        "provenance": node.get("provenance"),
        "ordinal": ordinal_index
    })
    
    # Embed at CONDITION LEVEL (Excluding Condition 1 / Definitions)
    is_defs = kind == "definition" or "definition" in title.lower() or (kind == "condition" and number == "1")
    if kind == "condition" and not is_defs:
        cond_chunks = build_condition_chunks(
            node, document_id, doc_title, doc_key, parser_version, enriched_text, enriched_segments
        )
        chunks_list.extend(cond_chunks)
        
    for idx, child in enumerate(node.get("children", [])):
        walk_and_populate_nodes(
            child, node_uid, doc_key, idx + 1, nodes_list, chunks_list, document_id, doc_title, parser_version, enriched_text, enriched_segments
        )

def load_document(conn, json_path, baselines):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    doc_meta = data["document"]
    document_id = doc_meta["id"]
    doc_title = doc_meta["title"]
    source_sha256 = doc_meta["source_sha256"]
    parser_version = doc_meta["parser_version"]
    
    print(f"\n==================================================")
    print(f"Loading Contract: {doc_title} (ID: {document_id})")
    print(f"==================================================")
    
    # Load corresponding enricher output if available
    enriched_text, enriched_segments = load_enricher_segments(document_id)
    if enriched_segments:
        print(f"  [Enricher] Loaded {len(enriched_segments)} enricher segments for boundary guidance.")
    else:
        print("  [Enricher] No pre-computed enricher JSON found; using standard syntactic boundaries.")
        
    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            # Check if this exact document & parser version is already loaded
            cur.execute(
                "SELECT document_key FROM document WHERE document_id = %s AND source_sha256 = %s AND parser_version = %s",
                (document_id, source_sha256, parser_version)
            )
            row = cur.fetchone()
            if row:
                print(f"  [Cache Hit] Document {document_id} already loaded (Key: {row['document_key']}). Skipping.")
                return False, row["document_key"], None
                
            cur.execute(
                "SELECT document_key FROM document WHERE document_id = %s AND is_current = true",
                (document_id,)
            )
            prior_doc = cur.fetchone()
            prior_key = prior_doc["document_key"] if prior_doc else None
            
            cur.execute("UPDATE document SET is_current = false WHERE document_id = %s", (document_id,))
            
            cur.execute(
                """
                INSERT INTO document (
                    document_id, title, scheme, round, version, source_file, source_sha256, 
                    page_count, parser_version, config_profile, parsed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING document_key
                """,
                (
                    document_id, doc_title, doc_meta.get("scheme", "CfD"), doc_meta.get("round"), 
                    doc_meta.get("version"), doc_meta.get("source_file", json_path.name), source_sha256, 
                    doc_meta.get("page_count"), parser_version, doc_meta.get("config_profile"), 
                    doc_meta["parsed_at"]
                )
            )
            doc_key = cur.fetchone()["document_key"]
            
            nodes_list = []
            chunks_list = []
            
            walk_and_populate_nodes(
                data["main_body"], None, doc_key, 1, nodes_list, chunks_list, document_id, doc_title, parser_version, enriched_text, enriched_segments
            )
            
            print(f"  Inserting {len(nodes_list):,} nodes and {len(chunks_list)} condition chunks into PostgreSQL...")
            
            # Bulk Insert Nodes
            for node in nodes_list:
                cur.execute(
                    """
                    INSERT INTO node (
                        node_uid, document_key, parent_uid, line_id, kind, depth, label_depth, 
                        series, number, title, text_full, text_sha256, breadcrumb, 
                        page_start, page_end, absorbed, provenance, ordinal
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        node["node_uid"], node["document_key"], node["parent_uid"], node["line_id"],
                        node["kind"], node["depth"], node["label_depth"], node["series"],
                        node["number"], node["title"], node["text_full"], node["text_sha256"],
                        node["breadcrumb"], node["page_start"], node["page_end"],
                        node["absorbed"], json.dumps(node["provenance"]) if node["provenance"] else None,
                        node["ordinal"]
                    )
                )
                
            # Bulk Insert Chunks
            for chunk in chunks_list:
                cur.execute(
                    """
                    INSERT INTO chunk (
                        chunk_uid, document_key, source_table, source_uid, text_sha256, 
                        char_length, breadcrumb, page_start, page_end,
                        sequence_index, total_parts, clause_range, enriched_subtitle
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chunk["chunk_uid"], chunk["document_key"], chunk["source_table"],
                        chunk["source_uid"], chunk["text_sha256"], chunk["char_length"],
                        chunk["breadcrumb"], chunk["page_start"], chunk["page_end"],
                        chunk["sequence_index"], chunk["total_parts"], chunk["clause_range"],
                        chunk["enriched_subtitle"]
                    )
                )
                
            # Save chunk payloads into temporary cache for embedding worker
            save_chunk_payloads_to_cache(chunks_list)
            
            print(f"  [Pass] Successfully loaded {doc_title} (Document Key: {doc_key}).")
            return True, doc_key, prior_key

def save_chunk_payloads_to_cache(chunks_list):
    """Saves text_to_embed payloads to a local cache folder so embedding worker has the full text."""
    cache_dir = WORKSPACE_ROOT / "search_functionality" / "data" / "chunk_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    for c in chunks_list:
        p = cache_dir / f"{c['text_sha256']}.txt"
        if not p.exists():
            with open(p, "w", encoding="utf-8") as fp:
                fp.write(c["text_to_embed"])

def embed_pending_chunks(conn):
    """Fetches all chunk hashes lacking an embedding and sends batches to Isaacus Kanon 2."""
    print("\n==================================================")
    print("STARTING ISAACUS KANON 2 EMBEDDING WORKER")
    print("==================================================")
    
    cache_dir = WORKSPACE_ROOT / "search_functionality" / "data" / "chunk_cache"
    
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT c.text_sha256 
            FROM chunk c 
            LEFT JOIN embedding e ON e.text_sha256 = c.text_sha256 
            WHERE e.text_sha256 IS NULL
            """
        )
        queue = [r["text_sha256"] for r in cur.fetchall()]
        
    total = len(queue)
    if total == 0:
        print("  ✓ All chunks in database already have embeddings in pgvector.")
        return
        
    print(f"  Found {total} distinct condition chunks requiring embeddings.")
    batch_size = 10  # Isaacus recommend batch size
    
    for i in range(0, total, batch_size):
        batch_hashes = queue[i:i+batch_size]
        batch_texts = []
        valid_hashes = []
        
        for h in batch_hashes:
            cache_file = cache_dir / f"{h}.txt"
            if cache_file.exists():
                with open(cache_file, "r", encoding="utf-8") as fp:
                    batch_texts.append(fp.read())
                    valid_hashes.append(h)
                    
        if not batch_texts:
            continue
            
        print(f"    Sending Batch {i // batch_size + 1} / {math.ceil(total / batch_size)} ({len(batch_texts)} texts)...")
        
        max_retries = 3
        vectors = None
        input_tokens = 0
        
        for attempt in range(max_retries):
            try:
                response = client.embeddings.create(
                    model=Config.ISAACUS_MODEL_ID,
                    texts=batch_texts,
                    task="retrieval/document",
                )
                vectors = [item.embedding for item in response.embeddings]
                input_tokens = getattr(response.usage, "input_tokens", 0)
                break
            except Exception as e:
                print(f"      [Retry {attempt+1}] API call failed: {e}")
                time.sleep(2 ** attempt + 1)
                
        if vectors:
            with conn.cursor() as cur:
                for h, vec in zip(valid_hashes, vectors):
                    vector_idx = truncate_and_normalize(vec, 1024)
                    cur.execute(
                        """
                        INSERT INTO embedding (text_sha256, model, dimensions, task, vector, vector_idx, input_tokens)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (text_sha256, model, dimensions, task) DO NOTHING
                        """,
                        (
                            h, Config.ISAACUS_MODEL_ID, 1792, "retrieval/document",
                            vec, vector_idx, input_tokens // len(batch_texts) if len(batch_texts) > 0 else 0
                        )
                    )
                    
    print(f"\n  ✓ Successfully generated and inserted {total} vectors into pgvector.")


def main():
    print("==================================================")
    print("STARTING FULL CONTRACT INGESTION & PGVECTOR LOADER")
    print("==================================================")
    
    conn = get_db_connection()
    init_db(conn)
    
    outputs_dir = WORKSPACE_ROOT / "contracts" / "parsed_outputs" / "parser_separation" / "final_jsons_040926"
    stacked_files = sorted(list(outputs_dir.glob("*_stacked.json")))
    
    print(f"Found {len(stacked_files)} finalized stacked contract JSONs to process.")
    
    for f in stacked_files:
        load_document(conn, f, {})
        
    # Generate embeddings and populate pgvector
    embed_pending_chunks(conn)
    
    # Verification query
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM document;")
        doc_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM node;")
        node_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM chunk;")
        chunk_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM embedding;")
        emb_count = cur.fetchone()[0]
        
    print("\n==================================================")
    print("POSTGRES INGESTION & PGVECTOR VERIFICATION")
    print("==================================================")
    print(f"  Documents in Database:  {doc_count}")
    print(f"  Total Tree Nodes:       {node_count:,}")
    print(f"  Condition Search Chunks:{chunk_count:,}")
    print(f"  Dense Vectors (pgvector):{emb_count:,}")
    print("==================================================")
    
    conn.close()

if __name__ == "__main__":
    main()
