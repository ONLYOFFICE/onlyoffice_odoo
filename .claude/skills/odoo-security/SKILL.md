---
name: odoo-security
description:
  Odoo security for the ONLYOFFICE modules - access rights (ir.model.access.csv and XML), groups, sudo discipline, route
  authentication for every public route, the document role model, and input handling for docbuilder scripts and
  spreadsheet formulas. Use whenever models, routes, or permissions change, and as a final checklist for any change.
---

# Security

## Access rights (ACL)

Every model needs at least one line in `security/ir.model.access.csv`:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_my_model_user,my.model user,model_my_model,base.group_user,1,1,1,0
```

- No `group_id` = applies to everyone (including portal/public via server code). Avoid unless intended.
- Model reference name: `model_` + model name with dots as underscores.

Current ACLs:

| Module    | Model                                                                                                    | Group                                   | Rights                                                   |
| --------- | -------------------------------------------------------------------------------------------------------- | --------------------------------------- | -------------------------------------------------------- |
| base      | `onlyoffice.odoo`                                                                                        | `base.group_user`                       | read                                                     |
| documents | `onlyoffice.odoo.documents`, `onlyoffice.odoo.documents.access`, `onlyoffice.odoo.documents.access.user` | `base.group_user`                       | full CRUD (owner/admin checks live in the model methods) |
| templates | `onlyoffice.odoo.templates`                                                                              | `group_onlyoffice_odoo_templates_user`  | read                                                     |
| templates | `onlyoffice.odoo.templates`                                                                              | `group_onlyoffice_odoo_templates_admin` | full CRUD                                                |
| templates | `onlyoffice.odoo.templates`                                                                              | (none)                                  | 0/0/0/0                                                  |
| templates | `onlyoffice.odoo.demo.templates`                                                                         | `base.group_system`                     | full CRUD                                                |

The templates user/admin ACLs are declared twice — in `ir.model.access.csv` **and** as `ir.model.access` records in
`security/onlyoffice_templates_security.xml`. Change both together.

## Groups

`onlyoffice_odoo_templates/security/onlyoffice_templates_security.xml` defines a module category and two groups:

- `group_onlyoffice_odoo_templates_user` — read templates, print with them. Assigned to `base.default_user` (so new
  internal users get it).
- `group_onlyoffice_odoo_templates_admin` — create/edit/delete templates, edit them in the editor; implies the user
  group. Assigned to `base.user_admin` and `base.user_root`.

Check membership with:

```python
request.env.user.has_group("onlyoffice_odoo_templates.group_onlyoffice_odoo_templates_admin")
```

Template editing is admin-group-only (`/onlyoffice/template/editor` gives `can_write` only to admins); template
filling/printing is for the user group; the menu is visible to both. The settings app is `base.group_system`. Advanced
Share in the documents module is allowed to the document owner or `base.group_system` (checked in
`onlyoffice.odoo.documents`).

## sudo discipline

- Default: run as the real user. On public routes, resolve the user from `oo_security_token` and use `.with_user(user)`.
- `sudo()` only for: reading config parameters (`config_utils`), internal bookkeeping (renaming history attachments, the
  docbuilder cache rows, `field_keys` writes), resolving the token user (`res.users.sudo().browse`), and lookups that
  must ignore ACLs — always after the user's own access was already verified.
- Never `sudo()` the actual file read/write on behalf of an unverified caller.
- Add a one-line comment for every new `sudo()`.

## Document roles (onlyoffice_odoo_documents)

`onlyoffice.odoo.documents.access` (per-document `internal_users` / `link_access` roles) and
`onlyoffice.odoo.documents.access.user` (per-user role) sit on top of standard Odoo rights. Security invariants: a role
can only lower what ORM write access allows, never raise it; `none` denies opening; share links use `link_access`
(per-user role wins for logged-in users) and saving through a link requires `editor`/`custom_filter`. Role list,
resolution order and the per-file-type matrix: `onlyoffice-odoo-documents`.

## Route authentication summary

| Route                                                                          | Module    | auth          | Required checks                                                                                                                            |
| ------------------------------------------------------------------------------ | --------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `/onlyoffice/editor/get_config`, `/onlyoffice/preview`                         | base      | user          | `validate_access` + attachment read (and write for `can_write`); document lock/read rule                                                   |
| `/onlyoffice/editor/<id>`                                                      | base      | public        | `validate_access(access_token)` + attachment read/write as the session user (public user for anonymous links)                              |
| `/onlyoffice/file/content/<id>`                                                | base      | public        | `oo_security_token` → user; `validate_access`; read right; Document Server JWT header when JWT enabled                                     |
| `/onlyoffice/editor/callback/<id>`                                             | base      | public        | `oo_security_token` → user; `validate_access`; write right; Document Server JWT (body or header)                                           |
| `/onlyoffice/file/content/test.txt`                                            | base      | public        | none (static test content)                                                                                                                 |
| `/onlyoffice/oforms/*`                                                         | base      | user          | none beyond login (proxy to a public API)                                                                                                  |
| `/onlyoffice/documents/file/create`, `/file/convert`                           | documents | user          | Documents ACL/rules; convert also lock, share role ≠ `none`, folder write access when saving                                               |
| `/onlyoffice/editor/document/<id>`                                             | documents | public        | lock + `check_access_rule("read")`, write rule decides edit mode                                                                           |
| `/onlyoffice/documents/share/<share>/<token>/<doc>` and its `/callback`        | documents | public        | 17: `documents.share._get_documents_and_check_access(token)`; role from `link_access`/per-user; callback also `oo_security_token` + DS JWT |
| `/document/share/<share>/<token>` (override)                                   | documents | public        | inherited from Enterprise `ShareRoute`                                                                                                     |
| `/Products/Files`                                                              | documents | user          | redirect only                                                                                                                              |
| `/onlyoffice/documents/convert_spreadsheet_via_docbuilder`                     | documents | user          | spreadsheet read via `join_spreadsheet_session`, new document created as the user                                                          |
| `/onlyoffice/documents/insert_list_in_xlsx`, `insert_pivot_in_xlsx`            | documents | user          | document write rule (`_get_writable_document`)                                                                                             |
| `/onlyoffice/documents/docbuilder_callback/<token>`, `docbuilder_file/<token>` | documents | public        | token = random cache key; 404 when unknown/expired; entry deleted after use                                                                |
| `/onlyoffice/documents/evaluate_formulas_batch`                                | documents | public + CORS | `jwt_token` (internal secret, `uid` + `document_id` match); `check_access_rule("read")` as that user; env switched to that user            |
| `/onlyoffice/template/editor`                                                  | templates | user          | `validate_access`, read right; write only for the admin group                                                                              |
| `/onlyoffice/template/fill`, `/documents/check`, `/folders`, `/save`           | templates | user          | template ACL (user group); folder write access for save                                                                                    |
| `/onlyoffice/template/callback/docbuilder/*`, `/template/download/<id>`        | templates | public        | `oo_security_token` → user; template/attachment read as that user                                                                          |
| `/onlyoffice/template/template_content/<path>`                                 | templates | public        | path confined to `data/templates` (`get_template_content`)                                                                                 |
| `/report/onlyoffice-pdf/...`, `/report/download`                               | templates | (web)         | inherits `web.ReportController` behavior; report access as the current user                                                                |

Token details: `odoo-controllers-jwt`.

## Input handling

- User-controlled strings that reach the editor config go through `filter_xss` (titles) or are JSON-encoded by
  `scriptsafe.dumps` (QWeb page).
- Anything interpolated into a `.docbuilder` script is executed by the Document Server: pass record values as
  `json.dumps(...)`, sanitise file names (`re.sub(r"[<>:'/\\|?*\x00-\x1f]", " ", ...)`), never format raw strings into
  the script.
- Spreadsheet formulas arrive as strings from the editor sandbox: they are parsed with a strict regex and `_parse_args`;
  domains stored in metadata are evaluated with `safe_eval`. Keep evaluation behind the token check and as the token
  user.
- Uploaded XLSX files are parsed with `zipfile` + `ElementTree` inside `try/except`; parsing failures must degrade to
  "no metadata", never to an error for the user.
- Files served from the module directory (`data/templates`) go through `get_template_content` (`resolve().relative_to`
  - `file_open(filter_ext=...)`).
- Never log secrets or tokens; logging URLs and ids is fine.

## Final security checklist (run for every change)

- [ ] New models have ACL lines (and the XML twin for templates); new menus/actions restricted to the right groups
- [ ] No new `sudo()` without a one-line justification comment
- [ ] Public routes: token validated before any ORM read; formula/cache tokens handled as described above
- [ ] JWT: incoming tokens decoded and used instead of raw body
- [ ] No secrets (JWT secrets, tokens) in logs or error messages
- [ ] User-controlled strings sanitized before entering configs, filenames, or docbuilder scripts
- [ ] Access errors raise `Forbidden`/`AccessError`, not generic 200 responses
- [ ] Role model respected: a role never grants more than Odoo write access allows
