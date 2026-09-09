import os
import sys
import math
import time
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
import numpy as np

# Add path for Isaacus SDK
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "search_functionality"))
from isaacus import Isaacus
from config import Config

Config.validate()
client = Isaacus(api_key=Config.ISAACUS_API_KEY)

# 50 Contract related queries
BENCHMARK_QUERIES = [
    # Milestones & Delivery
    "What happens if the producer misses a milestone?",
    "What is the Milestone Delivery Date?",
    "How does the producer prove milestone compliance?",
    "What is the Milestone Satisfaction Date?",
    "When does the Milestone Delivery Period end?",
    # Strike Price & Inflation
    "How are strike prices adjusted for inflation?",
    "What is the Non-Gas Strike Price?",
    "How is the Indexation Adjustment calculated?",
    "What is the Strike Price Adjustment?",
    "When does the Strike Price Adjustment take effect?",
    "What happens if the indexation factor is negative?",
    # Change in Law
    "What is a qualifying change in law?",
    "What is a QCiL Construction Event?",
    "What is a QCiL Operations Cessation Event?",
    "How are QCiL Capital Costs calculated?",
    "What is a QCiL Strike Price Adjustment?",
    "How does the LCHA Counterparty notify the Producer of a QCiL?",
    "What is a QCiL Net Capital Saving?",
    # Termination & Breach
    "What are the termination rights for breach of contract?",
    "What is a Default Termination Event?",
    "How does the LCHA Counterparty issue a Default Termination Notice?",
    "What is the Termination Fees calculation?",
    "Can the Producer terminate for LCHA Counterparty Default?",
    "What is the Pre-Start Date termination fee?",
    # Force Majeure
    "What happens if there's a force majeure event?",
    "What is the Definition of Force Majeure?",
    "Can prolonged force majeure lead to termination?",
    "How long is the Prolonged Force Majeure period?",
    "Are carbon costs payable during force majeure?",
    # Conditions Precedent
    "What are the conditions precedent?",
    "What is the Initial Condition Precedent?",
    "What is the Operational Condition Precedent?",
    "When is the Longstop Date?",
    "How can the LCHA Counterparty waive a Condition Precedent?",
    # Carbon & Electricity
    "How are carbon costs handled?",
    "What is the Carbon Cost Protection Amount?",
    "How is the carbon price source defined?",
    "What happens if the carbon cost protection is triggered?",
    "What are the electricity market rules under LCHA?",
    # Reporting & KYC
    "What are the producer's reporting obligations?",
    "How does a Producer issue a KYC Notice?",
    "What details must be in a KYC Notice?",
    "What is a Change of Ownership under LCHA?",
    "What is a Relevant Change of Control?",
    "When does a Producer provide a Directors' Certificate?",
    # Disputes & Experts
    "How does the dispute resolution procedure work?",
    "When is a dispute referred to an Expert?",
    "How is the Expert selected?",
    "What is the Expert Determination Procedure?",
    "Can an Expert decision be appealed?",
    "What is the role of the Arbitration Act?"
]

def get_db_connection():
    conn_str = os.getenv("PGCONNSTR")
    if conn_str:
        return psycopg.connect(conn_str)
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    dbname = os.getenv("PGDATABASE", "lcha")
    user = os.getenv("PGUSER", "owenwarwick")
    password = os.getenv("PGPASSWORD", "")
    return psycopg.connect(host=host, port=port, dbname=dbname, user=user, password=password)

def truncate_and_normalize(vector, dimensions=1024):
    truncated = vector[:dimensions]
    sq_sum = sum(x*x for x in truncated)
    if sq_sum == 0:
        return truncated
    norm = math.sqrt(sq_sum)
    return [float(x / norm) for x in truncated]

def run_benchmark():
    print("==================================================")
    print("RUNNING 50-QUERY RECALL@10 DIMENSIONAL BENCHMARK")
    print("==================================================")
    
    conn = get_db_connection()
    
    # 1. Load all database embeddings
    print("Loading database vectors...")
    with conn.cursor(row_factory=dict_row) as cur:
        # Load chunks and their embeddings
        cur.execute(
            """
            SELECT c.chunk_uid, e.vector, e.vector_idx 
            FROM chunk c
            JOIN embedding e ON e.text_sha256 = c.text_sha256
            JOIN document d ON d.document_key = c.document_key
            WHERE d.is_current = true
            """
        )
        rows = cur.fetchall()
        
    if not rows:
        print("Error: No active chunks or embeddings found in the database. Please run the loader first.")
        conn.close()
        return
        
    print(f"Loaded {len(rows)} active document chunks from DB.")
    
    # Parse vectors into numpy arrays for fast calculations
    chunk_uids = [r["chunk_uid"] for r in rows]
    
    # Convert vectors from DB format (vector and halfvec are returned as string or float lists depending on driver)
    # psycopg pgvector returns string representations '[x1,x2,...]' or lists. Let's parse string representations:
    def parse_vector(val):
        if isinstance(val, str):
            return np.array([float(x) for x in val.strip("[]").split(",")], dtype=np.float32)
        elif isinstance(val, list):
            return np.array(val, dtype=np.float32)
        return np.array(val, dtype=np.float32)
        
    db_vectors_1792 = np.vstack([parse_vector(r["vector"]) for r in rows])
    db_vectors_1024 = np.vstack([parse_vector(r["vector_idx"]) for r in rows])
    
    overlaps = []
    rank_diffs = []
    
    print("\nProcessing benchmark queries...")
    for q_idx, query in enumerate(BENCHMARK_QUERIES, 1):
        print(f"  [{q_idx}/50] Querying: {query[:50]}...", end="\r")
        
        # Get query embedding
        max_retries = 3
        q_vec_1792 = None
        for attempt in range(max_retries):
            try:
                response = client.embeddings.create(
                    model=Config.ISAACUS_MODEL_ID,
                    texts=[query],
                    task="retrieval/query",
                )
                q_vec_1792 = np.array(response.embeddings[0].embedding, dtype=np.float32)
                break
            except Exception as e:
                time.sleep(2 ** attempt)
                
        if q_vec_1792 is None:
            print(f"\nFailed to embed query: {query}")
            continue
            
        # Truncate and re-normalise client-side
        q_vec_1024 = truncate_and_normalize(q_vec_1792.tolist(), 1024)
        q_vec_1024 = np.array(q_vec_1024, dtype=np.float32)
        
        # Normalize for safety
        q_vec_1792 = q_vec_1792 / np.linalg.norm(q_vec_1792)
        q_vec_1024 = q_vec_1024 / np.linalg.norm(q_vec_1024)
        
        # Calculate cosine similarities (inner products)
        scores_1792 = np.dot(db_vectors_1792, q_vec_1792)
        scores_1024 = np.dot(db_vectors_1024, q_vec_1024)
        
        # Sort indices (descending similarity)
        top_10_idx_1792 = np.argsort(scores_1792)[::-1][:10]
        top_10_idx_1024 = np.argsort(scores_1024)[::-1][:10]
        
        # Get top 10 UIDs
        top_1792_uids = [chunk_uids[idx] for idx in top_10_idx_1792]
        top_1024_uids = [chunk_uids[idx] for idx in top_10_idx_1024]
        
        # Compute overlap
        intersection = set(top_1792_uids) & set(top_1024_uids)
        overlap = len(intersection) / 10.0
        overlaps.append(overlap)
        
        # Compute rank correlation of top items
        # Let's map elements to their 1792 ranks
        rank_1792_map = {uid: rank for rank, uid in enumerate(top_1792_uids)}
        diff = 0
        match_count = 0
        for rank_1024, uid in enumerate(top_1024_uids):
            if uid in rank_1792_map:
                diff += abs(rank_1024 - rank_1792_map[uid])
                match_count += 1
        if match_count > 0:
            mean_rank_diff = diff / match_count
            rank_diffs.append(mean_rank_diff)
            
    mean_overlap = np.mean(overlaps) * 100.0
    mean_rank_diff = np.mean(rank_diffs) if rank_diffs else 0.0
    
    print("\n\n==================================================")
    print("BENCHMARK RESULTS")
    print("==================================================")
    print(f"Total Queries Evaluated:    {len(overlaps)}")
    print(f"Mean Recall@10 Stability:   {mean_overlap:.2f}%")
    print(f"Mean Top-10 Rank Shift:     {mean_rank_diff:.2f} positions")
    print("==================================================")
    
    # Assert acceptable recall stability
    ACCEPTABLE_THRESHOLD = 90.0 # 90% overlap
    if mean_overlap >= ACCEPTABLE_THRESHOLD:
        print(f"PASS: Recall stability exceeds threshold of {ACCEPTABLE_THRESHOLD}%.")
        print("Proceeding to create HNSW index...")
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("DROP INDEX IF EXISTS embedding_hnsw_idx")
                cur.execute(
                    """
                    CREATE INDEX embedding_hnsw_idx ON embedding
                    USING hnsw (vector_idx halfvec_cosine_ops)
                    WITH (m = 16, ef_construction = 64)
                    """
                )
        print("HNSW index created successfully!")
    else:
        print(f"FAIL: Recall stability is {mean_overlap:.2f}%, below {ACCEPTABLE_THRESHOLD}%.")
        print("Index creation aborted.")
        
    conn.close()

if __name__ == "__main__":
    run_benchmark()
