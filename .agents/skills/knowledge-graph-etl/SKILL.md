---
name: knowledge-graph-etl
description: Turn free text or JSON records into an ArangoDB-ready knowledge graph using the bidcore `kg` package and its MCP server (kg_build_graph, kg_query, kg_write_graph, kg_design_schema, kg_evaluate). Use this whenever the user wants entities and relationships pulled out of documents, wants to connect facts across postmortems, RFPs, tickets or reports, asks for a graph they can traverse, needs to design an ontology or schema for a domain, wants to populate ArangoDB edge collections from text, or says RAG keeps retrieving the right documents without connecting them. Prefer this over writing a pipeline from scratch — the server already implements extraction, resolution, typed edges, provenance and evaluation, and this skill tells you which tool to call and how to read the results.
---

# Knowledge Graph ETL

## What exists, so you don't rebuild it

`src/kg/` is the pipeline. `python -m kg.server` exposes it as MCP tools over streamable HTTP at `/mcp`, wrapped in FastAPI with `/health` and `POST /api/kg/build`. Register it with `mcp_bridge.register_server("kg", url, api_key)` or set `mcp_servers="kg=http://host:8765/mcp"`.

Do not write an extractor, a resolver or a scorer. Call the tools. If a tool genuinely cannot do what's needed, extend `src/kg/` — the code has one owner per stage and offline tests in `tests/kg/`.

## The ontology comes first

Every extraction is constrained by an `Ontology`: a closed set of entity types and typed edges with declared domain and range. The API rejects a type outside the set, so the schema *is* the training data. Four layers:

| Layer | What it holds | Where |
|---|---|---|
| upper | AGENT, PLACE, EVENT, ARTIFACT, CONCEPT — universal | `kg.ontology.UPPER` |
| domain | one field's vocabulary: `incident` (SERVICE/TEAM/INCIDENT…), `bidcore` (CLIENT_ORGANIZATION/REQUIREMENT/CAPABILITY…), `generic` | `REGISTRY` |
| task | a *restriction* of a domain to one job — fewer types, fewer edges | `ontology.task_view(...)` |
| application | collections, key policy, temporal edges, reification | `kg.arango` |

Every domain type names its upper parent, so a query written against AGENT/EVENT runs unchanged over any domain.

**Pick the narrowest vocabulary that fits.** Domain types beat the generic five every time: they tell the extractor what "central to this document" means. `kg_list_ontologies` shows what's registered; `kg_design_schema` proposes one for a new domain, applying the Stanford rules in `references/schema-design.md` — read that before designing by hand.

## The workflow

1. **Choose or design the ontology.** `kg_list_ontologies` → pick, or `kg_design_schema(domain_description, sample_text)` → get a validated ontology dict you can pass straight to the other tools.
2. **Build.** `kg_build_graph(documents=[{title, text}, …], ontology=…)`. Titles are source text — incident IDs live in filenames. JSON records go through `kg_extract_json`, which renders `field: value` lines so one extractor handles both.
3. **Read the health report before anything else.** `components` should be 1 for a corpus about one topic. Many islands = resolution under-merged. `dropped_relations` > 0 = the ontology rejected edges; the bundle says which and why. `review_queue` holds merges the model was unsure of — they are kept *apart* until a human decides.
4. **Query.** `kg_query(bundle, question, avoid_hub_types=["TEAM"])`. Traversal never routes *through* hub types — a team owns many unrelated things, so team-mediated paths implicate everything in everything. Answers cite edges.
5. **Write.** `kg_write_graph(bundle)` upserts into `kg_entities` / `kg_edges` by deterministic key. It is the only tool that writes. `purge=True` after deletions.
6. **Measure, if you changed anything.** `kg_evaluate(documents, gold, aliases, replicates=3)`. It reports the *ceiling* first — the fraction of gold facts that even appear in the source — and a noise band; a delta inside the band is not a result.

## What the tools guarantee

- Mentions come back **as written**, with a grounded one-sentence description and a verbatim evidence span selected from the source (an invented quote is unrepresentable in the schema).
- **Every mention gets an alias-map entry.** A name the model forgets becomes its own node rather than vanishing with every relation attached to it.
- Resolution runs **string rules first** (initialisms, surname+initial — free), embeddings only to *nominate* candidates, and the model to decide using descriptions. Embeddings never decide: they merge `ledger-api` with `ledger-db`.
- Edges carry `rel`, `confidence`, `source_doc`, `evidence`, `valid_from`/`valid_to`, keyed `identity(from, rel, to)`; vertices keyed `identity(type, normalised name)`. A rebuild overwrites, never duplicates. `SAME_AS` edges record every merged alias.
- Relations with more than two participants are reified (`kg.graph.add_nary_relation`), never squeezed into one edge.

## When the graph looks wrong

| Symptom | Likely stage | Check |
|---|---|---|
| Several components, same topic | resolution under-merged | `review_queue`; aliases on the vertices; is the extractor writing descriptions? |
| One canonical name swallowed many | resolution over-merged | the cluster's `confidence`; lower `kg_review_confidence` sends it to review |
| Entities present, few edges | extraction recall | `dropped` in the extraction result — often domain/range mismatches, i.e. the ontology says this edge can't exist between those types. Fix the ontology, not the prompt |
| A query returns "everything" | hub traversal | pass `avoid_hub_types` |
| Score far below expectation, precision ≈ 1 | gold set drift | `kg_evaluate` ceiling — the facts aren't in the source any more |

## Files

- `references/schema-design.md` — the Stanford CS520 rules (property vs label vs node, edge properties, reification, identity links) as this package applies them. Read before `kg_design_schema` or any hand-built ontology.
- `references/tools.md` — every tool's inputs, outputs and the shape of an ArangoBundle.
- `src/kg/ontology.py` — the registered ontologies; add a domain there when it will be reused.
