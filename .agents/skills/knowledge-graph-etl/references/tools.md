# MCP tools

All read tools are annotated `readOnlyHint`; `kg_write_graph` alone is `destructiveHint`. Names ≤ 64 chars. Structured JSON results.

| Tool | Input | Returns |
|---|---|---|
| `kg_list_ontologies` | — | `{name: {description, entity_types, edge_types}}` |
| `kg_get_ontology` | `name` | full ontology dict (types with parents/upper, edges with domain/range/temporal) |
| `kg_design_schema` | `domain_description`, `sample_text`, `base_ontology="generic"` | proposed ontology (`validated: true` → pass `ontology` to other tools), `properties` decisions with `rule_check`, `reified_relations` |
| `kg_extract_text` | `title`, `text`, `ontology?` | `ExtractionResult`: entities (mention/type/description/evidence), relations, `dropped` with reasons, `cached` |
| `kg_extract_json` | `records[]`, `title_field?`, `text_fields?`, `id_field?`, `ontology?` | one extraction per record |
| `kg_resolve_entities` | `entities[{mention,type,description}]`, `ontology?` | `alias_to_canonical`, `canonical_info`, `review_queue`, `stats` |
| `kg_build_graph` | `documents[{title,text}]`, `ontology?`, `summarize_top_n=0`, `skip_resolution=false` | `ArangoBundle` (below) |
| `kg_graph_health` | `bundle` | components, orphans, by_type, predicates, hubs, dropped |
| `kg_query` | `bundle`, `question`, `center?`, `hops=2`, `avoid_hub_types?` | `{answer, center, context}` — answer cites edges |
| `kg_evaluate` | `documents`, `gold`, `aliases?`, `ontology?`, `replicates=1`, `predicate_synonyms?` | ceiling, per-run scores, noise band |
| `kg_write_graph` | `bundle`, `purge=false` | counts written and totals |

`ontology` accepts a registered name (`incident`, `bidcore`, `generic`) or the dict `kg_design_schema` returned.

## ArangoBundle

```
entity_collection  "kg_entities"
edge_collection    "kg_edges"
vertices[]   {_key, name, type, upper_type, layer, description, aliases[], mentions,
              source_docs[], evidence[], profile?, ontology, generation, node_kind}
edges[]      {_key, _from, _to, rel, weight, confidence, source_doc, source_docs[],
              evidence, valid_from, valid_to, generation, validation_status}
aliases[]    {entity, canonical, alias, type}
review_queue[] {type, aliases[], confidence, reason}
health       graph_health() output
stats        {vertices, edges, aliases, resolution: {by_type, rule_merges, model_calls, review}}
```

`_from`/`_to` are full handles (`kg_entities/<key>`). `rel` is upper-case and drawn from the ontology, plus `SAME_AS` for identity links. Keys are content-derived: rebuilding the same corpus yields the same keys, so `kg_write_graph` overwrites.

## Gold set for `kg_evaluate`

```json
{"<document title>": {
   "entities":  [{"name": "…", "type": "…"}],
   "relations": [{"source": "…", "predicate": "…", "target": "…"}]}}
```
`aliases` maps lowercased surface variants to the gold name. Relation scoring is reported three ways: `relaxed` (endpoints only — an upper bound), `undirected`, and `strict` (predicate must match, after `predicate_synonyms`). Read the ceiling first: gold facts absent from the source cap recall regardless of the prompt.
