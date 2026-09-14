---
name: onlyoffice-odoo-templates
description:
  Fillable PDF templates module (onlyoffice_odoo_templates) — template lifecycle (create/upload/convert to PDF form,
  editor with Odoo field panel), docbuilder fill flow, field mapping and formatting from Odoo records, the
  onlyoffice-pdf report type, demo templates, Documents integration, access groups. Use for any change inside
  onlyoffice_odoo_templates.
---

# onlyoffice_odoo_templates

Builds filled PDFs from Odoo record data through the Document Server **docbuilder** service.
`depends: base, onlyoffice_odoo, web`; Python dependency `pyjwt`. Co-authored with Data Dance s.r.o. (some files carry
their copyright).

## Features (user scenarios)

Templates app (kanban/list/form) to create a template for an Odoo model from a blank PDF form, an uploaded PDF
(converted to a PDF form when needed) or the online gallery; template editor with a side panel of model fields that
inserts form fields keyed by field path; "Print with ONLYOFFICE" from any form/list view (one PDF, a ZIP for several
records, or save into a Documents folder); report type `onlyoffice-pdf` so standard print menus can fill a template;
demo templates installed per model and exportable from Settings; setting "Disable form fields after printing PDF form".

## Code map

### `models/`

- `onlyoffice_odoo_templates.py` — `onlyoffice.odoo.templates`. Non-obvious fields: `file` (Binary) is only an upload
  transport — the PDF lives in `attachment_id` (`res_model = onlyoffice.odoo.templates`); `field_keys` caches the PDF
  form keys as JSON; `report_id` links the optional `ir.actions.report`.
  - `create()` is overridden: downloads a PDF from `context["url"]` (gallery) or falls back to the blank
    `get_default_file_template(lang, "pdf")`, creates the attachment and, if `pdf_utils.is_pdf_form` is false, converts
    it to a PDF form through the converter (`pdf: {"form": True}`, source `/onlyoffice/template/download/<id>`). It
    calls `env.cr.commit()` around the conversion (`# pylint: disable=invalid-commit`) so the public download route sees
    the attachment from the Document Server's separate request — keep that if you change the flow. `_onchange_file`
    (re-upload) follows the same path and restores the old content on failure.
  - `_update_field_keys` / `_fetch_field_keys` — recompute the cached keys via `keys_utils.fetch_field_keys` (non-form
    PDFs clear the cache). Triggered from the `ir.attachment` overrides, not called directly.
  - `_create_demo_data()` — run by `data/templates_data.xml` at install (`noupdate="1"`) for every PDF under
    `data/templates/<model>/` whose model is installed.
  - `get_fields_for_model()` — field tree for the editor panel (skips `properties`/`html`/`json` and non-exportable
    fields, relations expandable up to depth 4). `update_relationship()` re-links `template_model_id` after a module
    reinstall changed `ir.model` ids. `create_action()` creates the associated report (`report_type="onlyoffice-pdf"`,
    `binding_model_id` = the template model).
- `onlyoffice_odoo_demo_templates.py` — `onlyoffice.odoo.demo.templates`: tree of bundled PDFs (only for installed
  models) and export to real templates; `get_template_content(path)` reads a bundled PDF with path-traversal protection
  (`resolve().relative_to` + `file_open(filter_ext=(".pdf",))`) — reuse it for any file served from `data/templates`.
- `ir_actions_report.py` — `ir.actions.report` extension: `report_type` adds `onlyoffice-pdf`, `onlyoffice_template_id`,
  `_render_onlyoffice_pdf()` modelled on `_render_qweb_pdf` (honours `attachment`/`attachment_use`, merges PDFs), plus
  its own copy of `fill_template` / `get_docbuilder_error` working with `self.env` instead of `request`.
- `ir_attachment.py` — `create`/`write` register `_refresh_template_field_keys` in `env.cr.postcommit` when content
  fields (`datas`, `raw`, `db_datas`, `store_fname`) change on template attachments; skipped with context
  `skip_field_keys_refresh`. Single point where the `field_keys` cache is refreshed (upload, conversion, editor save).
- `res_config_settings.py` — `editable_form_fields` ↔ `onlyoffice_connector.editable_form_fields` (own
  `utils/config_constants.py` / `config_utils.py`).

### `controllers/controllers.py`

`Onlyoffice_Inherited_Connector(OnlyofficeConnector)`:

| Route                                                     | auth / type            | Notes                                                                                                                                                                                   |
| --------------------------------------------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /onlyoffice/template/template_content/<string:path>` | public                 | Inline PDF preview of a bundled demo template (`_` in the path is turned back into `/`; content via `get_template_content`).                                                            |
| `POST /onlyoffice/template/editor`                        | user, json, csrf=False | Editor config for the template editor: `can_write` only for members of `group_onlyoffice_odoo_templates_admin`; everyone else opens in view mode. Returns `prepare_editor_values(...)`. |

`OnlyofficeTemplate_Connector(http.Controller)`:

| Route                                                        | auth / type | Notes                                                                                                                                                           |
| ------------------------------------------------------------ | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /onlyoffice/template/fill?template_id=&record_ids=`     | user, http  | Entry point of "Print with ONLYOFFICE" (see Fill flow). One record → PDF, several → ZIP `onlyoffice-templates-<timestamp>.zip`; errors → `request.not_found()`. |
| `GET /onlyoffice/template/callback/docbuilder/fill_template` | public      | Docbuilder fetches the fill script here (`oo_security_token`, `record_ids`, `template_id` in the query).                                                        |
| `GET /onlyoffice/template/callback/docbuilder/get_keys`      | public      | Docbuilder fetches the key-extraction script here (`get_keys.docbuilder` collects `GetFormKey()` of all forms into `keys.txt`).                                 |
| `GET /onlyoffice/template/download/<int:attachment_id>`      | public      | Serves the template PDF to the docbuilder/converter; requires `oo_security_token`, reads as that user.                                                          |
| `POST /onlyoffice/template/documents/check`                  | user, json  | Is the Enterprise `documents` module installed.                                                                                                                 |
| `POST /onlyoffice/template/documents/folders`                | user, json  | Writable folders (17: `documents.folder` with `has_write_access`).                                                                                              |
| `POST /onlyoffice/template/documents/save`                   | user, json  | Fill and store the PDFs as `documents.document` records in the chosen folder.                                                                                   |

Helpers on `OnlyofficeTemplate_Connector`: `fill_template(oo_security_token, record_ids, template_id)` (POST
`<docserver>docbuilder` with `{"async": False, "url": <callback url>}`, JWT in body `token` and in the header when a
secret is set; returns `urls`), `_get_cached_keys(template, oo_security_token)` (reads `field_keys`, falls back to
`get_keys` and stores the result), `get_keys`, `get_fields(keys, model, record_id, user)` (see Field mapping),
`get_record(model, record_id, user)` (`with_user(user)`, user language in context), `get_user_from_token` and
`get_docbuilder_error` (local copies of the base-module logic).

`.docbuilder` files: `fill_template.docbuilder` walks body paragraphs/tables, header/footer and shapes, fills text
forms, checkboxes, images and repeats table rows for list values; `get_keys.docbuilder` extracts form keys.

### `controllers/report_controller.py`

Subclasses `odoo.addons.web.controllers.report.ReportController`: `report_routes` handles
`converter == "onlyoffice-pdf"` (`/report/onlyoffice-pdf/<report_name>[/<ids>]`, `options`/`context` query params) by
calling `report._render_onlyoffice_pdf`; `report_download` handles `report_type == "onlyoffice-pdf"` and sets the
filename from `print_report_name`. The JS side is `static/src/js/report/action_manager_report.esm.js` (handler in
`registry.category("ir.actions.report handlers")`).

### `utils/`

- `config_constants.py` / `config_utils.py` — only `EDITABLE_FORM_FIELDS` (`onlyoffice_connector.editable_form_fields`)
  with `get_/set_editable_form_fields`.
- `keys_utils.py` — `fetch_field_keys(env, attachment_id, oo_security_token)`: docbuilder round trip via the `get_keys`
  callback, downloads `keys.txt` (UTF-8 with BOM) and returns the JSON list. Shared by the model cache and the
  controller fallback.
- `pdf_utils.py` — `is_pdf_form(bytes)`: detects the ONLYOFFICE PDF-form signature (`ONLYOFFICEFORM` in the first
  object).

Field mapping and value formatting are **not** in `utils/` — they live in `controllers.py::get_fields` (see below).

### `security/`

Two groups, `group_onlyoffice_odoo_templates_user` (read/print; given to `base.default_user`) and
`group_onlyoffice_odoo_templates_admin` (CRUD + editor write access; implies user). The user/admin ACLs exist twice — in
`onlyoffice_templates_security.xml` and in `ir.model.access.csv` — keep them in sync. Details: `odoo-security`.

### `views/`

- `onlyoffice_menu_views.xml` — form/search/kanban/list views, actions and menu for `onlyoffice.odoo.templates`.
  Non-obvious bits: the kanban uses `js_class="onlyoffice_kanban"`; the list is a `<tree>` on 17; the report stat
  buttons on the form are `groups="base.group_system"`; the file upload group is hidden by `hide_file_field` (set from
  the gallery flow); the menu is visible to both groups.
- `ir_actions_report_views.xml` — report form: `onlyoffice_template_id` shown/required and `model` readonly when
  `report_type == "onlyoffice-pdf"`.
- `res_config_settings_views.xml` — "Manage templates" dialog for `onlyoffice.odoo.demo.templates` (widget
  `onlyoffice_template_tree`) and the settings block inserted after the base block `o_onlyoffice_settings_common`.
- `data/templates_data.xml` — `<function model="onlyoffice.odoo.templates" name="_create_demo_data"/>`, `noupdate`.

### `static/src/` (frontend)

- `views/editor/onlyoffice_editor.js|xml` + `onlyoffice_editor_export_data.js|xml` — client action
  `onlyoffice_template_editor`: editor + `ExportData` field panel (`get_fields_for_model`). Uses the Automation API
  connector: `GetVersion` as a license probe (without a license the key is copied to the clipboard instead of inserting
  a form), `onClick` + `GetCurrentContentControlPr` to highlight the selected field. Panel ↔ editor talk through
  `env.bus` events `onlyoffice-template-create-form` / `onlyoffice-template-highlight-field`.
- `views/dialog/onlyoffice_dialog.js|xml` — `TemplateDialog` ("Print from template"): preview via `OnlyofficePreview`,
  print via `download({url: "/onlyoffice/template/fill"})`, "Add to Documents" via `FolderSelectionDialog` →
  `/onlyoffice/template/documents/save`.
- `views/form/onlyoffice_form_view.js`, `views/list/onlyoffice_list_view.js` — `patch(FormController/ListController)`
  adding "Print with ONLYOFFICE" to `getStaticActionMenuItems`.
- `views/kanban/` — `onlyoffice_kanban` view (`js_class`): "Create from template" opens `FormGallery` and then the
  template form with `default_name`, `default_hide_file_field` and `url` in context (consumed by `create()`); record
  click opens the editor.
- `views/widget/onlyoffice_templates_tree.js|xml` — field widget `onlyoffice_template_tree` for the demo-templates
  dialog.
- `js/report/action_manager_report.esm.js` — `ir.actions.report handlers` entry for `onlyoffice-pdf`.

Assets: `static/src/css/*`, `static/src/views/**/*`, `static/src/js/report/action_manager_report.esm.js`.

## Fill flow

1. UI calls `GET /onlyoffice/template/fill?template_id=&record_ids=1,2` (or the report route / Documents save).
2. `fill_template` POSTs to `<docserver>docbuilder` with
   `{"async": False, "url": <odoo>/onlyoffice/template/callback/docbuilder/fill_template?oo_security_token=…&record_ids=…&template_id=…}`
   (JWT in body and header when a secret is set; inner URL for the Document Server host).
3. The Document Server GETs that callback. Odoo resolves the user from the token, loads the template, gets the form keys
   (`_get_cached_keys`), and for every record emits `OpenFile(<download url>)` + `fields` JSON + the fill script +
   `SaveFile("pdf", "<Template> - <Record>.pdf")`. With `editable_form_fields` enabled the save uses the print param
   (`isPrint`) so filled fields are flattened.
4. The Document Server downloads the template from `/onlyoffice/template/download/<id>?oo_security_token=…`, runs the
   script and returns `{"urls": {filename: url}}`.
5. Odoo downloads the result(s) through `onlyoffice_request` and streams a PDF or ZIP, or stores them as
   `documents.document`.

Report path: `_render_onlyoffice_pdf` calls its own `fill_template` per record (one docbuilder call per record) and
merges the streams like `_render_qweb_pdf`.

## Field mapping (`get_fields`)

- Form keys are field paths separated by spaces: `partner_id name` → `{"partner_id": {"name": …}}`; nested keys are
  grouped per relation (`convert_keys`). Field ids in the editor panel use `/` (`partner_id/name`); `createForm` turns
  them into space-separated keys when it creates the form (`CreateTextForm` for scalar/relational fields,
  `CreateCheckBoxForm` for booleans, `CreatePictureForm` for binaries). Without the Automation API license the key is
  copied to the clipboard instead.
- Relations: `many2one` → nested dict of the requested sub-keys; `one2many`/`many2many` → list of dicts (rendered as
  repeated table rows by the docbuilder script).
- Value formatting, by field type: `boolean` → `"true"`/`"false"`; `binary` → base64 image data; `char`/`text` → str;
  `float` → `res.lang.format` with the field's digits; `integer` → `res.lang.format("%d")`; `monetary` →
  `misc.format_amount` with the record's currency field; `date` → `misc.format_date`; `datetime` →
  `misc.format_datetime` in the user's tz; `selection` → label; tuples (m2o read) → display name; `html`/`json` are
  skipped. All formatting uses the token user's language.
- New field types or formats belong in `get_fields`; if you extract them into a util, update both the controller and
  `ir_actions_report.py` call sites.

## Rules specific to this module

- Template editing (write mode in the editor) is admin-group-only; filling/printing is for the user group. Keep this
  split when adding features, and keep XML + CSV ACLs identical.
- Everything the Document Server must download goes through `/onlyoffice/template/download/<id>` with an
  `oo_security_token`; build the URL from `config_utils.get_base_or_odoo_url(env)`.
- Strings that end up inside a generated `.docbuilder` script (field values, file names) are user data — keep the
  `json.dumps` / filename sanitisation (`re.sub(r"[<>:'/\\|?*\x00-\x1f]", " ", …)`) in place and never interpolate raw
  strings into the script.
- The `onlyoffice-pdf` report converter must keep working for report buttons defined on any model, not just templates
  explicitly configured for it — test against a report action, not only the fill dialog.
- Documents integration uses 17-only models (`documents.folder`); guard with `KeyError` handling as the code does and
  re-check on other code lines.
- Changelog: `CHANGELOG templates.md`. For the general workflow and repo-wide rules see `onlyoffice-odoo-core`.
