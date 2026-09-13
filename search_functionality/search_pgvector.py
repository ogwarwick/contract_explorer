#!/usr/bin/env python3
"""
Semantic Search & Condition Retrieval using PostgreSQL + pgvector and Isaacus Kanon 2.

Usage:
    /Users/owenwarwick/.local/bin/uv run python search_functionality/search_pgvector.py "Your query here"
"""

import os
import sys
import argparse
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(WORKSPACE_ROOT / ".env")

sys.path.insert(0, str(WORKSPACE_ROOT / "search_functionality"))
from isaacus import Isaacus
from config import Config

_isaacus_client = None


def get_isaacus_client():
    global _isaacus_client
    if _isaacus_client is None:
        Config.validate()
        _isaacus_client = Isaacus(api_key=Config.ISAACUS_API_KEY)
    return _isaacus_client


def search_pgvector(query: str, top_k: int = 5, scheme_filter: str = None):
    # 1. Embed query with Isaacus (task="retrieval/query")
    client = get_isaacus_client()
    response = client.embeddings.create(
        model=Config.ISAACUS_MODEL_ID,
        texts=query,
        task="retrieval/query"
    )
    query_vector = response.embeddings[0].embedding
    
    # 2. Query PostgreSQL pgvector
    with psycopg.connect(Config.DATABASE_URL) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            params = [query_vector]
            where_clauses = ["d.document_key != 21"]
            if scheme_filter and scheme_filter.strip():
                sf = scheme_filter.strip()
                where_clauses.append("(d.scheme ILIKE %s OR d.title ILIKE %s OR d.document_id ILIKE %s)")
                params.extend([f"%{sf}%", f"%{sf}%", f"%{sf}%"])
            
            where_sql = f"WHERE {' AND '.join(where_clauses)}"
            params.extend([query_vector, top_k])

            
            sql = f"""
                SELECT 
                    d.title AS doc_title,
                    d.scheme,
                    d.round,
                    c.chunk_uid,
                    c.source_uid,
                    c.breadcrumb,
                    c.enriched_subtitle,
                    c.clause_range,
                    c.sequence_index,
                    c.total_parts,
                    n.title AS condition_title,
                    n.page_start,
                    n.page_end,
                    (1 - (e.vector <=> %s::vector)) AS similarity_score
                FROM chunk c
                JOIN document d ON d.document_key = c.document_key
                JOIN node n ON n.node_uid = c.source_uid
                JOIN embedding e ON e.text_sha256 = c.text_sha256
                {where_sql}
                ORDER BY e.vector <=> %s::vector ASC
                LIMIT %s;
            """
            cur.execute(sql, params)
            results = cur.fetchall()

            
    return results

def format_search_results(query: str, results: list):
    print("=" * 80)
    print(f"QUERY: \"{query}\"")
    print(f"Found {len(results)} matching condition chunks in PostgreSQL (pgvector)")
    print("=" * 80)
    
    for rank, r in enumerate(results, 1):
        sim = r["similarity_score"]
        doc = r["doc_title"]
        bc = r["breadcrumb"]
        subtitle = r["enriched_subtitle"] or r["condition_title"]
        crange = r["clause_range"]
        seq = r["sequence_index"]
        total = r["total_parts"]
        p_start = r["page_start"]
        p_end = r["page_end"]
        uid = r["chunk_uid"]
        
        chain_indicator = f"[Part {seq}/{total}]" if total > 1 else "[Single Condition]"
        
        print(f"\n#{rank}  Similarity: {sim:.4f}  {chain_indicator}")
        print(f"    Document:    {doc}")
        print(f"    Breadcrumb:  {bc}")
        print(f"    Topic:       {subtitle}")
        print(f"    Scope:       {crange} (Pages {p_start}–{p_end})")
        print(f"    Chunk UID:   {uid}")
        
    print("\n" + "=" * 80)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search legal contract conditions in PostgreSQL using pgvector.")
    parser.add_argument("query", nargs="?", default="What are the procedures for calculating QCiL True-Up Compensation?", help="Search query")
    parser.add_argument("--top_k", type=int, default=5, help="Number of results to return")
    parser.add_argument("--scheme", type=str, default=None, help="Filter by scheme (e.g. CfD, CCUS, H2)")
    
    args = parser.parse_args()
    res = search_pgvector(args.query, top_k=args.top_k, scheme_filter=args.scheme)
    format_search_results(args.query, res)
