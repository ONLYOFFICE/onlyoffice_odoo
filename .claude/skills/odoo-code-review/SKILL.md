---
name: odoo-code-review
description:
  Review checklist for changes to the ONLYOFFICE Odoo modules - correctness, security, performance, docbuilder and
  spreadsheet specifics, version compatibility, tests, and repo conventions, with a fixed report format. Use before
  merging any change or when asked to review a diff or pull request.
---

# Code Review

## First move

1. Identify the target: whole module, diff, PR, commit range, or files. Read the manifest version of every touched
   module (17/18/19) and load the module skill (`onlyoffice-odoo-base` / `-documents` / `-templates`).
2. Note whether the branch is a release line (`17.0`, `18.0`, `19.0`, `feature/18.0`, `feature/19.0`) or a work branch.
   On release lines do not ask for unrelated restyling; existing file style wins over generic preferences.
3. Read the whole file for every touched controller/model, not only the hunk — duplicated flows (base callback vs share
   callback, controller `fill_template` vs report `fill_template`) are easy to miss from a diff.

Review in the order below. Stop and report blockers first.

## 1. Correctness

- Does the change fix the root cause, or only a symptom?
- Editor round trip still works: open → edit → callback → file saved, document key changes with content.
- JWT paths tested both enabled and disabled (secret set / empty). Inner vs public Document Server URL (Docker) still
  handled through `onlyoffice_request` / `replace_public_url_to_internal`.
- Error paths return safe responses; the Document Server retries on callback `{"error": 1}` — is that the intended
  behavior here?
- Converter/docbuilder flows: the callback URL is reachable from the Document Server, the token in it is the right type,
  the returned URL is downloaded through `onlyoffice_request`, error codes are mapped.
- Spreadsheet formulas: JS `ODOO_*` signatures, `_HANDLERS` in `spreadsheet_formulas.py` and the formulas written by the
  `.docbuilder` scripts stay in sync; metadata written to `onlyoffice_spreadsheet_metadata` matches what
  `load_document_snapshot` expects.
- Documents versioning (`oo_attachment_version`, renamed history attachment) intact when the callback changes.
- Both copies of duplicated logic updated (see First move, step 3).

## 2. Security (blockers)

- New/changed public routes validate `oo_security_token` (or the formula `jwt_token`) and the Document Server JWT before
  any data access; cache-key tokens are looked up, not trusted.
- No `sudo()` without a justification comment; ORM runs as the resolved user (`with_user`, `request.update_env`).
- New models have ACL entries (templates: CSV and XML twins); admin-only features check the right group.
- No secrets or tokens in logs; URLs in logs are fine.
- User input sanitized before entering filenames, editor configs, or docbuilder scripts (values as `json.dumps` literals
  only — script injection into docbuilder content is a real risk); formulas/domains evaluated only through the existing
  parser / `safe_eval`.
- XLSX parsing failures degrade gracefully; files under the module directory served through `get_template_content`-style
  path confinement.
- Role model: a role never grants more than ORM write access allows.

## 3. Performance

- No queries inside loops over records (batch with `browse`/`read` instead); `read_group` results cached per request
  where the spreadsheet evaluator does it (`request._rg_cache`).
- Files streamed (`ir.binary._get_stream_from`), not loaded when large.
- No new synchronous Document Server round trips in hot paths — cache like `field_keys` does for template form keys and
  like the docbuilder cache does for callback payloads.
- External calls have timeouts (the helpers default to 120 s; oforms proxy 20 s).
- Formula batches: one snapshot load per request, no per-formula document reads.

## 4. Transactions

- No new `env.cr.commit()` without a comment and `# pylint: disable=invalid-commit`; existing commits (internal secret,
  template conversion, docbuilder cache) keep their reasons valid.
- Database errors that may abort the transaction are wrapped in savepoints (`_safe_read_group`, cache deletion race).
- `postcommit` hooks (`ir.attachment` in templates) remain idempotent.

## 5. Conventions and hygiene

- Manifest version left unchanged (versioning is a separate release process); the module's `CHANGELOG*.md` updated for
  behavior changes; `README.md` formats table / `doc/index.rst` / `static/description/index.html` updated when
  user-visible behavior or formats change.
- Simple English in code, comments, and docstrings; docstring style matches the file (`odoo-code-style`).
- Lint passes: `ruff`, `pylint-odoo`, `eslint`, `prettier` (`pre-commit run -a`).
- Translations: user-facing strings wrapped in `_()` / `_t()`.
- Logging follows the route-prefix pattern with `%s` formatting; no leftover debug prints, `console.log`, commented-out
  code, or unrelated reformatting.
- New JS covered by a manifest asset glob (or intentionally raw-loaded with a comment); template names prefixed with the
  module name; copyright header on new files.

## 6. Tests

- Bug fix → regression test included in the module that owns the fix.
- Standard tests do not call a live Document Server (mock `onlyoffice_request` / `_fetch_field_keys`).
- If a test needs a real Document Server, it must opt in explicitly (skipped by default and in CI) and be tagged
  `-standard` — see `odoo-testing`.
- Changes in `onlyoffice_odoo_documents` / `onlyoffice_odoo_templates` (not run in CI): manual verification steps
  described in the PR.

## 7. Portability (17 → 18 → 19)

- Does the change use APIs known to be renamed/removed in 18 or 19 (`check_access_rights`, `documents.share`,
  `documents.folder`, `ShareRoute`, `DocumentsInspector`, `<tree>`, `_sql_constraints`, `useService("rpc")`)? If yes,
  note it for the port and prefer forward-compatible options when they exist on 17.
- Will porting this into another Odoo-version code line conflict with the Documents rework there? Flag it.

## Report format

```markdown
## Findings

- Blocker: `path/file.py:XX` - issue, why it matters, minimal fix.
- Should fix: `path/file.py:XX` - correctness/performance risk, suggested fix.
- Nit: `path/file.js:XX` - style.

## Checks run

- What was read/executed (lint, tests, manual trace).

## Not verified

- Areas not reviewed or not verifiable from the available context (e.g. no Enterprise sources, no Document Server).

## Summary

- One or two sentences on change quality after the findings.
```

Cite file and line for each finding. Suggest the minimal fix, not a rewrite. Do not bury blockers under style notes; if
there are no findings say so and still list what was and was not verified.
