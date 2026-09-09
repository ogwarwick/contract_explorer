#!/usr/bin/env python3
"""
Generate pre-computed 2-sentence plain-English legal executive summaries 
for all 955 contract condition chunks using OpenAI API.

Stores results in PostgreSQL `chunk.summary` column.
"""

import os
import sys
import time
import asyncio
from pathlib import Path
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row
from openai import AsyncOpenAI

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(WORKSPACE_ROOT / ".env")

API_KEY = os.getenv("OPEN_AI_KEY") or os.getenv("OPENAI_API_KEY")
if not API_KEY:
    raise ValueError("OPEN_AI_KEY not found in .env file")

client = AsyncOpenAI(api_key=API_KEY)
CACHE_DIR = WORKSPACE_ROOT / "search_functionality" / "data" / "chunk_cache"
CONCURRENCY_LIMIT = 6

SYSTEM_PROMPT = """You are a senior UK energy and infrastructure legal analyst specializing in CfD, CCUS, and LCHA contracts.
Given the contract condition/clause text, provide a concise 2-sentence plain-English executive summary for non-expert commercial users:
- Sentence 1: State the core legal/contractual mechanism, rights, or relief established by this condition.
- Sentence 2: State the primary operational trigger, notice requirements, timelines, or financial/legal consequences.

Guidelines:
- Keep it under 40-50 words total.
- Be crisp, direct, and legally precise.
- Do NOT use filler phrases like 'This condition outlines...', 'This clause states...', or 'In summary...'. Start directly with the core action/rule."""


async def generate_single_summary(semaphore, chunk_uid: str, text: str, breadcrumb: str, subtitle: str) -> str:
    async with semaphore:
        prompt_text = f"Breadcrumb: {breadcrumb}\nTopic: {subtitle}\n\nContract Clause Content:\n{text[:4500]}"
        for attempt in range(4):
            try:
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt_text}
                    ],
                    max_tokens=100,
                    temperature=0.2,
                )
                summary = response.choices[0].message.content.strip()
                return summary
            except Exception as e:
                wait_time = (2 ** attempt) + 0.5
                print(f"  [Warning] Retry {attempt+1}/4 for {chunk_uid} after error: {e} (waiting {wait_time:.1f}s)")
                await asyncio.sleep(wait_time)
        return ""


async def run_batch():
    # 1. Fetch chunks needing summary
    with psycopg.connect("dbname=lcha") as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT 
                    c.chunk_uid,
                    c.source_uid,
                    c.text_sha256,
                    c.breadcrumb,
                    c.enriched_subtitle,
                    n.title AS node_title
                FROM chunk c
                JOIN node n ON n.node_uid = c.source_uid
                WHERE c.summary IS NULL OR c.summary = ''
                ORDER BY c.document_key, c.sequence_index;
            """)
            chunks_to_process = cur.fetchall()

    total = len(chunks_to_process)
    print(f"Found {total} chunks needing plain-English summaries.")
    if total == 0:
        print("All chunks already have summaries! Nothing to do.")
        return

    # 2. Process concurrently with Semaphore
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    start_time = time.time()
    completed_count = 0

    async def process_and_save(item):
        nonlocal completed_count
        uid = item["chunk_uid"]
        sha = item["text_sha256"]
        bc = item["breadcrumb"]
        subtitle = item["enriched_subtitle"] or item["node_title"] or ""

        # Load text from cache or DB
        cache_file = CACHE_DIR / f"{sha}.txt"
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                raw_text = f.read()
        else:
            raw_text = bc

        summary = await generate_single_summary(semaphore, uid, raw_text, bc, subtitle)
        if summary:
            # Update DB with thread-safe / separate connection
            with psycopg.connect("dbname=lcha", autocommit=True) as db_conn:
                with db_conn.cursor() as cur:
                    cur.execute("UPDATE chunk SET summary = %s WHERE chunk_uid = %s;", (summary, uid))

        completed_count += 1
        if completed_count % 25 == 0 or completed_count == total:
            elapsed = time.time() - start_time
            rate = completed_count / elapsed if elapsed > 0 else 0
            print(f"  Progress: {completed_count}/{total} chunks completed ({completed_count/total*100:.1f}%) — {rate:.1f} chunks/sec")

    tasks = [process_and_save(item) for item in chunks_to_process]
    await asyncio.gather(*tasks)

    total_time = time.time() - start_time
    print(f"\nSuccessfully generated and stored summaries for {completed_count} chunks in {total_time:.1f} seconds!")


if __name__ == "__main__":
    asyncio.run(run_batch())
