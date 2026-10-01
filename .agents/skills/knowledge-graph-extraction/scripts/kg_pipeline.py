"""Knowledge graph construction from unstructured text with Claude -- standalone.

Self-contained, with no imports from any host repository, so the skill works in
any project. Four stages, each cached on disk
so the paid ones are paid once:

    extract    Document -> typed entities + relations, evidence anchored to source
    resolve    mentions -> canonical entities (string rules, blocking, model arbitration)
    build      canonical graph -> NetworkX MultiDiGraph, health, queries
    export     ArangoDB-shaped vertices/edges (or plain JSON)

The schema is an `Ontology`: closed entity types with an upper-layer parent,
and typed edges with declared domain/range. Types and predicates reach the
model as `Literal`s, so an invalid one is rejected by the API; an edge whose
endpoints violate domain/range is refused at assembly with a reason.

    python kg_pipeline.py ./corpus --ontology incident --out graph.json
    python kg_pipeline.py ./corpus --ontology incident --skip-resolution   # control graph
    python kg_pipeline.py ./corpus --ontology incident --ask "which teams touch redis?"

Requires: anthropic, pydantic, networkx, numpy; scikit-learn optional (blocking).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import anthropic
import networkx as nx
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, create_model

EXTRACTION_MODEL = "claude-haiku-4-5"   # once per document: volume, the schema carries precision
SYNTHESIS_MODEL = "claude-sonnet-5"     # resolution + profiles: judgment across documents
ANSWER_MODEL = "claude-opus-5"          # grounded answers

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def identity(*parts) -> str:
    """Hash content, never run ids or timestamps: same input, same key."""
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def source_anchors(text: str) -> dict[str, tuple[int, int, str]]:
    """Paragraph-ish passages the extractor can point at instead of quoting."""
    return {f"q{i}": (m.start(), m.end(), m.group()) for i, m in enumerate(
        re.finditer(r".+?(?:\n\n|\Z)", text, re.S)) if m.group().strip()}


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------
# ontology: closed vocabulary, typed edges, upper-layer parents
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityType:
    name: str
    description: str
    parent: str | None = None  # upper-layer ancestor
    membership_stable: bool = True  # Stanford 2.2.1: labels only for stable membership


@dataclass(frozen=True)
class EdgeType:
    name: str
    domain: tuple[str, ...]
    range: tuple[str, ...]
    description: str
    temporal: bool = False  # Stanford 2.2.3: carries valid_from / valid_to


UPPER = {n: EntityType(n, d, p) for n, d, p in [
    ("THING", "Anything that can be a node.", None),
    ("AGENT", "Something that acts: a person or organisation.", "THING"),
    ("PERSON", "An individual human.", "AGENT"),
    ("ORGANIZATION", "A collective agent.", "AGENT"),
    ("PLACE", "A location.", "THING"),
    ("EVENT", "Something that happened at a time.", "THING"),
    ("ARTIFACT", "A made thing.", "THING"),
    ("CONCEPT", "An abstract idea, capability or category.", "THING"),
]}


@dataclass(frozen=True)
class Ontology:
    name: str
    entity_types: dict[str, EntityType]
    edge_types: dict[str, EdgeType]
    description: str = ""

    def entity(self, name: str) -> EntityType:
        if name in self.entity_types:
            return self.entity_types[name]
        if name in UPPER:
            return UPPER[name]
        raise KeyError(f"unknown entity type {name!r}")

    def lineage(self, name: str) -> list[str]:
        out, current, in_domain = [name], self.entity(name), name in self.entity_types
        while current.parent is not None:
            nxt = current.parent
            # a domain type may name its upper namesake as parent; resolve upward, not to itself
            current = UPPER[nxt] if (nxt == current.name or not in_domain or nxt not in self.entity_types) else self.entity_types[nxt]
            in_domain = current is not UPPER.get(current.name)
            if nxt in out and nxt != name:
                break
            out.append(nxt)
            if current.parent == current.name:
                current = UPPER[current.name]
        return out

    def is_a(self, name: str, ancestor: str) -> bool:
        return ancestor in self.lineage(name)

    def upper_of(self, name: str) -> str:
        for t in self.lineage(name):
            if t in UPPER and (t not in self.entity_types or t == name and False):
                return t
        return next((t for t in self.lineage(name)[1:] if t in UPPER), self.lineage(name)[-1])

    def entity_names(self) -> list[str]:
        return sorted(self.entity_types)

    def edge_names(self) -> list[str]:
        return sorted(self.edge_types)

    def validate_edge(self, rel: str, source_type: str, target_type: str) -> None:
        e = self.edge_types.get(rel)
        if e is None:
            raise KeyError(f"unknown edge type {rel!r}")
        if not any(self.is_a(source_type, d) for d in e.domain):
            raise ValueError(f"{rel}: source type {source_type} not in domain {list(e.domain)}")
        if not any(self.is_a(target_type, r) for r in e.range):
            raise ValueError(f"{rel}: target type {target_type} not in range {list(e.range)}")

    def task_view(self, name: str, entity_types: list[str], edge_types: list[str] | None = None) -> "Ontology":
        """A restriction: the types and edges one job may emit. Never an extension."""
        ents = {n: self.entity_types[n] for n in entity_types}
        edges = {n: self.edge_types[n] for n in (edge_types or self.edge_names())}
        ok = {}
        for n, e in edges.items():
            if any(self.is_a(k, d) for k in ents for d in e.domain) and any(self.is_a(k, r) for k in ents for r in e.range):
                ok[n] = e
        return Ontology(name, ents, ok, f"task view of {self.name}")

    def prompt_block(self) -> str:
        lines = ["Entity types (use exactly these):"]
        lines += [f"  - {t}: {self.entity_types[t].description}" for t in self.entity_names()]
        lines += ["", "Relation types (use exactly these; direction is source -> target):"]
        lines += [f"  - {r}: {e.description}  [{'|'.join(e.domain)} -> {'|'.join(e.range)}]"
                  for r, e in sorted(self.edge_types.items())]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description,
                "entity_types": [{"name": t.name, "parent": t.parent, "description": t.description,
                                  "membership_stable": t.membership_stable} for t in self.entity_types.values()],
                "edge_types": [{"name": e.name, "domain": list(e.domain), "range": list(e.range),
                                "description": e.description, "temporal": e.temporal} for e in self.edge_types.values()]}


def _o(name, desc, parent):
    return EntityType(name, desc, parent)


def _e(name, dom, rng, desc, temporal=False):
    return EdgeType(name, tuple(dom), tuple(rng), desc, temporal)


GENERIC = Ontology("generic", {t.name: t for t in [
    _o("PERSON", "An individual human.", "PERSON"),
    _o("ORGANIZATION", "A company, agency, team or institution.", "ORGANIZATION"),
    _o("LOCATION", "A geographic or named place.", "PLACE"),
    _o("EVENT", "A dated occurrence: mission, launch, incident, meeting.", "EVENT"),
    _o("ARTIFACT", "A made thing: vehicle, document, system, product.", "ARTIFACT"),
]}, {e.name: e for e in [
    _e("PART_OF", ["THING"], ["THING"], "Component or member of."),
    _e("LOCATED_IN", ["THING"], ["LOCATION"], "Situated in."),
    _e("PARTICIPATED_IN", ["PERSON", "ORGANIZATION", "ARTIFACT"], ["EVENT"], "Took part in.", True),
    _e("CREATED", ["PERSON", "ORGANIZATION"], ["ARTIFACT"], "Produced."),
    _e("MEMBER_OF", ["PERSON"], ["ORGANIZATION"], "Belongs to.", True),
    _e("OPERATED", ["ORGANIZATION"], ["ARTIFACT", "EVENT"], "Ran or was responsible for."),
    _e("LED", ["PERSON"], ["EVENT", "ORGANIZATION"], "Commanded or headed.", True),
    _e("RELATED_TO", ["THING"], ["THING"], "Generic association; prefer a specific type."),
]}, "The cookbook's five types; a starting point, not a prescription.")

INCIDENT = Ontology("incident", {t.name: t for t in [
    _o("SERVICE", "A deployed software service or API.", "ARTIFACT"),
    _o("COMPONENT", "Shared infrastructure a service depends on: cluster, queue, database.", "ARTIFACT"),
    _o("JOB", "A scheduled or batch process.", "ARTIFACT"),
    _o("INCIDENT", "A production incident with an identifier.", "EVENT"),
    _o("TEAM", "An engineering team that owns services.", "ORGANIZATION"),
    _o("PERSON", "An engineer named in a report.", "PERSON"),
    _o("CHANGE", "A deploy, migration or planned replacement.", "EVENT"),
]}, {e.name: e for e in [
    _e("OWNS", ["TEAM"], ["SERVICE", "COMPONENT", "JOB"], "Team is responsible for the thing.", True),
    _e("MEMBER_OF", ["PERSON"], ["TEAM"], "Person belongs to team.", True),
    _e("DEPENDS_ON", ["SERVICE", "JOB"], ["SERVICE", "COMPONENT"], "Source needs target to function."),
    _e("AFFECTED", ["INCIDENT"], ["SERVICE", "COMPONENT", "JOB"], "Incident degraded the thing."),
    _e("CAUSED_BY", ["INCIDENT"], ["SERVICE", "COMPONENT", "JOB", "CHANGE"], "Root cause of the incident."),
    _e("RESPONDED_TO", ["PERSON", "TEAM"], ["INCIDENT"], "Handled or investigated the incident."),
    _e("WRITES_TO", ["SERVICE", "JOB"], ["COMPONENT"], "Source writes data into target."),
    _e("REPLACES", ["CHANGE"], ["COMPONENT", "SERVICE"], "Planned change retires the target."),
    _e("LEADS", ["PERSON"], ["TEAM", "CHANGE"], "Person leads the team or effort.", True),
    _e("RELATED_TO", ["THING"], ["THING"], "Generic association; prefer a specific type."),
]}, "Operational incidents: what broke, what it depends on, who owns it.")

ONTOLOGIES = {"generic": GENERIC, "incident": INCIDENT}


def ontology_from_dict(d: dict) -> Ontology:
    return Ontology(d["name"],
                    {t["name"]: EntityType(t["name"], t.get("description", ""), t.get("parent"), t.get("membership_stable", True))
                     for t in d["entity_types"]},
                    {e["name"]: EdgeType(e["name"], tuple(e["domain"]), tuple(e["range"]), e.get("description", ""), e.get("temporal", False))
                     for e in d["edge_types"]}, d.get("description", ""))


def property_or_node(*, shared_across_entities: bool, membership_changes_over_time: bool,
                     queries_join_on_it: bool, few_distinct_values: bool = False) -> tuple[str, str]:
    """Stanford 2.2.1-2.2.2 as a function; see references/schema-design.md."""
    if membership_changes_over_time:
        return "node", "membership changes over time: a node with a temporal edge"
    if queries_join_on_it or shared_across_entities:
        return "node", "shared or joined on: a node lets queries use the relation index"
    if few_distinct_values:
        return "label", "stable, few values: a label groups nodes for cheap filtering"
    return "property", "one value per node, stable, not joined on"


# --------------------------------------------------------------------------
# contracts
# --------------------------------------------------------------------------


class Document(Contract):
    id: str
    title: str
    text: str


class Entity(Contract):
    mention: str = Field(min_length=1)  # as written, never canonicalised
    type: str
    description: str = Field(min_length=1)  # what resolution compares
    evidence: str = ""


class Relation(Contract):
    source: str
    predicate: str
    target: str
    evidence: str = ""
    valid_from: str | None = None
    valid_to: str | None = None


class ExtractedGraph(Contract):
    entities: list[Entity]
    relations: list[Relation]


class Cluster(Contract):
    canonical: str
    aliases: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    reason: str = ""


class ResolvedClusters(Contract):
    clusters: list[Cluster]


class TimeRange(Contract):
    start: str
    end: str


class EntityProfile(Contract):
    summary: str
    key_facts: list[str]
    time_range: TimeRange


# --------------------------------------------------------------------------
# stage 1: extraction
# --------------------------------------------------------------------------

EXTRACTION_PROMPT = """Extract a knowledge graph from the document below.

<document title="{title}">
{text}
</document>

{vocabulary}

Guidelines:
- Extract only entities central to what this document is about; skip incidental mentions.
- Write each entity's mention exactly as it appears in the text. Do not normalise, expand or canonicalise -- merging variants happens later and needs the original form.
- For each entity, write a one-sentence description grounded in this document. These descriptions are used later to tell apart entities that share a name.
- Use only the entity and relation types listed. Relation direction is source -> target as each type's description states.
- Every relation must connect two entities you extracted.
- For evidence, select the source passage id that supports the entity or relation.
- If the text states when a relation began or ended, fill valid_from / valid_to as YYYY or YYYY-MM.
- The document title is part of the source: identifiers that appear only in the title still count."""


def document_text(doc: Document) -> str:
    """Title first. Incident IDs, ticket numbers and dates live in filenames."""
    return f"{doc.title}\n\n{doc.text}"


def build_schema(ontology: Ontology, anchors: dict) -> type[ExtractedGraph]:
    ids = tuple(anchors)
    entity = create_model("AnchoredEntity", __base__=Entity,
                          type=(Literal[tuple(ontology.entity_names())], ...),
                          evidence=(Literal[ids], ...))
    relation = create_model("AnchoredRelation", __base__=Relation,
                            predicate=(Literal[tuple(ontology.edge_names())], ...),
                            evidence=(Literal[ids], ...))
    return create_model("AnchoredGraph", __base__=ExtractedGraph,
                        entities=(list[entity], Field(default_factory=list)),
                        relations=(list[relation], Field(default_factory=list)))


def enforce_ontology(graph: ExtractedGraph, ontology: Ontology) -> tuple[ExtractedGraph, list[dict]]:
    """Drop rejected relations and say why. Recall loss nobody can see is the failure."""
    types = {e.mention: e.type for e in graph.entities}
    kept, dropped = [], []
    for r in graph.relations:
        if r.source not in types or r.target not in types:
            dropped.append({**r.model_dump(), "reason": "endpoint not among extracted entities"}); continue
        if r.source == r.target:
            dropped.append({**r.model_dump(), "reason": "self-loop"}); continue
        try:
            ontology.validate_edge(r.predicate, types[r.source], types[r.target])
        except (KeyError, ValueError) as exc:
            dropped.append({**r.model_dump(), "reason": str(exc)}); continue
        kept.append(r)
    return ExtractedGraph(entities=graph.entities, relations=kept), dropped


def extract(doc: Document, ontology: Ontology, client: anthropic.Anthropic, cache: Path | None,
            model: str = EXTRACTION_MODEL, prompt: str = EXTRACTION_PROMPT) -> tuple[ExtractedGraph, list[dict], bool]:
    text = document_text(doc)
    anchors = source_anchors(text)
    passages = "\n".join(f'<passage id="{a}">{q.strip()}</passage>' for a, (_, _, q) in anchors.items())
    rendered = prompt.format(title=doc.title, text=passages, vocabulary=ontology.prompt_block())
    key = identity(model, ontology.to_dict(), rendered)
    path = cache / "extract" / f"{key}.json" if cache else None
    if path and path.exists():
        graph = ExtractedGraph.model_validate(json.loads(path.read_text())["graph"])
        graph, dropped = enforce_ontology(graph, ontology)
        return graph, dropped, True
    response = client.messages.parse(model=model, max_tokens=8192,
                                     messages=[{"role": "user", "content": rendered}],
                                     output_format=build_schema(ontology, anchors))
    raw = response.parsed_output
    graph = ExtractedGraph(
        entities=[Entity(mention=e.mention, type=e.type, description=e.description,
                         evidence=anchors[e.evidence][2].strip() if e.evidence in anchors else "") for e in raw.entities],
        relations=[Relation(source=r.source, predicate=r.predicate, target=r.target,
                            evidence=anchors[r.evidence][2].strip() if r.evidence in anchors else "",
                            valid_from=r.valid_from, valid_to=r.valid_to) for r in raw.relations])
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"input_hash": key, "model": model, "graph": graph.model_dump()}))
    graph, dropped = enforce_ontology(graph, ontology)
    return graph, dropped, False


# --------------------------------------------------------------------------
# stage 2: resolution
# --------------------------------------------------------------------------

RESOLVE_PROMPT = """Below are {entity_type} entities extracted from several documents. Some are different surface forms of the same real-world entity.

<entities>
{entity_list}
</entities>

Cluster them. Each input name must appear in exactly one cluster's aliases list. Entities that are genuinely distinct get their own single-element cluster. Use the descriptions to avoid merging entities that merely share a name, and to merge entities whose names differ but whose descriptions clearly denote one thing. The canonical name should be the most complete, unambiguous form. Give each cluster a confidence from 0 to 1 and one sentence of reasoning."""

_PUNCT = re.compile(r"[^\w\s-]")


def normalize_name(name: str) -> str:
    return " ".join(_PUNCT.sub(" ", unicodedata.normalize("NFKC", name).casefold()).split())


def _tokens(name: str) -> list[str]:
    return normalize_name(name).replace("-", " ").split()


def _same_by_rule(a: str, b: str) -> str | None:
    """Cheap rules that catch most real duplicates; each returns its name."""
    if normalize_name(a) == normalize_name(b):
        return "normalized_equal"
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return None
    ia, ib = "".join(t[0] for t in ta), "".join(t[0] for t in tb)
    if len(ta) == 1 and len(ta[0]) >= 2 and ta[0] == ib:
        return "initialism"
    if len(tb) == 1 and len(tb[0]) >= 2 and tb[0] == ia:
        return "initialism"
    if len(ta) >= 2 and len(tb) >= 2 and ta[-1] == tb[-1]:
        if ta[0] == tb[0]:
            return "shared_head_and_tail"
        if ta[0][0] == tb[0][0] and (len(ta[0]) == 1 or len(tb[0]) == 1):
            return "surname_and_initial"
        if ta[0] == "".join(t[0] for t in tb[:-1]) or tb[0] == "".join(t[0] for t in ta[:-1]):
            return "initialism_with_tail"
    return None


def string_prefilter(names: list[str]) -> tuple[list[list[str]], list[dict]]:
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x

    merges = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            rule = _same_by_rule(a, b)
            if rule:
                parent[find(a)] = find(b); merges.append({"a": a, "b": b, "rule": rule})
    groups = defaultdict(list)
    for n in names:
        groups[find(n)].append(n)
    return [sorted(g) for g in groups.values()], merges


def hash_embed(texts: list[str], dim: int = 256) -> np.ndarray:
    """Character-trigram hashing: enough to put near spellings in one block, no network."""
    rows = np.zeros((len(texts), dim), dtype=np.float32)
    for i, text in enumerate(texts):
        t = f"  {text.casefold()}  "
        for j in range(len(t) - 2):
            rows[i, int(hashlib.blake2b(t[j:j + 3].encode(), digest_size=4).hexdigest(), 16) % dim] += 1
        n = np.linalg.norm(rows[i]); rows[i] /= n if n else 1
    return rows


def blocks_for(names: list[str], descs: dict[str, str], distance: float, max_block: int) -> list[list[str]]:
    """Embeddings NOMINATE candidates only. They never decide a merge."""
    if len(names) < 2:
        return [names]
    try:
        from sklearn.cluster import AgglomerativeClustering
    except ImportError:
        return [names[i:i + max_block] for i in range(0, len(names), max_block)]
    m = hash_embed([f"{n}: {descs.get(n, '')}" for n in names])
    labels = AgglomerativeClustering(n_clusters=None, distance_threshold=distance, metric="cosine",
                                     linkage="average").fit_predict(m)
    out = defaultdict(list)
    for n, l in zip(names, labels):
        out[int(l)].append(n)
    return [sorted(b)[i:i + max_block] for b in out.values() for i in range(0, len(b), max_block)]


def resolve(raw: list[dict], client: anthropic.Anthropic, cache: Path | None, model: str = SYNTHESIS_MODEL,
            distance: float = 0.6, block_size: int = 80, review_confidence: float = 0.7) -> dict:
    """mentions -> alias map. Every name is mapped; unsure merges go to review, kept apart."""
    a2c, info, review = {}, {}, []
    stats = {"rule_merges": 0, "model_calls": 0, "by_type": {}}
    by_type = defaultdict(dict)
    for e in raw:
        by_type[e["type"]].setdefault(e["mention"], e["description"])
    for etype, unique in sorted(by_type.items()):
        names = sorted(unique)
        groups, merges = string_prefilter(names)
        stats["rule_merges"] += len(merges)
        rep_aliases = {max(g, key=len): g for g in groups}
        reps = sorted(rep_aliases)
        clusters = []
        for block in blocks_for(reps, unique, distance, block_size):
            if len(block) == 1:
                clusters.append(Cluster(canonical=block[0], aliases=block, confidence=1.0, reason="singleton")); continue
            entity_list = "\n".join(f"- {n}: {unique[n]}" for n in block)
            key = identity(model, etype, sorted((n, unique[n]) for n in block))
            path = cache / "resolve" / f"{key}.json" if cache else None
            if path and path.exists():
                got = ResolvedClusters.model_validate(json.loads(path.read_text())).clusters
            else:
                stats["model_calls"] += 1
                got = client.messages.parse(model=model, max_tokens=8192,
                                            messages=[{"role": "user", "content": RESOLVE_PROMPT.format(entity_type=etype, entity_list=entity_list)}],
                                            output_format=ResolvedClusters).parsed_output.clusters
                if path:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({"clusters": [c.model_dump() for c in got]}))
            known = set(block)
            for c in got:
                al = [a for a in c.aliases if a in known]
                if al:
                    clusters.append(Cluster(canonical=c.canonical if c.canonical in known else max(al, key=len),
                                            aliases=al, confidence=c.confidence, reason=c.reason))
        placed = set()
        for c in clusters:
            aliases = sorted({a for r in c.aliases for a in rep_aliases.get(r, [r])})
            if len(c.aliases) > 1 and c.confidence < review_confidence:
                review.append({"type": etype, "aliases": aliases, "confidence": c.confidence, "reason": c.reason})
                for r in c.aliases:
                    for a in rep_aliases.get(r, [r]):
                        a2c[a] = r; placed.add(a)
                    info[r] = {"type": etype, "aliases": rep_aliases.get(r, [r]), "description": unique.get(r, "")}
                continue
            info[c.canonical] = {"type": etype, "aliases": aliases, "description": unique.get(c.canonical, ""),
                                 "confidence": c.confidence}
            for a in aliases:
                a2c[a] = c.canonical; placed.add(a)
        for n in names:  # guarantee: a name the model forgot is its own node, not a lost one
            if n not in placed:
                a2c[n] = n; info.setdefault(n, {"type": etype, "aliases": [n], "description": unique[n]})
        stats["by_type"][etype] = {"names": len(names), "after_rules": len(reps), "canonical": len({a2c[n] for n in names})}
    return {"alias_to_canonical": a2c, "canonical_info": info, "review_queue": review, "stats": stats}


# --------------------------------------------------------------------------
# stage 3: graph
# --------------------------------------------------------------------------


def build_graph(extractions: list[tuple[Document, ExtractedGraph]], resolution: dict, ontology: Ontology) -> nx.MultiDiGraph:
    a2c, info = resolution["alias_to_canonical"], resolution["canonical_info"]
    G = nx.MultiDiGraph(dropped=[])
    for doc, g in extractions:
        for e in g.entities:
            c = a2c.get(e.mention)
            if c is None:
                continue
            if c not in G:
                t = info.get(c, {}).get("type", e.type)
                G.add_node(c, type=t, upper_type=ontology.upper_of(t), description=info.get(c, {}).get("description") or e.description,
                           aliases=info.get(c, {}).get("aliases", [c]), source_docs=[], mentions=0, evidence=[])
            n = G.nodes[c]; n["source_docs"].append(doc.title); n["mentions"] += 1
            if e.evidence and e.evidence not in n["evidence"]:
                n["evidence"].append(e.evidence)
    for doc, g in extractions:
        for r in g.relations:
            s, t = a2c.get(r.source), a2c.get(r.target)
            if not s or not t or s == t or s not in G or t not in G:
                G.graph["dropped"].append({**r.model_dump(), "source_doc": doc.title, "reason": "unresolved endpoint"}); continue
            try:
                ontology.validate_edge(r.predicate, G.nodes[s]["type"], G.nodes[t]["type"])
            except (KeyError, ValueError) as exc:
                G.graph["dropped"].append({**r.model_dump(), "source_doc": doc.title, "reason": str(exc)}); continue
            G.add_edge(s, t, key=identity(s, r.predicate, t, doc.title), predicate=r.predicate, source_doc=doc.title,
                       evidence=r.evidence, valid_from=r.valid_from, valid_to=r.valid_to)
    for n in G.nodes:
        G.nodes[n]["source_docs"] = sorted(set(G.nodes[n]["source_docs"]))
    return G


def graph_health(G: nx.MultiDiGraph) -> dict:
    n = G.number_of_nodes()
    deg = sorted(G.degree(), key=lambda x: -x[1])
    by_type, preds = defaultdict(int), defaultdict(int)
    for node in G.nodes:
        by_type[G.nodes[node]["type"]] += 1
    for _, _, d in G.edges(data=True):
        preds[d["predicate"]] += 1
    largest = max((len(c) for c in nx.weakly_connected_components(G)), default=0)
    return {"nodes": n, "edges": G.number_of_edges(), "components": nx.number_weakly_connected_components(G) if n else 0,
            "largest_component_fraction": largest / n if n else 0.0, "orphans": [x for x, d in deg if d == 0],
            "by_type": dict(by_type), "predicates": dict(preds),
            "top_hubs": [{"name": x, "degree": d, "type": G.nodes[x]["type"]} for x, d in deg[:10]],
            "dropped_relations": len(G.graph.get("dropped", []))}


def serialize_subgraph(G: nx.MultiDiGraph, center: str, hops: int = 2, avoid_hub_types: set[str] | None = None) -> str:
    """k-hop triples. Never traverse THROUGH hub types (a TEAM implicates everything)."""
    avoid = avoid_hub_types or set()
    nodes, frontier = {center}, {center}
    for _ in range(hops):
        nxt = set()
        for n in frontier:
            if n != center and G.nodes[n]["type"] in avoid:
                continue
            nxt |= set(G.successors(n)) | set(G.predecessors(n))
        frontier = nxt - nodes; nodes |= frontier
    sub = G.subgraph(nodes)
    return "\n".join(sorted({f"({s}:{G.nodes[s]['type']}) --[{d['predicate']}]--> ({t}:{G.nodes[t]['type']})"
                             for s, t, d in sub.edges(data=True)}))


ASK_PROMPT = """Answer using only the knowledge graph below. Cite the specific edges that support your answer. If the graph does not contain enough information, say so rather than filling the gap from general knowledge.

<graph>
{graph_context}
</graph>

Question: {question}"""


def ask(question: str, context: str, client: anthropic.Anthropic, model: str = ANSWER_MODEL) -> str:
    r = client.messages.create(model=model, max_tokens=4096,
                               messages=[{"role": "user", "content": ASK_PROMPT.format(graph_context=context, question=question)}])
    return next(b.text for b in r.content if b.type == "text")


def to_arango(G: nx.MultiDiGraph, ontology: Ontology, entity_collection: str = "kg_entities",
              edge_collection: str = "kg_edges", generation: str = "kg-v1") -> dict:
    """Vertices/edges with deterministic _key, _from/_to handles, provenance, SAME_AS alias links."""
    keys = {n: identity(G.nodes[n]["type"], normalize_name(n)) for n in G.nodes}
    vertices = [{"_key": keys[n], "name": n, **{k: v for k, v in G.nodes[n].items()},
                 "aliases": [a for a in G.nodes[n].get("aliases", []) if a != n], "ontology": ontology.name,
                 "generation": generation} for n in G.nodes]
    edges = {}
    for s, t, d in G.edges(data=True):
        f, to = f"{entity_collection}/{keys[s]}", f"{entity_collection}/{keys[t]}"
        k = identity(f, d["predicate"], to)
        if k in edges:
            edges[k]["weight"] += 1; edges[k]["source_docs"].append(d["source_doc"]); continue
        edges[k] = {"_key": k, "_from": f, "_to": to, "rel": d["predicate"], "weight": 1.0, "confidence": 1.0,
                    "source_doc": d["source_doc"], "source_docs": [d["source_doc"]], "evidence": d.get("evidence", ""),
                    "valid_from": d.get("valid_from"), "valid_to": d.get("valid_to"), "generation": generation}
    for n in G.nodes:
        for a in G.nodes[n].get("aliases", []):
            if a == n:
                continue
            f, to = f"{entity_collection}/{identity(G.nodes[n]['type'], normalize_name(a))}", f"{entity_collection}/{keys[n]}"
            k = identity(f, "SAME_AS", to)
            edges[k] = {"_key": k, "_from": f, "_to": to, "rel": "SAME_AS", "weight": 1.0, "confidence": 1.0,
                        "source_doc": "", "source_docs": [], "evidence": "", "valid_from": None, "valid_to": None,
                        "generation": generation, "alias_of": keys[n]}
    return {"entity_collection": entity_collection, "edge_collection": edge_collection,
            "vertices": vertices, "edges": list(edges.values()), "dropped": G.graph.get("dropped", [])}


# --------------------------------------------------------------------------
# end-to-end
# --------------------------------------------------------------------------


def load_documents(path: Path) -> list[Document]:
    if path.is_file() and path.suffix == ".json":
        return [Document(id=str(d.get("id", i)), title=d.get("title", f"doc-{i}"), text=d["text"])
                for i, d in enumerate(json.loads(path.read_text()))]
    files = sorted(p for p in path.rglob("*") if p.suffix in {".txt", ".md"})
    return [Document(id=identity(p.stem, p.read_text())[:16], title=p.stem, text=p.read_text(encoding="utf-8")) for p in files]


def run(documents: list[Document], ontology: Ontology, client: anthropic.Anthropic | None = None,
        cache: Path | None = Path(".kg_cache"), skip_resolution: bool = False, verbose: bool = True) -> tuple[nx.MultiDiGraph, dict]:
    client = client or anthropic.Anthropic()
    extractions, dropped_total, cached = [], 0, 0
    for d in documents:
        g, dropped, was_cached = extract(d, ontology, client, cache)
        extractions.append((d, g)); dropped_total += len(dropped); cached += was_cached
        if verbose:
            print(f"  {d.title[:40]:<40} {len(g.entities):>3} entities {len(g.relations):>3} relations"
                  f"{'  (cached)' if was_cached else ''}{f'  dropped={len(dropped)}' if dropped else ''}")
    raw = [{"mention": e.mention, "type": e.type, "description": e.description} for _, g in extractions for e in g.entities]
    if skip_resolution:
        seen = {e["mention"]: e for e in raw}
        resolution = {"alias_to_canonical": {m: m for m in seen},
                      "canonical_info": {m: {"type": e["type"], "aliases": [m], "description": e["description"]} for m, e in seen.items()},
                      "review_queue": [], "stats": {"skipped": True}}
    else:
        resolution = resolve(raw, client, cache)
    G = build_graph(extractions, resolution, ontology)
    G.graph["health"] = graph_health(G) | {"dropped_at_extraction": dropped_total, "cached_extractions": cached}
    G.graph["resolution"] = resolution
    return G, resolution


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--ontology", default="generic", help="generic | incident | path to an ontology .json")
    ap.add_argument("--out", type=Path, default=Path("graph.json"))
    ap.add_argument("--cache", type=Path, default=Path(".kg_cache"))
    ap.add_argument("--skip-resolution", action="store_true", help="control graph: every mention its own node")
    ap.add_argument("--ask", default=None)
    ap.add_argument("--avoid-hubs", nargs="*", default=["TEAM", "ORGANIZATION"], help="types never traversed through")
    args = ap.parse_args()
    onto = ONTOLOGIES.get(args.ontology) or ontology_from_dict(json.loads(Path(args.ontology).read_text()))
    docs = load_documents(args.corpus)
    if not docs:
        sys.exit(f"no documents under {args.corpus}")
    print(f"Extracting {len(docs)} documents with ontology {onto.name!r}...")
    G, resolution = run(docs, onto, cache=args.cache, skip_resolution=args.skip_resolution)
    h = G.graph["health"]
    print(f"\nGraph: {h['nodes']} nodes, {h['edges']} edges, {h['components']} component(s); by type {h['by_type']}")
    print(f"Dropped: {h['dropped_at_extraction']} at extraction, {h['dropped_relations']} at assembly (see graph.json 'dropped')")
    if resolution.get("review_queue"):
        print(f"Review queue ({len(resolution['review_queue'])}): merges kept apart until a human decides")
    for hub in h["top_hubs"][:5]:
        print(f"  {hub['name'][:45]:<45} degree {hub['degree']:>3}  ({hub['type']})")
    bundle = to_arango(G, onto) | {"health": h, "review_queue": resolution.get("review_queue", []),
                                   "resolution_stats": resolution.get("stats", {})}
    args.out.write_text(json.dumps(bundle, indent=2, default=str))
    print(f"\nWrote {args.out}")
    if args.ask:
        centre = h["top_hubs"][0]["name"]
        ctx = serialize_subgraph(G, centre, 2, set(args.avoid_hubs))
        print(f"\nQ: {args.ask}\n(context: 2 hops from {centre!r}, not through {args.avoid_hubs})\n")
        print(ask(args.ask, ctx, anthropic.Anthropic()))


if __name__ == "__main__":
    main()
