# Contributing to LingoView

Thanks for your interest in contributing! This document outlines a few quick guidelines to help you get started.

## Development Setup
- Backend: `cd python && python -m venv .venv && source .venv/bin/activate && pip install -e .[dev] && ./run_api.sh`
- Frontend: `cd web && pnpm install && pnpm dev`
- Combined (local): `./start.sh`

## Code Style
- Python: keep line length <= 100; run `ruff` and `pytest` locally if available.
- Web: use TypeScript + Prettier; run `pnpm lint` and `pnpm test` where applicable.

## Commit Messages
Use conventional commits when possible:
- `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `ci:`

## Pull Requests
- Describe the motivation and approach concisely.
- Include screenshots or logs for UI/UX or CLI changes when helpful.
- Keep PRs focused. Prefer multiple small PRs over one large PR.

## Issues
- Bug report: include OS, steps to reproduce, expected vs actual behavior, logs.
- Feature request: describe the problem, desired outcome, and alternative solutions considered.

## Security
Please do not disclose security issues publicly. See `SECURITY.md` for instructions.

## License
By contributing, you agree that your contributions will be licensed under the same license as the project (see `LICENSE`).
