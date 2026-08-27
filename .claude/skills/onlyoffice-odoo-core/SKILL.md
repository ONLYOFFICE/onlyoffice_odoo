---
name: onlyoffice-odoo-core
description:
  Shared rules across all three ONLYOFFICE Odoo modules (onlyoffice_odoo, onlyoffice_odoo_documents,
  onlyoffice_odoo_templates) - version detection, cross-module architecture, and the bug-fix/feature/port workflows. Use
  at the start of every task in this repo before loading the module-specific skill
  (onlyoffice-odoo-base/-documents/-templates).
---

# ONLYOFFICE Odoo Core

Base skill for this repository. Read it before any change, then load the skill for the module you are actually editing:

| Module                             | Skill                       |
| ---------------------------------- | --------------------------- |
| `onlyoffice_odoo` (base connector) | `onlyoffice-odoo-base`      |
| `onlyoffice_odoo_documents`        | `onlyoffice-odoo-documents` |
| `onlyoffice_odoo_templates`        | `onlyoffice-odoo-templates` |

This skill only holds what is true for **all three modules at once**: version handling, shared architectural facts, and
cross-module rules. Module-specific code maps, data flow, and task notes live in the skills above.

## Shared architecture facts

- All three modules share the same JWT layers and Document Server call path — defined once in `onlyoffice_odoo` and
  reused by the other two (see `onlyoffice-odoo-base`).
- `onlyoffice_odoo_documents` and `onlyoffice_odoo_templates` both depend on `onlyoffice_odoo` and extend its
  controllers (`OnlyofficeConnector`) rather than duplicating routes.
- `onlyoffice_odoo_documents` is the most version-specific module — the Enterprise `documents` app was reworked in 18
  and again in 19.

## Rules that always apply

- Detect the Odoo version first from the `__manifest__.py` version prefix (`17.0.x` / `18.0.x` / `19.0.x`) — that is the
  source of truth. Branch names are only a hint (work branches forked from `feature/18.0`/`feature/19.0` can be named
  anything). Use only that version's APIs; the per-version differences live in `odoo-migration-17-18-19`.
- This repository does not contain the Odoo core, Enterprise, or OCA sources and they may not be available locally.
  Before writing new code that depends on framework/Enterprise/OCA behavior for the manifest's version, ask the user
  whether they have those sources and where; use them when available instead of guessing. Extend, do not copy.
- Version-sensitive APIs used across this repo — check the manifest version before using: access checks (17:
  `check_access_rights`/`check_access_rule`; 18+: `has_access`/`check_access`), Documents models (17:
  `documents.folder`/`documents.share`; 18+: folders are documents, no share model), view tags (17: `<tree>`; 18+:
  `<list>`).
- Never call `requests` directly for Document Server traffic — use `onlyoffice_request` so certificate settings and URL
  replacement work.
- Public routes must validate `oo_security_token` (internal JWT) and, when JWT is enabled, the Document Server token
  too. Never trust a bare attachment id.
- Keep `env.cr.commit()` out of new code unless there is a documented reason (existing spots have comments explaining
  why).
- Never change the module version in `__manifest__.py` (versioning is a separate release process). Update the matching
  `CHANGELOG*.md` on behavior changes.
- Code and comments in simple English. Follow `.ruff.toml`, `.pylintrc`, `eslint.config.cjs`, `prettier.config.cjs`. For
  naming, comment, and logging conventions, see `odoo-code-style`.

## Task workflows

### Bug fix

1. Reproduce or trace the path (route → controller → util → Document Server).
2. Find the root cause; prefer the smallest upstream fix.
3. Check whether the same bug exists in the other two modules (they share patterns) and, if you have access to the other
   Odoo-version code lines, there too.
4. Add or update a test. Update changelog.

### New feature (editor integration)

1. Confirm which module owns the feature (connector vs documents vs templates) and load its skill
   (`onlyoffice-odoo-base` / `onlyoffice-odoo-documents` / `onlyoffice-odoo-templates`).
2. Reuse `prepare_editor_values`, `onlyoffice_request`, and the JWT utils.
3. Add security entries for any new model; add route auth checks.

### Working on any Odoo-version code line (17/18/19)

Use the bug-fix/feature workflows above with that version's APIs from the start (see the version tables in
`odoo-migration-17-18-19`). Verify the Enterprise `documents` integration against sources of that same version. If a fix
also applies to another version's code line, apply it there too.

### Porting a change to another version

A separate task from normal bug-fix/feature work. Follow `odoo-migration-17-18-19`: port forward version by version
(never skip one), resolving conflicts in favor of the target-version API.
