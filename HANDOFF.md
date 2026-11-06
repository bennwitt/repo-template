# Maintenance modernization handoff

Implementation of `docs/plans/REPO_TEMPLATE_MODERNIZATION_PLAN.md` in `/ai/Moore/repo-template`.
Changes are prepared for publication; Git history records the final commit and PR. The pre-existing
`machine_update_repo_update.md` is untouched. The
supplied plan is preserved with its target, formatting and implementation record updated.

## Delivered behavior

The existing registries, CLI, transactional updater and sole maintenance scheduler now cover
freshness evidence, source filtering, forced checks, maximum age, JSON, dry runs, automatic
admission and optional native providers. Default freshness is 24 hours; executable cooldown is
one day. Partial checks cannot claim complete freshness. Ordinary repository commands stay
offline with warnings and preserve “Standards are current” semantics.

Plugin receipts verify marketplace identity, installed manifest, actual assets, content and
executable permissions. Fresh installation needs reviewed revision/digest metadata; floating
sources remain review-required. Customized/unusable installations are preserved. Failed fresh
installs roll back with diagnostic backups; failed revocations explicitly retain/report active
grants. Pack selection never activates optional write MCP integrations. Authentication remains
machine-owned.

The twice-daily scheduler evaluates without write credentials, then uses a scoped App to publish
one eligible update PR. Merging requires exact-head App admission evidence, successful checks and
verified repository protections. Behind PRs are rebuilt from the newly tested tree without force
pushing. No candidate code runs in the credential-bearing publication job.

Five attributed LangSmith skills extend agent-evals. Native and legacy MCP examples have separate
locks. One injectable LangGraph runs locally, through FastAPI, Foundry Responses and Invocations.
The HTTP resume endpoint denies approval unless the application injects thread authorization.
See [maintenance operations](docs/maintenance.md) and [the example](examples/mcp/langchain/README.md).

## Accepted revisions and deferred candidates

The existing updater accepted `grilling`, `improve-codebase-architecture`, `research` and
`wayfinder` from `mattpocock/skills` at `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d`, after integrity,
license and scanner checks. LangSmith adaptations derive from `langchain-ai/langsmith-skills`
commit `13c168b28dbc3a7679e8f0358160063ad3329694`, with MIT attribution/license copies. The unrelated
langsmith-custom-apps capability remains excluded.

Native pins include langchain[mcp] 1.4.9, LangGraph 1.2.19 and langchain-azure-ai[hosting] 1.3.0.
Inspection caught LangGraph 1.2.20 inside its one-day cooldown; it was replaced with eligible
1.2.19 before final fixture validation. Required Azure preview dependencies are explicit pins
and remain labeled review-required. Legacy coverage locks langchain-mcp-adapters 0.3.2 and MCP 1.26.0.

Final complete inspection started at `2026-11-05T17:25:52.927371Z`: 310 inventory entries,
156 source/reference records, 132 current skill entries, 39 changed entries, 18 review entries,
263 discovered entries and zero source errors. Categories overlap; discovery does not authorize
installation or remove exclusions. Timestamp-only cache state is not committed.

| Deferred automatic candidates | Reason |
| --- | --- |
| azure-ai, azure-diagnostics, azure-validate | Executable/non-documentation changes |
| azure-prepare, microsoft-foundry, codebase-design | Changed files outside scanner coverage |
| code-reviewer, security-reviewer, spec-miner, fastmcp-server, model-recipes | Untrusted/new URLs need review |

Inspection also reports changed derived inputs for Addy Osmani adaptations,
knowledge-graph-extraction, code-review, implement-spec and shadcn; an Azure description override;
and a changed Vercel license input. These require manual reviewed merges. Executable pin updates,
unresolved build-backend versions and Azure preview dependencies remain visible. Initial native
provider mappings have no fresh-install approval or reproducibility claim: review the exact
marketplace revision, plugin subtree, license, hooks and dependencies before recording approval.

## Validation evidence

- Full root suite: **1,115 tests pass** (91.89 seconds); final targeted plugin/automation checks
  also pass after the last review corrections.
- Ruff lint, Ruff formatting (including the supplied plan) and mypy pass.
- Native LangChain: 15 tests pass, including real HTTP/stdio/in-process discovery, collisions,
  structured results, failed authentication, timeouts, lifecycle cleanup, approved/denied native
  MCP writes, durable SQLite recovery, and continuation/resume through all hosting adapters.
- Existing Python MCP: 12 tests pass. Legacy LangChain: 1 test passes.
- TypeScript build and 7 tests pass under pinned Node 22.22.0, used from a temporary npm cache.
- Full creation with uv.lock, update, repeated update, packs-only and personal adoption pass in
  temporary repositories/homes. Project content is preserved. Root self-check prints
  “Standards are current.” Catalog regeneration/integrity validation used temporary homes.
- Independent standards and specification reviews found cache-coverage, source-filtering,
  executable-mode, plugin rollback/preservation and PR-evidence issues; focused regression tests
  cover their fixes. No live GitHub publication, real-machine plugin installation, Docker image
  build or Azure deployment is claimed. Container/deployment configuration is supplied.

Session evidence is under `/tmp`: `repo-template-upstream-baseline.txt`,
`repo-template-upgrade-report.json`, `repo-template-final-upstream.json`,
`repo-template-full-tests.txt`, `repo-template-native-tests.txt`, `repo-template-legacy-tests.txt`,
`repo-template-python-fixture.txt`, and `repo-template-typescript-fixture.txt`.
The final upstream JSON contains available revisions and exact configuration-bound check evidence.

## Activation and rollback

The default gh account is read-only; the already authenticated repository-owner account has admin
access and is used per command for this implementation's PR, without changing the default login.
Scheduled automation still needs its own scoped App,
`MAINTENANCE_APP_ID`, `MAINTENANCE_APP_PRIVATE_KEY`, repository auto-merge/squash merging and
required main-branch checks. Give the App Contents, Pull requests and Checks write access plus
Administration read access to verify protection, with no protection bypass. Details are in
`docs/maintenance.md`. All publication behavior has been validated locally against stand-ins.

Revert a published maintenance PR to roll it back. Existing local transaction journals recover
on the next upgrade; retain staging directories until recovery completes. The disposable cache
can be removed to force unknown freshness and reinspection. Remove a confirmed plugin with
`--remove-plugin`, then reconcile projects with `check`/`update` to restore managed fallback
assets. Revoke optional writes with `--revoke-write-mcp`; if custom content or native errors
prevent removal, disable the integration in its client and resolve the conflict before treating
access as revoked. Diagnostic plugin backups are under `~/.repo-template/backups/`.

Use `UV_CACHE_DIR=/tmp/repo-template-uv-cache` for Python commands in this sandbox. Local MCP
fixtures need loopback sockets/process IPC; they ran with that permission and synthetic tools
and models. To discard the uncommitted implementation, review the changed-file list and restore
only task-owned changes, preserving the user's pre-existing documents.
