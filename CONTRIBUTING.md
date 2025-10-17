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
- Keep PRs focused; small PRs merge faster.
- CI must pass (web build/lint + basic backend tests). CodeQL 结果供参考，不阻塞合并。
- 目前不强制签名提交；如你愿意，可使用 GPG/SSH 提交签名。

## Issues
- Bug report: include OS, steps to reproduce, expected vs actual behavior, logs.
- Feature request: describe the problem, desired outcome, and alternative solutions considered.

## Security
Please do not disclose security issues publicly. See `SECURITY.md` for instructions.

## License
By contributing, you agree that your contributions will be licensed under the same license as the project (see `LICENSE`).
