# Project context

## Purpose

`repo-template` is the single maintained source for repository engineering defaults and
portable AI-development configuration across machines.

## Domain language

- **Standards repository**: this Git repository, including the CLI and portable global files.
- **Project baseline**: the files rendered into a new or existing application repository.
- **Managed file**: a generated file that may be updated only while unchanged since generation.
- **Seed file**: a generated starting point that becomes project-owned immediately.
- **Portable global**: a skill or setting safe to version and use on multiple machines.
- **Machine state**: credentials, sessions, caches, and local preferences that must remain local.

## Boundaries

The CLI creates and updates Python/uv repository scaffolding and installs global symlinks. It
does not create GitHub repositories, push commits, copy secrets, or overwrite conflicting
project-owned files.

## Safety invariants

- Existing unrecognized content is preserved.
- Replaced global files are backed up before symlinks are installed.
- `~/.claude` itself is never symlinked; only portable settings and individual skills are.
- Generated repositories never commit `.agents`, `.claude`, `.codex`, `.env`, or private keys.

