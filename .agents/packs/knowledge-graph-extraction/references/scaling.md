# Scaling beyond memory

`kg_pipeline.py` runs in memory and caches stages 1 and 2 on disk. Four things
change as the corpus grows, in the order you will hit them.

## 1. Resolution breaks first — block, then arbitrate

Extraction scales linearly and is embarrassingly parallel. Resolution compares
entities *to each other*, and ten thousand `PERSON` entities do not fit one
prompt.

The pipeline already does the right thing in three passes. **String rules**
(normalised equality, initialism, surname + initial) merge for free and shrink
the set. **Embedding blocking** — agglomerative clustering on cosine distance —
groups what's left so each model call sees 50–100 candidates. **The model
arbitrates** within a block, reading descriptions.

Two rules that are easy to get backwards:

**Embeddings nominate; they never decide.** They are recall-oriented (a false
candidate costs one comparison) and exactly wrong for the merge decision,
because smooth similarity puts `ledger-api` and `ledger-db` next to each other.
The decision is always the model reading descriptions. If you replace the
hash embedder with a real one (VoyageAI, Azure), do it *only* in `blocks_for`.

**Blocking is a recall ceiling.** Two surface forms in different blocks can
never merge, so a blocking signal that separates `Edwin Aldrin` from
`Buzz Aldrin` throws away the case you brought a model in for. Prefer generous,
overlapping blocks. Better still, add cheap *context* signals before lowering
any threshold: document-local co-reference, and shared relational context
(both owned by the same team). Measured on an incident corpus, those two
signals correctly merged `batch job` with `nightly reconciliation batch job`,
which scored 0.75 on names alone and would otherwise have split a team's
incident history across two nodes.

## 2. Cost

**Prompt caching.** The schema, vocabulary and instructions are byte-identical
across documents; only the text varies. Caching is a *prefix* match, so put the
document last and verify with `usage.cache_read_input_tokens` — zero across
repeated calls means something in the prefix varies (a timestamp, an unsorted
`json.dumps`).

**Batches API.** Extraction is the archetypal batch job: thousands of
independent calls, no latency requirement, 50% cheaper. Results arrive in
**any order** — key by `custom_id`, never by position, or every provenance
claim downstream is wrong while looking healthy.

**Models.** Extraction stays on Haiku: it runs once per document and the schema
carries precision. Resolution and profiles run a handful of times; Sonnet
there buys judgment cheaply.

## 3. Incremental updates

Rebuilding the whole graph per new document is wasteful and non-deterministic
— canonical names can shift between runs. Instead: extract the new document;
resolve its entities **against the existing canonical set**, not against each
other (feed existing names + descriptions, ask which each mention refers to or
whether it is new); add only new edges; re-profile an entity only when its
source-document set changes materially.

## 4. Storage

`to_arango()` emits the shape directly: vertices keyed
`identity(type, normalised name)`, edges keyed `identity(from, rel, to)` with
`_from`/`_to` handles, `rel` upper-case, `weight`, `confidence`, `source_doc`,
`evidence`, `valid_from`/`valid_to`, plus `SAME_AS` edges for every merged
alias (Stanford's identity links). A rebuild overwrites by key rather than
duplicating.

**Property graph (Neo4j, Neptune, ArangoDB).** Vertices and edges map
one-to-one. Neo4j and ArangoDB support vector indexes natively for hybrid
graph+vector retrieval: embed entity profiles, retrieve candidates by
similarity, then traverse.

**Relational (Postgres).** Three tables — `entities(id, name, type, summary)`,
`relations(source_id, target_id, predicate, ...)`, `aliases(entity_id, alias)`
— with indexes on both `relations` endpoints; multi-hop traversal is a
recursive CTE. Adequate into the low millions of edges.

The four-stage structure and the ontology hold at every size. Scaling adds
blocking before stage 2, caching and batching around stage 1, and a persistence
layer after stage 3.
