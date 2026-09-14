# ONLYOFFICE Modules for Odoo

This repository contains three Odoo addons that connect Odoo with ONLYOFFICE Docs (Document Server). The same modules
exist for Odoo 17, 18, and 19 on separate code lines.

**Source of truth for the version is the manifest.** Read the version prefix in `__manifest__.py` (`17.0.x`, `18.0.x`,
`19.0.x`) — for example in `onlyoffice_odoo/__manifest__.py` — and apply only patterns valid for that version (see the
version tables in the skills and `.claude/skills/odoo-migration-17-18-19/SKILL.md`).

Never guess the version from a branch name alone; if the manifest prefix and the expected target disagree, stop and ask.

Read this file first, then load the matching skill from `.claude/skills/` before you change code.

## Modules

Three independent Odoo addons, each with its own `controllers/models/security/ static/tests`, connected only through
`depends` in the manifest. Work on one module at a time and master it—don't assume that changes to one module require
changes to others, unless specified in the assignment or explicitly required.

### `onlyoffice_odoo` — base connector

Opens office files from `ir.attachment` in the ONLYOFFICE editor. Handles settings, JWT, the save callback, and the
read-only preview. Depends on `base`, `mail`. The other two modules both depend on this one and extend its controllers
rather than duplicating routes.

- The user opens a file → a controller builds an editor config (document URL, permissions, callback URL) and renders the
  `onlyoffice_odoo.onlyoffice_editor` QWeb page, which loads `api.js` from the Document Server.
- The Document Server downloads the file from Odoo (`/onlyoffice/file/content/<id>`); the user edits it in the browser.
- On save, the Document Server POSTs to `/onlyoffice/editor/callback/<id>` (status 2/3); Odoo downloads the result and
  writes it back to the attachment.
- Two JWT layers protect this: the Document Server secret (config) and an internal secret used for `oo_security_token`
  (identifies the Odoo user on public routes).
- Key code: `onlyoffice_odoo/controllers/main.py` (`OnlyofficeConnector`, `onlyoffice_request`, `onlyoffice_urlopen`),
  `onlyoffice_odoo/utils/` (`config_utils`, `jwt_utils`, `file_utils`, `url_utils`).
- Skill: `.claude/skills/onlyoffice-odoo-base/SKILL.md`.

### `onlyoffice_odoo_documents` — Enterprise Documents integration

Open/create/share files from the Enterprise `documents` app, per-document access roles, attachment versioning. Depends
on `onlyoffice_odoo`, `documents`. The `documents` app differs a lot between 17/18/19 — **this module differs the most
between Odoo-version code lines.**

- Key code: `onlyoffice_odoo_documents/controllers/controllers.py` (documents
  - share routes, access roles), `models/onlyoffice_documents_access*.py`.
- Skill: `.claude/skills/onlyoffice-odoo-documents/SKILL.md`.

### `onlyoffice_odoo_templates` — fillable PDF templates

Builds PDFs from Odoo record data through the Document Server docbuilder service; adds the `onlyoffice-pdf` report
converter. Depends on `onlyoffice_odoo`, `web`.

- The module sends docbuilder scripts to `<docserver>/docbuilder`; the Document Server calls back to public routes to
  fetch the script and the template file, then returns URLs of the generated PDFs.
- Key code: `onlyoffice_odoo_templates/controllers/controllers.py` (fill flow, field mapping),
  `controllers/report_controller.py` (`onlyoffice-pdf` converter).
- Skill: `.claude/skills/onlyoffice-odoo-templates/SKILL.md`.

## Skills

Always start with the core skill, then load the skill for the module you are actually editing:

| Task                                            | Skill                                               |
| ----------------------------------------------- | --------------------------------------------------- |
| Any work in this repo (start here)              | `.claude/skills/onlyoffice-odoo-core/SKILL.md`      |
| Editing `onlyoffice_odoo`                       | `.claude/skills/onlyoffice-odoo-base/SKILL.md`      |
| Editing `onlyoffice_odoo_documents`             | `.claude/skills/onlyoffice-odoo-documents/SKILL.md` |
| Editing `onlyoffice_odoo_templates`             | `.claude/skills/onlyoffice-odoo-templates/SKILL.md` |
| Naming/comment/logging style for new code       | `.claude/skills/odoo-code-style/SKILL.md`           |
| HTTP routes, JWT, requests to Document Server   | `.claude/skills/odoo-controllers-jwt/SKILL.md`      |
| Attachments, binary data, file types, streaming | `.claude/skills/odoo-attachments-files/SKILL.md`    |
| OWL components, assets, JS/XML frontend         | `.claude/skills/odoo-owl-assets/SKILL.md`           |
| Access rights, groups, record rules, route auth | `.claude/skills/odoo-security/SKILL.md`             |
| Writing or fixing tests                         | `.claude/skills/odoo-testing/SKILL.md`              |
| Porting changes to 18.0 / 19.0 branches         | `.claude/skills/odoo-migration-17-18-19/SKILL.md`   |
| Reviewing a change before merge                 | `.claude/skills/odoo-code-review/SKILL.md`          |

## Workflow rules

- **Work where you already are**: fix bugs and add features directly on the Odoo version detected from the
  `__manifest__.py` prefix. Do not assume work must start on 17.0 — porting to another version is a separate task, see
  `.claude/skills/odoo-migration-17-18-19/SKILL.md`.
- Do not reinvent: the Odoo core, Enterprise, and OCA sources are not part of this repository and may not be available
  locally. Before writing new code that depends on framework/Enterprise/OCA behavior, ask the user whether they have
  those sources and where — use them when available instead of guessing.
- Code, comments, and docstrings in English. Keep changes small and scoped.
- Every new model needs `security/ir.model.access.csv` entries.
- Never change the module version in `__manifest__.py` — versioning is a separate release process. Do update the
  matching `CHANGELOG*.md` when behavior changes.
- Write new code compliant with the repo's lint rules: `ruff` + `pylint` (see `.ruff.toml`, `.pylintrc`), JS: `eslint` +
  `prettier`.
- Ask before running anything that needs a database or a live Document Server.
