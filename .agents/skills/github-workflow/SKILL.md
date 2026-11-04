---
name: github-workflow
description: Work with GitHub repositories, pull requests and Actions using available MCP tools and gh. Use for GitHub inspection, PR creation or merging, CI diagnosis and account-context problems; issue management uses github-issues.
---

# GitHub workflow

Resolve the requested repository, host, branch and PR from the task and local remotes. Use an
explicit `--repo OWNER/REPO` when a command could target the wrong checkout. Inspect working-tree
status before changing branches; preserve staged and unrelated work.

## Choose tools and identity

Use the connected GitHub MCP for reads when it exposes the needed capability. Discover its tools
rather than assuming a tool name or treating a missing tool as missing data. repo-template's
managed endpoint is read-only. Use authenticated `gh` for task-authorized writes and capabilities
absent from MCP; consult `gh <command> --help` for the installed version.

MCP's `GITHUB_PERSONAL_ACCESS_TOKEN`, the active `gh` account and Git's SSH identity can differ.
A successful Git push does not prove the API account can open or merge a PR. Check `gh auth status`
and repository access when permissions fail; choose an already authorized account appropriate to
the target. Avoid changing the default account just to complete one repository's task. Keep token
values out of output, command arguments, repository files and PR descriptions. A repository `.env`
is not automatically loaded by every client.

## Pull requests

Read the repository's PR template and contribution rules. Use the existing `pr` skill for the
body's evidence and rollback details while retaining required repository headings. Reuse current
verification; identify the tested revision and any material limits. Write multiline text to a
file and pass `--body-file` instead of constructing shell-interpolated bodies.

Before creation, inspect existing PRs for the branch. Before retrying an uncertain API write,
check whether it already succeeded. Creating a PR, submitting a review, posting a comment and
merging are separate effects governed by the user's task and existing authorization.

For a requested merge, verify the base/head and required review/check state for the current head.
Treat pending, missing and skipped checks according to repository policy, not as success. Use
`gh pr merge --match-head-commit <reviewed-sha>` with the repository's merge method; avoid bypassing
protections. Verify the remote merged state and merge commit. Update a clean local default branch
with a fast-forward; use a separate worktree when the active checkout contains unrelated work.

## CI failures

Identify the failed run, job and revision using `gh pr checks`, `gh run view` and failed-job logs.
Redact credentials and private payloads from reports. Distinguish an application failure from an
infrastructure/authentication failure before rerunning. A workflow rerun can deploy or spend money;
its scope must fit the task. Use `github-actions-hardening` when changing workflow security.

References: [GitHub CLI manual](https://cli.github.com/manual/),
[merge head matching](https://cli.github.com/manual/gh_pr_merge),
[GitHub MCP](https://github.com/github/github-mcp-server).
