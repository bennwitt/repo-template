# Maintaining the agent capability catalog

The existing updater owns inspection, admission, staging, integrity checks, security scans and
transactional application. `new`, `update` and `check` remain offline. Missing or stale freshness
evidence prints a warning without changing their reconciliation result.

## Inspect and apply

```bash
repo-template globals --upstream --standards-root .
repo-template globals --upstream --force --json --standards-root .
repo-template globals --upstream --source langchain-ai/langchain-skills --max-age-hours 24
repo-template globals --upgrade --auto --dry-run --catalog-only --standards-root .
repo-template globals --upgrade --auto --catalog-only --json --standards-root .
```

Freshness means time since successful inspection, not the age of an upstream commit. The default
is 24 hours. Executable releases have a separate one-day cooldown. Yanked/deprecated releases are
excluded; reviewed pin exceptions still require a reason. Source inspection failures are isolated
and return exit 3 after remaining sources have been evaluated. Review-needed content remains
installed at its previous usable revision.

Inspection caches live under `~/.cache/repo-template/upstream/`, or `REPO_TEMPLATE_CACHE` for
isolated runs. They record attempted and successful checks separately. A failed attempt never
advances successful freshness; corrupt/missing evidence forces another check. A dry run writes
neither cache nor catalog state. Check evidence is disposable and never authorizes application.
Installed revisions and synchronization/validation provenance stay in the existing skill records.
Integrity-and-scan validation is identified explicitly; it does not claim a full test suite ran.

JSON inspection output includes the inventory, available references, source evidence, updates,
review candidates and errors. Sources, local adaptations, packs, pins, optional plugins and
documentation references are derived from existing manifests, including disabled entries.

Each existing source can set `admission.updates` to `auto` or `review`. Automatic mode accepts only
verified documentation updates with a clean scan and no review notes. Executable changes, new
capabilities without reviewed placement, altered permissions, license changes and unsupported
files remain for review. Local adaptations remain manual merges. Source discovery is configurable
through `discover`; explicit exclusions are retained. New sources can be inspected and explicitly
admitted through the existing `owner/repo@skill-or-path#ref` upgrade interface.

`--catalog-only` uses a temporary home for catalog regeneration, leaving the operator's client
configuration alone. Ordinary `globals` still performs machine setup. Upgrades require a clean
catalog; source-code changes outside the catalog can remain in progress.

## Native plugins and optional MCP

Vendored skills and standalone MCP definitions remain the default. Provider metadata lives in
the existing skill sources and pack manifests. Native plugins may contain hooks, mutable
dependencies or write-capable services: preview the exact provider before selecting it.

```bash
repo-template globals --check --plugin codex:langchain-mcp@langchain-plugins
repo-template globals --plugin codex:langchain-mcp@langchain-plugins
repo-template globals --check --plugin claude:azure@azure-skills \
  --allow-write-mcp claude:azure@azure-skills
repo-template globals --plugin claude:azure@azure-skills \
  --allow-write-mcp claude:azure@azure-skills
repo-template globals --remove-plugin codex:langchain-mcp@langchain-plugins
```

Selection runs native client commands and records confirmed installation evidence in
`~/.repo-template/capabilities.json`. Installation failure retains the managed fallback. Changed
plugin files or native plugin settings invalidate suppression evidence. Reselect a provider to
reconfirm it. Only owned links/configuration entries are reconciled; custom files are preserved.
Run the normal repository `check`/`update` workflow afterward to reconcile existing project links.
Plugin installation is user-scoped and can affect every session on that machine.

Fresh native installations require `reviewedRevision` (the immutable marketplace commit) and
`reviewedDigest` (the reviewed plugin subtree digest) in the provider record. Review manifests,
hooks, executable dependencies, license and permission scope at that revision first. The installer
verifies the marketplace origin, checkout and local subtree before invoking native installation,
then verifies installed content. External or floating plugin sources remain review-required;
the initial optional provider mappings deliberately carry no reproducibility claim or automatic
installation approval. Already installed native plugins can be explicitly selected for verified
asset reconciliation. Missing skills/MCP definitions retain their managed fallback.

Optional standalone integrations are activated independently:

```bash
repo-template globals --check --allow-write-mcp langsmith
repo-template globals --allow-write-mcp langsmith
repo-template globals --allow-write-mcp azure-write
repo-template globals --revoke-write-mcp azure-write
```

LangSmith uses the official remote endpoint and client OAuth. Complete sign-in in the client;
the base template works without it. Azure uses machine-owned Azure CLI authentication. Selecting
a pack never grants write access. The template changes no client trust, sandbox or approval
settings and never reads or stores credential values. A catalog bearer-token field is an
environment-variable name only, permitted for explicitly optional integrations and the existing
fixed GitHub read-only endpoint. Revoking a plugin grant removes the managed plugin; reconcile
affected projects afterward.

The five LangSmith evaluation skills are attributed local adaptations. Their authentication,
installation and feedback boundaries differ intentionally from the upstream native plugin.
Native provider selection is an explicit choice to use the upstream implementation.

## Scheduled updates and activation

The existing Catalog maintenance workflow runs at 06:17 and 18:17 UTC. Forced inspection provides
retry headroom; GitHub scheduling and service outages cannot guarantee a strict 24-hour SLA.
The job publishes inspection and upgrade reports as a 30-day artifact, even on failure.
Immutable blobs are reused after hash verification. Runs without admitted content changes skip
development dependency installation and fixture tests; no timestamp-only catalog changes are made.

Evaluation and tests run without write credentials. Publication uses a separate job and a scoped
GitHub App. Configure repository variable `MAINTENANCE_APP_ID` and secret
`MAINTENANCE_APP_PRIVATE_KEY`; install the App only on this repository, with Contents and Pull
requests and Checks write access, plus Administration read access for protection verification.
Enable repository auto-merge and squash merging and configure main branch protection to require the
quality and all MCP fixture jobs. Do not give the App a branch-protection bypass.

One `automation/catalog-maintenance` PR is outstanding at a time. A subsequent maintenance run
merges it only when its recorded head still matches, its author is the configured App, all expected
checks succeeded, an App-issued admission check matches that head, and repository review/protection
requirements are satisfied. Editing the PR description cannot authorize a different head. Missing, skipped,
pending or failed checks prevent merging. Human edits to the PR head require a new reviewed
candidate. The job never force-pushes an existing branch. Missing credentials, conflicts, moved
base revisions and unmet protections produce actionable failures, not bypasses.

When protection reports an otherwise validated PR behind `main`, the next evaluation rebuilds
the candidate on current `main`. Publication commits exactly that tested tree with the old PR
head and new base as parents, updates the existing PR without force, and issues fresh admission
evidence. Checks must pass on the new head before merging. If re-evaluation finds no eligible
changes, the obsolete automation PR is closed. Unrecognized head changes are never refreshed.

Customized native plugin files are preserved during removal. Revocation that cannot safely
remove a customized plugin reports failure and keeps its grant recorded: disable that plugin
in its native client before retrying. A failed fresh installation is rolled back through the
native client, retaining diagnostic content under `~/.repo-template/backups/`.

The validated artifact contains only an allowed catalog patch and evidence. Publication executes
the trusted default-branch helper, never candidate code or hooks. A merge can be rolled back by
reverting its PR. Automatic source changes never authorize deployments, application SDK migrations,
machine tool installations or enabling optional integrations.
