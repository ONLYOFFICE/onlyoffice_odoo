---
name: onlyoffice-odoo-core
description:
  Shared rules across all three ONLYOFFICE Odoo modules (onlyoffice_odoo, onlyoffice_odoo_documents,
  onlyoffice_odoo_templates) - first moves, task routing, version detection, cross-module architecture, repo tooling,
  and the bug-fix/feature/port workflows. Use at the start of every task in this repo before loading the module-specific
  skill (onlyoffice-odoo-base/-documents/-templates).
---

# ONLYOFFICE Odoo Core

Base skill for this repository. Read it before any change, then load the skill for the module you are actually editing.

## First move (every task)

1. Read `__manifest__.py` of the module you touch. The version prefix (`17.0.x` / `18.0.x` / `19.0.x`) is the source of
   truth for which Odoo APIs to use. Branch names are only a hint.
2. Identify the owning module and load its skill (table below). Anything touching two modules: load both.
3. Check whether Odoo core / Enterprise sources are available: this repo does not contain them, but a parent workspace
   often does (look for sibling folders such as `enterprise-<version>/`, `addons-<version>/`, or an `$ODOO_SOURCE` /
   `$ODOO_ENTERPRISE_SOURCE` environment variable). Use them instead of guessing framework or Documents-app behavior. If
   nothing is available and the change depends on framework/Enterprise behavior, ask the user where the sources are.
4. Do not run commands that touch a database or a running Odoo (`-i`, `-u`, `--test-enable`, docker compose) without
   confirming with the user first. Take the intended commands from `CONTRIBUTING.md` and `docker-compose.yml`.

## Route the task

| Module / topic                                              | Skill                       |
| ----------------------------------------------------------- | --------------------------- |
| `onlyoffice_odoo` (base connector, editor, settings, JWT)   | `onlyoffice-odoo-base`      |
| `onlyoffice_odoo_documents` (Documents app, share, convert) | `onlyoffice-odoo-documents` |
| `onlyoffice_odoo_templates` (PDF forms, docbuilder, report) | `onlyoffice-odoo-templates` |
| Routes, tokens, Document Server / docbuilder / converter    | `odoo-controllers-jwt`      |
| Attachments, binary data, file formats, versioning          | `odoo-attachments-files`    |
| ACLs, groups, sudo, public routes                           | `odoo-security`             |
| OWL components, patches, asset bundles                      | `odoo-owl-assets`           |
| Naming, comments, docstrings, logging                       | `odoo-code-style`           |
| Reviewing a diff / PR                                       | `odoo-code-review`          |
| Adding or fixing tests                                      | `odoo-testing`              |
| Porting between 17 / 18 / 19, version deltas                | `odoo-migration-17-18-19`   |

## Shared architecture facts

- All three modules share the same JWT layers and the same Document Server call path. Both are defined once in
  `onlyoffice_odoo` (`controllers/main.py`, `utils/`) and imported by the other two.
- `onlyoffice_odoo_documents` and `onlyoffice_odoo_templates` depend on `onlyoffice_odoo`. Each of them has one class
  that subclasses `OnlyofficeConnector` (to override `get_config` / add editor routes) **and** one or more plain
  `http.Controller` classes for its own routes. `onlyoffice_odoo_documents` also subclasses the Enterprise `ShareRoute`.
- The QWeb editor page `onlyoffice_odoo.onlyoffice_editor` and the OWL client action `onlyoffice_editor` live in the
  base module and are reused by the other two (documents renders the same template for document/share editors; templates
  has its own `onlyoffice_template_editor` action).
- The Document Server has three services used here: the editor (`api.js` + save callback, base), the **converter**
  (`/converter`: settings validation in base, format conversion in documents, PDF → PDF-form in templates) and the
  **docbuilder** (`/docbuilder`: template filling and form-key extraction in templates, spreadsheet export/insert in
  documents). Shared request-building code for the converter is `onlyoffice_odoo/utils/conversion_utils.py`.
- Supported formats are not hard-coded: `onlyoffice_odoo/static/assets/document_formats/onlyoffice-docs-formats.json` (a
  vendored submodule) is read by Python (`format_utils` / `file_utils`) and fetched by JS.
- Some code is intentionally duplicated between modules or classes (template filling exists in
  `onlyoffice_odoo_templates/controllers/controllers.py` and `models/ir_actions_report.py`; the save callback exists in
  the base module and in the documents share callback). When you change one copy, check the others.
- `onlyoffice_odoo_documents` is the most version-specific module — the Enterprise `documents` app was reworked in 18
  and again in 19. `onlyoffice_odoo_templates` is version-sensitive through its Documents integration
  (`documents.folder` on 17), `<tree>` views and access-check APIs.

## Rules that always apply

- Use only the manifest version's APIs; the per-version differences live in `odoo-migration-17-18-19`. Version-sensitive
  APIs used across this repo: access checks (17: `check_access_rights`/`check_access_rule`; 18+:
  `has_access`/`check_access`), Documents models (17: `documents.folder`/`documents.share`; 18+: folders are documents,
  no share model), view tags (17: `<tree>`; 18+: `<list>`).
- Never call `requests`/`urlopen` directly for Document Server traffic — use `onlyoffice_request` / `onlyoffice_urlopen`
  from `onlyoffice_odoo.controllers.main` so certificate settings and public→inner URL replacement work. Direct
  `requests` is only acceptable for non-Document-Server hosts (the oforms gallery API) and for the settings validation
  that runs before settings are saved.
- Public routes must validate `oo_security_token` (internal JWT) and, when JWT is enabled, the Document Server token
  too. Never trust a bare attachment or document id. See `odoo-controllers-jwt` for the token table.
- Build callback/content URLs from `config_utils.get_base_or_odoo_url(env)`, never from `request.httprequest.host`.
- Keep `env.cr.commit()` out of new code unless there is a documented reason (existing spots — internal secret
  generation, template PDF conversion, docbuilder cache — have comments or pylint pragmas explaining why).
- Never change the module version in `__manifest__.py` (versioning is a separate release process).
- Update the matching changelog on behavior changes: `CHANGELOG.md` → `onlyoffice_odoo`, `CHANGELOG documents.md` →
  `onlyoffice_odoo_documents`, `CHANGELOG templates.md` → `onlyoffice_odoo_templates`. Format:
  `## Added / Changed / Fixed` bullet lists under the version (or `Unreleased`).
- When supported formats or user-visible features change, also check `README.md` ("Supported formats"),
  `<module>/doc/index.rst` and `<module>/static/description/index.html`.
- Code and comments in simple English. Follow `.ruff.toml`, `.pylintrc`, `eslint.config.cjs`, `prettier.config.cjs` (run
  `pre-commit run -a`). For naming, comment, and logging conventions, see `odoo-code-style`.

## Repo tooling

- `pre-commit run -a` runs all linters (ruff, pylint-odoo, prettier with plugin-xml, eslint, OCA checks); setup is in
  `CONTRIBUTING.md`. The config excludes `**/assets/**` (vendored formats/templates) and
  `static/description/index.html`.
- CI (`.github/workflows/test.yml`) runs the `onlyoffice_odoo` and `onlyoffice_odoo_templates` tests (a matrix, with
  stub `documents`/`documents_spreadsheet` manifests and the coverage thresholds of `.coveragerc*`); the documents
  module is tested locally only. `.github/workflows/e2e.yml` runs the Playwright suite in `e2e/` against a live Document
  Server on every push / pull request; `lint.yml` runs pre-commit and a strict pylint. Details in `odoo-testing`.
- A local Odoo 17 + Enterprise usually runs from a `docker-compose.yml` in the parent workspace (repo mounted as
  `/mnt/extra-addons`).

## Task workflows

### Bug fix

1. Trace the path: UI (OWL/QWeb) → route → controller → util → Document Server → callback → ORM write. Note the token
   type at each hop.
2. Find the root cause; prefer the smallest upstream fix.
3. Check whether the same bug exists in the duplicated code paths (see "Shared architecture facts") and in the other two
   modules; if you have access to the other Odoo-version code lines, check there too.
4. Add or update a test (`odoo-testing`). Update the module's changelog.

### New feature (editor integration)

1. Confirm which module owns the feature (connector vs documents vs templates) and load its skill.
2. Reuse `prepare_editor_values`, `onlyoffice_request`, `conversion_utils`, and the JWT utils; do not add a second way
   to talk to the Document Server.
3. Add security entries for any new model; add route auth checks; add manifest asset globs for new JS.
4. Update changelog and, if user-visible, `doc/index.rst` / `static/description/index.html`.

### Working on any Odoo-version code line (17/18/19)

Use the bug-fix/feature workflows above with that version's APIs from the start (see the version tables in
`odoo-migration-17-18-19`). Verify the Enterprise `documents` integration against sources of that same version. If a fix
also applies to another version's code line, apply it there too.

### Porting a change to another version

A separate task from normal bug-fix/feature work. Follow `odoo-migration-17-18-19`: port forward version by version
(never skip one), resolving conflicts in favor of the target-version API.
