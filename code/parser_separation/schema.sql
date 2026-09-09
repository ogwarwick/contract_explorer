CREATE EXTENSION IF NOT EXISTS vector;

-- One row per contract, per parse.
CREATE TABLE IF NOT EXISTS document (
  document_key    bigserial PRIMARY KEY,
  document_id     text NOT NULL,              -- "AR3_Standard_Terms_and_Conditions"
  title           text NOT NULL,
  scheme          text NOT NULL,              -- CfD | CCUS | H2
  round           text,
  version         text,
  source_file     text NOT NULL,
  source_sha256   text NOT NULL,
  page_count      integer,
  parser_version  text NOT NULL,
  config_profile  text,
  parsed_at       timestamptz NOT NULL,
  loaded_at       timestamptz NOT NULL DEFAULT now(),
  is_current      boolean NOT NULL DEFAULT true,
  UNIQUE (document_id, parser_version)
);

-- Body nodes. Composite parent/child relations.
CREATE TABLE IF NOT EXISTS node (
  node_uid        text PRIMARY KEY,
  document_key    bigint NOT NULL REFERENCES document(document_key) ON DELETE CASCADE,
  parent_uid      text REFERENCES node(node_uid) ON DELETE CASCADE,
  line_id         integer,
  kind            text NOT NULL,
  depth           integer NOT NULL,
  label_depth     integer,
  series          text,
  number          text,                      -- string or NULL, never ''
  title           text NOT NULL,
  text_full       text NOT NULL,
  text_sha256     char(64) NOT NULL,
  breadcrumb      text,
  page_start      integer,
  page_end        integer,
  absorbed        integer[],
  provenance      jsonb,
  ordinal         integer NOT NULL,          -- sibling order
  CONSTRAINT node_kind_ck CHECK (kind IN
    ('root','part','annex','condition','definition','clause','subclause','text','subtitle'))
);

-- Add deferrable foreign key check
ALTER TABLE node DROP CONSTRAINT IF EXISTS node_parent_fk;
ALTER TABLE node ADD CONSTRAINT node_parent_fk
  FOREIGN KEY (parent_uid) REFERENCES node(node_uid)
  DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX IF NOT EXISTS node_doc_key_idx   ON node (document_key);
CREATE INDEX IF NOT EXISTS node_parent_idx    ON node (parent_uid);
CREATE INDEX IF NOT EXISTS node_kind_idx      ON node (document_key, kind);
CREATE INDEX IF NOT EXISTS node_hash_idx      ON node (text_sha256);
CREATE INDEX IF NOT EXISTS node_title_fts_idx ON node USING gin (to_tsvector('english', title));

-- Annex items. Flat, no parent.
CREATE TABLE IF NOT EXISTS annex_item (
  item_uid        text PRIMARY KEY,
  document_key    bigint NOT NULL REFERENCES document(document_key) ON DELETE CASCADE,
  item_id         integer NOT NULL,
  label           text NOT NULL,             -- section_header|text|list_item|formula|footnote
  text            text NOT NULL,
  text_sha256     char(64) NOT NULL,
  page_start      integer,
  page_end        integer,
  absorbed        integer[],
  provenance      jsonb
);

CREATE INDEX IF NOT EXISTS annex_doc_key_idx ON annex_item (document_key);

-- Embeddings table.
CREATE TABLE IF NOT EXISTS embedding (
  text_sha256     char(64) NOT NULL,
  model           text NOT NULL,             -- "kanon-2-embedder"
  dimensions      integer NOT NULL,
  task            text NOT NULL,             -- "retrieval/document"
  vector          vector(1792) NOT NULL,
  vector_idx      halfvec(1024),             -- indexed copy
  input_tokens    integer,
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (text_sha256, model, dimensions, task)
);

-- Chunks table.
CREATE TABLE IF NOT EXISTS chunk (
  chunk_uid          text PRIMARY KEY,          -- equals node_uid or node_uid:part_N
  document_key       bigint NOT NULL REFERENCES document(document_key) ON DELETE CASCADE,
  source_table       text NOT NULL,             -- 'node' | 'annex_item'
  source_uid         text NOT NULL,             -- equals master node_uid
  text_sha256        char(64) NOT NULL,
  char_length        integer NOT NULL,
  breadcrumb         text,
  page_start         integer,
  page_end           integer,
  sequence_index     integer NOT NULL DEFAULT 1,
  total_parts        integer NOT NULL DEFAULT 1,
  clause_range       text,
  enriched_subtitle  text
);

CREATE INDEX IF NOT EXISTS chunk_hash_idx ON chunk (text_sha256);
CREATE INDEX IF NOT EXISTS chunk_doc_key_idx  ON chunk (document_key);
CREATE INDEX IF NOT EXISTS chunk_source_uid_idx ON chunk (source_uid, sequence_index);

