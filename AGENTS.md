# Repository Guidelines

## Project Structure & Module Organization

This repository is at S0: movie recommendation feasibility, contracts, and prototypes. The production recommendation service is not implemented.

- `scripts/`: Pydantic contracts, FastAPI mock, schema exporter, probes, and evaluation utilities.
- `tests/s0/`: offline contract, HTTP, evaluation, and prototype syntax tests.
- `contracts/examples/`: shared synthetic requests and responses; `contracts/generated/`: exported JSON Schema and OpenAPI.
- `data/s0/`: synthetic catalog, evaluation tasks, and pending-review TMDB query seeds.
- `web/s0/index.html`: standalone interaction prototype.
- `docs/s0/`: setup, interface specifications, data licensing, and acceptance records. Read `docs/限期开发实施计划_20261029.md` and `docs/三人开发任务台账.md` for current scope and ownership.

## Build, Test, and Development Commands

Run from the repository root with Python 3.11+; CI uses Python 3.13 and Node 24.

```sh
python -m pip install -r requirements-s0.txt
python -m scripts.s0_check
python -m pytest -q
python -m scripts.s0_export_contracts
python -m scripts.s0_export_contracts --check
python -m uvicorn scripts.s0_mock_server:app --host 127.0.0.1 --port 8000
```

`s0_check` validates fixtures, generated contracts, and tests. Export schemas after changing contract types; `--check` detects stale exports. The local server exposes the prototype at `/` and API documentation at `/docs`. No frontend build is required.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions/modules, `PascalCase` classes, and explicit imports. Follow existing `s0_*.py` naming for feasibility scripts. Keep JSON fields in `snake_case` and files UTF-8. No formatter or linter is configured. Modify contract types in `scripts/s0_contracts.py`, then regenerate exports rather than editing generated files manually.

## Testing Guidelines

Follow TDD: failing behavior test, minimal implementation, then refactor. Name tests `test_*.py` and functions `test_<behavior>`. Use pytest, FastAPI TestClient, and HTTPX MockTransport; keep default tests offline. Cover missing fields, ambiguous identities, errors, budgets, and evidence references. Core-rule branch coverage has a planned ≥90% target; coverage enforcement is not yet configured. Prototype syntax checks require Node; browser visual acceptance remains separate.

## Commit & Pull Request Guidelines

History uses messages such as `docs: add three-person development plan and TDD specifications`. Prefer `<type>: <imperative summary>`. PRs should identify the stage/task, behavior changes, test results, and remaining limitations; link an issue when available. Include screenshots for UI changes and regenerate affected contracts. Preserve unrelated working-tree changes.

## Configuration & Data Handling

Keep all `.env` and `.env.*` files local and untracked, including `.env.example`; scripts do not automatically load `.env`. Consult `docs/s0/README.md` for variable names. Keep secrets and reports under ignored paths. Live probes require `--live` and explicit environment configuration. Preserve synthetic labels and pending-review status; do not represent fixtures as verified movie data or upload raw interview material.
