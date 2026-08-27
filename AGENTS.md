# Agent Setup — ONLYOFFICE Odoo Modules

Read `CLAUDE.md` for the project overview. Skills live in `.claude/skills/`; each skill is a folder with a `SKILL.md`
file. This file only routes tasks.

## Environment

- **Version detection: the `__manifest__.py` version prefix is the source of truth** (`17.0.x` / `18.0.x` / `19.0.x`).
  Check the manifest before anything version-sensitive.

## Skill Routing

- **Start every task** with `onlyoffice-odoo-core` — shared conventions and the bug-fix / feature / port workflows.
- Then load the skill for the module you are actually editing: `onlyoffice-odoo-base` (`onlyoffice_odoo`),
  `onlyoffice-odoo-documents` (`onlyoffice_odoo_documents`), or `onlyoffice-odoo-templates`
  (`onlyoffice_odoo_templates`) — each has that module's code map and data flow.
- Use `odoo-code-style` when generating new code, to match this repo's naming, comment, and logging conventions.
- Use `odoo-controllers-jwt` for anything touching `http.route`, editor callbacks, JWT tokens, or outgoing requests to
  the Document Server.
- Use `odoo-attachments-files` for `ir.attachment`, binary fields, file formats, streaming, and access tokens.
- Use `odoo-owl-assets` for OWL components, XML templates, asset bundles, and JS in `static/src/`.
- Use `odoo-security` when models, routes, groups, or access rules change, and as a checklist before finishing any
  change.
- Use `odoo-testing` when writing or repairing tests, including the live Document Server test setup.
- Use `odoo-migration-17-18-19` when porting work to another Odoo-version code line, or when checking version
  compatibility.
- Use `odoo-code-review` to review a diff before merge.

## Command Safety

Odoo commands need a database and an addons path, neither of which is defined in this repository. Ask the user for the
intended install/test command and the Odoo instance/Document Server location, then confirm before running anything that
touches a database, installs packages, or calls a live Document Server.
