---
name: onlyoffice-odoo-documents
description:
  Integration with the Enterprise Documents app (onlyoffice_odoo_documents) — open/create/share/convert files from
  Documents, per-document access roles, attachment versioning, Odoo Spreadsheet ↔ XLSX with live ODOO_* formulas via
  docbuilder, ONLYOFFICE Desktop Editors mode. Use for any change inside onlyoffice_odoo_documents.
---

# onlyoffice_odoo_documents

Integrates ONLYOFFICE into the Enterprise `documents` app. `depends: onlyoffice_odoo, documents, documents_spreadsheet`
(the last one is needed for the Odoo Spreadsheet features: `join_spreadsheet_session`, `@spreadsheet_edition` JS).

**This is the most version-specific module in the repo** — the Enterprise `documents` app was reworked in Odoo 18 and
again in 19, so controllers, QWeb inheritance and JS patches differ per branch. Trust the code on the current branch,
not this list, for exact signatures; see `odoo-migration-17-18-19` for the known API deltas. The code map below
describes the 17.0 code line.

## Features (user scenarios)

Open any supported document from the Documents inspector (new tab or `same_tab` client action); create a blank
docx/xlsx/pptx/pdf or a gallery form in the current folder; Advanced Share (per-document roles for internal users, a
link and individual users); share links (17: `documents.share`) with an "Open in ONLYOFFICE" button on the portal page
and a dedicated save callback; convert a document to another format via the Document Server converter; open an Odoo
Spreadsheet as a static XLSX copy or convert it to an XLSX with live `ODOO_*` formulas evaluated by Odoo, and insert
Odoo lists/pivots into an existing XLSX; version history on every save; a restricted UI for ONLYOFFICE Desktop Editors.

## Code map

### `controllers/controllers.py` — three classes

`OnlyofficeDocuments_Connector(http.Controller)`:

| Route                                     | auth / type | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ----------------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /onlyoffice/documents/file/create`  | user, json  | `folder_id`, `supported_format`, `title`, optional `url` (gallery form, downloaded with plain `requests`). Creates `documents.document` (`raw`, `mimetype`, `folder_id`) plus default access rows: `internal_users="none"`, `link_access="viewer"`, creator = `editor`. Returns a JSON **string** `{"error", "file_id", "document_id"}`.                                                                                                                              |
| `POST /onlyoffice/documents/file/convert` | user, json  | `document_id`, `target_format`, `save_to_documents`. Access via `_validate_document_for_convert` (read rule, lock, share role ≠ `none`, `folder_id.has_write_access` when saving). Target must be in the source format's `convert` list from the formats JSON. Calls `/converter` (`async: False`, `region` from the user lang) through `conversion_utils` + `onlyoffice_request`; saves a new document in the same folder or returns `{"data": base64, "filename"}`. |

`OnlyofficeDocuments_Inherited_Connector(OnlyofficeConnector)`:

| Route                                                                                                           | auth / type                | Notes                                                                                                                                                                                                                                                                                 |
| --------------------------------------------------------------------------------------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /onlyoffice/editor/get_config` (override)                                                                 | user, json                 | Calls `super()`, then adds `document_id`, `jwt_token` (internal secret, payload `{"uid", "document_id"}`) and, when the document has spreadsheet metadata, `has_odoo_formulas=True` + `filter_values_json`.                                                                           |
| `GET /onlyoffice/documents/share/<int:share_id>/<access_token>/<int:document_id>`                               | public, http               | Editor for a document opened through a share link. 17: `documents.share._get_documents_and_check_access`. Config built by `prepare_share_editor` (role from `link_access`, overridden by a per-user role for logged-in users; document URL `document/download/<share>/<token>/<id>`). |
| `GET /onlyoffice/editor/document/<int:document_id>`                                                             | public, http, website=True | Main editor page for a document (`prepare_document_editor`: lock check, `check_access_rule("read")`, write access decides `can_write`, adds the spreadsheet values above).                                                                                                            |
| `POST /onlyoffice/documents/share/callback/<int:share_id>/<access_token>/<int:document_id>/<oo_security_token>` | public, http, csrf=False   | Save callback for share-link editing: write allowed only if `link_access` or the user's role is `editor`/`custom_filter`; then the same status-2/3 logic as the base callback. Kept separate from the base callback — change both when touching callback behavior.                    |

`OnlyOfficeShareRoute(ShareRoute)` (Enterprise `odoo.addons.documents.controllers.documents.ShareRoute`):

| Route                                                                                               | auth / type                                       | Notes                                                                                                                                                                                                                                                                                          |
| --------------------------------------------------------------------------------------------------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /document/share/<int:share_id>/<token>` (override `share_portal`)                              | public, website=True                              | Adds `onlyoffice_supported` to the QWeb context (per document for `type == "domain"` shares, boolean for single-file shares) so `views/onlyoffice_templates_share.xml` can show the "Open in ONLYOFFICE" button.                                                                               |
| `GET /Products/Files[/]`                                                                            | user                                              | Redirect for ONLYOFFICE Desktop Editors to `documents.document_action`.                                                                                                                                                                                                                        |
| `POST /onlyoffice/documents/convert_spreadsheet_via_docbuilder`                                     | user, json                                        | `document_id`, `xlsx_base64` (native o-spreadsheet export made in the browser). Delegates to `SpreadsheetDocBuilder.convert_spreadsheet_to_xlsx`: patches `ODOO.*` cells into `ODOO_*` formulas via docbuilder and saves a new XLSX document.                                                  |
| `GET /onlyoffice/documents/docbuilder_callback/<string:oo_security_token>`                          | public                                            | Docbuilder fetches its script here. The token is a **cache key** (uuid stored in an `ir.attachment`), not a JWT. 404 when expired/unknown.                                                                                                                                                     |
| `GET /onlyoffice/documents/docbuilder_file/<string:oo_security_token>`                              | public                                            | Serves the cached source XLSX for `builder.OpenFile()`; deletes the cache entry afterwards.                                                                                                                                                                                                    |
| `POST /onlyoffice/documents/evaluate_formulas_batch`                                                | public, json, csrf=False, cors="\*", POST+OPTIONS | Called from the editor sandbox (no Odoo session). Validates `jwt_token` (internal secret, `document_id` must match), switches the env to the token user and language (`request.update_env`), loads the document snapshot once, evaluates each formula, returns `{"values": {formula: value}}`. |
| `POST /onlyoffice/documents/insert_list_in_xlsx`, `POST /onlyoffice/documents/insert_pivot_in_xlsx` | user, json, csrf=False                            | Insert a sheet with `ODOO_LIST`/`ODOO_PIVOT` formulas into an existing XLSX (docbuilder rebuild, metadata updated).                                                                                                                                                                            |

Module-level helpers: `_get_document_share_role(document)` (same resolution order as `get_documents_permissions`),
`_validate_document_for_convert(document, save_to_documents)`; shared singletons `_formula_evaluator`
(`SpreadsheetFormulaEvaluator`) and `_docbuilder` (`SpreadsheetDocBuilder(_formula_evaluator)`).

### Spreadsheet formulas (`controllers/spreadsheet_formulas.py`, `spreadsheet_docbuilder.py`, `*.docbuilder`)

- **Why server-side**: the native `ODOO.PIVOT`/`ODOO.LIST` compute code needs the full o-spreadsheet model and Odoo web
  services and cannot run inside the editor sandbox, so the formulas are re-implemented in Python against the ORM.
- `SpreadsheetFormulaEvaluator` — `load_document_snapshot(document_id)` (metadata from `onlyoffice_spreadsheet_metadata`
  or from the source spreadsheet's `join_spreadsheet_session`, cached per request),
  `evaluate_single_formula(snapshot, "=ODOO_X(...)")`, `evaluate_odoo_formulas_in_snapshot`, `parse_and_resolve_domain`
  (`safe_eval` + `uid` substitution), `get_pivot_column_formats`/`get_list_column_formats`. Handlers: `LIST`,
  `LIST_HEADER`, `PIVOT`, `PIVOT_HEADER`, `PIVOT_TABLE`, `FILTER_VALUE`, `CURRENCY_RATE`. `read_group` calls run inside
  a savepoint and are cached on `request._rg_cache` for the batch.
- `SpreadsheetDocBuilder` — `convert_spreadsheet_to_xlsx`, `insert_list`, `insert_pivot`, `build_callback_script`,
  `get_cached_file`. The module also defines `XLSX_MIMETYPE` (imported by `controllers.py` and `models/documents.py`;
  set explicitly because Odoo may sniff a rebuilt workbook as `application/zip`). Payloads for the docbuilder callback
  are stored in `ir.attachment` records named `onlyoffice_docbuilder_cache_<uuid>` (TTL 1 h, committed immediately so
  another worker can read them). Scripts selected by the cached `mode`: `patch_formulas.docbuilder` (patch `ODOO.*`
  cells in a native export — the only conversion path, a native `xlsx_base64` export is required) and
  `insert_sheet.docbuilder` (add a sheet); `convert_spreadsheet.docbuilder` (full rebuild from the JSON snapshot) is
  kept in the module but no longer selected. A shared JS helper block is substituted into the scripts as text.
- Metadata (lists, pivots, global filters, resolved domains, column formats) is stored on the document
  (`onlyoffice_spreadsheet_metadata`) **and** inside the XLSX in a hidden `_OdooMetadata` sheet, so a re-uploaded file
  can be restored (`Document._ensure_onlyoffice_spreadsheet_metadata`).
- Client side: `onlyoffice_odoo/static/src/js/odoo_custom_functions_init.js` registers the `ODOO_*` functions and
  batches evaluation requests (50 ms debounce) to `evaluate_formulas_batch` with `window.odooJwtToken`.
- Domains are resolved (including `uid`) once, at conversion time, as the converting user; later viewers evaluate under
  their own access rights but with those baked-in domains.

### `models/`

- `documents.py` — `documents.document` extension: `onlyoffice_spreadsheet_source_id` (m2o to the source Odoo
  Spreadsheet), `onlyoffice_spreadsheet_metadata` (Text, JSON), `onlyoffice_spreadsheet_metadata_checked`;
  `_ensure_onlyoffice_spreadsheet_metadata()` (lazy, on editor open), `get_onlyoffice_spreadsheets_to_display` /
  `get_onlyoffice_spreadsheets_count` (XLSX documents for the ONLYOFFICE tab of the spreadsheet selector),
  `_compute_thumbnail` override (no thumbnails for PDFs). `_extract_odoo_metadata_from_xlsx` unzips the workbook and
  parses `xl/workbook.xml`, its rels, the `_OdooMetadata` sheet and `sharedStrings.xml` with `ElementTree`.
- `ir_attachment.py` — `oo_attachment_version = Integer(default=1)` (used by the base module's save callback).
- `onlyoffice_documents_access.py` — `onlyoffice.odoo.documents.access`: `document_id` (cascade), `internal_users`
  (default `none`), `link_access` (default `viewer`).
- `onlyoffice_documents_access_user.py` — `onlyoffice.odoo.documents.access.user`: `document_id`, `user_id`, `role`.
- `onlyoffice_odoo_documents.py` — `onlyoffice.odoo.documents` (no fields): `advanced_share_data(vals)` and
  `advanced_share_save(vals)` used by the Advanced Share dialog (owner or `base.group_system` only; single document;
  only docx/xlsx/pptx/pdf), `_get_available_roles(filename)`.

### `security/ir.model.access.csv`

`onlyoffice.odoo.documents`, `onlyoffice.odoo.documents.access`, `onlyoffice.odoo.documents.access.user` — full CRUD for
`base.group_user`. Owner/admin restrictions are enforced in the model methods and controllers, not by ACL.

### `views/onlyoffice_templates_share.xml`

QWeb inheritance of the Enterprise portal pages `documents.share_files_page` (single file) and
`documents.share_workspace_page` (folder share): adds "Open in ONLYOFFICE" linking to
`/onlyoffice/documents/share/<share_id>/<token>/<document_id>` when `onlyoffice_supported`.

### `static/src/` (frontend, 17 Documents app)

- `documents_view/onlyoffice_odoo_documents_controller_mixin.js|xml` — mixin applied with `patch` to
  `DocumentsKanbanController` and `DocumentsListController`; extends `documents.DocumentsViews.ControlPanel` with the
  buttons **Create with ONLYOFFICE** (`CreateModeDialog` → blank `CreateDialog` or `FormGallery` →
  `/onlyoffice/documents/file/create`), **Advanced Share** (`ShareDialog` →
  `onlyoffice.odoo.documents.advanced_share_*`) and **Convert with ONLYOFFICE** (`ConvertDialog` →
  `/onlyoffice/documents/file/convert`, targets from the formats JSON `convert` list).
- `models/documents_inspector_onlyoffice.js` + `components/documents_inspector_onlyoffice/*.xml` —
  `patch(DocumentsInspector)`: "Open in ONLYOFFICE" and "Convert to ONLYOFFICE XLSX (with formulas)". For an Odoo
  Spreadsheet (`handler === "spreadsheet"`) both first export a native XLSX in the browser (`join_spreadsheet_session`
  - `/spreadsheet/xlsx`); "Open" creates a new `<name>_<timestamp>.xlsx` document with
    `onlyoffice_spreadsheet_source_id`, "Convert" sends the export to `convert_spreadsheet_via_docbuilder`.
    `_openDocumentInOnlyoffice` honours `same_tab` except in Desktop Editors.
- `spreadsheet_selector/` — `OnlyofficeSelectorPanel` (extra tab in `SpreadsheetSelectorDialog` from
  `@spreadsheet_edition`, lists XLSX documents) and a patch of `SpreadsheetSelectorDialog._confirm` that routes
  `insertList`/`insertPivot` to `insert_list_in_xlsx` / `insert_pivot_in_xlsx`; chart and link insertion are not
  supported for ONLYOFFICE spreadsheets.
- `js/desktop_mode_init.js`, `js/desktop_restriction.js`, `js/desktop_auth.js`, `css/desktop_restriction.css` — active
  only when `navigator.userAgent.includes("AscDesktopEditor")`: theme sync, forced navigation to Documents (service
  `desktop_restriction`), hiding of non-ONLYOFFICE menus, `portal:login` to the desktop app (service `desktop_auth`).

Assets are listed explicitly in the manifest (desktop scripts first, then `models/*.js`, `components/*/*.xml`,
`documents_view/**/*`, `onlyoffice_create_template/**/*`, `spreadsheet_selector/**/*`, `css/*.css`).

## Access model

- `onlyoffice.odoo.documents.access` (defaults per document: `internal_users` role + `link_access` role) and
  `onlyoffice.odoo.documents.access.user` (per-user role).
- Roles: `none` / `viewer` / `commenter` / `reviewer` / `editor` / `form_filling` / `custom_filter`. Available roles
  depend on the file type (`_get_available_roles`): docx — no `form_filling`/`custom_filter`; xlsx — no
  `reviewer`/`form_filling`; pptx — `none`/`viewer`/`commenter`/`editor`; pdf — `none`/`viewer`/`editor`/`form_filling`;
  anything else — `none`/`viewer`/`editor`.
- `OnlyofficeConnector.get_documents_permissions` (base module) maps roles to editor permissions (`viewer` → view mode;
  `commenter` → `comment`; `reviewer` → `review`; `editor` → `edit`; `form_filling` → `fillForms`; `custom_filter` →
  `edit` + `modifyFilter: false`). Resolution order: owner → per-user role → `internal_users` default → fallback
  `viewer` (no access row). `none` raises `AccessError`. A role can only lower what standard Odoo write access allows,
  never raise it (`editor` requires `can_write`).
- Share links use `link_access`, overridden by the per-user role for logged-in users (`prepare_share_editor`).
- Documents created through ONLYOFFICE start with `internal_users="none"`, `link_access="viewer"`, creator `editor`.
- Full route-auth table and checklist: `odoo-security`.

## Versioning

Implemented in the base module's `editor_callback` (branch `attachment.res_model == "documents.document"`): the document
is written through `document.write({"datas"})`, `oo_attachment_version` is bumped and the previous attachment is renamed
to `"name (N).ext"`; history attachments open read-only. Exact steps and invariants: `odoo-attachments-files`. The
share-link callback in this module writes the document without this bookkeeping.

## Workflow notes

- Check every fix against the Documents app source (Python and JS) of the Odoo version you are editing — do not assume
  an API from one version exists in another.
- Spreadsheet changes: keep the formula grammar in sync in three places — the `ODOO_*` JS functions (base module), the
  `_HANDLERS` map in `spreadsheet_formulas.py`, and the `.docbuilder` scripts that write formulas into cells.
- New docbuilder flows: store the payload with the cache helpers (`_store_docbuilder_data`), never in process memory —
  the callback may hit another worker.
- This module has no automated tests and is excluded from CI (Enterprise is not available there); document manual
  verification steps in the PR and mock `onlyoffice_request` if you add tests (`odoo-testing`).
- Changelog: `CHANGELOG documents.md`.
