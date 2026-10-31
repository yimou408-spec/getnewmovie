# Repository Guidelines

## Project Structure & Module Organization

This repository contains the S0 experiments and a running Apple-catalog movie application. The current MVP adds model interpretation and a LangGraph workflow; it is not a production service. Read `docs/MVP开发工作记录.md` for current scope, actual results, and remaining work; historical three-person schedules are reference only. Prefer updating existing Markdown files over creating new ones.

- `scripts/`: real Apple/TMDB catalog service, optional model intent parser, Pydantic contracts, schema exporter, probes, and historical mock utilities.
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

`s0_check` validates fixtures, generated contracts, and tests. Export schemas after changing contract types; `--check` detects stale exports. The command above starts the historical mock. The product demo uses `start-demo.cmd` or `python -m scripts.movie_demo`, builds `web/app`, and serves the product plus API documentation at `/docs`.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions/modules, `PascalCase` classes, and explicit imports. Follow existing `s0_*.py` naming for feasibility scripts. Keep JSON fields in `snake_case` and files UTF-8. No formatter or linter is configured. Modify contract types in `scripts/s0_contracts.py`, then regenerate exports rather than editing generated files manually.

## Testing Guidelines

Follow TDD: failing behavior test, minimal implementation, then refactor. Name tests `test_*.py` and functions `test_<behavior>`. Use pytest, FastAPI TestClient, and HTTPX MockTransport; keep default tests offline. Cover missing fields, ambiguous identities, errors, budgets, and evidence references. Core-rule branch coverage has a planned ≥90% target; coverage enforcement is not yet configured. Prototype syntax checks require Node; browser visual acceptance remains separate.

## Commit & Pull Request Guidelines

History uses messages such as `docs: add three-person development plan and TDD specifications`. Prefer `<type>: <imperative summary>`. PRs should identify the stage/task, behavior changes, test results, and remaining limitations; link an issue when available. Include screenshots for UI changes and regenerate affected contracts. Preserve unrelated working-tree changes.

## Configuration & Data Handling

Keep all `.env` and `.env.*` files local and untracked, including `.env.example`. The MVP model adapter (`scripts/mvp_model.py`) reads the repository-root `.env`, with process environment taking precedence; legacy S0 probes still read process environment only. Consult `docs/MVP开发工作记录.md` for MVP configuration and `docs/s0/README.md` for legacy probe variables. Keep secrets and reports under ignored paths. Live probes require `--live` and explicit configuration. Preserve synthetic labels and pending-review status; do not represent fixtures as verified movie data or upload raw interview material.
