"""Extraction quality against a gold set -- honest version.

    ceiling      fraction of gold facts that even appear in the source. Read it
                 FIRST. Precision near 1.0 with low recall is gold-set drift,
                 not a bad prompt (the cookbook's own Apollo baselines are now
                 unreproducible for exactly this reason: Wikipedia shrank).
    strict / relaxed / undirected   relation match with predicate, endpoints
                 only, and ignoring direction. The gaps separate mislabelling
                 from misreading from a prompt-convention mismatch.
    split-aware precision   distinct gold matched / predicted count, so two
                 unmerged nodes for one entity cost precision.
    noise band   max(2*SE, 0.02) over replicates; a delta inside it is nothing.

Extract and score are split. `extract` caches raw model output under
--runs-dir/<variant>/rep-N.json; `score` re-grades EVERY cached run against the
CURRENT gold/alias files. Fixing the alias map re-grades the old baseline too,
so you cannot compare a leniently graded new prompt to a strictly graded old one.

    python eval_extraction.py extract corpus/ --gold gold.json --variant baseline --replicates 3
    python eval_extraction.py extract corpus/ --gold gold.json --variant recall --prompt-file recall.txt --replicates 3
    python eval_extraction.py score --gold gold.json --aliases aliases.json --compare baseline recall
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from kg_pipeline import EXTRACTION_PROMPT, ONTOLOGIES, extract, identity, load_documents, ontology_from_dict  # noqa: E402


def canon(name: str, aliases: dict) -> str:
    n = name.casefold().strip()
    return aliases.get(n, n)


def prf(p: set, g: set) -> tuple[float, float, float]:
    tp = len(p & g)
    pr = tp / len(p) if p else 0.0
    rc = tp / len(g) if g else 0.0
    return pr, rc, (2 * pr * rc / (pr + rc) if pr + rc else 0.0)


def ceiling(gold: dict, docs: list, aliases: dict) -> dict:
    texts = {d.title: f"{d.title}\n{d.text}".casefold() for d in docs}
    surface = {}
    for k, v in aliases.items():
        surface.setdefault(v, set()).add(k)
    out, e_ok, e_all, r_ok, r_all = {}, 0, 0, 0, 0
    for title, labels in gold.items():
        text = texts.get(title)
        if text is None:
            out[title] = "document not in corpus"; continue
        findable = lambda n: any(s in text for s in {canon(n, aliases), n.casefold()} | surface.get(canon(n, aliases), set()))
        ents = [e["name"] for e in labels["entities"]]
        rels = [(r["source"], r["target"]) for r in labels.get("relations", [])]
        eo = [e for e in ents if findable(e)]; ro = [r for r in rels if findable(r[0]) and findable(r[1])]
        out[title] = {"entities": f"{len(eo)}/{len(ents)}", "relations": f"{len(ro)}/{len(rels)}", "absent": sorted(set(ents) - set(eo))}
        e_ok += len(eo); e_all += len(ents); r_ok += len(ro); r_all += len(rels)
    return {"per_document": out, "entity_recall_ceiling": e_ok / e_all if e_all else 0, "relation_recall_ceiling": r_ok / r_all if r_all else 0}


def score_document(pred: dict, labels: dict, aliases: dict, synonyms: dict) -> dict:
    mentions = [canon(e["mention"], aliases) for e in pred["entities"]]
    pe, ge = set(mentions), {canon(e["name"], aliases) for e in labels["entities"]}
    p, r, f = prf(pe, ge)
    syn = {k.casefold(): v.casefold() for k, v in synonyms.items()}
    norm = lambda x: syn.get(x.casefold().replace("_", " "), x.casefold().replace("_", " "))

    def sets(rows):
        d, u, s = set(), set(), set()
        for x in rows:
            a, b = canon(x["source"], aliases), canon(x["target"], aliases)
            d.add((a, b)); u.add(frozenset((a, b))); s.add((a, norm(x["predicate"]), b))
        return d, u, s

    pd, pu, ps = sets(pred["relations"]); gd, gu, gs = sets(labels.get("relations", []))
    return {"entity_f1": f, "entity_p": p, "entity_r": r,
            "entity_split_aware_p": len(pe & ge) / len(mentions) if mentions else 0.0, "fragmentation": len(mentions) - len(pe),
            "relaxed": prf(pd, gd), "undirected": prf(pu, gu), "strict": prf(ps, gs),
            "missed_entities": sorted(ge - pe), "extra_entities": sorted(pe - ge),
            "missed_relations": sorted(f"{s} -> {t}" for s, t in gd - pd)}


def score_run(predictions: dict, gold: dict, aliases: dict, synonyms: dict) -> dict:
    per = {t: score_document(predictions[t], l, aliases, synonyms) for t, l in gold.items() if t in predictions}
    if not per:
        raise SystemExit("no gold document matched a prediction; titles must agree")
    mean = lambda k, i=None: statistics.fmean((d[k][i] if i is not None else d[k]) for d in per.values())
    return {"documents": len(per), "per_document": per, "entity_f1": mean("entity_f1"), "entity_r": mean("entity_r"),
            "entity_split_aware_p": mean("entity_split_aware_p"), "relaxed_f1": mean("relaxed", 2), "relaxed_r": mean("relaxed", 1),
            "undirected_f1": mean("undirected", 2), "strict_f1": mean("strict", 2)}


def noise_band(v: list[float]) -> float:
    return max(2 * statistics.stdev(v) / len(v) ** 0.5, 0.02) if len(v) >= 2 else float("nan")


def cmd_extract(a) -> None:
    import anthropic
    onto = ONTOLOGIES.get(a.ontology) or ontology_from_dict(json.loads(Path(a.ontology).read_text()))
    docs = load_documents(a.corpus)
    gold = json.loads(a.gold.read_text())
    prompt = a.prompt_file.read_text() if a.prompt_file else EXTRACTION_PROMPT
    client = anthropic.Anthropic()
    for rep in range(1, a.replicates + 1):
        preds = {}
        for d in docs:
            if d.title not in gold:
                continue
            # no cache on purpose: replicates must be independent samples
            g, dropped, _ = extract(d, onto, client, None, model=a.model, prompt=prompt)
            preds[d.title] = g.model_dump() | {"dropped": dropped}
        path = a.runs_dir / a.variant / f"rep-{rep}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"variant": a.variant, "replicate": rep, "model": a.model,
                                    "prompt_hash": identity(prompt)[:12], "predictions": preds}, indent=1))
        print(f"  {a.variant} rep-{rep}: {len(preds)} documents -> {path}")


def cmd_score(a) -> None:
    gold = json.loads(a.gold.read_text())
    aliases = {k.casefold(): v.casefold() for k, v in (json.loads(a.aliases.read_text()) if a.aliases else {}).items()}
    synonyms = json.loads(a.synonyms.read_text()) if a.synonyms else {}
    print(f"rubric fingerprint: {identity(gold, aliases, synonyms)[:12]}  (gold+aliases+synonyms; every run below is graded against it)")
    if a.corpus:
        c = ceiling(gold, load_documents(a.corpus), aliases)
        print(f"\nCEILING  entity recall <= {c['entity_recall_ceiling']:.2f}   relation recall <= {c['relation_recall_ceiling']:.2f}")
        for t, v in c["per_document"].items():
            print(f"  {t:<28} {v if isinstance(v, str) else f'entities {v['entities']}  relations {v['relations']}  absent: {v['absent']}'}")
    variants = a.compare or sorted(p.name for p in a.runs_dir.iterdir() if p.is_dir())
    results = {}
    for v in variants:
        runs = [score_run(json.loads(p.read_text())["predictions"], gold, aliases, synonyms) for p in sorted((a.runs_dir / v).glob("rep-*.json"))]
        if not runs:
            print(f"\n{v}: no cached runs"); continue
        results[v] = runs
        print(f"\n{v}  ({len(runs)} replicate{'s' if len(runs) != 1 else ''})")
        for k in ("entity_f1", "entity_r", "entity_split_aware_p", "relaxed_f1", "relaxed_r", "undirected_f1", "strict_f1"):
            vals = [r[k] for r in runs]
            band = f"  band {noise_band(vals):.3f}" if len(vals) >= 2 else ""
            print(f"  {k:<22} {statistics.fmean(vals):.3f}  runs={[round(x, 3) for x in vals]}{band}")
        every = set.intersection(*[set(m for d in r["per_document"].values() for m in d["missed_entities"]) for r in runs])
        if every:
            print(f"  missed in EVERY run (prompt problem, not variance): {sorted(every)}")
    if a.compare and len(a.compare) == 2 and all(v in results for v in a.compare):
        x, y = a.compare
        for k in ("relaxed_r", "relaxed_f1", "entity_f1"):
            xv, yv = [r[k] for r in results[x]], [r[k] for r in results[y]]
            d, band = statistics.fmean(yv) - statistics.fmean(xv), max(noise_band(xv), noise_band(yv))
            verdict = "single runs: nothing proven" if len(xv) < 2 or len(yv) < 2 else ("NOT PROVEN (inside band)" if abs(d) <= band else ("better" if d > 0 else "worse"))
            print(f"\n{y} vs {x} on {k}: delta {d:+.3f}  band {band:.3f}  -> {verdict}")
        print("\nPower: on a small gold set one fact is several recall points; treat deltas under ~0.10 as unresolved unless the band says otherwise.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="run a prompt variant N times, cache raw output")
    e.add_argument("corpus", type=Path); e.add_argument("--gold", type=Path, required=True)
    e.add_argument("--variant", default="baseline"); e.add_argument("--replicates", type=int, default=1)
    e.add_argument("--prompt-file", type=Path); e.add_argument("--ontology", default="generic")
    e.add_argument("--model", default="claude-haiku-4-5"); e.add_argument("--runs-dir", type=Path, default=Path("runs"))
    e.set_defaults(fn=cmd_extract)
    s = sub.add_parser("score", help="score every cached run against the current gold/aliases (free)")
    s.add_argument("--gold", type=Path, required=True); s.add_argument("--aliases", type=Path)
    s.add_argument("--synonyms", type=Path, help="predicate synonyms {\"was commander of\": \"commanded\"}")
    s.add_argument("--corpus", type=Path, help="if given, prints the achievable ceiling first")
    s.add_argument("--runs-dir", type=Path, default=Path("runs")); s.add_argument("--compare", nargs="+")
    s.set_defaults(fn=cmd_score)
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
