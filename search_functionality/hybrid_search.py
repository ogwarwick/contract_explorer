#!/usr/bin/env python3
"""
Legal Hybrid Search Engine: Dense Vectors (pgvector) + Lexical BM25 (PostgreSQL FTS) 
+ Reciprocal Rank Fusion (RRF) + Isaacus Cross-Encoder Reranker.

Usage:
    /Users/owenwarwick/.local/bin/uv run python search_functionality/hybrid_search.py "Your legal query"
    /Users/owenwarwick/.local/bin/uv run python search_functionality/hybrid_search.py "Force Majeure notice" --scheme "LCHA" --top_k 5
"""

import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(WORKSPACE_ROOT / ".env")

sys.path.insert(0, str(WORKSPACE_ROOT / "search_functionality"))
from isaacus import Isaacus
from config import Config

Config.validate()
client = Isaacus(api_key=Config.ISAACUS_API_KEY)
CACHE_DIR = WORKSPACE_ROOT / "search_functionality" / "data" / "chunk_cache"


def get_dense_candidates(query_vector: list, scheme_filter: str = None, doc_key_filter: int = None, candidate_limit: int = 25):
    """Retrieves top candidate chunks using dense vector cosine distance."""
    with psycopg.connect("dbname=lcha") as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            params = [query_vector]
            where_clauses = []
            if doc_key_filter is not None:
                where_clauses.append("c.document_key = %s")
                params.append(doc_key_filter)
            elif scheme_filter and scheme_filter.strip():
                sf = scheme_filter.strip()
                where_clauses.append("(d.scheme ILIKE %s OR d.title ILIKE %s OR d.document_id ILIKE %s)")
                params.extend([f"%{sf}%", f"%{sf}%", f"%{sf}%"])
                
            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            params.extend([query_vector, candidate_limit])
            
            sql = f"""
                SELECT 
                    c.chunk_uid,
                    c.source_uid,
                    c.document_key,
                    d.title AS doc_title,
                    d.scheme,
                    d.round,
                    c.breadcrumb,
                    c.enriched_subtitle,
                    c.clause_range,
                    c.sequence_index,
                    c.total_parts,
                    c.text_sha256,
                    c.summary AS chunk_summary,
                    n.title AS condition_title,
                    n.number AS condition_number,
                    n.page_start,
                    n.page_end,
                    (1 - (e.vector <=> %s::vector)) AS dense_similarity
                FROM chunk c
                JOIN document d ON d.document_key = c.document_key
                JOIN node n ON n.node_uid = c.source_uid
                JOIN embedding e ON e.text_sha256 = c.text_sha256
                {where_sql}
                ORDER BY e.vector <=> %s::vector ASC
                LIMIT %s;
            """
            cur.execute(sql, params)
            return cur.fetchall()


def get_bm25_candidates(query_text: str, scheme_filter: str = None, doc_key_filter: int = None, candidate_limit: int = 25):
    """Retrieves top candidate chunks using PostgreSQL Full-Text Search (BM25 style)."""
    with psycopg.connect("dbname=lcha") as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Build flexible OR tsquery from query lexemes
            cur.execute("""
                SELECT to_tsquery('english', string_agg(lexeme, ' | '))
                FROM unnest(tsvector_to_array(to_tsvector('english', %s))) AS lexeme;
            """, (query_text,))
            or_row = cur.fetchone()
            or_query = or_row["to_tsquery"] if or_row and "to_tsquery" in or_row else None
            
            if not or_query:
                return []
                
            where_params = [or_query, or_query]
            where_clauses = [
                """(
                    to_tsvector('english', coalesce(n.title, '') || ' ' || coalesce(n.text_full, '')) @@ %s
                    OR to_tsvector('english', coalesce(c.breadcrumb, '') || ' ' || coalesce(c.enriched_subtitle, '') || ' ' || coalesce(c.clause_range, '')) @@ %s
                )"""
            ]
            
            if doc_key_filter is not None:
                where_clauses.append("c.document_key = %s")
                where_params.append(doc_key_filter)
            elif scheme_filter and scheme_filter.strip():
                sf = scheme_filter.strip()
                where_clauses.append("(d.scheme ILIKE %s OR d.title ILIKE %s OR d.document_id ILIKE %s)")
                where_params.extend([f"%{sf}%", f"%{sf}%", f"%{sf}%"])
                
            where_sql = f"WHERE {' AND '.join(where_clauses)}"
            # The ranking query is the first placeholder in the SELECT list;
            # the two matching queries follow in the WHERE clause.
            params = [or_query, *where_params, candidate_limit]
            
            sql = f"""
                SELECT 
                    c.chunk_uid,
                    c.source_uid,
                    c.document_key,
                    d.title AS doc_title,
                    d.scheme,
                    d.round,
                    c.breadcrumb,
                    c.enriched_subtitle,
                    c.clause_range,
                    c.sequence_index,
                    c.total_parts,
                    c.text_sha256,
                    c.summary AS chunk_summary,
                    n.title AS condition_title,
                    n.number AS condition_number,
                    n.page_start,
                    n.page_end,
                    ts_rank_cd(to_tsvector('english', coalesce(n.title, '') || ' ' || coalesce(n.text_full, '')), %s) AS bm25_rank_score
                FROM chunk c
                JOIN document d ON d.document_key = c.document_key
                JOIN node n ON n.node_uid = c.source_uid
                {where_sql}
                ORDER BY bm25_rank_score DESC
                LIMIT %s;
            """
            cur.execute(sql, params)
            return cur.fetchall()



def compute_reciprocal_rank_fusion(dense_results: list, bm25_results: list, k: int = 60, dense_weight: float = 1.0, bm25_weight: float = 1.0, max_candidates: int = 20):
    """
    Combines dense vector and BM25 candidate ranks using Reciprocal Rank Fusion (RRF).
    Formula: RRF_Score(d) = sum( weight_m / (k + rank_m(d)) )
    """
    rrf_scores = defaultdict(float)
    chunk_data_map = {}
    dense_ranks = {}
    bm25_ranks = {}
    
    # 1. Score Dense Candidates
    for rank_idx, item in enumerate(dense_results, 1):
        uid = item["chunk_uid"]
        dense_ranks[uid] = rank_idx
        rrf_scores[uid] += dense_weight / (k + rank_idx)
        chunk_data_map[uid] = item
        
    # 2. Score BM25 Candidates
    for rank_idx, item in enumerate(bm25_results, 1):
        uid = item["chunk_uid"]
        bm25_ranks[uid] = rank_idx
        rrf_scores[uid] += bm25_weight / (k + rank_idx)
        if uid not in chunk_data_map:
            chunk_data_map[uid] = item
            
    # 3. Sort by combined RRF score
    sorted_uids = sorted(rrf_scores.keys(), key=lambda u: rrf_scores[u], reverse=True)
    
    fused_candidates = []
    for rrf_rank, uid in enumerate(sorted_uids[:max_candidates], 1):
        item = dict(chunk_data_map[uid])
        item["rrf_rank"] = rrf_rank
        item["rrf_score"] = rrf_scores[uid]
        item["dense_rank"] = dense_ranks.get(uid, None)
        item["dense_similarity"] = item.get("dense_similarity", None)
        item["bm25_rank"] = bm25_ranks.get(uid, None)
        item["bm25_score"] = item.get("bm25_rank_score", None)
        fused_candidates.append(item)
        
    return fused_candidates


def fetch_chunk_text(text_sha256: str, source_uid: str):
    """Loads the cached text payload or falls back to querying the node text from database."""
    cache_file = CACHE_DIR / f"{text_sha256}.txt"
    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            return f.read()
            
    # Fallback to DB
    with psycopg.connect("dbname=lcha") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT breadcrumb || E'\n\n' || text_full FROM node WHERE node_uid = %s", (source_uid,))
            res = cur.fetchone()
            return res[0] if res else ""


def rerank_with_isaacus(query: str, candidates: list, top_k: int = 5):
    """
    Reranks the top fused candidates using Isaacus cross-encoder reranker model.
    """
    if not candidates:
        return []
        
    candidate_texts = []
    for c in candidates:
        text = fetch_chunk_text(c["text_sha256"], c["source_uid"])
        # Truncate text preview for cross-encoder to safe length (e.g. 6,000 chars)
        candidate_texts.append(text[:6000])
        
    try:
        response = client.rerankings.create(
            model="kanon-universal-classifier",
            query=query,
            texts=candidate_texts,
            top_n=min(top_k, len(candidate_texts))
        )
        
        final_results = []
        for res_item in response.results:
            c = candidates[res_item.index].copy()
            c["rerank_score"] = res_item.score
            c["text_preview"] = candidate_texts[res_item.index][:350]
            final_results.append(c)
            
        return final_results
    except Exception as e:
        print(f"  [Warning] Isaacus Reranker call failed ({e}). Falling back to RRF rankings.")
        for idx, c in enumerate(candidates[:top_k], 1):
            c["rerank_score"] = c["rrf_score"]
            c["text_preview"] = fetch_chunk_text(c["text_sha256"], c["source_uid"])[:350]
        return candidates[:top_k]


import re

CONTRACT_ALIASES = [
    (re.compile(r"\b(ar\s*3|allocation\s*round\s*3)\b", re.I), "AR3_Standard_Terms_and_Conditions"),
    (re.compile(r"\b(ar\s*4|allocation\s*round\s*4)\b", re.I), "AR4_Standard_Terms_and_Conditions"),
    (re.compile(r"\b(ar\s*5|allocation\s*round\s*5)\b", re.I), "ar5_standard_terms_and_conditions"),
    (re.compile(r"\b(ar\s*6|allocation\s*round\s*6)\b", re.I), "cfd_ar6_standard_terms_and_conditions"),
    (re.compile(r"\b(ar\s*7|allocation\s*round\s*7)\b", re.I), "AR7_Standard_Terms_and_Conditions_July_2025_8491678118"),
    (re.compile(r"\b(generic\s*cfd|ar\s*1)\b", re.I), "Generic_CfD_TCs_29_August_2014"),
    (re.compile(r"\b(final\s*cfd|ar\s*2|2017\s*cfd)\b", re.I), "FINAL_CFD_Standard_Terms_and_Conditions_V2_13_March_2017"),
    (re.compile(r"\b(ccus\s*icc|icc|industrial\s*carbon\s*capture)\b", re.I), "CCUS_ICC_Standard_Terms_and_Conditions_Template_1_November_2025"),
    (re.compile(r"\b(ccus\s*dpa|dpa|dispatchable\s*power)\b", re.I), "ccus_dpa_standard_terms_and_conditions_november_2022"),
    (re.compile(r"\b(lcha|low\s*carbon\s*hydrogen|hydrogen\s*agreement)\b", re.I), "LCHA"),
    (re.compile(r"\b(ccus|carbon\s*capture)\b", re.I), "CCUS"),
    (re.compile(r"\b(cfd|contracts?\s*for\s*difference)\b", re.I), "CfD"),
]


def extract_contract_filter(query: str, manual_scheme: str = None):
    """
    Automatically detects target contract or scheme from the user's free text query
    if not manually overridden.
    """
    if manual_scheme and manual_scheme.strip():
        return manual_scheme.strip()
        
    for pattern, target in CONTRACT_ALIASES:
        if pattern.search(query):
            return target
            
    return None


def hybrid_search(query: str, top_k: int = 5, scheme: str = None, doc_key: int = None, use_reranker: bool = True, dense_weight: float = 1.0, bm25_weight: float = 1.0):
    """
    End-to-End Hybrid Search function:
    1. Automatic contract / scheme detection from query (or doc_key filter)
    2. Dense embedding query -> pgvector
    3. BM25 query -> PostgreSQL FTS
    4. RRF Fusion
    5. Isaacus Reranking
    """
    effective_scheme = extract_contract_filter(query, manual_scheme=scheme) if doc_key is None else None

    # 1. Embed query with Isaacus
    embed_resp = client.embeddings.create(
        model=Config.ISAACUS_MODEL_ID,
        texts=query,
        task="retrieval/query"
    )
    query_vector = embed_resp.embeddings[0].embedding
    
    # 2. Parallel candidate retrieval
    dense_candidates = get_dense_candidates(query_vector, scheme_filter=effective_scheme, doc_key_filter=doc_key, candidate_limit=25)
    bm25_candidates = get_bm25_candidates(query, scheme_filter=effective_scheme, doc_key_filter=doc_key, candidate_limit=25)
    
    # 3. Reciprocal Rank Fusion (RRF)
    fused = compute_reciprocal_rank_fusion(
        dense_candidates,
        bm25_candidates,
        k=60,
        dense_weight=dense_weight,
        bm25_weight=bm25_weight,
        max_candidates=20
    )
    
    # 4. Isaacus Cross-Encoder Reranker
    if use_reranker:
        final_results = rerank_with_isaacus(query, fused, top_k=top_k)
    else:
        final_results = fused[:top_k]
        for c in final_results:
            c["text_preview"] = fetch_chunk_text(c["text_sha256"], c["source_uid"])[:350]
            c["rerank_score"] = c["rrf_score"]
            
    return {
        "query": query,
        "detected_filter": effective_scheme,
        "dense_count": len(dense_candidates),
        "bm25_count": len(bm25_candidates),
        "fused_count": len(fused),
        "results": final_results
    }


def format_cli_output(search_data: dict):
    query = search_data["query"]
    results = search_data["results"]
    
    print("\n" + "=" * 95)
    print(f"HYBRID LEGAL SEARCH (pgvector + BM25 + RRF + Isaacus Reranker)")
    print(f"QUERY: \"{query}\"")
    print(f"Retrieved: {search_data['dense_count']} Dense, {search_data['bm25_count']} BM25 candidates ➔ Fused {search_data['fused_count']} ➔ Top {len(results)} Reranked")
    print("=" * 95)
    
    for rank, r in enumerate(results, 1):
        rerank_sc = r.get("rerank_score", 0.0)
        rrf_rank = r.get("rrf_rank", "-")
        dense_rk = f"#{r['dense_rank']}" if r.get('dense_rank') else "None"
        bm25_rk = f"#{r['bm25_rank']}" if r.get('bm25_rank') else "None"
        
        doc = r["doc_title"]
        bc = r["breadcrumb"]
        subtitle = r["enriched_subtitle"] or r["condition_title"]
        crange = r["clause_range"]
        seq = r["sequence_index"]
        tot = r["total_parts"]
        uid = r["chunk_uid"]
        preview = r.get("text_preview", "").replace("\n", " ")
        
        chain_tag = f"[Part {seq}/{tot}]" if tot > 1 else "[Single Condition]"
        
        print(f"\n#{rank}  Cross-Encoder Score: {rerank_sc:.4f}  {chain_tag}")
        print(f"    Ranks:       [Rerank: #{rank}] [RRF: #{rrf_rank}] [Dense: {dense_rk}] [BM25: {bm25_rk}]")
        print(f"    Document:    {doc}")
        print(f"    Breadcrumb:  {bc}")
        print(f"    Topic:       {subtitle}")
        print(f"    Scope:       {crange} (Pages {r['page_start']}–{r['page_end']})")
        print(f"    UID:         {uid}")
        print(f"    Snippet:     \"{preview[:220]}...\"")
        
    print("\n" + "=" * 95)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hybrid Search with pgvector, BM25, RRF, and Isaacus Reranker.")
    parser.add_argument("query", nargs="?", default="What constitutes a Qualifying Shutdown Event and who bears the cost?", help="Search query")
    parser.add_argument("--top_k", type=int, default=5, help="Number of final results")
    parser.add_argument("--scheme", type=str, default=None, help="Filter by scheme (e.g. CfD, CCUS, LCHA)")
    parser.add_argument("--no_rerank", action="store_true", help="Disable Isaacus cross-encoder reranker")
    parser.add_argument("--dense_weight", type=float, default=1.0, help="Weight for dense vector candidates in RRF")
    parser.add_argument("--bm25_weight", type=float, default=1.0, help="Weight for BM25 candidates in RRF")
    
    args = parser.parse_args()
    output = hybrid_search(
        query=args.query,
        top_k=args.top_k,
        scheme=args.scheme,
        use_reranker=not args.no_rerank,
        dense_weight=args.dense_weight,
        bm25_weight=args.bm25_weight
    )
    format_cli_output(output)
