#!/usr/bin/env python3
"""Run the reviewable RAG question set and save answers as JSON."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "search_functionality"))
sys.path.insert(0, str(WORKSPACE_ROOT / "web_app"))

from dotenv import load_dotenv

load_dotenv(WORKSPACE_ROOT / ".env")

from hybrid_search import hybrid_search
from llm_service import answer_from_search


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the contract RAG review question set")
    parser.add_argument("--questions", default=str(Path(__file__).with_name("rag_question_set.json")))
    parser.add_argument("--output", default=str(Path(__file__).with_name("rag_qa_results.json")))
    parser.add_argument("--model", default=None, help="Override OPENAI_RAG_MODEL for synthesis questions")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=60, help="OpenAI request timeout in seconds")
    parser.add_argument("--resume", action="store_true", help="Reuse successful records already in the output file")
    args = parser.parse_args()

    if args.model:
        os.environ["OPENAI_RAG_MODEL"] = args.model
    os.environ["OPENAI_RAG_TIMEOUT_SECONDS"] = str(args.timeout)

    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    existing = {}
    if args.resume and Path(args.output).exists():
        prior = json.loads(Path(args.output).read_text(encoding="utf-8"))
        existing = {
            item["id"]: item
            for item in prior.get("results", [])
            if item.get("answer_status") == "retrieval_only"
            or (item.get("answer_status") == "generated" and item.get("answer"))
        }
    results = []
    total = len(questions)

    def save_checkpoint() -> None:
        checkpoint = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": os.getenv("OPENAI_RAG_MODEL", "gpt-5-mini"),
            "question_count": len(results),
            "results": results,
        }
        Path(args.output).write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False), encoding="utf-8")

    for index, item in enumerate(questions, 1):
        if item["id"] in existing:
            results.append(existing[item["id"]])
            print(f"[{index}/{total}] {item['id']}: reused checkpoint", flush=True)
            continue
        question = item["question"]
        started = time.time()
        print(f"[{index}/{total}] {item['id']}: {question}", flush=True)
        try:
            search_data = hybrid_search(query=question, top_k=args.top_k, use_reranker=True)
            answer_data = answer_from_search(question, search_data, mode="auto")
            results.append(
                {
                    **item,
                    **answer_data,
                    "retrieval": {
                        "detected_filter": search_data.get("detected_filter"),
                        "dense_count": search_data.get("dense_count", 0),
                        "bm25_count": search_data.get("bm25_count", 0),
                        "fused_count": search_data.get("fused_count", 0),
                    },
                    "elapsed_seconds": round(time.time() - started, 2),
                }
            )
            print(f"  -> {answer_data['question_type']} / {answer_data['answer_status']}", flush=True)
        except Exception as exc:
            results.append({**item, "question_type": "error", "answer_status": "error", "error": str(exc)})
            print(f"  -> ERROR: {exc}", flush=True)
        save_checkpoint()

    save_checkpoint()
    print(f"\nSaved review file to {args.output}")


if __name__ == "__main__":
    main()
