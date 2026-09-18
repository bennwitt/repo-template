# The prompts, and what was measured

Three prompts in `kg_pipeline.py`: `EXTRACTION_PROMPT`, `RESOLVE_PROMPT`,
`ASK_PROMPT`. Each clause below does specific work; extraction feeds
resolution feeds assembly, so a change in one shows up as a vague quality
drop two stages later. Where a claim was measured, the measurement is here;
where it wasn't, it says so.

## Extraction

The vocabulary block is generated from the ontology and is not prose to edit —
change the ontology.

**"central to what this document is about; skip incidental mentions"** — the
precision lever. Too weak: orphans in the health report. Too strong: gold
entities missed. Tune with the eval harness, not by eye.

**"Write each mention exactly as it appears… Do not normalise, expand or
canonicalise"** — the extractor must emit surface forms. Resolution needs the
original form as evidence, and an extractor that canonicalises hides its own
mistakes. Measured: without this clause the model returns `Ledger API` for
`ledger-api` and the alias is lost.

**"write a one-sentence description… used later to tell apart entities that
share a name"** — the most important clause in the pipeline, and its value is
non-local. Resolution compares descriptions, not strings. Telling the model
*why* the description exists makes it write to distinguish, not to summarise.
Measured across six agent runs: the one implementation that dropped
descriptions fell back to name matching and split entities across documents.

**"Relation direction is source -> target as each type's description states"**
— without it, a reasonable extractor emits some relations backwards. Direction
mismatches show up as a gap between the *relaxed* and *undirected* relation
tiers in the eval; the fix is this clause and the edge descriptions, not the
extractor.

**"Every relation must connect two entities you extracted"** — `enforce_ontology`
drops dangling relations *with a reason*; this clause keeps that list short.

**"select the source passage id"** — evidence is an anchor the model picks from
a closed list, decoded to the verbatim passage afterwards. A hallucinated quote
is unrepresentable.

**"The document title is part of the source"** — incident IDs, ticket numbers
and dates live in filenames. Four independent runs on a five-file corpus lost
every incident node before this clause and the `document_text()` change.

### The recall clause — measured, and not what the docs used to say

An earlier version of this file said adding *"Extract every stated
relationship, including minor ones."* trades precision for recall. It was
tested: three replicates per arm on a two-document gold set.

```
                 relation R   relation P   relation F1
baseline            0.140        0.387        0.207
recall-tuned        0.180        0.503        0.260
delta               +0.040       +0.117       +0.053
noise band           0.060   →   NOT PROVEN
```

The recall gain is inside the band. Precision went *up*, not down. There is no
evidence for the tradeoff that was asserted. Use the clause if relation recall
is your binding constraint, run three replicates, and believe the band.

## Resolution

**"Each input name must appear in exactly one cluster"** — a correctness
requirement, not style. The pipeline backstops it (a forgotten name becomes its
own node), but the model placing the name is far better than the fallback
inventing an unmerged one.

**"genuinely distinct get their own single-element cluster"** — counters the
pull toward tidy output. Without it resolution over-merges to produce a
satisfying short list.

**"Use the descriptions to avoid merging entities that merely share a name,
and to merge entities whose names differ but whose descriptions clearly denote
one thing"** — both directions stated, because the model needs both. Measured
live on the incident corpus: `MP checkout` → `Meridian Payments checkout`,
`Payments Platform team` → `Payments Platform`, `J. Okonkwo` → `Jane Okonkwo`
all merged correctly (the first two by the model, the last by string rules
before any call). Two under-merges remained — `batch job` vs `reporting batch
job`, `Meridian Payments` vs `Meridian Payments checkout` — with the model
confident they were distinct. Both are defensible readings of the source, and
both show why the review queue and the health report exist.

**"confidence from 0 to 1 and one sentence of reasoning"** — feeds the review
queue. Below the threshold, aliases are kept *apart* until a person decides.

**Resolve one entity type at a time.** Cross-type clustering invites nonsense
merges and lengthens the prompt for nothing.

## Answering

**"Cite the specific edges"** and **"say so rather than filling the gap from
general knowledge"** — the value of a grounded answer over an ungrounded one is
traceability, and on a private corpus the ungrounded answer does not exist at
all. Measured: asked which teams connect to Redis incidents, the model cited
every edge, separated direct from indirect connections, and flagged the two
unmerged `batch job` nodes as a limitation of the graph rather than papering
over them.
