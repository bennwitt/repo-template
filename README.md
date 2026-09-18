# repo-template

`repo-template` creates a complete Python/uv repository and safely brings existing
repositories toward the same standard. This repository also owns the portable Codex and
Claude skills/settings shared across your machines.

The baseline was derived from BidCore, with project-specific code and configuration removed.
It keeps the useful parts: source layout, uv, pytest, Ruff, mypy, CI, Dependabot, VS Code,
Git hooks, agent guidance, context/ADR documentation, and secret-safe defaults.

## Install

Keep this repository at a stable path. On your Mac, `/aiDevStandards` is the recommended
location:

```bash
git clone YOUR_GITHUB_REPOSITORY /aiDevStandards
cd /aiDevStandards
uv tool install --editable .
repo-template globals --standards-root /aiDevStandards
```

On this Linux machine the same commands work with `/ai/Moore/repo-template` as the path.
An editable tool install means CLI changes take effect without reinstalling it.

## Create a repository

```bash
repo-template new my-service \
  --parent /ai/Moore \
  --description "Processes customer jobs."
cd /ai/Moore/my-service
uv run pytest
```

By default, `new` initializes Git on `main`, enables `.githooks/pre-commit`, and creates
`uv.lock`. Use `--no-git` or `--no-lock` only when another system owns those steps.

## Update an existing repository

Preview first, then apply:

```bash
repo-template check /path/to/repository
repo-template update /path/to/repository
```

Update behavior is intentionally conservative:

- Missing files are created.
- `.gitignore`, VS Code JSON, and compatible `pyproject.toml` settings are merged.
- Generated files are updated only when their last generated version was not edited.
- Existing project documentation and source files are treated as seeds and preserved.
- Conflicts are listed for manual review, never silently overwritten.
- `.repo-template.json` records template ownership and project variables.
- `uv.lock` is created or refreshed when project dependencies change; use `--no-lock` when
  another system owns the lockfile.

Exit code `2` from `update` means files were preserved for manual review. Exit code `1` from
`check` means the repository is not current.

## Global AI standards

The standards repository intentionally versions:

- `.agents/skills/` as the single skill source for Codex and Claude
- `.claude/settings.json` as portable Claude settings
- `.claude/skills/` as a visible mirror of the same skills

Run:

```bash
repo-template globals --standards-root /aiDevStandards --check
repo-template globals --standards-root /aiDevStandards
```

The command links `~/.agents` to the central copy, links `~/.claude/settings.json`, creates
one Claude skill link per central skill, and adds `.agents`, `.claude`, and `.codex` to your
global Git ignore. It does **not** link all of `~/.claude`, so credentials, session history,
caches, machine state, and Claude's `synced` directory remain local. Replaced files are moved
to timestamped backups under `~/.repo-template/backups/`.

Set `AI_DEV_STANDARDS=/aiDevStandards` to omit `--standards-root`.

## Maintain and publish

```bash
uv sync --dev
uv run ruff check .
uv run mypy src
uv run pytest
git add .
git commit -m "Initialize repository standards"
git remote add origin YOUR_GITHUB_REPOSITORY
git push -u origin main
```

Edit template content in `src/repo_template/templates.py`. Increase the package version in
`pyproject.toml` and `src/repo_template/__init__.py` when changing generated standards, then
run the test suite before publishing.
