# ONLYOFFICE Modules for Odoo

Three Odoo addons that connect Odoo with ONLYOFFICE Docs (Document Server). The same addons live on one code line per
Odoo version. Project background, known problems and history are in `HANDOVER.md`.

| Odoo | Development branch | Release branch       |
| ---- | ------------------ | -------------------- |
| 17   | `develop`          | `17.0`               |
| 18   | `feature/18.0`     | `18.0`               |
| 19   | `feature/19.0`     | `19.0`               |
| 20   | `feature/20.0`     | — (not released yet) |

**The version comes from the manifest.** Read the prefix of `version` in `<addon>/__manifest__.py` (`17.0.x`, `18.0.x`,
…) and use only the APIs of that Odoo version (`.claude/skills/odoo-migration-17-18-19/SKILL.md`). If the prefix and the
expected target disagree, stop and ask.

## Structure

- `onlyoffice_odoo/` — base connector: editor for `ir.attachment`, settings, JWT, save callback, preview. Key code:
  `controllers/main.py` (`OnlyofficeConnector`, `onlyoffice_request`, `onlyoffice_urlopen`), `utils/`.
- `onlyoffice_odoo_documents/` — Enterprise Documents: create, share roles, links, conversion, Odoo spreadsheet ↔ XLSX
  with `ODOO_*` formulas (`controllers/spreadsheet_*.py`). Depends on Enterprise `documents`, `documents_spreadsheet`.
  Differs the most between versions.
- `onlyoffice_odoo_templates/` — PDF form templates filled through docbuilder, `onlyoffice-pdf` report.
- `e2e/` — Playwright tests against a live Docs; `.github/workflows/` — `lint.yml`, `test.yml`, `e2e.yml`.
- `onlyoffice_odoo/static/assets/` — vendored formats list and blank files; never edit by hand.
- `CHANGELOG.md` (base), `CHANGELOG documents.md`, `CHANGELOG templates.md`.

## Commands

```bash
# setup (once)
npm install && python -m venv .venv && .venv/Scripts/pip install -e .[dev] && pre-commit install

# lint, as CI
pre-commit run -a
pylint --rcfile=.pylintrc onlyoffice_odoo onlyoffice_odoo_documents onlyoffice_odoo_templates
ruff check onlyoffice_odoo onlyoffice_odoo_documents onlyoffice_odoo_templates   # only addon folders

# unit tests in a running Odoo container (needs a DB; add --test-tags ...,external_docserver and
# ONLYOFFICE_TEST_LIVE_DOCSERVER=1 ONLYOFFICE_TEST_DOCSERVER_URL=http://<docs>/ for live Docs tests)
odoo -d <db> -u onlyoffice_odoo,onlyoffice_odoo_templates --test-enable \
  --test-tags /onlyoffice_odoo,/onlyoffice_odoo_templates --stop-after-init --no-http

# e2e: own Docker stack (Odoo on 8069, Docs on 8080 must be free)
cd e2e && npm run setup   # once
cd e2e && npm run e2e     # stack up → tests → stack down; report: npm run report
```

`onlyoffice_odoo_documents` needs Odoo Enterprise of the same version in the addons path. On 17 it has no tests; on
18–20 add it to `-u` and `--test-tags`. After changing Python, restart Odoo; after changing data/XML/assets, `-u` the
addon.

## Conventions

- Code, comments, docstrings, commit messages in simple English. Commit message: one line, `fix: …` / `feat: …` /
  `test: …` / `docs: …` / `chore: …`. No bug numbers or tracker links in code and tests.
- Fixes start on 17 (`develop`, through a PR from `fix/17.0-<topic>`), then merge upward version by version: `develop` →
  `feature/18.0` → `feature/19.0` → `feature/20.0`, adapting each to its version. On 18–20 there are no PRs; merge and
  commit directly in `feature/<v>.0`.
- Every behavior change gets a test (on 18+ also for documents) and a line in the matching `CHANGELOG*.md` under
  `## Unreleased`.
- Talk to Docs only through `onlyoffice_request` / `onlyoffice_urlopen`. Build Odoo URLs with
  `config_utils.get_base_or_odoo_url(env)`. Compare URLs by parsing, never with `startswith`.
- Public routes must check `oo_security_token` (and the Docs JWT when enabled). Never trust a bare id.
- Every new model needs `security/ir.model.access.csv` entries (20: `ir.access.csv`).
- Duplicated paths: save callback (base + documents share callback), template filling (templates controller +
  `ir_actions_report.py`). Change both.
- When a change makes a rule in `.claude/skills/` wrong, fix the skill in the same change.

## Never

- Change `version` in `__manifest__.py` or the released `CHANGELOG*` headings outside a release
  (`.claude/skills/release/SKILL.md`).
- Add new `env.cr.commit()` calls (the existing three are documented in `HANDOVER.md`).
- Force-push or rewrite `develop`, `feature/*`, or release branches. Push only when asked.
- Put secrets, customer data, or internal-only information in the repository: every branch is mirrored to the public
  GitHub repository.
- Run commands that touch a database, install addons, or call a live Docs without confirming with the user.

## Skills

Start with `.claude/skills/onlyoffice-odoo-core/SKILL.md`, then load the skill of what you touch:

| Task                              | Skill                       |
| --------------------------------- | --------------------------- |
| `onlyoffice_odoo`                 | `onlyoffice-odoo-base`      |
| `onlyoffice_odoo_documents`       | `onlyoffice-odoo-documents` |
| `onlyoffice_odoo_templates`       | `onlyoffice-odoo-templates` |
| Naming, comments, logging         | `odoo-code-style`           |
| Routes, JWT, requests to Docs     | `odoo-controllers-jwt`      |
| Attachments, binary data, formats | `odoo-attachments-files`    |
| OWL, assets, JS/XML               | `odoo-owl-assets`           |
| Access rights, groups, route auth | `odoo-security`             |
| Tests                             | `odoo-testing`              |
| Porting between versions          | `odoo-migration-17-18-19`   |
| Review before merge               | `odoo-code-review`          |
| Release and Odoo Apps publication | `release`                   |
