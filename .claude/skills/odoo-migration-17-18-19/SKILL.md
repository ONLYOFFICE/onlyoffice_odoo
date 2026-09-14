---
name: odoo-migration-17-18-19
description:
  Porting ONLYOFFICE module changes between Odoo 17, 18 and 19 code lines via merge, plus a reference of framework and
  Enterprise Documents differences between the versions and the exact places in this repo that depend on them. Use for
  any port, merge, version-compatibility question, or when writing version-correct code on any branch whose manifest
  version is 18.0.x or 19.0.x.
---

# Porting 17 → 18 → 19

This skill has two uses:

1. **Port workflow** — moving changes forward through merges.
2. **Version reference** — the difference tables below tell you which API to use in the code you are editing right now.
   Pick the column by the `__manifest__.py` version prefix (`17.0.x` / `18.0.x` / `19.0.x`), never by the branch name —
   work branches forked from the integration branches (`feature/18.0`, `feature/19.0`) can be named anything. If the
   manifest prefix does not match the version you expected to work on, stop and ask before changing anything.

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
| OWL                | 2.x                        | 3.x — stricter props validation                                                 | all components and patches     |
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
