# Schema design rules (Stanford CS520, "How to Create a Knowledge Graph")

Upfront schema design is optional in a property graph and pays for itself
anyway: the choice of nodes, labels, properties, relations and relation
properties determines what queries are cheap and what facts can be stated at
all. These are the rules `kg.ontology` encodes and a hand-written ontology JSON applies.

## Sources decide the first step

Structured or semi-structured input (JSON, tables) needs **schema mapping** —
relate the source's fields to the graph's types — then **record linkage** —
relate new instances to existing ones. Unstructured text needs **entity
extraction** and **relation extraction**. In this package the JSON loader
is the mapping, the resolver is the linkage, and the extractor is the rest.

## Property, label, or node? (2.2.1–2.2.2)

The gender example. Three ways to hold one fact:

1. labels `:Male` / `:Female` on the Person node
2. a property `gender: "male"` on the node
3. a `Gender` node joined by `has_gender`

`kg_pipeline.property_or_node` decides:

| Condition | Model as | Why |
|---|---|---|
| membership changes over time | **node** with a temporal edge | neither a label nor a property can hold "was X until 2023" |
| shared across entities, or queries join on it | **node** | the movie/genre case: `(m1)-[:has_genre]->(g)<-[:has_genre]-(m2)` uses the relation index; a property comparison cannot |
| stable, few distinct values, filtered on | **label** | a label groups nodes into a set queries can filter cheaply |
| one value per node, stable, rarely joined | **property** | simplest; nothing else earns its cost |

A label is a class. Ask "should this be a class?" — a phrase that occurs
naturally and often in the domain is a candidate, *as long as membership does
not change with time*. `EntityType.membership_stable=False` marks the ones that
fail this and must be modelled as a related node instead.

The hybrid is legitimate: most people's gender is a property; the few whose
gender changed get a `Gender` node with a validity interval on the edge.

## Relationship properties (2.2.3)

Put on the edge, never on either endpoint: **time validity** (`valid_from`,
`valid_to`), **weight or confidence**, **provenance** (which document, which
quote). `to_arango` writes all of these on every edge; `EdgeType.temporal=True`
declares which relations *need* the interval (ownership, employment, deployment).

Some engines do not index relationship properties. If a property is only for
final filtering that is fine; if query evaluation *centres* on it, reify the
relation.

## Non-binary relationships (2.2.4)

`C is between A and B`. A clinical trial with a drug, a condition, an outcome
and a sponsor. No single edge has four ends. **Reify**: the relation becomes a
node with one role-labelled edge to each participant. a reified relation node
does this; `EdgeType.arity > 2` flags an edge type that must be.

## Identity and linking (2.1.4)

Three kinds of link make a graph useful beyond itself:

- **relationship links** — to related things elsewhere (a person to their city)
- **identity links** — `owl:sameAs`: two identifiers, one real-world thing
- **vocabulary links** — from a type to the definition it specialises

Resolution emits identity links as `SAME_AS` edges for every merged alias, so
another source can say "my `ledger-api` is your `Ledger API`" without either
graph rewriting the other. Every domain type's `parent` is its vocabulary link
to the upper layer.

## Naming (2.1.1)

Identifiers should be **simple, stable and manageable**: short, mnemonic, free
of implementation detail, and owned by the publisher. Vertex keys here are
`identity(type, normalised name)` — deterministic from content, never from a
run id or timestamp, so a rebuild produces the same keys.

## Reuse vocabularies before inventing them (2.1.3)

Schema.org, SKOS, the Organization ontology exist. Inside bidcore the existing
vocabularies are `models.taxonomy` and the relation set of
`models.rfp_model.ContextRelation`; the `bidcore` domain ontology uses those
names so edges from this package and from the ETL context builder traverse
together. A new vocabulary should be documented, self-describing (every term
has a label and definition — every type has a description), and
versioned.

## Accuracy is a design input (1)

Web-scale retrieval tolerates imperfect triples; enterprise use often needs
near-perfect ones and human verification before use. The review queue is the
concession to that: merges below `kg_review_confidence` are kept apart until a
person decides, rather than guessed either way.
