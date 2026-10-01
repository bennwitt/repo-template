---
name: knowledge-graph-extraction
description: "Build a knowledge graph from unstructured text with Claude: a closed-vocabulary ontology, entity and relation extraction anchored to source evidence, entity resolution, graph assembly, multi-hop queries, ArangoDB-shaped export, and evaluation against a gold set. Use when turning documents into entities and relationships, deduplicating names across sources, building GraphRAG, designing an ontology, or connecting facts that span documents, even if nobody says \"knowledge graph\"."
---

# Knowledge Graph Extraction

## What this solves

A pile of documents and questions that live *between* them — "which teams keep getting burned by the same dependency", "who collaborated with people who worked on X". No single chunk holds the answer; vector retrieval returns plausible neighbours and never chains the facts. A graph makes entities nodes and typed relations edges, so multi-hop reasoning is traversal.

The classical pipeline needed a trained NER model, a trained relation classifier and hand-written resolution heuristics. Each is now one Claude call with a schema — and **the schema is the only training data**, so design it first.

## Design the schema before extracting anything

`scripts/kg_pipeline.py` carries an `Ontology`: closed entity types, each with an upper-layer parent (PERSON→AGENT, SERVICE→ARTIFACT), and typed edges with declared domain and range (`OWNS: TEAM → SERVICE|COMPONENT|JOB`). Types and predicates reach the model as `Literal`s, so an invented type is rejected by the API, and an edge whose endpoints violate domain/range is refused at assembly *with a reason*. Two registered ontologies: `generic` (the cookbook's five types) and `incident` (SERVICE/COMPONENT/JOB/INCIDENT/TEAM/PERSON/CHANGE). Write your own as JSON and pass `--ontology my.json`.

**Domain types beat the generic five.** They tell the extractor what "central to this document" means. `references/schema-design.md` has the rules for deciding what becomes a node, a label or a property, when an edge needs time validity, and when a relation must be reified — read it before writing a schema by hand.

Measured on a five-document incident corpus, the typed edges caught an extractor mistake (`reporting batch job DEPENDS_ON Payments Platform` — a TEAM is not in `DEPENDS_ON`'s range) that an untyped graph would have stored.

## The pipeline

| Stage | Model | Why |
|---|---|---|
| 1. Extract | `claude-haiku-4-5` | Once per document; the schema carries precision, so volume and cost dominate |
| 2. Resolve | `claude-sonnet-5` | Weighing evidence across documents; runs per entity type, not per document |
| 3. Assemble | none | Pure Python: alias map → `MultiDiGraph`, typed-edge validation, health |
| 4. Query / profile | `claude-opus-5` / `claude-sonnet-5` | Grounded answers with edge citations; hub profiles |

Adapt `scripts/kg_pipeline.py` rather than writing from scratch — it already handles every failure mode below and caches stages 1 and 2 so re-running anything downstream is free.

## What each stage guarantees, and why it matters

**Extraction emits mentions as written, never canonical names.** Merging is a separate stage with separate failure modes; an extractor that canonicalises as it goes destroys the evidence resolution needs and hides its own mistakes. Each entity gets a **one-sentence description** — the single highest-leverage detail in the pipeline, because resolution compares descriptions, not strings. Evidence is a passage the model *selects* from the source, so a fabricated quote is unrepresentable. **The document title is part of the source text**: incident IDs, ticket numbers and dates live in filenames, and four independent runs lost every incident node before that line existed.

**Resolution runs three passes and never loses a name.** Cheap string rules first — normalised equality, initialism (`MP` ~ `Meridian Payments`), surname + initial (`J. Okonkwo` ~ `Jane Okonkwo`) — free and deterministic; they catch most real duplicates. Embeddings then *nominate* candidate blocks so each model call stays small. The model *decides*, reading descriptions; only it reaches `Edwin Aldrin` → `Buzz Aldrin`. **Embeddings never decide** — smooth vectors merge `ledger-api` with `ledger-db`. Every input name gets an alias-map entry (a name the model forgets becomes its own node rather than vanishing with every relation attached), and merges below a confidence threshold go to a **review queue**, kept apart until a human decides.

**Assembly rejects, and says why.** `MultiDiGraph` because two entities can share several predicates and direction carries meaning. Edges carry predicate, source document, evidence, and `valid_from`/`valid_to` when the text states them. Relations with more than two participants are reified as a node with role edges, never squeezed into one edge.

**Queries don't traverse through hubs.** `serialize_subgraph(..., avoid_hub_types={"TEAM"})` — a team owns many unrelated things, so team-mediated paths implicate everything in everything. Match on types and reachability, never on predicate strings; predicate wording is unstable model output. Ask for edge-level citations.

## Reading the health report

| Symptom | Stage | What to check |
|---|---|---|
| Many components, one topic | resolution under-merged | aliases on nodes; review queue; are descriptions being written? |
| One canonical name swallowed many | resolution over-merged | the cluster's confidence; lower `review_confidence` |
| Entities fine, edges sparse | extraction recall | the `dropped` list — usually domain/range: the ontology says that edge can't exist between those types. Fix the ontology, not the prompt |
| A query returns "everything" | hub traversal | `avoid_hub_types` |
| Scores far below expectation, precision ≈ 1 | gold-set drift | the ceiling (`references/evaluation.md`) — the facts aren't in the source |

`--skip-resolution` builds the control graph (every mention its own node) so what resolution buys can be shown, not asserted.

## Evaluation is a feedback loop, not a number

`scripts/eval_extraction.py` splits **extract** (cached replicates) from **score** (free, re-grades every cached run against the *current* gold and alias files, so fixing the alias map re-grades the old baseline too). It reports the achievable **ceiling** first, three relation tiers (strict / relaxed / undirected), split-aware entity precision, and a **noise band**. A delta inside the band is not a result — on a two-document gold set a four-point recall change is unprovable, and the harness says so.

No expected scores are quoted anywhere in this skill. The cookbook's published Apollo baselines are unreproducible today because the source text shrank; any absolute number would drift the same way.

## Limits

No temporal validity on edges beyond what the text states — "who owned this *at the time of* INC-2201" needs the interval on every ownership edge. Nothing here reads images or tables as structure. Resolution is per entity type; a mention typed differently in two documents will not merge, which is usually right and occasionally wrong.

## Files

- `scripts/kg_pipeline.py` — ontology, extract, resolve, build, query, ArangoDB export. Runnable CLI, importable.
- `scripts/eval_extraction.py` — extract/score split, ceiling, tiers, noise band, A/B compare.
- `references/schema-design.md` — the Stanford CS520 design rules as this pipeline applies them.
- `references/prompts.md` — what each prompt clause does; what was measured when a clause changed.
- `references/scaling.md` — blocking, caching, batches, incremental updates, property-graph and relational storage.
- `references/evaluation.md` — gold format, what the metrics can and cannot resolve.
