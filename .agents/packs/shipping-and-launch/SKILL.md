---
name: shipping-and-launch
description: Evaluate release readiness and prepare a staged rollout and recovery plan. Use before production launch or a risky cutover to combine correctness, security, testing, operational and compatibility evidence.
---

# Release readiness

A readiness review produces a decision and a plan. Deployment, publishing, pushing and destructive
changes remain governed by the user's actual authorization; a GO verdict does not grant it.

## Pin the release

Identify the exact revision/artifact, diff base, target environment, affected users, data and
dependencies. Include relevant uncommitted work only when it belongs to the requested review,
and label it so a verdict cannot be mistaken for approval of a different build.
Read the project checks, operational requirements, rollout history and known constraints.

## Collect independent evidence

For a substantial or sensitive release, use independent reviewers when the host supports them.
Give each the same frozen scope and relevant evidence, and ask for:

- correctness, requirements and compatibility;
- threat model, authorization, data handling and dependency exposure;
- tests, missing failure cases, concurrency and recovery coverage.

Bound the work to the task. Reviewers return findings and evidence; they do not change the target,
deploy, or recursively delegate. With no subagents, run the passes sequentially and explicitly
report that they were not independent. For a small low-risk change, a focused combined pass is
sufficient; choose effort by impact, not an arbitrary line-count threshold.

Check operational evidence directly: migrations and mixed-version compatibility, configuration,
secrets references, health signals, alerts/runbooks, capacity, accessibility for UI changes, and
relevant performance measurements. Mark missing environment access or artifacts as unverified.
Do not infer production readiness from passing unit tests alone.

## Plan rollout and recovery

Choose stages from deployment capabilities and traffic volume, not fixed percentages. For each,
state owner, observation window, success/stop thresholds and the signal that measures them.
Include low-traffic and delayed-job behavior; a short quiet canary may provide little evidence.

Write recovery steps for the exact artifact and data changes. Distinguish code rollback from
irreversible data effects, and identify restore or forward-repair requirements. Quote recovery
times only when measured or explicitly identified as targets. Plan flag retirement and the
conditions for removing compatibility code.

## Report

Return GO, NO-GO, or INSUFFICIENT EVIDENCE for the stated scope. Include blockers with locations
and supporting evidence, unresolved checks, explicitly accepted risks, the rollout/recovery plan,
and links to test and specialist reports. A material unresolved security/correctness issue blocks
a GO recommendation; missing essential evidence cannot be converted into a pass.

Adapted from Addy Osmani's shipping skill, ship command, definition of done and review personas
(MIT). These portable review roles are contained here; upstream plugin commands are not required.
