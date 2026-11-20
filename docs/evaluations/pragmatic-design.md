# Pragmatic design (the 72% plan): sources and candidates

Reviewed 2026-11-19 through a fan-out research run (5 search angles, 20 sources fetched,
25 claims adversarially verified by three votes each: 21 confirmed, 4 refuted). Repository
facts (stars, licenses, archive status) are as of that date.

## Recommendation

Author the `seventy-two-percent-plan` skill locally and pair it with the existing `the-fool`
in a `pragmatic-design` pack. Vendor nothing and ship no MCP server. The strongest external
candidates either overlap a route this catalog already chose or fail its licensing rule.

## Principles, ranked by verification strength

| Principle | Source | Verdict | Where it lands |
| --- | --- | --- | --- |
| Appetite: fixed time, variable scope | Shape Up ch. 3 and 6 | 3-0, three claims | Step 3 and the stop rule |
| The pitch: problem, appetite, solution, rabbit holes, no-gos | Shape Up ch. 6 | 3-0, two claims | Plan template sections |
| Prudent versus reckless debt; the design payoff line | Fowler, TechnicalDebtQuadrant, DesignPayoffLine, SacrificialArchitecture | 3-0, three claims | Shortcuts table, hardening path |
| Decide at about 70% of the information | Bezos, 2016 letter | 3-0 | Stop rule, pivot rule |
| One-way and two-way doors | Bezos, 2015 letter (SEC exhibit) and 2016 letter | 2-1 (the one-way wording lives in the 2015 letter) | Door sort, `one-way-doors.md` |
| MADR 4.0.0 as the lean record format (MIT OR CC0-1.0) | adr.github.io/madr | 3-0, two claims | Hardening path points to `domain-modeling` |

Not verified in this run, cited in `principles.md` from the authors' own texts: Choose Boring
Technology (McKinley), YAGNI (Fowler; Beck), Gall's law, the walking skeleton and tracer
bullets, and the prototype pitfall (Atwood). "Disposable data" has no primary source and is
stated as this repository's own rule.

Refuted and kept out of the skill: that Shape Up frames quality as constraint-relative (1-2);
that Bezos's "being wrong is cheaper than being slow" justifies disposable schemas (0-3); a
detailed inventory of rjs/shaping-skills (0-3); that the wshobson ADR skill's scope table
matches the one-way-door test (1-2).

## Candidates

| Candidate | Facts | Disposition |
| --- | --- | --- |
| obra/superpowers `skills/brainstorming` | MIT; v7.0.2 (2026-11-03); design doc with goals, non-goals, anti-goals, alternatives, what is left to the builder; its full path gates into `writing-plans` | Not vendored. [superpowers.md](superpowers.md) (2026-11-03) already keeps the current route and borrows its techniques; the local skill borrows non-goals and "left to the builder". |
| wshobson/agents `plugins/documentation-generation/skills/architecture-decision-records` | MIT (2024 Seth Hobson); last change 2026-10-17; lightweight ADR, Y-statement and MADR-style templates, split under Codex's 8 KB cap | Not vendored. ADRs are already the global `domain-modeling` skill's job and `architecture-designer` writes them too; a third would be sprawl. The one vendorable option if the pack ever needs templates of its own. |
| rjs/shaping-skills | Archived; README declares the skills obsolete; no license (API `license: null`) | Must not be vendored: fails the licensing rule. Prior art only. |
| MADR 4.0.0 templates | MIT OR CC0-1.0; newest release 2024-09-17 | Not vendored; the plan's one-way-door table is leaner, and the hardening path names when to promote rows to records. |
| `@adrkit/mcp` | Apache-2.0; read-only stdio server with four tools over ADRs in a git worktree; 26 stars; v0.20.0 (2026-10-11); tool set has changed across releases | No MCP server shipped. Pays off only if a project adopts adrkit's whole layout; too small and too mobile for the catalog's pin and admission rules. |

## Method and limits

Sources are primary but first-party: a method author's book, a CEO's letters, essayists' own
sites. They establish what each author prescribes, not that it works. No skill from a candidate
repository was installed or run. The research run's full output is not committed; the verified
claims and their sources are reproduced in the skill's `references/principles.md`.
