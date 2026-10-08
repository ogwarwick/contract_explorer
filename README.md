# ContractExplorer

**Structure-aware RAG for navigating and querying complex energy contracts.**

ContractExplorer is an internal prototype for querying large, highly cross-referenced energy contracts while keeping answers grounded in the underlying source document.

Traditional document chat systems tend to treat a contract as a collection of text chunks. That creates problems when meaning depends on **document hierarchy, defined terms, cross-references and precise clause context**.

ContractExplorer instead builds a structured representation of the contract and combines it with hybrid retrieval and source-level verification.

## Why this exists

A typical energy contract can run to hundreds of pages and contain:

- nested Parts, Conditions and Clauses
- defined terms used throughout the document
- references to other clauses
- references to legislation and external documents
- provisions whose meaning depends on surrounding structure

A user asking:

> "What are the circumstances in which the Secretary of State can terminate the agreement?"

doesn't necessarily need the most semantically similar paragraph.

They need the **relevant provision, its surrounding structure, associated definitions and the ability to verify the answer against the original contract**.

## <img width="1312" height="1199" alt="image" src="https://github.com/user-attachments/assets/acdae593-9f89-48b5-8faf-c0cacaef9b0e" />

## Project status

This is an internal prototype exploring how structured document representations can improve retrieval and verification for complex contracts.

The focus is currently on:

- accurate clause retrieval
- preserving document structure
- navigating cross-references
- making generated answers verifiable against the source

## What I learned

The main lesson from the project is that for highly structured documents, **the representation of the underlying document can be just as important as the model used to query it and having a failure mode where the user can clarify output is important for user trust. This is especially true in highly regulated domains where the margin for error for inaccuracies is effectively 0%**.

This provides confidence to the user that the system is providing the correct answer and if it doesn't seem right there are appropriate features in place that mitigate the potential inaccuracies by referring directly at the source.

ContractExplorer explores this by combining:

**document structure + metadata + hybrid retrieval + grounded generation + source verification.**
