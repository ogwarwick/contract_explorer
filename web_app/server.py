#!/usr/bin/env python3
"""
Legal Contract Intelligence — FastAPI Backend Server.

Wraps the existing hybrid_search() engine (pgvector dense + BM25 + RRF + Isaacus Reranker)
and serves a premium chat interface for querying UK energy/infrastructure legal contracts.

Start:
    /Users/owenwarwick/.local/bin/uv run uvicorn web_app.server:app --reload --port 8000
"""

import os
import sys
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
import psycopg
from psycopg.rows import dict_row

# ── Path Setup ────────────────────────────────────────────────────────────────
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "search_functionality"))
sys.path.insert(0, str(WORKSPACE_ROOT / "web_app"))

from hybrid_search import hybrid_search  # noqa: E402
from contract_navigator_service import (  # noqa: E402
    get_contract_hierarchy,
    get_pdf_page_range,
    parse_enricher_cross_references,
)
from ar1_hierarchy_service import get_ar1_hierarchy  # noqa: E402
from llm_service import (  # noqa: E402
    answer_from_search,
    generate_search_interpretation,
)

# ── FastAPI Application ───────────────────────────────────────────────────────
app = FastAPI(
    title="LCHA Legal Contract Intelligence",
    description="Hybrid Search (pgvector + BM25 + RRF + Isaacus Reranker) & Interactive Contract Navigator.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static Files ──────────────────────────────────────────────────────────────
STATIC_DIR = Path(__file__).resolve().parent / "static"
PDF_DIR = WORKSPACE_ROOT / "contracts" / "raw_pdf's"

# Document 21 is a legacy DOCX-backed copy of the LCHA contract. It shares
# the same structure/page count as document 22, whose source is the canonical
# PDF, so both records can still open a matching PDF in the navigator.
PDF_ALIASES = {
    "lcha_terms_conditions": "low-carbon-hydrogen-agreement-standard-terms-and-conditions.pdf",
}

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Request / Response Models ─────────────────────────────────────────────────
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    scheme: Optional[str] = None
    document_key: Optional[int] = None
    top_k: int = Field(default=5, ge=1, le=20)
    use_reranker: bool = True


class SearchResult(BaseModel):
    rank: int
    document: str
    scheme: str
    round: Optional[str] = None
    breadcrumb: str
    topic: str
    summary: Optional[str] = None
    clause_range: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    pdf_page_start: Optional[int] = None
    pdf_page_end: Optional[int] = None
    document_key: str
    chunk_uid: str
    sequence_index: Optional[int] = None
    total_parts: Optional[int] = None
    rerank_score: float
    rrf_score: float
    dense_rank: Optional[int] = None
    bm25_rank: Optional[int] = None
    text_preview: str


class SearchInterpretation(BaseModel):
    user_intent: Optional[str] = None
    match_description: Optional[str] = None
    status: str = "generated"


class SearchResponse(BaseModel):
    query: str
    detected_filter: Optional[str] = None
    dense_count: int
    bm25_count: int
    fused_count: int
    results: list[SearchResult]
    interpretation: Optional[SearchInterpretation] = None


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    mode: Literal["auto", "retrieval", "synthesis"] = "auto"
    scheme: Optional[str] = None
    document_key: Optional[int] = None
    top_k: int = Field(default=6, ge=1, le=10)
    use_reranker: bool = True


class AskSource(BaseModel):
    source_id: int
    document: str
    scheme: str
    breadcrumb: str
    topic: str
    clause_range: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    pdf_page_start: Optional[int] = None
    pdf_page_end: Optional[int] = None
    document_key: str
    chunk_uid: str
    text: str


class AskResponse(BaseModel):
    query: str
    question_type: str
    answer_status: str
    answer: Optional[str] = None
    model: Optional[str] = None
    detected_filter: Optional[str] = None
    dense_count: int
    bm25_count: int
    fused_count: int
    results: list[SearchResult]
    sources: list[AskSource]


# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the main chat interface."""
    index_path = STATIC_DIR / "index.html"
    return FileResponse(index_path, media_type="text/html")


@app.post("/api/search", response_model=SearchResponse)
async def api_search(req: SearchRequest):
    """
    Execute hybrid search: Dense (pgvector) + BM25 (FTS) + RRF + Isaacus Reranker.
    Returns ranked contract condition matches.
    """
    try:
        raw = hybrid_search(
            query=req.query,
            top_k=req.top_k,
            scheme=req.scheme,
            doc_key=req.document_key,
            use_reranker=req.use_reranker,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search engine error: {str(e)}")

    results = []
    for rank, r in enumerate(raw["results"], 1):
        pdf_page_start, pdf_page_end = get_pdf_page_range(
            int(r.get("document_key")),
            r.get("page_start"),
            r.get("page_end"),
            r.get("condition_number"),
        )
        results.append(SearchResult(
            rank=rank,
            document=r.get("doc_title", ""),
            scheme=r.get("scheme", ""),
            round=r.get("round"),
            breadcrumb=r.get("breadcrumb", ""),
            topic=r.get("enriched_subtitle") or r.get("condition_title", ""),
            summary=r.get("chunk_summary"),
            clause_range=r.get("clause_range"),
            page_start=r.get("page_start"),
            page_end=r.get("page_end"),
            pdf_page_start=pdf_page_start,
            pdf_page_end=pdf_page_end,
            document_key=str(r.get("document_key", "")),
            chunk_uid=str(r.get("chunk_uid", "")),
            sequence_index=r.get("sequence_index"),
            total_parts=r.get("total_parts"),
            rerank_score=round(r.get("rerank_score", 0.0), 4),
            rrf_score=round(r.get("rrf_score", 0.0), 6),
            dense_rank=r.get("dense_rank"),
            bm25_rank=r.get("bm25_rank"),
            text_preview=r.get("text_preview", ""),
        ))

    interpretation = None
    try:
        top_res_dict = results[0].model_dump() if results else None
        interp_data = generate_search_interpretation(
            query=raw["query"],
            top_result=top_res_dict,
            detected_filter=raw.get("detected_filter"),
        )
        interpretation = SearchInterpretation(**interp_data)
    except Exception:
        interpretation = None

    return SearchResponse(
        query=raw["query"],
        detected_filter=raw.get("detected_filter"),
        dense_count=raw["dense_count"],
        bm25_count=raw["bm25_count"],
        fused_count=raw["fused_count"],
        results=results,
        interpretation=interpretation,
    )


@app.post("/api/ask", response_model=AskResponse)
async def api_ask(req: AskRequest):
    """Retrieve evidence and, for synthesis questions, generate a grounded answer."""
    try:
        raw = hybrid_search(
            query=req.query,
            top_k=req.top_k,
            scheme=req.scheme,
            doc_key=req.document_key,
            use_reranker=req.use_reranker,
        )
        answer_data = answer_from_search(req.query, raw, mode=req.mode)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG answer error: {str(e)}")

    results = []
    for rank, r in enumerate(raw["results"], 1):
        pdf_page_start, pdf_page_end = get_pdf_page_range(
            int(r.get("document_key")),
            r.get("page_start"),
            r.get("page_end"),
            r.get("condition_number"),
        )
        results.append(SearchResult(
            rank=rank,
            document=r.get("doc_title", ""),
            scheme=r.get("scheme", ""),
            round=r.get("round"),
            breadcrumb=r.get("breadcrumb", ""),
            topic=r.get("enriched_subtitle") or r.get("condition_title", ""),
            summary=r.get("chunk_summary"),
            clause_range=r.get("clause_range"),
            page_start=r.get("page_start"),
            page_end=r.get("page_end"),
            pdf_page_start=pdf_page_start,
            pdf_page_end=pdf_page_end,
            document_key=str(r.get("document_key", "")),
            chunk_uid=str(r.get("chunk_uid", "")),
            sequence_index=r.get("sequence_index"),
            total_parts=r.get("total_parts"),
            rerank_score=round(r.get("rerank_score", 0.0), 4),
            rrf_score=round(r.get("rrf_score", 0.0), 6),
            dense_rank=r.get("dense_rank"),
            bm25_rank=r.get("bm25_rank"),
            text_preview=r.get("text_preview", ""),
        ))

    sources = []
    for source in answer_data["sources"]:
        pdf_page_start, pdf_page_end = get_pdf_page_range(
            int(source["document_key"]),
            source.get("page_start"),
            source.get("page_end"),
            None,
        )
        sources.append(AskSource(
            **source,
            pdf_page_start=pdf_page_start,
            pdf_page_end=pdf_page_end,
        ))

    return AskResponse(
        query=req.query,
        question_type=answer_data["question_type"],
        answer_status=answer_data["answer_status"],
        answer=answer_data.get("answer"),
        model=answer_data.get("model"),
        detected_filter=raw.get("detected_filter"),
        dense_count=raw["dense_count"],
        bm25_count=raw["bm25_count"],
        fused_count=raw["fused_count"],
        results=results,
        sources=sources,
    )


@app.get("/api/schemes")
async def api_schemes():
    """Return available contract schemes for the filter dropdown."""
    try:
        with psycopg.connect("dbname=lcha") as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT DISTINCT scheme FROM document ORDER BY scheme;")
                rows = cur.fetchall()
                return {"schemes": [r["scheme"] for r in rows if r["scheme"]]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/contracts")
async def api_contracts():
    """Return list of all ingested contracts with rich metadata and stats."""
    try:
        with psycopg.connect("dbname=lcha") as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""
                    SELECT 
                        d.document_key, 
                        d.document_id, 
                        d.title, 
                        d.scheme, 
                        d.round,
                        (SELECT COUNT(*) FROM chunk c WHERE c.document_key = d.document_key) AS chunk_count,
                        (
                            SELECT COUNT(*)
                            FROM node n
                            JOIN node p ON p.node_uid = n.parent_uid
                            WHERE n.document_key = d.document_key
                              AND n.kind = 'condition'
                              AND p.kind = 'part'
                        ) AS condition_count,
                        COALESCE(d.page_count, (SELECT MAX(page_end) FROM node n WHERE n.document_key = d.document_key)) AS total_pages
                    FROM document d
                    ORDER BY 
                        CASE d.scheme 
                            WHEN 'LCHA' THEN 1 
                            WHEN 'CCUS' THEN 2 
                            WHEN 'CfD' THEN 3 
                            ELSE 4 
                        END, 
                        d.title;
                """)
                return {"contracts": cur.fetchall()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ar1/hierarchy")
async def api_ar1_hierarchy():
    """Return clean structural hierarchy for Generic_CfD_TCs_29_August_2014 (AR1)."""
    try:
        return get_ar1_hierarchy()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/contracts/{doc_key}/hierarchy")
async def api_contract_hierarchy(doc_key: int):
    """Return document hierarchy (Parts -> Conditions -> Sections with page numbers)."""
    try:
        hierarchy = get_contract_hierarchy(doc_key)
        if "error" in hierarchy:
            raise HTTPException(status_code=404, detail=hierarchy["error"])
        return hierarchy
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/contracts/{doc_key}/enricher")
async def api_contract_enricher(doc_key: int):
    """Return Isaacus Enricher cross-references, impact frequencies, and definitions."""
    try:
        enricher_data = parse_enricher_cross_references(doc_key)
        return enricher_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pdf/{doc_key}")
async def api_pdf(doc_key: str):
    """
    Serve a contract PDF from the raw_pdf's directory.
    doc_key maps to the PDF filename via the document table.
    """
    try:
        with psycopg.connect("dbname=lcha") as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT document_id, source_file FROM document WHERE document_key = %s;",
                    (doc_key,),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail=f"Document '{doc_key}' not found.")

                source_file = row["source_file"]
                if not source_file.lower().endswith(".pdf"):
                    source_file = PDF_ALIASES.get(row["document_id"])

                if not source_file:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No PDF is registered for document '{doc_key}'.",
                    )

                pdf_path = (PDF_DIR / source_file).resolve()
                if pdf_path.parent != PDF_DIR.resolve() or not pdf_path.is_file():
                    raise HTTPException(
                        status_code=404,
                        detail=f"Registered PDF '{source_file}' was not found for document '{doc_key}'.",
                    )

                return FileResponse(
                    str(pdf_path),
                    media_type="application/pdf",
                    filename=pdf_path.name,
                    headers={"Cache-Control": "no-store"},
                )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
