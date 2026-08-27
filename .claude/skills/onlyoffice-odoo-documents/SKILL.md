---
name: onlyoffice-odoo-documents
description:
  Integration with the Enterprise documents app (onlyoffice_odoo_documents) — open/create/share files from Documents,
  per-document access roles, attachment versioning. Use for any change inside onlyoffice_odoo_documents.
---

# onlyoffice_odoo_documents

Integrates ONLYOFFICE into the Enterprise `documents` app: open/create/share files, per-document access roles,
attachment versions. `depends: onlyoffice_odoo, documents`.

**This is the most version-specific module in the repo** — the Enterprise `documents` app was reworked in Odoo 18 and
again in 19, so controllers and JS patches differ per branch. Trust the code on the current branch, not this list, for
exact route signatures; see `odoo-migration-17-18-19` for the known API deltas.

## Code map

- `controllers/controllers.py` (route set on 17; verify on 18/19):
  - `/onlyoffice/documents/file/create` — new file in a folder from a template
  - `/onlyoffice/documents/share/...` — open a shared document by link token (17: via `documents.share`; 18+: the share
    model was removed, sharing goes through the documents access/permission model)
  - `/onlyoffice/editor/document/<id>` — open by document id
  - Extends `OnlyofficeConnector` from `onlyoffice_odoo` (`get_documents_permissions` lives on the parent class and is
    used here for role-to-permission mapping).
- `models/onlyoffice_odoo_documents.py`, `models/onlyoffice_documents_access.py`,
  `models/onlyoffice_documents_access_user.py` — the access/role models below.
- `static/src/` — Documents kanban/list patches, create-file dialog, share dialog, desktop-mode scripts (see
  `odoo-owl-assets`).

## Access model

- `onlyoffice.odoo.documents.access` (defaults per document: internal-users role + link role) and
  `onlyoffice.odoo.documents.access.user` (per-user role).
- Roles: `none` / `viewer` / `commenter` / `reviewer` / `editor` / `form_filling` / `custom_filter`.
  `OnlyofficeConnector.get_documents_permissions` (base module) maps roles to editor permissions. Resolution order:
  owner → per-user role → internal-users default → fallback `viewer`. A role can only lower what standard Odoo write
  access allows, never raise it.
- Full route-auth table and checklist: `odoo-security`.

## Versioning

Saving a `documents.document` through the editor callback bumps `oo_attachment_version` and renames the previous
attachment (history versions open read-only). Implemented in the base module's callback
(`onlyoffice_odoo/controllers/main.py::editor_callback`), triggered whenever
`attachment.res_model == "documents.document"`. Keep this flow intact when touching the callback — see
`odoo-attachments-files` for the exact steps.

## Workflow notes

- Any fix here should be checked against the Documents app source of the Odoo version you are editing (17/18/19 differ
  significantly) — do not assume an API from one version exists in another.
- Verify JS patches to Documents components against the same-version source before changing them — see
  `odoo-owl-assets`.
- For the general bug-fix/feature workflow and repo-wide rules, see `onlyoffice-odoo-core`.
