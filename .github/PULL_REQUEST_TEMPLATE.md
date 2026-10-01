## Description

<!-- What changed and why. Link the issue or spec it addresses, e.g. "Closes #123". -->

## Type of change

- [ ] 🐞 Bug fix
- [ ] ✨ Feature
- [ ] ⚡ Enhancement
- [ ] 🧹 Refactor
- [ ] 🧪 Tests
- [ ] 📜 Documentation
- [ ] 🚀 Infrastructure / CI
- [ ] 💥 Breaking change <!-- explain the migration under Risk and rollback -->

## Areas affected

- [ ] ⚙️ Application / API (`src/`)
- [ ] 🎨 Frontend / UI
- [ ] 💾 Data / migrations
- [ ] 📦 Dependencies (`pyproject.toml`, `uv.lock`)
- [ ] 🛠️ Tooling, scripts or Git hooks
- [ ] 🏗️ CI, GitHub or infrastructure
- [ ] 📜 Documentation (`README.md`, `AGENTS.md`, `GLOSSARY.md`, `docs/adr/`)

## How to verify

<!-- Steps a reviewer can follow, one action and its expected outcome per line. -->

- [ ] **Action:** <!-- e.g. `uv run app load a.csv` --> → **Outcome:** <!-- 3 rows saved -->
- [ ] **Action:** <!-- e.g. rerun the import --> → **Outcome:** <!-- no duplicates -->

## Checks

- [ ] `uv run ruff check .` and `uv run ruff format --check .`
- [ ] `uv run mypy src`
- [ ] `uv run pytest`, with tests added or updated for changed behavior
- [ ] `AGENTS.md`, `GLOSSARY.md` or an ADR updated when scope, terms or decisions changed

## Risk and rollback

<!-- What could break, who is affected, and how to undo it, including migrations. -->
