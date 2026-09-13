"""LLM-backed answer layer for the contract RAG experiment.

The search engine remains the source of truth for retrieval. This module only
adds question routing, evidence packaging, and optional answer synthesis.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from hybrid_search import fetch_chunk_text

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(WORKSPACE_ROOT / ".env")

DEFAULT_MODEL = "gpt-5-mini"

_SYNTHESIS_PATTERNS = (
    re.compile(r"\b(explain|describe|outline|summari[sz]e|compare|contrast)\b", re.I),
    re.compile(r"\bhow\s+(?:does|do|are|is|would|can)\b", re.I),
    re.compile(r"\bwhy\b", re.I),
    re.compile(r"\b(in practice|overall|walk me through|implications?|relationship)\b", re.I),
)


def classify_question(query: str) -> str:
    """Classify a user query as direct retrieval or evidence synthesis."""
    normalized = " ".join(query.split()).strip()
    if any(pattern.search(normalized) for pattern in _SYNTHESIS_PATTERNS):
        return "synthesis"
    if re.search(
        r"\bwhat\s+(?:are|is)\b.*\b(work|process|effect|implication|requirements?)\b",
        normalized,
        re.I,
    ):
        return "synthesis"
    return "retrieval"


def _model_name() -> str:
    return os.getenv("OPENAI_RAG_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _client() -> OpenAI:
    api_key = os.getenv("OPEN_AI_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPEN_AI_KEY or OPENAI_API_KEY is not configured")
    timeout = float(os.getenv("OPENAI_RAG_TIMEOUT_SECONDS", "60"))
    return OpenAI(api_key=api_key, timeout=timeout, max_retries=0)


def build_sources(search_data: dict[str, Any], max_chars: int = 3500) -> list[dict[str, Any]]:
    """Turn ranked search results into bounded, citeable evidence records."""
    sources = []
    for index, result in enumerate(search_data.get("results", []), 1):
        text = fetch_chunk_text(result["text_sha256"], result["source_uid"])
        sources.append(
            {
                "source_id": index,
                "document": result.get("doc_title", ""),
                "scheme": result.get("scheme", ""),
                "breadcrumb": result.get("breadcrumb", ""),
                "topic": result.get("enriched_subtitle") or result.get("condition_title", ""),
                "clause_range": result.get("clause_range"),
                "page_start": result.get("page_start"),
                "page_end": result.get("page_end"),
                "document_key": str(result.get("document_key", "")),
                "chunk_uid": str(result.get("chunk_uid", "")),
                "text": text[:max_chars],
            }
        )
    return sources


def _format_evidence(sources: list[dict[str, Any]]) -> str:
    blocks = []
    for source in sources:
        page = source.get("page_start") or "?"
        if source.get("page_end") and source["page_end"] != source.get("page_start"):
            page = f"{page}-{source['page_end']}"
        blocks.append(
            "\n".join(
                [
                    f"SOURCE [{source['source_id']}]",
                    f"Document: {source['document']}",
                    f"Location: {source['breadcrumb']} (contract pages {page})",
                    f"Topic: {source['topic']}",
                    f"Clause range: {source.get('clause_range') or 'not specified'}",
                    "Text:",
                    source["text"],
                ]
            )
        )
    return "\n\n---\n\n".join(blocks)


def generate_synthesis_answer(query: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate a grounded answer and return model metadata for review."""
    if not sources:
        return {
            "answer": "I could not find sufficiently relevant contract text to answer this question.",
            "model": None,
            "answer_status": "no_evidence",
        }

    model = _model_name()
    system_prompt = """You are a careful UK energy and infrastructure contract research assistant.
Answer the user's question using only the supplied contract excerpts. Do not invent
a clause, obligation, deadline, remedy, or interpretation that is not supported by
those excerpts. Cite supporting excerpts inline as [1], [2], etc. If the excerpts
are incomplete or conflicting, say so clearly. Distinguish what the contract says
from a short practical explanation. Do not provide personalised legal advice.

Write a useful answer with a short direct answer first, followed by concise bullets
when that makes the sequence, conditions, deadlines, or consequences clearer."""
    user_prompt = f"""Question:
{query}

Retrieved contract evidence:
{_format_evidence(sources)}

Answer with inline source citations such as [1] and [2]."""

    response = _client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        reasoning_effort="low",
        max_completion_tokens=2000,
    )
    answer = (response.choices[0].message.content or "").strip()
    return {
        "answer": answer,
        "model": model,
        "answer_status": "generated" if answer else "empty_response",
    }


def answer_from_search(
    query: str,
    search_data: dict[str, Any],
    mode: str = "auto",
) -> dict[str, Any]:
    """Route a search result set and optionally synthesize an answer."""
    selected_mode = mode if mode in {"auto", "retrieval", "synthesis"} else "auto"
    question_type = classify_question(query) if selected_mode == "auto" else selected_mode
    sources = build_sources(search_data)
    if question_type == "synthesis":
        generated = generate_synthesis_answer(query, sources)
    else:
        generated = {"answer": None, "model": None, "answer_status": "retrieval_only"}
    return {"question_type": question_type, "sources": sources, **generated}


def generate_search_interpretation(
    query: str,
    top_result: dict[str, Any] | None = None,
    detected_filter: str | None = None,
) -> dict[str, Any]:
    """Generate an AI interpretation of the search query and top match.

    Returns:
        A dict with:
        - 'user_intent': 1-sentence summary of what the user meant/sought.
        - 'match_description': 1-2 sentence description explaining what the term/provision is.
        - 'status': 'generated', 'fallback', or 'no_match'
    """
    scope_name = (
        detected_filter.replace("_", " ") if detected_filter else "the contract collection"
    )
    clean_query = " ".join(query.split()).strip()

    if not top_result:
        return {
            "user_intent": f"You are searching for provisions related to '{clean_query}' across {scope_name}.",
            "match_description": None,
            "status": "no_match",
        }

    # Extract provision metadata from result
    doc = top_result.get("document") or top_result.get("doc_title") or scope_name
    breadcrumb = top_result.get("breadcrumb") or "Contract provision"
    topic = top_result.get("topic") or top_result.get("condition_title") or ""
    clause_range = top_result.get("clause_range")
    summary = top_result.get("chunk_summary") or top_result.get("summary") or ""
    text_preview = (top_result.get("text_preview") or "")[:400]

    # Baseline fallback in case LLM is unreachable
    fallback_intent = f"You are asking about {clean_query.rstrip('?')} in {scope_name}."
    fallback_desc = summary or f"{breadcrumb} ({topic}) sets out conditions governing this provision."

    try:
        client = _client()
        model = _model_name()

        user_content = f"""Query: {clean_query}
Scope: {scope_name}
Top Match Document: {doc}
Top Match Provision: {breadcrumb}{f' - {topic}' if topic else ''}
{f'Clause Range: {clause_range}' if clause_range else ''}
{f'Provision Summary: {summary}' if summary else ''}
{f'Excerpt: {text_preview}' if text_preview else ''}"""

        system_content = """You are an expert legal research assistant for UK energy and infrastructure contracts (CfD, LCHA, CCUS).
Analyze the user's search query and the top matching contract provision.
Respond in valid JSON with exactly two fields:
1. "user_intent": A clear, 1-sentence summary of what the user meant or is looking for (written in second person, e.g. "You are asking how the Strike Price is adjusted for inflation over time.").
2. "match_description": A brief 1-2 sentence description explaining what this specific matched term or provision is in the contract.
Keep both fields concise, precise, and objective. Do not add formatting like markdown inside the JSON values."""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            reasoning_effort="low",
            max_completion_tokens=500,
        )

        raw_json = (response.choices[0].message.content or "").strip()
        parsed = json.loads(raw_json)
        return {
            "user_intent": parsed.get("user_intent") or fallback_intent,
            "match_description": parsed.get("match_description") or fallback_desc,
            "status": "generated",
        }
    except Exception:
        return {
            "user_intent": fallback_intent,
            "match_description": fallback_desc,
            "status": "fallback",
        }

