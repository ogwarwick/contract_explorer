# LCHA Contract Explorer

The current product combines three layers:

- `code/` — contract parsing, validation, and PostgreSQL loading;
- `search_functionality/` — hybrid PostgreSQL/BM25/vector search;
- `web_app/` — the FastAPI contract viewer, hierarchy navigation, PDF viewer,
  and cross-reference panel.

## Local data

The contract PDFs, parser intermediates, enrichment inputs, PostgreSQL
database, and search indexes are local development data and are intentionally
not stored in the normal Git history. The app expects those assets to be
available in the existing local workspace.

The small normalized cross-reference projections under
`contracts/enriched_outputs/cross_references/` are kept with the application
because they are the app-facing output consumed by the viewer.

## Run the viewer

```bash
./.venv/bin/uvicorn web_app.server:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`.

## Baseline product scope

The contract viewer currently supports:

- contract and condition hierarchy navigation;
- PDF page navigation with printed-page mapping;
- hybrid clause search;
- inbound and outbound condition cross-references.

## RAG chat experiment

The normal search bar is retrieval-only: it returns ranked contract references
and a deterministic search interpretation. The optional LLM answer endpoint and
batch experiment remain available for controlled evaluation, but are not called
by the main app.

To generate a reviewable set of questions and answers without changing contract
JSON or PostgreSQL data:

```bash
./.venv/bin/python experiments/run_rag_qa_experiment.py
```

The question set is in `experiments/rag_question_set.json` and the generated
review file is written to `experiments/rag_qa_results.json` (ignored by Git).
