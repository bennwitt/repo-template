---
name: deprecation-and-migration
description: Plan retiring APIs or features and migrating consumers or production schemas. Use for compatibility windows, expand/contract changes, backfills, cutovers, and removal criteria.
---

# Deprecation and migration

Read the current contract, consumers, deployment topology and available usage evidence. Define
the replacement's compatibility requirements before planning removal. Use `legacy-modernizer`
for broader system decomposition; this workflow owns the migration and retirement plan.

1. Inventory consumers, owners, retry/replay paths, old deployments and stored data. Classify
   unknown usage as unknown, not zero. State why the old system is being retired.
2. Verify the replacement covers required behavior, including errors and undocumented behavior
   that real consumers depend on. Provide migration instructions and tooling where useful.
3. Prefer advisory deprecation until a deadline is justified and agreed. Record the owner,
   supported window, compatibility strategy, and evidence required for each phase.
4. Migrate a small cohort, observe correctness and load, then expand. Define pause criteria and
   an executable recovery plan before a cutover. Use project-specific thresholds.
5. Remove the old system only after evidence covers all relevant consumers and the agreed
   observation window, including delayed jobs and offline clients. Retire its configuration,
   obsolete tests, documentation and deprecation notices together.

## Database changes

For a rename or representation change, separate these deploys:

| Phase | Evidence required before proceeding |
| --- | --- |
| Expand | Add the new nullable shape; old code continues to work |
| Dual-write | Every writer updates both representations; concurrency behavior is tested |
| Backfill | Restartable, bounded batches; progress, load and failures observable |
| Switch reads | Values agree; old deployments and retries remain compatible |
| Contract | No remaining old readers/writers; retention and recovery requirements met |

Design for concurrent backfill and live writes: a stale backfill must not overwrite a newer
value. Use conditional updates, version checks or an equivalent database-supported mechanism.
Prove retry idempotence, interruption recovery and reconciliation on representative fixtures.
Check the database/version's locking and online-index behavior before scheduling DDL.

An additive change may be reversible; dropping a column or deleting data often is not.
Distinguish code rollback, schema rollback, restore from backup, and forward repair. Test the
applicable recovery path and state possible data loss and recovery time based on evidence.
A `down` migration that recreates an empty column does not restore its data.

Deliver a phase plan with owners, compatibility tests, progress metrics, stop criteria and
recovery procedures. A plan authorizes no production writes or destructive changes by itself.

Adapted from Addy Osmani's `deprecation-and-migration` (MIT); pinned provenance is in the
standards repository's `.agents/skill-sources.json`.
