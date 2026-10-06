---
name: odoo-migration-17-18-19
description:
  Porting ONLYOFFICE module changes between Odoo 17, 18, 19 and 20 code lines via merge, plus a reference of framework
  and Enterprise Documents differences between the versions and the exact places in this repo that depend on them. Use
  for any port, merge, version-compatibility question, or when writing version-correct code on any branch whose manifest
  version is 18.0.x, 19.0.x or 20.0.x.
---

# Porting 17 → 18 → 19 → 20

This skill has two uses:

1. **Port workflow** — moving changes forward through merges.
2. **Version reference** — the difference tables below tell you which API to use in the code you are editing right now.
   Pick the column by the `__manifest__.py` version prefix (`17.0.x` / `18.0.x` / `19.0.x` / `20.0.x`), never by the
   branch name — work branches forked from the integration branches (`feature/18.0`, `feature/19.0`, `feature/20.0`) can
   be named anything. If the manifest prefix does not match the version you expected to work on, stop and ask before
   changing anything.

## Workflow

A change ports forward from whichever code line it was made on, toward newer ones — 17 → 18 → 19 is the typical path,
but a fix can just as well start on 18 and only need porting to 19. Release branches are `17.0`, `18.0`, `19.0`;
integration branches are `feature/18.0` and `feature/19.0`; new 18/19 work is usually done on branches forked from them
and merged back (`hotfix/<version>` branches exist for urgent fixes).

1. Finish and test the change on its original code line.
2. If an 18 code line is affected and the change didn't originate there, merge into the 18 integration branch
   (`feature/18.0`) or a branch forked from it. Resolve conflicts in favor of the 18 API.
3. If a 19 code line is affected and the change didn't originate there, merge the 18 result into the 19 integration
   branch (`feature/19.0`) or a fork of it. Resolve for the 19 API.
4. Run the module tests on each target; confirm each target's manifest prefix before resolving anything.

Rules:

- Never skip an intermediate version when porting forward (e.g. don't merge 17 straight into 19) — go through each
  version in between, applying its checklist.
- Keep compatibility edits (API renames) in separate commits from behavior changes when possible — it makes the next
  merge easier.
- Verify against the real target source. Do not trust memory for renamed APIs; open the same file in the target Odoo
  branch (github.com/odoo/odoo, github.com/odoo/enterprise) or a local checkout (look for sibling
  `enterprise-<version>/` folders in the workspace or `$ODOO_SOURCE`).
- Never change the manifest version prefix or bump the version yourself — that is a separate release process.
- Update the module changelog on the target line too; `.pylintrc` `valid-odoo-versions` and the CI container
  (`.github/workflows/test.yml`) are per code line — do not merge them blindly.

## Version-sensitive places in this repo (grep list)

Run these greps on the merge result before committing; each hit must use the target version's API.

| Pattern                                                                                                                                  | Where (17 code)                                                                                                                                     | 18/19 concern                                                                      |
| ---------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `check_access_rights`, `check_access_rule`                                                                                               | base `controllers/main.py`; documents `controllers/controllers.py`, `spreadsheet_docbuilder.py`; templates `controllers/controllers.py`             | `has_access` / `check_access`                                                      |
| `documents.share`, `_get_documents_and_check_access`, `share.type`                                                                       | documents share editor + share callback                                                                                                             | share model removed in 18; sharing via document access/permissions                 |
| `ShareRoute`, `share_portal`, `documents.share_files_page`, `share_workspace_page`                                                       | documents `OnlyOfficeShareRoute`, `views/onlyoffice_templates_share.xml`                                                                            | portal controller and QWeb templates reworked                                      |
| `documents.folder`, `folder_id`, `has_write_access`                                                                                      | documents `file/create`, `file/convert`, `_validate_document_for_convert`; templates `documents/folders`, `documents/save`, `FolderSelectionDialog` | folders are `documents.document` with `type="folder"` in 18+; access fields differ |
| `owner_id`, `is_locked`, `lock_uid`, `handler == "spreadsheet"`                                                                          | documents permissions, convert validation, inspector patch                                                                                          | verify field names on the target `documents.document`                              |
| `DocumentsInspector`, `documents.DocumentsInspector.buttons`                                                                             | documents `models/documents_inspector_onlyoffice.js` + XML                                                                                          | inspector replaced by a details panel in 18 — patch a different component          |
| `DocumentsKanbanController`, `DocumentsListController`, `documents.DocumentsViews.ControlPanel`, `DocumentsKanbanRecord`                 | documents mixin, kanban/list patches, desktop restriction                                                                                           | component/template names and control-panel structure changed                       |
| `@spreadsheet_edition/...spreadsheet_selector_dialog/...`, `join_spreadsheet_session`, `/spreadsheet/xlsx`, `@spreadsheet/helpers/model` | documents `spreadsheet_selector/`, inspector patch, `spreadsheet_formulas.py`                                                                       | verify module paths and helper names in the target `spreadsheet*` addons           |
| `@mail/core/common/attachment_list`, `mail.AttachmentList`, `o-mail-AttachmentCard-aside`                                                | base chatter patch + XML                                                                                                                            | module path / template / CSS class may differ                                      |
| `useService("rpc")`, `this.env.services.rpc`                                                                                             | all OWL components and patches                                                                                                                      | `import { rpc } from "@web/core/network/rpc"`                                      |
| `getStaticActionMenuItems`                                                                                                               | templates form/list controller patches                                                                                                              | verify signature and menu item shape                                               |
| `ir.actions.report handlers`, `web.controllers.report.ReportController`                                                                  | templates report handler + `report_controller.py`                                                                                                   | verify registry name and controller methods (`report_routes`, `report_download`)   |
| `<tree`                                                                                                                                  | templates `views/onlyoffice_menu_views.xml`                                                                                                         | `<list>` in 18+                                                                    |
| `groups="..."` on menus/views, `implied_ids` XML                                                                                         | templates security XML and views                                                                                                                    | groups XML changed in 18+ (verify `res.groups` fields)                             |
| `/** @odoo-module **/`                                                                                                                   | all JS                                                                                                                                              | optional on 18+ (harmless to keep)                                                 |
| `_sql_constraints`, raw SQL strings                                                                                                      | none today — check new code                                                                                                                         | `models.Constraint` / `SQL()` in 19                                                |
| `get_frontend_session_info`, `web.assets_frontend*`, `web.conditional_assets_tests`                                                      | base `views/templates.xml`, `prepare_editor_values`                                                                                                 | verify the frontend layout/session helpers on the target                           |

## 17 → 18: changes that hit these modules

API deltas are in the grep list above (access checks, `<tree>` → `<list>`, Documents models/JS, rpc import, module
header). Generic framework changes that do not touch this repo today (chatter tag, `SQL()` builder) only matter for new
code.

Port checklist (18):

- [ ] Replace access-check calls; grep for `check_access_rights` and `check_access_rule`
- [ ] Rework Documents integration: folder ids, share links + share callback, portal QWeb, access roles
- [ ] Re-check every JS patch of Documents/spreadsheet components against 18 sources
- [ ] Rename tree views to list; re-test all templates views
- [ ] Re-test the `onlyoffice-pdf` report route and handler
- [ ] Run tests (do not bump the manifest version)

## 18 → 19: changes that hit these modules

| Area               | 18                         | 19                                                                              | Affects                        |
| ------------------ | -------------------------- | ------------------------------------------------------------------------------- | ------------------------------ |
| SQL constraints    | `_sql_constraints` list    | `models.Constraint()` class attributes                                          | any model with SQL constraints |
| OWL                | 2.x                        | 2.8 — stricter props validation (Owl 3 arrives in 20)                           | all components and patches     |
| `res.users` create | `groups_id` in vals worked | `groups_id` ignored in `create()`; add via `group.write({"users": [(4, uid)]})` | test setUp code                |
| Raw SQL            | discouraged                | `SQL()` builder required                                                        | any raw SQL                    |
| Python             | 3.10+                      | 3.12+                                                                           | dependency checks              |
| Documents app      | 18 access model            | changed again — re-verify                                                       | `onlyoffice_odoo_documents`    |

Port checklist (19):

- [ ] Convert `_sql_constraints` to `models.Constraint`
- [ ] Update OWL props to object form (`{ type, required, optional }`)
- [ ] Fix user creation in tests (groups after create)
- [ ] Wrap any raw SQL in `SQL()`
- [ ] Re-verify all Enterprise `documents` and `spreadsheet` touch points
- [ ] Run tests (do not bump the manifest version)

## 19 → 20: changes that hit these modules

Found while porting this repo to 20 (Odoo 20.0, Enterprise 20.0). A module with a `19.0.x` manifest is simply
`installable=False` on 20 (log: "has an incompatible version") — nothing below is reported until the prefix is `20.0.`.

| Area               | 19                                                        | 20                                                                                                                                         | Affects                                                             |
| ------------------ | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| Access rights      | `ir.model.access` (+ `ir.rule`)                           | one model `ir.access`; `security/ir.access.csv` (`id,name,model_id,group_id/id,operation,domain`), see `odoo-security`                     | all three `security/` folders, templates security XML               |
| Model access check | `check_access_rights(op, raise_exception=False)`          | removed — `records.browse().has_access(op)`                                                                                                | base `get_config`                                                   |
| System parameters  | `get_param` / `set_param` (strings, `False` deletes)      | typed `get_str/get_bool/get_int/get_float`, `set_str/set_bool/...`; read flags with `get_bool`, a stored `"False"` is truthy for `get_str` | `config_utils` (both modules), `onlyoffice.odoo`, tests, e2e        |
| Binary content     | `datas` (base64), values are base64 `bytes`               | `datas` removed (writes **silently ignored**); values are `BinaryValue`; `read()` gives `{content, size}`; see `odoo-attachments-files`    | save callbacks, docbuilder, templates model, thumbnails             |
| `read_group`       | `read_group(domain, fields, groupby, lazy=False)` → dicts | `read_group(domain, groupby, aggregates)` → tuples; dicts via `formatted_read_group`                                                       | documents `_safe_read_group` (compat wrapper `_read_group_dicts`)   |
| `odoo.http`        | module with `content_disposition`, `serialize_exception`  | package: `odoo.http.stream.content_disposition`, `odoo.http.dispatcher.serialize_exception`                                                | templates `report_controller.py`, callback error handlers           |
| `odoo.tools`       | `ustr`                                                    | removed                                                                                                                                    | templates `get_fields_for_model`                                    |
| JSON in templates  | `scriptsafe.dumps(session_info)`                          | session info holds `mappingproxy` → `scriptsafe.dumps(x, default=json_default)`                                                            | editor pages (base, documents)                                      |
| Static selection   | `field.selection` is a list                               | tuple                                                                                                                                      | templates field formatting                                          |
| Postcommit hooks   | ORM usable                                                | transaction is reset after commit → open a new cursor (`registry.cursor()`), tests use `registry_test_mode()`                              | templates `ir_attachment.py`                                        |
| Frontend           | Owl 2.8                                                   | Owl 3 (`useProps`, `proxy`, `signal.ref`, `this.` in templates, `t-out`) — see `odoo-owl-assets`                                           | every component, template and patch                                 |
| Icons              | Font Awesome                                              | Material Symbols (`oi` + `data-icon`, subset font)                                                                                         | all XML/JS/SCSS with `fa`                                           |
| Documents app      | 19 templates without `this.`                              | xpath anchors with `this.`; "All" section (`folder_id` false); selector panel API; kanban `buttonTemplate`                                 | documents controller mixin, file create, selector, templates kanban |
| Server/runtime     | listens on all interfaces; PostgreSQL 12+                 | `http_interface` defaults to `127.0.0.1` (set `0.0.0.0` in Docker); PostgreSQL 16+ (`any_value()`)                                         | docker compose, CI, e2e                                             |
| Access error text  | `... User: <login> (id=<id>)`                             | `... User: <id>`                                                                                                                           | e2e `access.spec.ts`                                                |

Port checklist (20):

- [ ] Manifest prefix `20.0.` (a release decision — ask first), `.pylintrc` `valid-odoo-versions=20.0`
- [ ] `ir.model.access.csv` → `ir.access.csv`; drop the duplicated `ir.model.access` XML records
- [ ] grep `get_param`, `set_param`, `datas`, `check_access_rights`, `read_group(`, `tools.ustr`,
      `from odoo.http import`
- [ ] Owl 3: grep `useState`, `useRef`, `static props`, `t-esc`, `t-model`, bare names in templates, xpath anchors
- [ ] Icons: grep `fa-` / `"fa ` and check each Material Symbol name renders
- [ ] Run unit tests, e2e (`postgres:16`, `odoo:20.0`, `--http-interface=0.0.0.0`) and open every dialog in a browser
- [ ] Unit tests in a second database on a shared server make routes without a session answer 404 (no `dbfilter`): drop
      the test database afterwards or use a separate PostgreSQL

## Merge conflict rules

- Config/util modules (`config_utils`, `jwt_utils`, `file_utils`, `url_utils`, `conversion_utils`, `keys_utils`,
  `pdf_utils`) rarely differ between branches — take the incoming change, then re-apply version-specific bits.
- Controllers and `onlyoffice_odoo_documents` differ the most — resolve hunk by hunk with the target-version API open
  next to you. The spreadsheet files (`spreadsheet_formulas.py`, `spreadsheet_docbuilder.py`, `.docbuilder`) are mostly
  version-neutral Python/JS; their Odoo touch points are `join_spreadsheet_session`, `read_group`, `fields_get`,
  `safe_eval` and the `documents.document` fields.
- If a 17 feature has no 18/19 equivalent API, port the intent, not the code: find how the target Documents app models
  the same concept.
- After any merge, run the grep list above before committing.
