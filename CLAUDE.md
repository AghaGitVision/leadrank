# LeadRank

## Git versioning

This repo follows the global Conventional Commits + Semantic Versioning
convention (see the user's global `CLAUDE.md`). Concrete setup here:

- Root `package.json` hosts the tooling only — it is not a workspace root for
  `backend/` (Python) or `frontend/` (Next.js), which keep their own
  dependency files.
- `commitlint.config.js` extends `@commitlint/config-conventional` with a
  `scope-enum` of: `backend`, `frontend`, `scoring`, `scanner`, `triage`,
  `admin`, `docs`, `ci`, `release`.
- `.husky/commit-msg` runs `commitlint --edit`, wired up via
  `git config core.hooksPath .husky` (local to this repo).
- `release.config.js` runs changelog + git plugins only — no npm publish, no
  CI-triggered auto-release wired up yet (this is a challenge submission, not
  a published package).
- Run `npm install` at the repo root once to pull in the tooling before
  committing.
- Use `npm run commit` (Commitizen wizard) for interactive commits, or hand-write
  `<type>(<scope>): <subject>` — an AI agent committing here should hand-write
  it directly, picking type/scope from the enum above based on what actually
  changed.
