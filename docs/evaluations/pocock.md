# Pocock collection evaluation — 2026-10-27

## Scope and evidence

Reviewed all 38 skill entry points in `mattpocock/skills` at **59db609eb1e18aaf59b63284d0e52255aff0c63c**: the 35 already included by repo-template and its three explicit omissions. Compared skill-tree hashes with the current lock, read their workflow instructions, inspected the executable/supporting templates, and compared the engineering workflow with Addy Osmani's collection at **aeac41d4d005999432bb7312f7ff06383a91d59d**. Sources below link to immutable commits. This is a source and integration review, not a controlled model-performance benchmark. Popularity and upstream marketing do not establish superiority.

The existing 35 skills have current upstream trees except `setup-matt-pocock-skills`. Its new body adds migration from legacy CONTEXT names and insists on a working remote for a GitHub/GitLab tracker. There are no newly discovered skill names beyond the three already excluded. A different repository commit alone is not a reason to replace byte-identical skill folders.

Primary sources: [upstream tree](https://github.com/mattpocock/skills/tree/59db609eb1e18aaf59b63284d0e52255aff0c63c/skills), [Addy skill tree](https://github.com/addyosmani/agent-skills/tree/aeac41d4d005999432bb7312f7ff06383a91d59d/skills). The source remains MIT-licensed. Skill preservation includes its bundled `agents/openai.yaml` metadata and references.

## Findings that affect the template

### Correct the default review scope

Pocock's [code-review](https://github.com/mattpocock/skills/blob/59db609eb1e18aaf59b63284d0e52255aff0c63c/skills/engineering/code-review/SKILL.md) advertises reviewing work in progress but uses `git diff <fixed-point>...HEAD`. That reviews committed branch changes only. In an agent session ending with uncommitted edits, the skill can produce an empty review or omit the actual work. It also requires tracker setup before checking whether a local spec or the user's current request supplies the requirements.

Keep the useful split between independent Standards and Spec reviews, but make this skill a clearly attributed local adaptation. Preserve its documented-standard precedence and its distinction between heuristic smells and proven defects. Make the following scope choices explicit:

- Working tree: compare tracked files against HEAD with `git diff HEAD --`, and separately enumerate/read relevant untracked files using `git ls-files --others --exclude-standard`. This includes staged and unstaged net changes. Do not stage files merely to review them.
- Staged only: use `git diff --cached --` and label the scope accordingly.
- Committed branch: resolve the base and head commits first, compute their merge-base, then diff the two captured SHAs. An explicit request for an exact two-point comparison must retain that meaning instead of silently using merge-base.
- Branch plus current work: diff the captured merge-base against the working tree, plus relevant untracked files. State that working-tree content is not immutable and detect changes during a long review before declaring coverage complete.
- Use the user's supplied scope. If absent, infer the active task's edited files; ask only if competing scopes would materially change the result. If there truly are no changes, report that without spawning reviewers.
- Treat local specs and the conversation as legitimate requirements. Read a configured tracker when necessary. Missing tracker configuration is not a blocker for a local review.
- Pass the same captured scope, requirements and standards to both reviewers. Where subagents are unavailable, perform the two passes sequentially and disclose that limitation.

Verification cases should include staged-only changes, unstaged-only changes, an untracked implementation file, a committed branch with no dirty files, a dirty branch with both kinds, and a local-spec review without tracker configuration. A test that merely checks the words `git diff HEAD` appear in the document does not prove review behavior.

### Keep setup, adapt its ownership and effect boundaries

The [setup skill](https://github.com/mattpocock/skills/blob/59db609eb1e18aaf59b63284d0e52255aff0c63c/skills/engineering/setup-matt-pocock-skills/SKILL.md) configures workflow state; it does not install skills. Keep its familiar invocation for existing users and adapt it locally:

- `AGENTS.md` is the template's authoritative guide; `CLAUDE.md` is an `@AGENTS.md` stub. Add the context pointer to AGENTS, retaining the stub. The upstream preference for CLAUDE conflicts with this repository's documented ownership model. The same issue exists in `setup-ts-deep-modules`; project guidance should explicitly preserve that ownership.
- Reuse existing `docs/agents/issue-tracker.md`, `triage-labels.md`, and `domain.md` before asking questions. Keep edits focused and preserve local choices.
- Use local Markdown as a workable default when no tracker is configured, rather than requiring a remote setup merely to plan or review local work. A chosen remote tracker must be reachable before publishing there, but configuring a remote is a distinct action.
- Confirm only unresolved choices. Existing session decisions are sufficient. Ordinary TDD, debugging, or local review does not require setup.
- Separate creating local configuration from remotely creating labels. Write the draft/config first and publish labels only when the user has authorized those external changes.
- Preserve the latest useful legacy glossary migration behavior without moving project-owned files automatically over conflicting destinations.

The bundled tracker templates contain useful native dependency and wayfinding conventions; preserve these resources if deriving a local setup skill. Record derivation at this commit and copy the MIT license. Never label a changed body as byte-identical vendored content.

### Prefer targeted complements over a second universal workflow

Pocock's current implementation flow already composes `to-spec`, `to-tickets`, `implement`, `implement-spec`, `tdd`, and `code-review`. The [parallel implementation skill](https://github.com/mattpocock/skills/blob/59db609eb1e18aaf59b63284d0e52255aff0c63c/skills/engineering/implement-spec/SKILL.md) adds a real task-graph frontier and worktree isolation. It is not equivalent to a short generic implementation checklist. Conversely, Pocock's concise review lacks Addy's explicit production-readiness and measured performance breadth. These are complements, not grounds for deleting the existing implementation flow.

Addy's `source-driven-development` is distinct from Pocock `research`: it requires version-specific primary documentation at implementation time; `research` delegates a question and produces a durable artifact. Likewise, observability, explicit quality budgets and release readiness deserve scoped routes rather than being dismissed because a broad SRE or review skill exists.

### Keep boundaries and costs visible

- `tdd` explicitly puts refactoring in review, whereas Addy's TDD uses red/green/refactor. Pick one process per task and explain this difference; do not claim these are interchangeable. Preserve the useful public-interface, independent-expectation and vertical-slice principles. Established test seams and prior approval should satisfy the agreement requirement without repeated questions.
- `implement` commits at completion; `implement-spec` can create PRs, merge branches, close tickets and clean worktrees. These are explicit workflows, not default actions for every coding request. Session authorization and repository rules determine external effects.
- `wayfinder` is for large uncertain planning and can create/close issues and push research branches. Its recursive research delegation and parallelism need a host budget. Keep user invocation and clearly label tracker/network effects.
- `diagnosing-bugs` is excellent at insisting on a real failing signal, but literal claims that a loop guarantees finding every cause or must always take seconds are aspirations. For inaccessible production environments, report missing evidence without blocking unrelated progress.
- The Claude-only `claude-handoff` starts a separate `claude --bg` process. Prefer portable `handoff` on other hosts; do not present it as a generic Codex feature.
- The six included in-progress skills remain upstream beta: `claude-handoff`, `loop-me`, `setup-ts-deep-modules`, `writing-beats`, `writing-fragments`, `writing-shape`. Retaining current user-invoked availability avoids breaking users and consumes little discovery budget, but document their status. [Upstream beta policy](https://github.com/mattpocock/skills/blob/59db609eb1e18aaf59b63284d0e52255aff0c63c/skills/in-progress/README.md).

## Complete disposition matrix

`Global explicit` means retained globally with user-only invocation; it does not automatically activate during ordinary coding. The proposed adaptations keep existing names and placements.

| Skill | Recommended disposition | Evidence and judgment |
| --- | --- | --- |
| ask-matt | Keep, global explicit | Useful existing router and phase-boundary guidance; avoid loading it alongside a second universal router. Read target skills before recommending them as its own body requires. |
| claude-handoff | Keep, global explicit, label Claude-only beta | Launches `claude --bg`; portable `handoff` is the route on other hosts. |
| code-review | Local adaptation, global | Retain independent Standards/Spec passes; repair dirty/untracked scope and unnecessary tracker setup. |
| codebase-design | Keep, global | Specific deep-module/interface/seam vocabulary and alternate-design resource; Addy's API checklist covers a different surface. |
| diagnosing-bugs | Keep, global | Real reproduction loop, falsifiable hypotheses, minimized regression, cleanup; stronger focused bug protocol than a generic triage list. |
| domain-modeling | Keep, global | Distinguishes glossary from implementation notes and restricts ADRs to meaningful decisions. |
| git-guardrails-claude-code | Keep only as explicit optional setup, document limitations | Regex hook is not a security boundary; existing documented bypasses remain. Never install it in portable fail-open hooks automatically. |
| grill-me | Keep, global explicit | Thin stateless wrapper over shared grilling primitive. |
| grill-with-docs | Keep, global explicit | Reuses grilling plus domain-modeling without copying either workflow. |
| grilling | Keep, global | Dependency-aware question rounds and environment lookup reduce repeated questions; invoke only when requested or meaningful uncertainty warrants it. |
| handoff | Keep, global explicit | Portable artifact, primary-source pointers and redaction; useful independently of specific harnesses. |
| implement | Keep, global explicit | Concise TDD plus review execution route; commits are a deliberate workflow effect. |
| implement-spec | Keep, global explicit | Task graph, ready frontier, isolated worktrees and integration review; requires subagent/worktree support and authorized tracker writes. |
| improve-codebase-architecture | Keep, global explicit | Focuses on change hotspots and deepening candidates, then human selection; HTML uses external CDN assets, so offline rendering may degrade. |
| loop-me | Keep, global explicit beta | Produces workflow specifications; no automatic schedule installation. Different purpose from engineering implementation. |
| migrate-to-shoehorn | Keep in typescript pack | Focused test fixture migration; honor detected package manager and install as a test/dev dependency despite upstream's generic `npm i` example. |
| pr | Keep, global | Before/after evidence and reversibility are useful; repository PR templates and user requirements remain authoritative. |
| prototype | Keep, global | Answers one design question and separates disposable code from production; preserve user work and authorize branch/commit effects. |
| research | Keep, global | Primary-source research artifact via delegation; complementary to implementation-time source verification. |
| retro | Keep, global explicit | Turns repeated mechanical failures into executable checks and limits agent-instruction bloat. |
| setup-matt-pocock-skills | Local adaptation, global explicit | Configure workflow facts, preserve AGENTS authority, use known/default local choices, avoid automatic remote side effects. |
| setup-ts-deep-modules | Keep in typescript pack, explicit beta | Concrete dependency-cruiser rules with observed pass/fail/pass verification; retain AGENTS pointer convention and project layout. |
| tdd | Keep, global | Independent expected values, public-interface seams and one slice at a time. Document its refactor-in-review choice and honor previously agreed seams. |
| teach | Keep, global explicit | Stateful teaching workspace; different from repository documentation generation. No automatic invocation on engineering questions. |
| to-questionnaire | Keep, global explicit | Elicits information held by a third party without sending it; useful async requirements tool. |
| to-spec | Keep, global explicit | Synthesizes existing conversation and testing decisions; avoid redundant interviews, preserve tracker authorization. |
| to-tickets | Keep, global explicit | Native blockers, vertical slices and wide-refactor expand/contract exception; good input to task-graph execution. |
| triage | Keep, global explicit | State machine, reproduction, redundancy/prior-rejection checks and durable briefs; writes external comments/labels only within invoked scope. |
| wait-what | Keep, global explicit | Small conversational correction tool with no competing execution process. |
| wayfinder | Keep, global explicit | Multi-session decision map, rather than implementation todo list; valuable for large uncertainty but too heavy as a default. |
| wizard | Keep, global | Human-only setup steps, hidden input, secret-safe GitHub writes and static script verification; do not run interactively on the user's behalf. |
| writing-beats | Keep, global explicit beta | Interactive article composition; no added autonomous engineering policy. |
| writing-for-agents | Keep, global | Specific context-pointer, invocation and progressive-disclosure principles; supports the local adaptations. |
| writing-fragments | Keep, global explicit beta | Append-only material collection respecting concurrent user edits. |
| writing-shape | Keep, global explicit beta | Separate input/output files and incremental human-approved writing. |
| chief-of-staff | Continue exclusion, revise reason | Still unlisted in beta README; broad all-subagent mandate and proactive environment changes risk expanding every task. Lack of bounded budgets/work scope is a concrete reason, not beta status alone. |
| scaffold-exercises | Continue exclusion | Requires `pnpm ai-hero-cli internal lint` and course-specific layout unavailable to general repositories. |
| setup-pre-commit | Continue exclusion | Husky/Prettier setup can replace hook ownership and creates a conflicting source of check configuration. Existing baseline owns hooks; a targeted TS integration would need an explicit design. |

Each row refers to the same-named skill under the pinned [engineering](https://github.com/mattpocock/skills/tree/59db609eb1e18aaf59b63284d0e52255aff0c63c/skills/engineering), [productivity](https://github.com/mattpocock/skills/tree/59db609eb1e18aaf59b63284d0e52255aff0c63c/skills/productivity), [misc](https://github.com/mattpocock/skills/tree/59db609eb1e18aaf59b63284d0e52255aff0c63c/skills/misc), or [in-progress](https://github.com/mattpocock/skills/tree/59db609eb1e18aaf59b63284d0e52255aff0c63c/skills/in-progress) folder.

## Security and portability review

No skill-body evidence reviewed here establishes malicious intent. Treat that as a bounded source-review conclusion, not a guarantee. The actual bundled executables/configurations reviewed were:

- `diagnosing-bugs/scripts/hitl-loop.template.sh`: prompts a human, captures visible observations, prints them back. Its comments explicitly reserve sign-in for a step rather than secret capture. Avoid pasting secrets into observed error output.
- `wizard/template.sh`: interactive browser opening and dotenv/GitHub writes, hidden secret entry, no eval, secret values piped to `gh secret set`. Its writes are material effects that require the intended wizard scope; do not run the sample Stripe setup during evaluation. The writer deliberately follows existing `.env` symlinks and retains existing file modes, so it does not make a preexisting world-readable secret file safe.
- `git-guardrails-claude-code/scripts/block-dangerous-git.sh`: text regex matching, not shell parsing. Global flags such as `git -C ... push` and wrappers can bypass it; innocent text can also match. It prints the whole blocked command, so command strings containing secrets could leak. This is a convenience hook and should never be sold as complete enforcement.
- `setup-ts-deep-modules/dependency-cruiser.config.cjs`: static import-boundary rules, no install hooks/network calls. The configuration is specific to flat packages and needs the actual packages root.

Markdown-link audit found no missing bundled reference dependencies; unmatched relative links were clearly example project paths or placeholder links. Unlike several Addy workflows, these skills' real supplementary files are co-located. Cross-skill dependencies within the selected Pocock graph are present. The `agents/openai.yaml` files provide UI metadata, not blanket permission grants.

## Required documentation updates

1. Replace blanket "run setup before any engineering skill" advice with conditional setup for missing tracker/domain configuration. Show local-only workflows and distinguish availability, invocation and configuration.
2. Explain the primary path and its boundaries: clarify → spec/tickets when needed → implement/TDD → review; Addy production workflows complement this path.
3. Show all nine Addy command intents mapped to actual installed skills; do not claim native slash-command wrappers were installed when only portable skills were added.
4. Name beta and host-specific Pocock tools in the catalog/guide rather than hiding them in a count of global skills.
5. Record adaptations as local derivations with upstream source/path/commit/license, and distinguish them from pristine vendored trees in notices.
6. Keep evidence claims precise: source review and integration tests passed is different from a measured reduction in task failures.

## Automated scan result

Ran repo-template's committed `skill-scanner` implementation with PyYAML 6.0.3 against all 38 upstream skill directories. **All 38 returned zero pattern findings.** Raw reports are in `/tmp/pocock-scan.json`. Executed the trusted local scanner only; did not execute the upstream shell templates, install their hooks, contact trackers or run their workflows. The scanner reads only its recognized entry/reference/script locations, so manual review above also covered root-level shell templates and the dependency-cruiser config. This scan is deterministic pattern detection; it cannot demonstrate behavioral effectiveness or prove absence of security defects.
