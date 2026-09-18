# Evaluating extraction quality

Without a gold set you are tuning prompts on vibes. With one, and with the
checks below, you can tell a real change from noise. That distinction is the
whole point; most eval scripts skip it.

## Run it

```bash
# 1. extract: cache raw model output, N independent replicates per variant
python eval_extraction.py extract corpus/ --gold gold.json --variant baseline --replicates 3 --ontology incident
python eval_extraction.py extract corpus/ --gold gold.json --variant recall --prompt-file recall.txt --replicates 3 --ontology incident

# 2. score: free, re-grades every cached run against the CURRENT gold + aliases
python eval_extraction.py score --gold gold.json --aliases aliases.json --corpus corpus/ --compare baseline recall
```

Extract and score are separate on purpose. When you fix the alias map, the
old baseline is re-graded with it, so you can never compare a leniently graded
new prompt to a strictly graded old one. The score command prints a rubric
fingerprint so two people looking at different numbers can tell whether they
graded against the same rubric.

## Read the ceiling first

`score --corpus` prints the **achievable recall ceiling**: the fraction of gold
entities and relations whose names actually appear in the source text (after
aliasing). Everything above it is unreachable regardless of the prompt.

This is not hypothetical. The cookbook this skill descends from published
expected baselines (entities F1 0.75–0.85, relations 0.60–0.75). Run against
today's Wikipedia the same unmodified scorer gets 0.63 and 0.22 — with entity
precision 1.00. The summaries got shorter; Saturn V, Kennedy Space Center,
Gemini 8 and Purdue no longer appear in them. Anyone who trusted the published
numbers would have "fixed" a prompt that was performing near the data ceiling.
That is why no expected scores appear anywhere in this skill.

**Precision near 1.0 with low recall means drift, not a bad prompt.** Check the
`absent` list per document, then fix the gold set or the corpus.

## The gold set

Two to five representative documents, hand-labelled. It is a tripwire, not a
benchmark; an afternoon is enough. Pick documents that differ from each other —
one dense, one sparse, one with the naming variants you know are hard.

```json
{"INC-2209 ledger latency": {
   "entities":  [{"name": "Ledger API", "type": "SERVICE"}, {"name": "Reporting", "type": "TEAM"}],
   "relations": [{"source": "Ledger API", "predicate": "DEPENDS_ON", "target": "shared Redis cluster"}]}}
```

Keys are document titles and must match what the loader produces (the filename
stem). The **alias map** maps lowercased surface variants to the gold name:

```json
{"ledger-api": "ledger api", "j. okonkwo": "jane okonkwo", "mp checkout": "meridian payments checkout"}
```

Without it a correct prediction in a different surface form scores as a miss,
and you tune against a measurement artefact. Treat the map as living: every
time a *correct* prediction is scored as a miss, add the variant. The score
command re-grades everything when you do.

## What the numbers mean

**Entity precision / recall / F1** — set-based after canonicalisation.

**Split-aware precision** — distinct gold entities matched ÷ predicted node
count, alongside a `fragmentation` count. Two unmerged nodes for one entity
cost precision here and not in the set-based number. This is the metric that
sees the failure a naming-variant corpus is designed to exhibit.

**Relations, three tiers.** *Relaxed* matches endpoints only and ignores the
predicate — an upper bound, because "destroyed" between the right two nodes
counts. *Undirected* also ignores direction: a gap between relaxed and
undirected is usually a prompt-convention mismatch (the extractor wrote
`A OWNS B` where gold has `B OWNED_BY A`), fixed in the prompt, not the
extractor. *Strict* requires the predicate after `--synonyms` normalisation;
the gap between strict and relaxed is mislabelling. Report all three.

**Missed in every run** vs **missed in some runs** — a fact missing from every
replicate is a prompt problem; one missing from some is variance. They need
different fixes and the output separates them.

## The noise band

With replicates, each metric gets a band of `max(2 × SE, 0.02)`. `--compare A B`
reports the delta against the larger of the two bands and refuses to call a
delta inside it anything but "not proven".

Measured: the recall-tuning clause in `prompts.md`, three replicates per arm
on a two-document gold set, moved relation recall by +0.04 against a band of
0.06. Not proven. Precision moved +0.12 — the opposite direction from what the
clause's description had asserted. A single run would have reported "+0.04
recall, ship it". The band is what makes the harness honest.

**Power.** On a small gold set one fact is several recall points and the CI is
wide. This harness catches broken prompts, resolution regressions and changes
worth more than ~10 points. It cannot resolve v7-beats-v6-by-two-points; for
that you need more annotated documents, not a better prompt.

## Resolution is scored indirectly

`eval_extraction.py` scores stage 1. Resolution quality shows up as
`components` in the graph health (islands = under-merging), `fragmentation`
here, and the review queue. Build the control graph with `--skip-resolution`
and compare node counts: that is the measured difference resolution makes.
