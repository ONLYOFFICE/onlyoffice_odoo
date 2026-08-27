---
name: odoo-code-review
description:
  Review checklist for changes to the ONLYOFFICE Odoo modules - correctness, security, performance, version
  compatibility, tests, and repo conventions. Use before merging any change or when asked to review a diff or pull
  request.
---

# Code Review

Review in this order. Stop and report blockers first.

## 1. Correctness

- Does the change fix the root cause, or only a symptom?
- Editor round trip still works: open → edit → callback → file saved, document key changes with content.
- JWT paths tested both enabled and disabled (secret set / empty).
- Docker case considered: inner vs public Document Server URLs.
- Error paths return safe responses; the Document Server retries on callback `{"error": 1}` — is that the intended
  behavior here?

## 2. Security (blockers)

- New/changed public routes validate `oo_security_token` and Document Server JWT before any data access.
- No `sudo()` without a justification comment; ORM runs as the resolved user.
- New models have ACL entries; admin-only features check the right group.
- No secrets or tokens in logs, URLs in logs are fine.
- User input sanitized before entering filenames, configs, or docbuilder scripts (script injection into docbuilder
  content is a real risk).

## 3. Performance

- No queries inside loops over records (batch with `browse`/`read` instead).
- Files streamed (`ir.binary._get_stream_from`), not loaded when large.
- No new synchronous Document Server round trips in hot paths — cache like `field_keys` does for template form keys.
- External calls have timeouts.

## 4. Conventions and hygiene

- Manifest version left unchanged (versioning is a separate release process); `CHANGELOG*.md` updated for behavior
  changes.
- Simple English in code, comments, and docstrings.
- Lint passes: `ruff`, `pylint`, `eslint`, `prettier`.
- Translations: user-facing strings wrapped in `_()`.
- No leftover debug prints, commented-out code, or unrelated reformatting.
- New JS covered by a manifest asset glob; template names prefixed with the module name.

## 5. Tests

- Bug fix → regression test included.
- Standard tests do not call a live Document Server (mock `onlyoffice_request`).
- If a test needs a real Document Server, it must opt in explicitly (skipped by default and in CI) and be tagged
  `-standard` — see `odoo-testing`.

## 6. Portability (17 → 18 → 19)

- Does the change use APIs known to be renamed/removed in 18 or 19 (`check_access_rights`, `documents.share`, `<tree>`,
  `_sql_constraints`)? If yes, note it for the port and prefer forward-compatible options when they exist on 17.
- Will porting this into another Odoo-version code line conflict with the Documents rework there? Flag it.

## Report format

Group findings as: **Blockers** (security, data loss, broken flows), **Should fix** (correctness/performance risks),
**Nits** (style). Cite file and line for each finding. Suggest the minimal fix, not a rewrite.
