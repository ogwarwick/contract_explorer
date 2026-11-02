#!/usr/bin/env python3
"""
Retrieval eval for hybrid_search: measures where the gold condition lands at each
pipeline stage (dense, BM25, RRF fusion, reranker) so ranking changes can be compared.

Usage:
    /Users/owenwarwick/.local/bin/uv run python experiments/retrieval_eval/run_retrieval_eval.py --label baseline
    /Users/owenwarwick/.local/bin/uv run python experiments/retrieval_eval/run_retrieval_eval.py --label rrf_only --no_rerank
    /Users/owenwarwick/.local/bin/uv run python experiments/retrieval_eval/run_retrieval_eval.py --compare runs/a.json runs/b.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

EVAL_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = EVAL_DIR.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "search_functionality"))

from config import Config  # noqa: E402
from hybrid_search import hybrid_search  # noqa: E402

RUNS_DIR = EVAL_DIR / "runs"
STAGES = ["dense", "bm25", "rrf", "rerank"]
# Final list returned to the user is reranked from the fused pool; ask for all of it.
FULL_POOL = 20


def load_document_ids():
    with psycopg.connect(Config.DATABASE_URL) as conn:
        return dict(conn.execute("SELECT document_key, document_id FROM document").fetchall())


def load_conditions():
    """All (document_id, condition number, title) that have chunks, for validating gold labels."""
    with psycopg.connect(Config.DATABASE_URL) as conn:
        return conn.execute("""
            SELECT DISTINCT d.document_id, n.number, n.title
            FROM chunk c
            JOIN document d ON d.document_key = c.document_key
            JOIN node n ON n.node_uid = c.source_uid
            WHERE c.document_key != 21
        """).fetchall()


def gold_matches(gold_entry, document_id, condition_number, condition_title):
    if "document_id" in gold_entry and gold_entry["document_id"] != document_id:
        return False
    if "condition" in gold_entry and str(gold_entry["condition"]) != str(condition_number):
        return False
    if "title" in gold_entry and gold_entry["title"].lower() not in (condition_title or "").lower():
        return False
    return True


def is_gold(item, gold, doc_ids):
    document_id = doc_ids.get(item["document_key"])
    return any(gold_matches(g, document_id, item["condition_number"], item["condition_title"]) for g in gold)


def first_gold_rank(items, gold, doc_ids):
    """1-based rank of the first gold chunk in a ranked list, or None if absent."""
    for rank, item in enumerate(items, 1):
        if is_gold(item, gold, doc_ids):
            return rank
    return None


def first_gold_condition_rank(items, gold, doc_ids):
    """Rank after collapsing multi-part chunks of the same condition into one entry."""
    seen = []
    for item in items:
        key = (item["document_key"], item["condition_number"])
        if key in seen:
            continue
        seen.append(key)
        if is_gold(item, gold, doc_ids):
            return len(seen)
    return None


def describe(item, doc_ids):
    return f"{doc_ids.get(item['document_key'])} #{item['condition_number']} {item['condition_title']} [part {item['sequence_index']}/{item['total_parts']}]"


def validate_gold(queries):
    conditions = load_conditions()
    problems = []
    for q in queries:
        for g in q["gold"]:
            if not any(gold_matches(g, *c) for c in conditions):
                problems.append(f"  {q['id']}: gold {g} matches no indexed condition")
    return problems


def evaluate_query(q, doc_ids, use_reranker, use_judge):
    data = hybrid_search(q["query"], top_k=FULL_POOL, scheme=q.get("scheme"), use_reranker=use_reranker, include_candidates=True, use_judge=use_judge)
    cands = data["candidates"]
    final = data["results"]
    gold = q["gold"]
    ranks = {
        "dense": first_gold_rank(cands["dense"], gold, doc_ids),
        "bm25": first_gold_rank(cands["bm25"], gold, doc_ids),
        "rrf": first_gold_rank(cands["fused"], gold, doc_ids),
        "rerank": first_gold_rank(final, gold, doc_ids),
    }
    condition_rank = first_gold_condition_rank(final, gold, doc_ids)

    if ranks["rrf"] is None:
        outcome = "not_retrieved"
    elif ranks["rerank"] == 1:
        outcome = "hit"
    elif ranks["rerank"] is not None and ranks["rerank"] <= 5:
        outcome = "top5_not_first"
    else:
        outcome = "outside_top5"

    return {
        "id": q["id"],
        "query": q["query"],
        "detected_filter": data["detected_filter"],
        "ranks": ranks,
        "condition_rank": condition_rank,
        "outcome": outcome,
        "top5": [describe(item, doc_ids) for item in final[:5]],
        "gold": gold,
    }


def hit_at(ranks, k):
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks)


def mrr(ranks):
    return sum(1.0 / r for r in ranks if r is not None) / len(ranks)


def summarise(records):
    summary = {}
    for stage in STAGES:
        ranks = [r["ranks"][stage] for r in records]
        summary[stage] = {
            "hit@1": hit_at(ranks, 1),
            "hit@3": hit_at(ranks, 3),
            "hit@5": hit_at(ranks, 5),
            "mrr": mrr(ranks),
            "recall@pool": sum(1 for r in ranks if r is not None) / len(ranks),
        }
    cond_ranks = [r["condition_rank"] for r in records]
    summary["rerank_by_condition"] = {"hit@1": hit_at(cond_ranks, 1), "hit@3": hit_at(cond_ranks, 3), "hit@5": hit_at(cond_ranks, 5), "mrr": mrr(cond_ranks)}
    outcomes = {}
    for r in records:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
    summary["outcomes"] = outcomes
    return summary


def print_summary(summary, n):
    print(f"\n{'stage':<22}{'hit@1':>8}{'hit@3':>8}{'hit@5':>8}{'MRR':>8}{'in pool':>9}   (n={n})")
    for stage in STAGES + ["rerank_by_condition"]:
        s = summary[stage]
        pool = f"{s['recall@pool']:.2f}" if "recall@pool" in s else "-"
        print(f"{stage:<22}{s['hit@1']:>8.2f}{s['hit@3']:>8.2f}{s['hit@5']:>8.2f}{s['mrr']:>8.3f}{pool:>9}")
    print(f"\noutcomes: {summary['outcomes']}")


def print_misses(records):
    misses = [r for r in records if r["outcome"] != "hit"]
    if not misses:
        return
    print("\nMISSES (final rank != 1)")
    for r in misses:
        rk = r["ranks"]
        print(f"\n- {r['id']} [{r['outcome']}] filter={r['detected_filter']}")
        print(f"  query: {r['query']}")
        print(f"  gold rank -> dense:{rk['dense']} bm25:{rk['bm25']} rrf:{rk['rrf']} rerank:{rk['rerank']} (by condition: {r['condition_rank']})")
        print(f"  #1 was: {r['top5'][0] if r['top5'] else '-'}")


def compare(paths):
    runs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]
    print(f"\n{'run':<36}{'hit@1':>8}{'hit@3':>8}{'hit@5':>8}{'MRR':>8}{'cond@1':>8}")
    for run in runs:
        s = run["summary"]["rerank"]
        c = run["summary"]["rerank_by_condition"]
        print(f"{run['label'][:35]:<36}{s['hit@1']:>8.2f}{s['hit@3']:>8.2f}{s['hit@5']:>8.2f}{s['mrr']:>8.3f}{c['hit@1']:>8.2f}")
    # Per-query rank changes between the first and last run.
    first, last = runs[0], runs[-1]
    before = {r["id"]: r["ranks"]["rerank"] for r in first["records"]}
    changed = [(r["id"], before.get(r["id"]), r["ranks"]["rerank"]) for r in last["records"] if before.get(r["id"]) != r["ranks"]["rerank"]]
    if changed:
        print(f"\nfinal-rank changes {first['label']} -> {last['label']}:")
        for qid, a, b in changed:
            print(f"  {qid:<28}{str(a):>6} -> {b}")


def main():
    parser = argparse.ArgumentParser(description="Retrieval eval for hybrid_search against a gold set.")
    parser.add_argument("--gold", default=str(EVAL_DIR / "gold_queries.json"))
    parser.add_argument("--label", default="run", help="Name for this run (used in the output filename)")
    parser.add_argument("--no_rerank", action="store_true", help="Skip the Isaacus reranker (final order = RRF)")
    parser.add_argument("--judge", action="store_true", help="Let the LLM judge pick the final #1")
    parser.add_argument("--only", nargs="*", help="Run only these query ids")
    parser.add_argument("--compare", nargs="+", help="Compare saved run files instead of running")
    args = parser.parse_args()

    if args.compare:
        compare(args.compare)
        return

    queries = json.loads(Path(args.gold).read_text(encoding="utf-8"))["queries"]
    if args.only:
        queries = [q for q in queries if q["id"] in args.only]

    problems = validate_gold(queries)
    if problems:
        print("Gold labels that match nothing in the index (fix before trusting results):")
        print("\n".join(problems))

    doc_ids = load_document_ids()
    records = []
    for i, q in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {q['id']}", flush=True)
        records.append(evaluate_query(q, doc_ids, use_reranker=not args.no_rerank, use_judge=args.judge))

    summary = summarise(records)
    print_summary(summary, len(records))
    print_misses(records)

    RUNS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RUNS_DIR / f"{args.label}_{stamp}.json"
    out.write_text(json.dumps({
        "label": args.label,
        "generated_at": stamp,
        "use_reranker": not args.no_rerank,
        "use_judge": args.judge,
        "gold_file": args.gold,
        "summary": summary,
        "records": records,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved {out.relative_to(WORKSPACE_ROOT)}")


if __name__ == "__main__":
    main()
