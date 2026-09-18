# 📄 ContractExplorer: RAG and Viewer Tool for UK Energy Subsidy Terms and Conditions


> **ContractExplorer** is a specialized AI agent prototype built to navigate, cross-reference, and query 700+ page enterprise agreements



## 🚨 The Business Problem
During user discovery, I identified a major operational risk: policy teams were using generic LLM chatbots to query dense, heavily cross-referenced energy subsidy contracts. 

Because standard LLMs lose structural context in long legal documents, **the AI was confidently hallucinating answers.** Users were getting the wrong information, and because they trusted the tool, these errors compounded over time, creating significant commercial and compliance risks.

## 💡 The Solution
I built ContractExplorer because teams were using the wrong tool for the job. Instead of a flat-text chatbot, ContractExplorer uses a **Structure-Aware RAG pipeline** and a dedicated UI to ensure users can verify every AI-generated claim against the physical contract. 

### Core Product Features
🔎 Hybrid Clause Search: Combines dense vector retrieval (pgvector) and sparse lexical search (tsvector) via Reciprocal Rank Fusion (RRF), context-enriched with hierarchical breadcrumbs (Contract > Part > Condition > Clause).
📑 Synchronized PDF Navigator: A 3-panel workspace linking an expandable document hierarchy tree directly to an interactive PDF.js viewer with automated physical-to-printed page offset alignment.
🕸️ Cross-Reference Features: Automatically resolves condition-to-condition impact, inbound backlinks ("Referenced By"), intra-condition clause citations, and governing statutes (Energy Act 2013, etc.) with one-click page navigation.
🤖 Grounded Legal Q&A: RAG-powered query engine delivering answers strictly cited with exact condition numbers and page references.

## 🔄 Project Lifecycle & Impact
1. **Discovery:** Identified the "compounding error" problem with existing LLM tools.
2. **Prototyping:** Built the V1 architecture (Docling parsing + Hybrid Search).
3. **User Testing:** Ran initial user testing to validate that the UI solved the accuracy and trust issues.
4. **Iteration:** Expanded the pipeline to ingest a larger share of the department's contracts based on user feedback.
5. **Handoff:** Successfully proved the internal use case and transitioned the platform to the internal Data Science team to scale.

---

## ⚙️ Technical Architecture

*   **Ingestion Pipeline:** Uses **Docling** to parse raw PDFs, preserving exact document hierarchy (`Part -> Condition -> Clause`) rather than flat text chunks.
*   **Knowledge Graph Enrichment:** Leverages the **Isaacus AI API** to map defined terms, external citations, and internal clause-to-clause references into precomputed JSON artifacts.
*   **Retrieval Engine:** A Fast-API backend running **Hybrid Search (RRF)** on PostgreSQL, combining dense semantic vectors with sparse lexical search (`tsvector` BM25).

---
